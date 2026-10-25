// Browser rendering with ZERO direct page network access. Python owns every
// HTTP read, public-IP/redirect validation, byte limits and the overall deadline.
import readline from 'node:readline';
import {createRequire} from 'node:module';
import {appendFileSync} from 'node:fs';
const debug=(text)=>{ if(process.env.READER_DEBUG) try{appendFileSync(process.env.READER_DEBUG,text+'\n');}catch{} };
const lines=readline.createInterface({input:process.stdin});
const waiting=new Map(); let configure, sequence=0;
const configReady=new Promise(resolve=>configure=resolve);
lines.on('line',line=>{
  const value=JSON.parse(line);
  if(value.config) configure(value.config);
  else {const resolve=waiting.get(value.id); if(resolve){waiting.delete(value.id);resolve(value);}}
});
const send=value=>process.stdout.write(JSON.stringify(value)+'\n');
let browser;
try {
  const config=await configReady;
  let chromium;
  for(const pkg of [config.root+'/web/package.json',config.root+'/tools/tscaps/package.json',config.root+'/remotion/package.json','/opt/hyperframes/package.json']) {
    for(const name of ['playwright','playwright-core']) {
      try {chromium=createRequire(pkg)(name).chromium;break;} catch {}
    }
    if(chromium) break;
  }
  if(!chromium) throw Error('Browser reader runtime is not installed');
  browser=await chromium.launch({headless:true,executablePath:config.executable});
  const context=await browser.newContext({viewport:{width:1280,height:900},serviceWorkers:'block',acceptDownloads:false});
  if(context.routeWebSocket) await context.routeWebSocket('**/*',socket=>socket.close());
  await context.route('**/*',async route=>{
    const r=route.request();
    if(r.method()!=='GET' || !/^https?:\/\//i.test(r.url()) || !['document','script','stylesheet','xhr','fetch','image'].includes(r.resourceType())) { debug('ABORT '+r.method()+' '+r.resourceType()+' '+r.url().slice(0,120)); return route.abort(); }
    const id=++sequence;
    const answer=new Promise(resolve=>waiting.set(id,resolve));
    send({request:{id,url:r.url(),accept:r.headers().accept || '*/*',headers:r.headers()}});
    const value=await answer;
    if(value.error) { debug('FETCHFAIL '+r.resourceType()+' '+r.url().slice(0,120)); return route.abort(); }
    // CORS: the page's own scripts and API calls are served by this reader, so a cross-origin response must be readable by the page that asked for it.
    await route.fulfill({status:Number.isInteger(value.status)&&value.status>=100&&value.status<=599?value.status:200,contentType:value.content_type,headers:{'access-control-allow-origin':'*','access-control-allow-headers':'*','access-control-allow-methods':'GET'},body:Buffer.from(value.body,'base64')}).catch(()=>{});
  });
  const page=await context.newPage();
  page.on('console',m=>debug('CONSOLE '+m.type()+' '+m.text().slice(0,200)));
  page.on('pageerror',e=>debug('PAGEERROR '+String(e).slice(0,300)));
  await page.goto(config.url,{waitUntil:'domcontentloaded',timeout:config.goto_ms||25000});
  await page.waitForFunction(()=>((document.querySelector('main')||document.body)?.innerText||'').trim().length>120,{},{timeout:config.settle_ms||10000}).catch(()=>{});
  // Trigger lazy content throughout the page before a TRUE full-page capture.
  // Never silently label a clipped/sample image as the whole page.
  let height=await page.evaluate(()=>document.documentElement.scrollHeight);
  if(height>50000) throw Error('Page exceeds the safe full-page capture limit; no complete screenshot was claimed');
  for(let y=0;y<height;y+=800) {
    await page.evaluate(y=>window.scrollTo(0,y),y);
    await page.waitForTimeout(100);
    height=await page.evaluate(()=>document.documentElement.scrollHeight);
    if(height>50000) throw Error('Page grew beyond the full-page capture budget');
  }
  await page.evaluate(()=>window.scrollTo(0,0));
  const screenshots=[{y:0,full_page:true,body:(await page.screenshot({type:'jpeg',quality:65,fullPage:true,timeout:8000})).toString('base64')}];
  const evidence=await page.evaluate(()=>{
    const root=document.querySelector('main,[role=main],article')||document.body;
    const blocks=[...root.querySelectorAll('h1,h2,h3,p,li')].filter(e=>!e.closest('nav,header,footer,form,[aria-hidden=true]'))
      .map(e=>e.innerText.trim()).filter(Boolean).join('\n');
    return {title:document.title,content:(blocks.length>=80?blocks:(root?.innerText||'')).slice(0,24000),
      images:[...root.querySelectorAll('img')].slice(0,40).map(i=>({url:i.currentSrc||i.src,alt:i.alt||''})),
      description:document.querySelector('meta[name=description]')?.content||''};
  });
  send({result:{...evidence,screenshots}});
} catch(error) {send({error:error.message});}
finally {if(browser) await browser.close(); lines.close();process.exit(0);}
