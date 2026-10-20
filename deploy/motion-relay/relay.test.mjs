import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { Readable } from 'node:stream';
import handler from './api/motion.mjs';

const key='test-only-key';
process.env.MOTION_RELAY_KEY_SHA256=createHash('sha256').update(key).digest('hex');
function request(query, method='GET', body='', headers={}) {
  const req=Readable.from([Buffer.from(body)]);
  Object.assign(req,{url:'/api/motion?'+query,method,headers:{'x-motion-relay-key':key,...headers}});
  return req;
}
function response() {
  return {statusCode:200,headers:{},chunks:[],status(n){this.statusCode=n;return this;},
    json(data){this.data=data;return this;},setHeader(k,v){this.headers[k]=v;},
    write(c){this.chunks.push(c);return true;},end(){this.ended=true;},destroy(){this.destroyed=true;}};
}
test('rejects unauthorized and arbitrary destinations without network',async()=>{
  global.fetch=()=>assert.fail('No network');
  for(const req of [request('service=rest&path=/engines','GET','',{'x-motion-relay-key':'wrong'}),
    request('service=storage&url='+encodeURIComponent('https://127.0.0.1/x')),
    request('service=rest&path=//evil.org')]) {
    const res=response();await handler(req,res);assert.ok([401,403].includes(res.statusCode));
  }
});
test('REST and MCP keep authentication and session metadata',async()=>{
  global.fetch=async(url,init)=>{
    assert.equal(url,'https://mcp.motion.so/mcp');
    assert.equal(init.headers.get('authorization'),'Bearer '+key);
    assert.equal(init.headers.get('mcp-session-id'),'existing-session');
    assert.equal(init.headers.get('x-motion-relay-key'),null);
    assert.equal(init.redirect,'manual');
    return new Response('data: {"result":{}}\n\n',{headers:{'content-type':'text/event-stream','mcp-session-id':'new-session'}});
  };
  const res=response();await handler(request('service=mcp','POST',JSON.stringify({method:'tools/list'}),{'mcp-session-id':'existing-session'}),res);
  assert.equal(res.headers['mcp-session-id'],'new-session');
  assert.equal(res.headers['content-type'],'text/event-stream');
});
test('MCP cannot invoke generation; storage cannot receive API credentials',async()=>{
  global.fetch=()=>assert.fail('No generation');
  const denied=response();await handler(request('service=mcp','POST',JSON.stringify({method:'tools/call',params:{name:'create_video'}})),denied);
  assert.equal(denied.statusCode,403);
  global.fetch=async(url,init)=>{
    assert.equal(init.headers.get('authorization'),null);
    assert.equal(init.headers.get('range'),'bytes=0-3');
    return new Response('test',{status:206,headers:{'content-range':'bytes 0-3/4'}});
  };
  const res=response();await handler(request('service=storage&url='+encodeURIComponent('https://storage.googleapis.com/b/file'),'GET','',{range:'bytes=0-3'}),res);
  assert.equal(res.statusCode,206);
});
test('upstream error is not retried',async()=>{
  let count=0;global.fetch=async()=>{count++;throw Error('temporary');};
  const res=response();await handler(request('service=rest&path=/sessions','POST','{}'),res);
  assert.equal(count,1);assert.equal(res.statusCode,502);
});
