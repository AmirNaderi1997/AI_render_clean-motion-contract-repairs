import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {JSDOM} from 'jsdom';

test('composer mode menu preserves text, attachments and running work; arrow keys select Medium', async () => {
  const dom = new JSDOM('<div id="root"></div>', {url:'http://localhost/'});
  const previous = {window:globalThis.window,document:globalThis.document};
  Object.assign(globalThis,{window:dom.window,document:dom.window.document});
  const require = createRequire(new URL('../package.json',import.meta.url));
  const React=require('react'), {createRoot}=require('react-dom/client'), {flushSync}=require('react-dom');
  const compiled=await build({entryPoints:[new URL('../src/studio/Composer.tsx',import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',external:['react','react-dom'],plugins:[{
    name:'api-boundary',setup(b){b.onResolve({filter:/^\.\.\/api$/},a=>({path:a.path,namespace:'test'}));b.onLoad({filter:/.*/,namespace:'test'},()=>({contents:'export const api={};'}));}
  }]});
  const mod={exports:{}};new Function('require','module','exports',compiled.outputFiles[0].text)(require,mod,mod.exports);
  const file={key:'image',file:new dom.window.File(['png'],'brand.png',{type:'image/png'}),progress:100,attachmentId:'owned-id',url:'data:image/png;base64,'};
  const choices=[]; let sends=0;
  function Harness(){
    const [mode,setMode]=React.useState('lite');
    const [text,setText]=React.useState('پیش‌نویس دست‌نخورده');
    return React.createElement(mod.exports.Composer,{text,setText,files:[file],onFiles:()=>{},onRemoveFile:()=>{},processing:true,onStop:()=>{},onSend:()=>{sends++;choices.push(mode);},error:'',onDismissError:()=>{},hasSpeech:false,listening:false,onListen:()=>{},agentMode:mode,onAgentModeChange:setMode});
  }
  const root=createRoot(document.getElementById('root'));
  try {
    flushSync(()=>root.render(React.createElement(Harness)));
    const trigger=document.querySelector('.composer-agent');
    assert.equal(trigger.textContent,'EditorGPT Lite');
    flushSync(()=>trigger.click());
    const first=document.querySelector('[role="menuitem"]');
    first.focus();
    flushSync(()=>first.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true})));
    assert.match(document.activeElement.textContent,/EditorGPT Medium/);
    flushSync(()=>document.activeElement.click());
    assert.equal(trigger.textContent,'EditorGPT Medium');
    assert.equal(document.querySelector('textarea').value,'پیش‌نویس دست‌نخورده');
    assert.match(document.querySelector('.attach-row').textContent,/brand.png/);
    assert.equal(document.querySelectorAll('[role="menu"]').length,0);
    assert.equal(trigger.disabled,false,'switch remains usable while previous work runs');
    flushSync(()=>document.querySelector('[aria-label="Send message"]').click());
    assert.equal(sends,1);assert.deepEqual(choices,['medium']);
  } finally {flushSync(()=>root.unmount());dom.window.close();Object.assign(globalThis,previous);}
});

test('unavailable Medium has an actionable error, not a generic networking message', async () => {
  const require=createRequire(new URL('../package.json',import.meta.url));
  const built=await build({entryPoints:[new URL('../src/ui.tsx',import.meta.url).pathname],bundle:true,write:false,
    format:'cjs',platform:'node',external:['react','react-router-dom']});
  const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(require,mod,mod.exports);
  const text=mod.exports.friendlyError(new Error('503 EditorGPT Medium در این نصب فعال نیست'));
  assert.match(text,/EditorGPT Lite/);
  assert.match(text,/خودکار تغییر نکرده/);
  assert.doesNotMatch(text,/Check your connection/);
});
