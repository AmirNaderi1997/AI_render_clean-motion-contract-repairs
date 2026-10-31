import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {createRequire} from 'node:module';

const require=createRequire(new URL('../package.json',import.meta.url));
async function load(entry,plugins=[]) {
  const built=await build({entryPoints:[new URL(entry,import.meta.url).pathname],bundle:true,write:false,
    format:'cjs',platform:'node',external:['react','react-router-dom'],plugins});
  const mod={exports:{}};
  new Function('require','module','exports',built.outputFiles[0].text)(require,mod,mod.exports);
  return mod.exports;
}

test('multipart upload authenticates before sending and reports HTTP failures even for proxy HTML',async()=>{
  let fresh=false,mode='success',last;
  const previous=globalThis.XMLHttpRequest;
  globalThis.XMLHttpRequest=class {
    upload={};headers={};
    constructor(){last=this;}
    open(method,url){assert.equal(fresh,true);this.method=method;this.url=url;}
    setRequestHeader(name,value){this.headers[name]=value;}
    send(body){
      this.body=body;
      queueMicrotask(()=>{
        if(mode==='network'){this.onerror();return;}
        if(mode==='timeout'){this.ontimeout();return;}
        this.status=mode==='success'?201:mode==='invalid'?201:mode==='json'?422:413;
        this.responseText=mode==='success'?' {"id":"attachment"}':mode==='json'?' {"detail":"private server detail"}':'<html>proxy response with private details</html>';
        this.onload();
      });
    }
  };
  globalThis.__uploadFresh=()=>{fresh=true;};
  try {
    const {api}=await load('../src/api.ts',[{name:'auth',setup(b){
      b.onResolve({filter:/^\.\/auth$/},()=>({path:'auth',namespace:'test'}));
      b.onLoad({filter:/.*/,namespace:'test'},()=>({contents:'export const ensureFreshToken=async()=>globalThis.__uploadFresh(); export const getToken=()=>"test-token"; export const setToken=()=>{}; export const handleUnauthorized=()=>{throw new Error("Session expired");};'}));
    }}]);
    const file=new File(['video'],'input.mp4',{type:'video/mp4'});
    assert.deepEqual(await api.uploadStudioAttachment('conversation',file),{id:'attachment'});
    assert.equal(last.method,'POST');assert.equal(last.url,'/api/studio/conversations/conversation/attachments');
    assert.deepEqual(last.headers,{Authorization:'Bearer test-token'});
    assert.equal(last.body.get('file').name,'input.mp4');
    for(const [value,expected] of [['html','HTTP 413'],['json','HTTP 422'],['network','network error'],['timeout','network timeout'],['invalid','invalid response (HTTP 201)']]){
      mode=value;fresh=false;
      await assert.rejects(api.uploadStudioAttachment('conversation',file),e=>e.message===`Upload failed: ${expected}`);
    }
  } finally {globalThis.XMLHttpRequest=previous;delete globalThis.__uploadFresh;}
});

test('upload messages distinguish network and HTTP errors without exposing server contents',async()=>{
  const {friendlyError}=await load('../src/ui.tsx');
  assert.match(friendlyError(new Error('Upload failed: network error'),'upload attachment'),/network error/);
  assert.match(friendlyError(new Error('Upload failed: network timeout'),'upload attachment'),/timed out/);
  assert.match(friendlyError(new Error('Upload failed: HTTP 413'),'upload attachment'),/HTTP 413.*smaller file/);
  assert.match(friendlyError(new Error('Upload failed: HTTP 502'),'upload attachment'),/HTTP 502/);
  assert.match(friendlyError(new Error('Upload failed: invalid response (HTTP 201)'),'upload attachment'),/unreadable response.*HTTP 201/);
  assert.match(friendlyError(new Error('Session expired'),'upload attachment'),/Sign in again/);
});
