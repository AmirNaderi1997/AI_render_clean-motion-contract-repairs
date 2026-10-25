import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

test('video has no source or download before Play, then uses original streaming URL',async()=>{
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
    assert.equal(sessions,0);assert.equal(downloads,0);
    assert.equal(document.querySelector('video').getAttribute('src'),null);
    assert.equal(document.querySelector('video').preload,'none');
    document.querySelector('button').click();
    await new Promise(resolve=>setTimeout(resolve,20));
    assert.equal(sessions,1);assert.equal(downloads,0);
    assert.equal(document.querySelector('video').getAttribute('src'),'/api/studio/projects/p/output');
  }finally{flushSync(()=>root.unmount());dom.window.close();Object.assign(globalThis,before);delete globalThis.__playbackApi;}
});
