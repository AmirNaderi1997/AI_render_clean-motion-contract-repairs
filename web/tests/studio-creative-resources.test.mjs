import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

const require=createRequire(new URL('../package.json',import.meta.url));
const React=require('react'),{createRoot}=require('react-dom/client'),{flushSync}=require('react-dom');
const compiled=await build({entryPoints:[new URL('../src/studio/CreativeResources.tsx',import.meta.url).pathname],
  bundle:true,write:false,format:'cjs',platform:'node',external:['react'],plugins:[{
    name:'boundaries',setup(b){
      b.onResolve({filter:/^\.\.?\/(api|ui|ResourceEffectEditor|EditCard)$/},a=>({path:a.path,namespace:'test'}));
      b.onLoad({filter:/.*/,namespace:'test'},a=>({contents:a.path==='../api'
        ? 'export const api=globalThis.__studioResourcesAPI;'
        : a.path==='../ui' ? 'export const friendlyError=e=>String(e);'
        : a.path==='./EditCard' ? 'import React from "react"; export const EditCard=p=>React.createElement("section",null,p.title,p.children);'
        : 'import React from "react"; export const ResourceEffectEditor=p=>React.createElement("button",{disabled:p.disabled,onClick:()=>p.onApplied({...p.plan,title:"saved"})},"resource-editor");'}));
    }
  }]});
const settle=()=>new Promise(resolve=>setTimeout(resolve,30));
const project={id:'p',engine:'motion',external_ref:'owned-job',updated_at:'1',status:'draft'};
function environment(api){
  const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'});
  const previous={window:globalThis.window,document:globalThis.document};
  Object.assign(globalThis,{window:dom.window,document:dom.window.document,__studioResourcesAPI:api});
  const mod={exports:{}};
  new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  const root=createRoot(document.getElementById('root'));
  return {root,draw:props=>flushSync(()=>root.render(React.createElement(mod.exports.CreativeResources,props))),
    close(){flushSync(()=>root.unmount());dom.window.close();Object.assign(globalThis,previous);delete globalThis.__studioResourcesAPI;}};
}

test('chat Edit resources use the existing job, block active rendering and refresh Studio after apply',async()=>{
  const calls=[];let saved=0;
  const env=environment({planCreativeResources:async(...args)=>{calls.push(args);return {plan:{segments:[{id:'a'}]}};}});
  try{
    env.draw({project:{...project,status:'rendering'},onSaved:()=>{saved++;}});await settle();
    assert.equal(calls[0][0],'owned-job');assert.equal(document.querySelector('button').disabled,true);
    env.draw({project,onSaved:()=>{saved++;}});
    flushSync(()=>document.querySelector('button').click());await settle();
    assert.equal(saved,1);assert.equal(calls.length,1);
  }finally{env.close();}
});

test('Talking and Localize never receive incompatible EditPlan mutations; stale fetches are aborted',async()=>{
  const calls=[];
  const env=environment({planCreativeResources:(...args)=>{calls.push(args);return new Promise(()=>{});}});
  try{
    for(const engine of ['talking','localize']){
      env.draw({project:{...project,engine},onSaved:()=>{}});await settle();
      assert.equal(calls.length,0);assert.equal(document.getElementById('root').textContent,'');
    }
    env.draw({project,onSaved:()=>{}});await settle();assert.equal(calls.length,1);
    env.draw({project:{...project,external_ref:'next-job'},onSaved:()=>{}});await settle();
    assert.equal(calls[0][1].aborted,true);assert.equal(calls[1][0],'next-job');
  }finally{env.close();}
});
