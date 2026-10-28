import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';

test('connected apps requires server setup and never asks for browser credentials', async () => {
  const dom = new JSDOM('<div id="root"></div>', {url:'http://localhost/'});
  const previous = {window:globalThis.window,document:globalThis.document};
  Object.assign(globalThis,{window:dom.window,document:dom.window.document});
  const require=createRequire(new URL('../package.json',import.meta.url));
  const React=require('react'), {createRoot}=require('react-dom/client'), {flushSync}=require('react-dom');
  const built=await build({entryPoints:[new URL('../src/pages/hermes/ConnectedAppsPanel.tsx',import.meta.url).pathname],bundle:true,write:false,format:'cjs',platform:'node',external:['react'],plugins:[{
    name:'mock-connected-apps-api', setup(b){
      b.onResolve({filter:/services\/hermesApi$/},()=>({path:'api',namespace:'mock'}));
      b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:`export default {
        getComposioSettings: async()=>({configured:false,enabled:false,applications:['instagram'],external_actions_enabled:false})
      };`}));
    }
  }]});
  const mod={exports:{}};
  new Function('require','module','exports',built.outputFiles[0].text)(require,mod,mod.exports);
  const root=createRoot(document.getElementById('root'));
  try {
    flushSync(()=>root.render(React.createElement(mod.exports.default)));
    await new Promise(resolve=>setTimeout(resolve,30));
    assert.match(document.body.textContent,/Server configuration is required/);
    assert.equal(document.querySelectorAll('input').length,0);
    assert.ok([...document.querySelectorAll('button')].every(button=>button.disabled));
    assert.match(document.body.textContent,/publishing and messaging are not enabled/);
  } finally {
    flushSync(()=>root.unmount()); dom.window.close(); Object.assign(globalThis,previous);
  }
});
