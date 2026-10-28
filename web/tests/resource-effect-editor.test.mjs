import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';
const require=createRequire(new URL('../package.json',import.meta.url));
const React=require('react'),{createRoot}=require('react-dom/client'),{flushSync}=require('react-dom');
const compiled=await build({entryPoints:[new URL('../src/ResourceEffectEditor.tsx',import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',external:['react'],plugins:[{
  name:'boundaries',setup(b){b.onResolve({filter:/^\.\/(api|ui)$/},a=>({path:a.path,namespace:'test'}));b.onLoad({filter:/.*/,namespace:'test'},a=>({contents:a.path==='./api'?'export const api=globalThis.__resourceAPI;':'export const friendlyError=e=>String(e);'}));}
}]});
const settle=()=>new Promise(r=>setTimeout(r,30));
const plan={canvas:{fps:30},segments:[{id:'a',in:0,out:1},{id:'b',in:1,out:2},{id:'c',in:2,out:3}],visual_effects:[]};
const effects=[{id:'editorgpt:slow_push__neutral',name:'Slow Push'},{id:'editorgpt:slow_pull__neutral',name:'Slow Pull'}];
const transitions=['hard_cut','crossfade','directional','zoom'].map(id=>({id:'editorgpt-transition:'+id,name:id}));
function setup(api,overrides={}){
  const dom=new JSDOM('<div id="root"></div>',{url:'http://localhost/'}),old={window:globalThis.window,document:globalThis.document};
  Object.assign(globalThis,{window:dom.window,document:dom.window.document,__resourceAPI:api});
  const mod={exports:{}};new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  const root=createRoot(document.getElementById('root'));
  const applied=[],props={jobId:'owned',plan,savedPlanText:JSON.stringify(plan),dirty:false,disabled:false,onApplied:(...args)=>applied.push(args),onBusyChange:()=>{},...overrides};
  const draw=()=>flushSync(()=>root.render(React.createElement(mod.exports.ResourceEffectEditor,props)));
  draw();
  return {dom,props,applied,draw,
    async open(){const d=document.querySelector('details');flushSync(()=>{d.open=true;d.dispatchEvent(new dom.window.Event('toggle'));});await settle();},
    click(text){const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===text);assert.ok(!!b,`button ${text}`);flushSync(()=>b.click());},
    save(){return document.querySelector('.cr-save button');},
    close(){flushSync(()=>root.unmount());dom.window.close();Object.assign(globalThis,old);delete globalThis.__resourceAPI;}};
}
const context=(source=plan)=>({plan:source,version:7,effects,transitions});

test('real preview is explicit, draft-blocked and protected against double submission',async()=>{
  const calls=[];let finish;
  const env=setup({planCreativeResources:async()=>context(),previewCreativeResources:(...args)=>{
    calls.push(args);return new Promise(r=>{finish=r;});
  }});
  try{
    await env.open();assert.equal(calls.length,0);
    env.click('نزدیک‌شدن آرام');
    assert.equal([...document.querySelectorAll('button')].find(b=>b.textContent==='رندر پیش‌نمایش واقعی برنامه').disabled,true);
    env.click('لغو تغییرات');
    const b=[...document.querySelectorAll('button')].find(b=>b.textContent==='رندر پیش‌نمایش واقعی برنامه');
    flushSync(()=>{b.click();b.click();});assert.equal(calls.length,1);
    assert.deepEqual(calls[0],['owned',plan]);
    finish({status:'queued'});await settle();
    assert.equal(env.applied.length,1);
    assert.match(document.querySelector('details').textContent,/تب Preview/);
  }finally{env.close();}
});

