// Run with Vite at localhost:5187. Synthetic footage only; API calls are intercepted.
import { chromium } from 'playwright';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
const folder=mkdtempSync(join(tmpdir(),'editorgpt-hybrid-'));
const input=join(folder,'input.mp4');
execFileSync('ffmpeg',['-nostdin','-y','-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=30:duration=1.5','-f','lavfi','-i','sine=frequency=440:duration=1.5','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',input]);
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try {
  const page=await browser.newPage(); const posts=[]; const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('dialog',dialog=>dialog.accept());
  await page.route('**/api/**',route=>{
    if(route.request().method()!=='GET') posts.push(route.request().url());
    return route.fulfill({json:route.request().url().endsWith('/access')?{allowed:false}:[]});
  });
  await page.goto('http://localhost:5187/settings');
  assert.equal(await page.getByLabel('Processing mode',{exact:true}).inputValue(),'online');
  await page.getByLabel('Processing mode',{exact:true}).selectOption('device');
  await page.goto('http://localhost:5187/studio');
  await page.locator('input[type=file]').setInputFiles(input);
  await page.getByText(/On this device/).waitFor();
  assert.equal(posts.length,0,'Import must not create a conversation or upload');
  await page.getByText('Optional quick trim · without AI',{exact:true}).click();
  await page.getByText('Quick source export · not the AI project',{exact:true}).click();
  await page.getByLabel('End (s)').fill('0.7');
  await page.getByLabel('Size',{exact:true}).selectOption('360x640');
  await page.getByRole('button',{name:'Export selected media',exact:true}).click();
  const save=page.getByRole('link',{name:'Save video',exact:true});
  await save.waitFor({timeout:30000});
  const info=await save.evaluate(async anchor=>{
    const blob=await (await fetch(anchor.href)).blob();
    const raw=new Uint8Array(await blob.arrayBuffer());
    const parts=[];for(let i=0;i<raw.length;i+=8192)parts.push(String.fromCharCode(...raw.subarray(i,i+8192)));
    return {type:blob.type,bytes:raw.length,base64:btoa(parts.join(''))};
  });
  const output=join(folder,info.type.includes('mp4')?'device.mp4':'device.webm');
  writeFileSync(output,Buffer.from(info.base64,'base64'));
  const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',output],{encoding:'utf8'}));
  const video=probe.streams.find(s=>s.codec_type==='video');
  assert.equal(video.width,360); assert.equal(video.height,640);
  assert.ok(probe.streams.some(s=>s.codec_type==='audio'),'Audio must be encoded');
  assert.ok(Number(probe.format.duration)>.4);
  assert.equal(posts.length,0,'Device render must never upload or call a cloud renderer');
  await page.reload(); await page.getByText(/On this device/).waitFor();
  console.log(JSON.stringify({importPosts:posts.length,output,bytes:info.bytes,codec:video.codec_name,width:video.width,height:video.height,duration:probe.format.duration,draftRecovered:true,errors}));
  assert.deepEqual(errors,[]);
  const online=await browser.newPage();const uploads=[];
  await online.route('**/api/**',route=>{
    if(route.request().method()==='POST') {
      uploads.push(route.request().url());
      return route.fulfill({json:route.request().url().endsWith('/conversations')?{id:'online-test'}:{id:'attachment-test'}});
    }
    return route.fulfill({json:[]});
  });
  await online.goto('http://localhost:5187/studio');
  await online.locator('input[type=file]').setInputFiles(input);
  await online.waitForFunction(()=>document.querySelector('.attach-meta small')?.textContent?.includes('KB'));
  assert.ok(uploads.some(url=>url.includes('/attachments')),'Online mode must preserve immediate upload');
  console.log(JSON.stringify({onlineImmediateUpload:true,uploadRequests:uploads.length}));
  await online.close();
} finally {await browser.close();}
