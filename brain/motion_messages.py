"""Read-only Motion MCP activity; never exposes write/billing/generation tools."""
import hashlib
import json
import re
import threading
import time
from brain.motion_transport import client as relay_client


def decode(response):
    response.raise_for_status()
    if 'text/event-stream' in response.headers.get('content-type',''):
        records=[json.loads(line[5:].strip()) for line in response.text.splitlines() if line.startswith('data:')]
        return next((r for r in reversed(records) if 'result' in r or 'error' in r),{})
    return response.json()


class MessageReader:
    def __init__(self,key):
        self.key=key
        self.headers={'Authorization':'Bearer '+key,'Accept':'application/json, text/event-stream',
            'Content-Type':'application/json','MCP-Protocol-Version':'2025-03-26'}
        self.initialized=False

    def rpc(self,method,params=None):
        body={'jsonrpc':'2.0','id':1,'method':method,'params':params or {}}
        with relay_client(self.key,timeout=30) as http:
            response=http.post('https://mcp.motion.so/mcp',headers=self.headers,json=body)
        sid=response.headers.get('mcp-session-id')
        if sid:self.headers['Mcp-Session-Id']=sid
        data=decode(response)
        if data.get('error'):raise ValueError('Motion message stream is unavailable')
        return data.get('result',{})

    def pull(self,remote,state):
        if not self.initialized:
            self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'EditorGPT','version':'1.0'}})
            with relay_client(self.key,timeout=30) as http:
                http.post('https://mcp.motion.so/mcp',headers=self.headers,
                    json={'jsonrpc':'2.0','method':'notifications/initialized'}).raise_for_status()
            tools=self.rpc('tools/list').get('tools',[])
            tool=next((t for t in tools if t.get('name')=='list_chat_messages'),None)
            if not tool or not tool.get('annotations',{}).get('readOnlyHint'):
                raise ValueError('Read-only Motion messages capability is unavailable')
            self.initialized=True
        args={'chat_id':remote,'limit':100}
        if state.get('message_cursor') is not None:args['after_sequence']=state['message_cursor']
        messages={m['id']:m for m in state.get('messages',[])}
        for _ in range(5):
            result=self.rpc('tools/call',{'name':'list_chat_messages','arguments':args})
            if result.get('isError'):raise ValueError('Motion messages could not be read')
            data=result.get('structuredContent')
            if not isinstance(data,dict):
                data=next((json.loads(c['text']) for c in result.get('content',[]) if c.get('type')=='text' and c.get('text','').lstrip().startswith('{')), {})
            for item in data.get('messages',[]):
                if item.get('role')!='assistant':continue
                content=str(item.get('content','')).replace(self.key,'[REDACTED]')
                content=re.sub(r'(?is)<(?:think|analysis)>.*?</(?:think|analysis)>','',content)
                content=re.sub(r'(?s)```.*?```','',content)
                from brain.lm_gateway import safe
                content=safe(content,6000).strip()
                if not content:continue
                messages[item['id']]={'id':item['id'],'text':content,'sequence':item.get('sequence_num',0),
                    'timestamp':item.get('created_at'),'revision':hashlib.sha256(content.encode()).hexdigest()[:16]}
            cursor=data.get('next_after_sequence')
            if not data.get('has_more'):
                # Re-read the most recent message so edits to a streaming message
                # with the same ID are observed, not dropped at a strict cursor.
                seq=[m.get('sequence_num',0) for m in data.get('messages',[])]
                if seq:state['message_cursor']=max(0,max(seq)-1)
                break
            if cursor is None or cursor==args.get('after_sequence'):break
            args['after_sequence']=cursor
        state['messages']=sorted(messages.values(),key=lambda m:m['sequence'])[-500:]


def start_reader(remote,state_file,key,max_wait):
    """Non-blocking read-only poller. Separate snapshot cannot overwrite job state."""
    def run():
        import fcntl
        snapshot=state_file.with_name(state_file.stem+'.messages.json')
        with state_file.with_name(state_file.stem+'.messages.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return
            reader=MessageReader(key)
            state=json.loads(snapshot.read_text()) if snapshot.exists() else {}
            deadline=time.monotonic()+max(300,min(3600,max_wait))
            while time.monotonic()<deadline:
                try:
                    reader.pull(remote,state);state.pop('messages_unavailable',None)
                except Exception:state['messages_unavailable']=True
                temporary=snapshot.with_suffix('.tmp')
                temporary.write_text(json.dumps(state,ensure_ascii=False));temporary.replace(snapshot)
                try:status=json.loads(state_file.read_text()).get('status')
                except (OSError,ValueError):return
                if status in {'ready','failed','awaiting_user_input','submission_uncertain','polling_paused'}:return
                time.sleep(3)
    threading.Thread(target=run,daemon=True,name='motion-public-messages').start()

