import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

test('video is prepared on appearance: first frame and length only, never a full download, then streams by range',async()=>{
  const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
  const before={window:globalThis.window,document:globalThis.document};
  Object.assign(globalThis,{window:dom.window,document:dom.window.document});
  dom.window.HTMLMediaElement.prototype.play=()=>Promise.resolve();
  const require=createRequire(new URL('../package.json',import.meta.url));
  const React=require('react'),{createRoot}=require('react-dom/client'),{flushSync}=require('react-dom');
  let sessions=0, downloads=0;
  globalThis.__playbackApi={prepareMediaPlayback:async()=>{sessions++;},authenticatedObjectUrl:async()=>{downloads++;return 'blob:should-not-be-used';}};
  const result=await build({entryPoints:[new URL('../src/AuthenticatedMedia.tsx',import.meta.url).pathname],write:false,bundle:true,format:'cjs',platform:'node',external:['react','react-dom'],plugins:[{name:'boundaries',setup(b){
    b.onResolve({filter:/^\.\/(api|ui)$/},args=>({path:args.path,namespace:'test'}));
    b.onLoad({filter:/.*/,namespace:'test'},args=>({contents:args.path.endsWith('/api')?'export const api=globalThis.__playbackApi;':'export const friendlyError=String;'}));
  }}]});
  const mod={exports:{}};new Function('require','module','exports',result.outputFiles[0].text)(require,mod,mod.exports);
  const root=createRoot(document.getElementById('root'));
  try{
    flushSync(()=>root.render(React.createElement(mod.exports.AuthenticatedMedia,{as:'video',src:'/api/studio/projects/p/output',controls:true,preload:'metadata'})));
    await new Promise(resolve=>setTimeout(resolve,20));
    assert.equal(sessions,1);assert.equal(downloads,0);                       // the read-only media cookie is set once, the file is not downloaded into memory
    const video=document.querySelector('video');
    assert.equal(video.getAttribute('src'),'/api/studio/projects/p/output#t=0.1');   // the browser fetches the start of the file and shows its first frame
    assert.equal(video.preload,'metadata');
    assert.equal(document.querySelector('button'),null);                       // nothing to wait for: the native play control is there
  }finally{flushSync(()=>root.unmount());dom.window.close();Object.assign(globalThis,before);delete globalThis.__playbackApi;}
});
