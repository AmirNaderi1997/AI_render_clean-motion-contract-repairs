import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

test('creative catalog is opt-in, searchable, paginated and loads video only on explicit preview', {timeout: 10000}, async () => {
  const dom = new JSDOM('<div id="root"></div>', {url:'http://localhost/my-effects'});
  const previous = {window:globalThis.window, document:globalThis.document};
  Object.assign(globalThis, {window:dom.window, document:dom.window.document});
  const require = createRequire(new URL('../package.json', import.meta.url));
  const React = require('react'), {createRoot} = require('react-dom/client'), {flushSync} = require('react-dom');
  const requests = [];
  const resource = {id:'hyperframes:test', name:'Example', description:'Example motion', engine:'hyperframes',
    availability:'catalog-only', contexts:[], parameters:[], limitations:[], capabilities:{supports_rtl:null},
    license:{commercial_use_approved:false}, preview_video:'https://static.heygen.ai/hyperframes/example.mp4'};
  globalThis.__creativeRegistryAPI = {
    listEffects:async()=>[],getMyEffects:async()=>({favorites:{},dislikes:[],rules:[],custom_assets:{}}),
    getRafieiStyles:async()=>null,getStyleLibrary:async()=>({drafts:[],profiles:[]}),
    getPlanStyleSelection:async()=>({}),getLearnedProfile:async()=>null,
    searchCreativeResources:async(q,filter,offset)=>{requests.push({q,filter,offset});return {items:[resource],total:25,offset,limit:12};}
  };
  const built = await build({entryPoints:[new URL('../src/MyEffects.tsx',import.meta.url).pathname],
    bundle:true,write:false,format:'cjs',platform:'node',external:['react'],plugins:[{
      name:'boundaries',setup(b){
        b.onResolve({filter:/^\.\/(api|ui)$/},a=>({path:a.path,namespace:'test'}));
        b.onLoad({filter:/.*/,namespace:'test'},a=>({contents:a.path==='./api'
          ? 'export const api=globalThis.__creativeRegistryAPI;'
          : 'export const friendlyError=e=>String(e); export const LoadingState=()=>null;'}));
      }
    }]});
  const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(require,mod,mod.exports);
  const root=createRoot(document.getElementById('root'));
  const settle=async(ms=20)=>{await new Promise(resolve=>setTimeout(resolve,ms));};
  try {
    flushSync(()=>root.render(React.createElement(mod.exports.default)));
    await settle();
    assert.equal(requests.length,0,'closed catalog must not fetch');
    const details=document.querySelector('details');
    flushSync(()=>{details.open=true;details.dispatchEvent(new dom.window.Event('toggle'));});
    await settle(350);
    assert.equal(requests.length,1);
    assert.match(details.textContent,/صرفاً کاتالوگ/);
    assert.equal(Boolean(document.querySelector('video')),false,'no hidden video downloads');
    const preview=[...details.querySelectorAll('button')].find(b=>b.textContent.includes('نمایش نمونه'));
    flushSync(()=>preview.click());
    assert.equal(document.querySelector('video').getAttribute('preload'),'none');
    assert.equal(document.querySelector('video').hasAttribute('autoplay'),false);
    const next=[...details.querySelectorAll('button')].find(b=>b.textContent==='بعدی');
    flushSync(()=>next.click());await settle(350);
    assert.equal(requests.at(-1).offset,12);
    assert.equal(Boolean(document.querySelector('video')),false);
    const filter=details.querySelector('select');
    flushSync(()=>{filter.value='existing-pipeline';filter.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
    await settle(350);
    assert.deepEqual(requests.at(-1),{q:'',filter:'existing-pipeline',offset:0});
    flushSync(()=>{details.open=false;details.dispatchEvent(new dom.window.Event('toggle'));});
    await settle();
    assert.equal(Boolean(details.querySelector('section')),false);
  } finally {
    flushSync(()=>root.unmount());dom.window.close();Object.assign(globalThis,previous);
    delete globalThis.__creativeRegistryAPI;
  }
});
