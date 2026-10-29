// Inspect maintained local compositions only. Never use this to execute model HTML.
const {chromium}=await import('../tools/tscaps/node_modules/playwright-core/index.mjs').catch(()=>import('../web/node_modules/playwright/index.mjs'));
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const request=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const cache=path.join(os.homedir(),'.cache/hyperframes/chrome/chrome-headless-shell');
const candidates=fs.existsSync(cache)?fs.readdirSync(cache).flatMap(v=>fs.readdirSync(path.join(cache,v)).map(p=>path.join(cache,v,p,'chrome-headless-shell'))):[];
const executablePath=process.env.HYPERFRAMES_BROWSER_PATH||process.env.REMOTION_BROWSER_EXECUTABLE||candidates.find(p=>fs.existsSync(p));
const browser=await chromium.launch({headless:true,executablePath});
const width=request.width||1080,height=request.height||1920;
const page=await browser.newPage({viewport:{width,height}});
const findings=[], witnesses=[];
page.on("pageerror",error=>findings.push({time:null,message:"page runtime error: "+error.message}));
try {
  if(request.variables) await page.addInitScript(v=>{window.__hyperframes={getVariables:()=>v};},request.variables);
  await page.goto(pathToFileURL(path.resolve(request.project,'index.html')).href);
  await page.addStyleTag({content:`html,body{width:${width}px;height:${height}px} #root{width:${width}px;height:${height}px}`});
  await page.evaluate(()=>document.fonts.ready);
  const samples=request.samples || await page.evaluate(()=>Array.from(document.querySelectorAll('.visual-beat,.scene,.panel')).map(e=>Number(e.dataset.start)+Number(e.dataset.duration)/2));
  for(const time of samples){
    await page.evaluate(t=>{
      for(const tl of Object.values(window.__timelines||{}))tl.seek(t);
      for(const e of document.querySelectorAll('.clip')){const a=Number(e.dataset.start||0),d=Number(e.dataset.duration||1e9);e.style.visibility=t>=a&&t<a+d?'visible':'hidden';}
    },time);
    const issues=await page.evaluate(()=>{
      const out=[];const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
      while(walker.nextNode()){
        const n=walker.currentNode,e=n.parentElement;
        if(!n.textContent.trim()||e.closest('script,style,template,svg'))continue;
        let visible=true;for(let a=e;a;a=a.parentElement){const c=getComputedStyle(a);if(c.display==='none'||c.visibility==='hidden'||Number(c.opacity)<.05)visible=false;}
        if(/[A-Za-z0-9]/.test(n.textContent))out.push('non-Persian DOM text: '+n.textContent.trim().slice(0,100));
        if(!visible)continue;
        const range=document.createRange();range.selectNodeContents(n);
        const panel=e.closest('.visual-beat,.panel,.panelscene,.scene')||document.body;
        const box=panel.getBoundingClientRect();
        for(const r of range.getClientRects())if(r.left<box.left-2||r.right>box.right+2||r.top<box.top-2||r.bottom>box.bottom+2)out.push('text outside panel: '+n.textContent.trim().slice(0,70));
        if(e.scrollWidth>e.clientWidth+2||e.scrollHeight>e.clientHeight+2)if(getComputedStyle(e).display!=='inline' && ['hidden','clip','auto','scroll'].includes(getComputedStyle(e).overflow))out.push('text box overflow: '+n.textContent.trim().slice(0,70));
      }return [...new Set(out)];
    });
    findings.push(...issues.map(message=>({time,message})));
  }
  for(const wipe of request.wipes||[]){
    await page.evaluate(t=>{for(const tl of Object.values(window.__timelines||{}))tl.seek(t);for(const e of document.querySelectorAll('.scene'))e.style.visibility=t>=Number(e.dataset.start)&&t<Number(e.dataset.start)+Number(e.dataset.duration)?'visible':'hidden';},wipe.time);
    const normal=path.resolve(request.evidence,`wipe-${wipe.index}.png`),blank=path.resolve(request.evidence,`wipe-${wipe.index}-blank.png`);
    await page.screenshot({path:normal});
    await page.locator(`#s${wipe.index}pr`).evaluate(e=>e.style.visibility='hidden');
    await page.screenshot({path:blank});
    await page.locator(`#s${wipe.index}pr`).evaluate(e=>e.style.visibility='');
    witnesses.push({...wipe,normal,blank});
  }
  console.log(JSON.stringify({findings,witnesses,samples}));
}finally{await browser.close();}
