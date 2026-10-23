"""Bounded, anonymous browser; all requests are fulfilled by the safe reader."""
import base64
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor


def render_page(url: str, output: Path) -> dict:
    from .studio_url import _fetch, _public_url, MAX_SCRIPT
    url = _public_url(url)
    root = Path(__file__).resolve().parents[1]
    node = shutil.which('node')
    executable = next((p for p in [os.environ.get('REMOTION_BROWSER_EXECUTABLE'),shutil.which('chromium'),
        shutil.which('google-chrome'),'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'] if p and Path(p).is_file()), None)
    if not node or not executable:
        raise ValueError('Browser reader runtime is unavailable')
    child = subprocess.Popen([node,str(root/'scripts/read_public_page.mjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,text=True,env={k:v for k,v in os.environ.items() if k in {'PATH','HOME','TMPDIR','LANG'}})
    messages = queue.Queue(maxsize=100)
    def reader():
        for line in child.stdout:
            messages.put(line)
        messages.put(None)
    threading.Thread(target=reader,daemon=True).start()
    def write(value):
        try:
            child.stdin.write(json.dumps(value)+'\n');child.stdin.flush()
        except (BrokenPipeError,OSError):
            pass  # Read the queued browser error/result rather than hiding it behind EPIPE.
    deadline=time.monotonic()+45
    reads=total=0
    pool=ThreadPoolExecutor(max_workers=6)
    def fetch_resource(request):
        try:
            raw,_,kind=_fetch(request['url'],max_bytes=MAX_SCRIPT,accept=request['accept'],
                timeout=min(8,max(.1,deadline-time.monotonic())),allow_http_error=True)
            messages.put((request['id'],raw,kind))
        except (OSError,ValueError):messages.put((request['id'],None,None))
    try:
        write({'config':{'root':str(root),'url':url,'executable':executable}})
        while time.monotonic()<deadline:
            try: line=messages.get(timeout=max(.1,deadline-time.monotonic()))
            except queue.Empty: break
            if line is None: break
            if isinstance(line,tuple):
                rid,raw,kind=line
                if raw is None or total+len(raw)>24*1024*1024:write({'id':rid,'error':True})
                else:
                    total+=len(raw)
                    write({'id':rid,'body':base64.b64encode(raw).decode(),'content_type':kind})
                continue
            data=json.loads(line)
            if 'request' in data:
                request=data['request']; reads+=1
                if reads>70 or total>=24*1024*1024:write({'id':request['id'],'error':True})
                else:pool.submit(fetch_resource,request)
            if 'error' in data: raise ValueError(data['error'])
            if 'result' in data:
                result=data['result'];screens=[]
                output.mkdir(parents=True,exist_ok=True)
                for i,item in enumerate(result.pop('screenshots',[])[:3]):
                    raw=base64.b64decode(item['body'],validate=True)
                    if len(raw)>12*1024*1024: raise ValueError('Full-page screenshot is too large')
                    path=output/f'page-full-{i+1}.jpg';path.write_bytes(raw)
                    screens.append({'file':str(path),'scroll_y':item['y'],'full_page':item.get('full_page',False)})
                result['screenshots']=screens
                result['url']=url
                return result
        raise ValueError('Public page browser exceeded its deadline')
    finally:
        pool.shutdown(wait=False,cancel_futures=True)
        child.terminate()
        try:child.wait(timeout=3)
        except subprocess.TimeoutExpired:child.kill();child.wait(timeout=3)
        try:child.stdin.close()
        except OSError:pass
        child.stdout.close()
