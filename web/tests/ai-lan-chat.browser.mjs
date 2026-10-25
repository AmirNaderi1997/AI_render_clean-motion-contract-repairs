import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try{
 for(const mode of ['lan','device']){
  const context=await browser.newContext();const page=await context.newPage();const calls=[];
  page.setDefaultTimeout(15000);page.on('dialog',d=>d.accept());
  await page.addInitScript(mode=>localStorage.setItem('editorgpt.processing.v1',JSON.stringify({mode,engine:mode==='lan'?'lan':'device'})),mode);
  await page.route('**/api/**',r=>{
   const path=new URL(r.request().url()).pathname;
   if(r.request().method()==='POST')calls.push({path,body:path.endsWith('/messages')?r.request().postDataJSON():null});
   if(path.endsWith('/health'))return r.fulfill({json:{ok:true,local_installation:true}});
   if(path.endsWith('/render-capabilities'))return r.fulfill({json:{device_render_hold:true}});
   if(path.endsWith('/conversations')&&r.request().method()==='POST')return r.fulfill({json:{id:'fixture'}});
   if(path.endsWith('/attachments'))return r.fulfill({json:{id:'file-fixture'}});
   if(path.endsWith('/messages'))return r.fulfill({json:{id:'message-fixture'}});
   if(path.endsWith('/conversations/fixture'))return r.fulfill({json:{id:'fixture',state:{},projects:[],messages:[],attachments:[],actions:[]}});
   if(path.includes('/events'))return r.fulfill({contentType:'text/event-stream',body:': keepalive\n\n'});
   return r.fulfill({json:[]});
  });
  await page.goto('http://localhost:5187/studio',{waitUntil:'domcontentloaded'});
  await page.locator('input[type=file]').setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:Buffer.from('synthetic fixture')});
  await page.getByText(/On this device/).waitFor();assert.equal(calls.length,0);
  await page.getByRole('textbox',{name:'Message EditorGPT'}).fill('Make an AI video');
  await page.getByRole('button',{name:'Send message',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('.composer-input')?.value);
  const message=calls.find(c=>c.path.endsWith('/messages'));
  assert.ok(message,JSON.stringify(calls));
  assert.equal(message.body.render_target,mode==='lan'?'server':'browser');
  assert.deepEqual(message.body.attachment_ids,['file-fixture']);
  assert.ok(!calls.some(c=>c.path.includes('/render')||c.path.includes('/pair')));
  console.log(`PASS: ${mode} AI chat uses consented same-origin upload and ${message.body.render_target} target; no companion or render submission.`);
  await context.close();
 }
}finally{await browser.close();}
