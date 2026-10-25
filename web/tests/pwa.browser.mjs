import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try {
 const context=await browser.newContext();const page=await context.newPage();
 await page.route('**/api/**',route=>route.fulfill({status:401,json:{detail:'Test session'}}));
 await page.goto('http://localhost:5189/studio');
 await page.evaluate(()=>navigator.serviceWorker.ready);
 await page.reload();
 await page.waitForFunction(()=>Boolean(navigator.serviceWorker.controller));
 const cached=await page.evaluate(async()=>{
   const keys=await caches.keys();const paths=[];
   for(const key of keys)for(const request of await (await caches.open(key)).keys())paths.push(new URL(request.url).pathname);
   return {keys,paths};
 });
 assert.ok(cached.paths.includes('/index.html'));
 assert.ok(cached.paths.includes('/manifest.webmanifest'));
 assert.ok(!cached.paths.some(p=>p.startsWith('/api')||p.includes('job_data')));
 const manifest=await page.evaluate(()=>fetch('/manifest.webmanifest').then(r=>r.json()));
 assert.equal(manifest.name,'EditorGPT');assert.equal(manifest.display,'standalone');
 await context.setOffline(true);await page.reload();
 await page.locator('#root').waitFor();
 await page.waitForFunction(()=>document.querySelector('#root')?.textContent?.includes('EditorGPT'));
 console.log(JSON.stringify({serviceWorker:true,offlineShell:true,cachedPublicFiles:cached.paths.length,sensitiveCacheEntries:0}));
}finally{await browser.close();}