test('all segments and all boundaries stage together; a single atomic save is double-click protected',async()=>{
  const calls=[];let finish;
  const env=setup({planCreativeResources:async()=>context(),applyResourceOperations:(...args)=>{calls.push(args);return new Promise(r=>{finish=r;});}});
  try{
    await env.open();env.click('انتخاب همه');env.click('نزدیک‌شدن آرام');
    assert.equal(calls.length,0);assert.match(env.save().textContent,/۳|3/);
    env.click('ترنزیشن');env.click('انتخاب همه');env.click('زوم');
    assert.match(env.save().textContent,/۵|5/);
    flushSync(()=>{env.save().click();env.save().click();});assert.equal(calls.length,1);
    assert.equal(calls[0][0],'owned');assert.equal(calls[0][2],7);assert.deepEqual(calls[0][3],plan);
    assert.deepEqual(calls[0][1].filter(x=>x.op==='set_resource_effect').map(x=>x.segment_id),['a','b','c']);
    assert.deepEqual(calls[0][1].filter(x=>x.op==='set_resource_transition').map(x=>[x.from_segment_id,x.to_segment_id]),[['a','b'],['b','c']]);
    assert.equal(document.querySelectorAll('.cr-save button:not(:disabled)').length,0);
    finish({ok:true,plan,version:8});await settle();assert.equal(env.applied.length,1);
    assert.match(document.querySelector('details').textContent,/همهٔ تغییرات ذخیره شد/);
  }finally{env.close();}
});

test('different effects can be assigned to different selected clips without overwriting other draft operations',async()=>{
  const calls=[];const env=setup({planCreativeResources:async()=>context(),applyResourceOperations:async(...args)=>{calls.push(args);return {plan,version:8};}});
  try{
    await env.open();env.click('نزدیک‌شدن آرام');
    const inputs=[...document.querySelectorAll('.cr-target input')];
    flushSync(()=>{inputs[0].click();inputs[1].click();});env.click('دورشدن آرام');
    flushSync(()=>env.save().click());await settle();
    assert.deepEqual(calls[0][1],[{op:'set_resource_effect',segment_id:'a',resource_id:effects[0].id},{op:'set_resource_effect',segment_id:'b',resource_id:effects[1].id}]);
  }finally{env.close();}
});

test('unsaved input blocks staging; cancel clears staged changes without a network write',async()=>{
  let writes=0;const env=setup({planCreativeResources:async()=>context(),applyResourceOperations:async()=>{writes++;}},{dirty:true});
  try{
    await env.open();env.click('نزدیک‌شدن آرام');assert.equal(env.save().disabled,true);
    env.props.dirty=false;env.draw();env.click('نزدیک‌شدن آرام');assert.equal(env.save().disabled,false);
    env.click('لغو تغییرات');assert.equal(env.save().disabled,true);assert.equal(writes,0);
    assert.match(document.querySelector('details').textContent,/شماتیک‌اند/);
    assert.equal(document.querySelectorAll('video').length,0); // samples must not fetch private media
  }finally{env.close();}
});

test('external plan change preserves the draft and blocks stale mutation; no automatic retry',async()=>{
  let source=plan,writes=0;const env=setup({planCreativeResources:async()=>context(source),applyResourceOperations:async()=>{writes++;}});
  try{
    await env.open();env.click('نزدیک‌شدن آرام');source={...plan,title:'changed'};
    env.props.plan=source;env.props.savedPlanText=JSON.stringify(source);env.draw();await settle();
    assert.equal(env.save().disabled,true);assert.match(document.querySelector('details').textContent,/تغییرات این بخش حفظ/);
    assert.match(env.save().textContent,/1 تغییر/);assert.equal(writes,0);
  }finally{env.close();}
});

test('failed save retains operations and requires an explicit retry',async()=>{
  let writes=0;const env=setup({planCreativeResources:async()=>context(),applyResourceOperations:async()=>{writes++;throw Error('409');}});
  try{
    await env.open();env.click('نزدیک‌شدن آرام');flushSync(()=>env.save().click());await settle();
    assert.equal(writes,1);assert.match(document.querySelector('[role=alert]').textContent,/409/);
    assert.match(env.save().textContent,/1 تغییر/);await settle();assert.equal(writes,1);
  }finally{env.close();}
});
