import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try {
  const page=await browser.newPage({ignoreHTTPSErrors:true,viewport:{width:390,height:844},isMobile:true,hasTouch:true,colorScheme:'light'});
  page.setDefaultTimeout(10000);
  await page.route('https://fonts.googleapis.com/**',r=>r.abort());
  await page.route('https://fonts.gstatic.com/**',r=>r.abort());
  // Isolated UI fixture only: all API requests are mocked; no server account is created.
  const token=`test.${Buffer.from(JSON.stringify({sub:'ui-test',email:'ui@example.invalid',name:'UI Test',exp:Math.floor(Date.now()/1000)+3600})).toString('base64')}.test`;
  await page.route('**/api/**',r=>r.fulfill({json:r.request().url().endsWith('/auth/refresh')?{access_token:token}:r.request().url().endsWith('/access')?{allowed:false}:[]}));
  await page.goto('https://192.168.0.231:5190/settings',{waitUntil:'domcontentloaded'});
  await page.getByRole('group',{name:'Theme',exact:true}).waitFor();
  const theme=()=>page.evaluate(()=>document.documentElement.dataset.theme);
  assert.equal(await theme(),'light','Default follows light device');
  await page.emulateMedia({colorScheme:'dark'});
  await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
  await page.getByRole('button',{name:'Light',exact:true}).click();
  assert.equal(await theme(),'light');
  await page.emulateMedia({colorScheme:'light'});await page.emulateMedia({colorScheme:'dark'});
  assert.equal(await theme(),'light','Manual choice stays fixed');
  await page.getByRole('button',{name:'System',exact:true}).click();
  assert.equal(await theme(),'dark');
  await page.reload({waitUntil:'domcontentloaded'});await page.getByRole('group',{name:'Theme',exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'System',exact:true}).getAttribute('aria-pressed'),'true');
  await page.emulateMedia({colorScheme:'light'});
  await page.waitForFunction(()=>document.documentElement.dataset.theme==='light');
  const geometry=await page.evaluate(()=>{
    document.documentElement.style.setProperty('--safe-bottom','34px');
    const probe=document.createElement('div');probe.className='studio';probe.dataset.layout='mobile';
    probe.innerHTML='<div class="dock"></div><nav class="studio-tabs"></nav>';
    document.body.append(probe);
    const dock=parseFloat(getComputedStyle(probe.querySelector('.dock')).paddingBottom);
    const tabs=parseFloat(getComputedStyle(probe.querySelector('.studio-tabs')).paddingBottom);
    probe.remove();
    return {dock,tabs,width:document.documentElement.scrollWidth,viewport:innerWidth};
  });
  assert.equal(geometry.tabs,34);assert.equal(geometry.dock,12);
  assert.ok(geometry.width<=geometry.viewport);
  console.log('PASS: live system appearance, manual override, persisted System, mobile safe area applied once; browser emulation, not physical iOS.');
}finally{await browser.close();}
