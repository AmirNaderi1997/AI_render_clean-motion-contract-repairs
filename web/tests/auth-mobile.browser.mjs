import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try {
  const page=await browser.newPage({viewport:{width:390,height:844}});
  await page.addInitScript(()=>{
    const viewport=new EventTarget();
    Object.assign(viewport,{height:844,offsetTop:0});
    Object.defineProperty(window,'visualViewport',{value:viewport,configurable:true});
  });
  let login;
  await page.route('**/api/**',route=>{
    if(route.request().url().endsWith('/auth/login')) {
      login=route.request().postDataJSON();
      return route.fulfill({status:401,json:{detail:'Invalid email or password'}});
    }
    return route.fulfill({status:401,json:{detail:'Not authenticated'}});
  });
  await page.goto('http://192.168.0.231:5187/studio');
  await page.getByRole('textbox').first().fill('Test');
  await page.locator('.composer-send').count().then(async count=>{
    if(count) await page.locator('.composer-send').click();
    else await page.getByRole('textbox').first().press('Enter');
  });
  const email=page.getByLabel('Email',{exact:true});
  await email.waitFor();
  assert.equal(await email.getAttribute('inputmode'),'email');
  assert.equal(await email.getAttribute('autocapitalize'),'none');
  await email.fill('diagnostic@example.invalid');
  await page.evaluate(()=>{
    Object.assign(window.visualViewport,{height:430,offsetTop:0});
    window.visualViewport.dispatchEvent(new Event('resize'));
  });
  await page.waitForTimeout(500);
  const box=await page.locator('.sheet').boundingBox();
  assert.ok(box.y>=0 && box.y+box.height<=431,JSON.stringify(box));
  await page.getByLabel('Password',{exact:true}).fill('not-a-real-password');
  await page.getByRole('button',{name:'Log in',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'The email or password is incorrect'}).waitFor();
  assert.equal(login.email,'diagnostic@example.invalid');
  console.log('PASS: mobile auth keyboard geometry, email keyboard hints and actionable 401 error (simulated viewport; not physical iOS).');
} finally {await browser.close();}
