import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdtempSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const folder=mkdtempSync(join(tmpdir(),'editorgpt-settings-'));
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try {
 for(const [name,width,height] of [['desktop',1280,900],['mobile',390,844]]) {
  const page=await browser.newPage({viewport:{width,height}});const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/**',r=>r.fulfill({json:r.request().url().endsWith('/health')?{ok:true}:r.request().url().endsWith('/access')?{allowed:false}:[]}));
  await page.goto('http://127.0.0.1:5174/studio');await page.getByRole('textbox').first().waitFor();
  await page.evaluate(()=>{
   const event=new Event('beforeinstallprompt',{cancelable:true});
   Object.defineProperties(event,{prompt:{value:async()=>{window.__installCalls=(window.__installCalls||0)+1;}},userChoice:{value:Promise.resolve({outcome:'dismissed'})}});
   window.dispatchEvent(event);
  });
  assert.equal(await page.getByRole('button',{name:'Install EditorGPT',exact:true}).count(),0,'No floating Install in chat');
  await page.evaluate(()=>{history.pushState(null,'','/settings');dispatchEvent(new PopStateEvent('popstate'));});
  const install=page.getByRole('button',{name:'Install EditorGPT',exact:true});await install.waitFor();
  assert.equal(await install.evaluate(e=>Boolean(e.closest('section[aria-labelledby="set-install"]'))),true);
  await install.click();assert.equal(await page.evaluate(()=>window.__installCalls),1);
  await page.getByRole('button',{name:'How to install',exact:true}).click();
  await page.getByText('Local connection',{exact:true}).click();
  assert.equal(await page.getByLabel('Processing mode',{exact:true}).inputValue(),'online');
  const mode=page.getByLabel('Processing mode',{exact:true});
  await mode.selectOption('lan');
  await page.waitForFunction(()=>document.querySelector('select[aria-label="Processing mode"]')?.value==='lan');
  await page.reload();
  assert.equal(await page.getByLabel('Processing mode',{exact:true}).inputValue(),'lan');
  await page.getByLabel('Processing mode',{exact:true}).selectOption('online');
  const bounds=await page.evaluate(()=>({viewport:innerWidth,body:document.documentElement.scrollWidth}));
  assert.ok(bounds.body<=bounds.viewport,JSON.stringify(bounds));
  await page.screenshot({path:join(folder,`${name}.png`),fullPage:true});
  assert.deepEqual(errors,[]);console.log(JSON.stringify({name,noHorizontalOverflow:true,installInSettings:true,noChatOverlay:true,screenshot:join(folder,`${name}.png`)}));
  await page.close();
 }
}finally{await browser.close();}
