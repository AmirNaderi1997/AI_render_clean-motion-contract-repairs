import {chromium} from 'playwright';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try {
  const page=await browser.newPage({viewport:{width:390,height:844}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
    const vv=new EventTarget();Object.assign(vv,{height:844,offsetTop:0});
    Object.defineProperty(window,'visualViewport',{value:vv,configurable:true});
  });
  const content={goal:'',audience:'',message:'',tone:'',concept:{name:'',angle:''},concepts:[],style_options:[],structure:[],hook:{text:'آزمایش',highlight:[]},style:{id:'talking_1',label:'صحبتی',summary:''},look:{preset:'default',accent_color:'#FFFFFF',caption_font:'default',zoom:100,key_moments:true},brand:{name:'',tagline:'',cta:'',logo:{enabled:false,motion:'pop',has_logo:false}},pictures:[],audio:{voice:'',sfx:'',music:''},format:{aspect:'9:16',resolution:'1080p',fps:30},engines:[],estimate:{note:'',render:null},duration_s:30};
  const project={id:'p',conversation_id:'fixture',engine:'talking',title:'Mobile layout test',status:'awaiting_confirmation',current_version:1,state:{workflow:'awaiting_approval',plan:{versions:[{id:'v1',n:1,content}],approved_id:null}}};
  const conversation={id:'fixture',title:'آزمایش ویرایش',state:{current_project_id:'p'},projects:[project],messages:[],actions:[],attachments:[]};
  await page.route('**/api/**',r=>{
    const path=new URL(r.request().url()).pathname;
    if(path.endsWith('/conversations/fixture'))return r.fulfill({json:conversation});
    if(path.includes('/events'))return r.fulfill({contentType:'text/event-stream',body:': keepalive\n\n'});
    return r.fulfill({json:[]});
  });
  await page.goto('http://127.0.0.1:5187/studio/fixture');
  await page.locator('.studio-tabs button').filter({hasText:'Edit'}).click();
  await page.locator('.topbar button[aria-label="Full screen"]').waitFor();
  assert.equal(await page.locator('.ws-head').isVisible(),false);
  const field=page.locator('.plan textarea').first();await field.focus();
  await page.evaluate(()=>{window.visualViewport.height=430;window.visualViewport.dispatchEvent(new Event('resize'));});
  await page.waitForFunction(()=>document.documentElement.hasAttribute('data-keyboard-open'));
  assert.equal(await page.locator('.studio-tabs').isVisible(),false);
  const button=page.locator('.plan-actions .btn').first();
  const box=await button.boundingBox();assert.ok(box.height<=44,JSON.stringify(box));
  await page.screenshot({path:'/tmp/edit-mobile-keyboard.png'});
  project.status='running';project.state.workflow='production';project.state.last_observed={stage:'rendering',progress:42};
  await page.reload();
  await page.locator('.studio-tabs button').filter({hasText:'Edit'}).click();
  const progress=page.getByRole('progressbar',{name:'پیشرفت رندر'});
  await progress.waitFor();assert.equal(await progress.getAttribute('aria-valuenow'),'42');
  await page.screenshot({path:'/tmp/edit-mobile-render.png'});
  assert.deepEqual(errors,[]);
  console.log('PASS: mobile Edit header, topbar fullscreen, keyboard nav hiding, compact approval button and real reported render progress. Simulated viewport; no paid calls.');
} finally {await browser.close();}
