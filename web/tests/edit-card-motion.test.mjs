import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';
const require=createRequire(new URL('../package.json',import.meta.url));
const React=require('react'),{createRoot}=require('react-dom/client'),{flushSync}=require('react-dom');
const compiled=await build({stdin:{contents:'export {MotionScenes} from "./studio/MotionScenes"; export {EditCard} from "./studio/EditCard";',resolveDir:new URL('../src/',import.meta.url).pathname,loader:'tsx'},bundle:true,write:false,format:'cjs',platform:'node',external:['react'],plugins:[{
  name:'boundaries',setup(b){b.onResolve({filter:/^\.\.\/(api|ui|AuthenticatedMedia)$/},a=>({path:a.path,namespace:'test'}));b.onLoad({filter:/.*/,namespace:'test'},a=>({contents:a.path==='../api'?'export const api=globalThis.__editAPI;':a.path==='../ui'?'export const friendlyError=e=>String(e);':'export const AuthenticatedMedia=()=>null;'}));}
}]});
const settle=()=>new Promise(r=>setTimeout(r,30));
function env(api){
  const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'}),old={window:globalThis.window,document:globalThis.document};
  Object.assign(globalThis,{window:dom.window,document:dom.window.document,__editAPI:api});
  const mod={exports:{}};new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  const root=createRoot(document.getElementById('root'));
  return {root,...mod.exports,close(){flushSync(()=>root.unmount());dom.window.close();Object.assign(globalThis,old);delete globalThis.__editAPI;}};
}
test('configured motion.so alone never shows its card; existing project sessions do',async()=>{
  let items=[];
  const e=env({motionScenes:async()=>({configured:true,timeline_supported:true,items})});
  try{
    flushSync(()=>e.root.render(React.createElement(e.MotionScenes,{jobId:'unused',onSaved:()=>{}})));await settle();
    assert.equal(document.getElementById('root').textContent,'');
    items=[{id:'session',status:'queued',ready:false,remote_job_id:'existing'}];
    flushSync(()=>e.root.render(React.createElement(e.MotionScenes,{jobId:'used',onSaved:()=>{}})));await settle();
    assert.match(document.getElementById('root').textContent,/کلیپ موشن هوشمند/);
    assert.equal(document.querySelector('details.ec').dir,'rtl');
    assert.equal(!!document.querySelector('.ec-icon'),true);
  }finally{e.close();}
});
test('all EditCard sections share RTL layout, icon, chevron and a closed initial state',()=>{
  const e=env({});
  try{
    flushSync(()=>e.root.render(React.createElement('div',null,...['ظاهر و رنگ','صدا و موسیقی','متن فارسی','افکت و ترنزیشن'].map(title=>React.createElement(e.EditCard,{title,key:title},'controls')))));
    const cards=[...document.querySelectorAll('details.ec')];assert.equal(cards.length,4);
    assert(cards.every(c=>c.dir==='rtl'&&!c.open&&c.querySelector('.ec-icon')&&c.querySelector('.ec-chev')));
  }finally{e.close();}
});
