// Real composition/encoder, synthetic manifest only. No AI calls or paid media.
import {chromium} from 'playwright';
import {readFileSync,writeFileSync,mkdtempSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const fixtureFolder=mkdtempSync(join(tmpdir(),'editor-ai-audio-')),audioFile=join(fixtureFolder,'tone.wav');
execFileSync('ffmpeg',['-nostdin','-y','-v','error','-f','lavfi','-i','sine=frequency=440:duration=0.2',audioFile]);
try{
 const page=await browser.newPage({ignoreHTTPSErrors:true,viewport:{width:1200,height:900}});
 page.setDefaultTimeout(15000);page.on('dialog',d=>d.accept());
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const token=`fixture.${Buffer.from(JSON.stringify({sub:'test',exp:Math.floor(Date.now()/1000)+3600})).toString('base64')}.fixture`;
 const project={id:'fixture-project',conversation_id:'fixture',engine:'motion',external_ref:'fixture',title:'Synthetic AI composition',status:'awaiting_input',current_version:1,state:{render_target:'browser',last_observed:{}},created_at:new Date().toISOString()};
 const conversation={id:'fixture',title:'Fixture',state:{current_project_id:project.id},projects:[project],messages:[],actions:[],attachments:[]};
 const posts=[];
 await page.route('**/*',r=>new URL(r.request().url()).hostname==='192.168.0.231'?r.continue():r.abort());
 await page.route('**/api/**',r=>{
  const url=new URL(r.request().url());if(r.request().method()==='POST')posts.push(url.pathname);
  if(url.pathname==='/api/track/register-usage-point')return r.fulfill({json:{success:true,billable:false,classification:'intercepted-test-only'}});
  if(url.pathname.endsWith('/auth/refresh'))return r.fulfill({json:{access_token:token}});
  if(url.pathname.endsWith('/access'))return r.fulfill({json:{allowed:false}});
  if(url.pathname.endsWith('/conversations/fixture'))return r.fulfill({json:conversation});
  if(url.pathname.includes('/events'))return r.fulfill({contentType:'text/event-stream',body:': keepalive\n\n'});
  if(url.pathname.endsWith('/browser-render/assets/audio'))return r.fulfill({contentType:'audio/wav',body:readFileSync(audioFile)});
  if(url.pathname.includes('/browser-render/assets/'))return r.fulfill({contentType:'image/png',body:readFileSync('public/icons/app-192.png')});
  if(url.pathname.endsWith('/browser-render'))return r.fulfill({json:{renderer:'remotion-product-v1',revision:'fixture',width:1080,height:1920,fps:30,durationInFrames:6,props:{scenes:[{asset:'image',narration:'audio',title:'آزمایش رندر',frames:6}],music:null,font:null},assets:[{id:'image',bytes:10000},{id:'audio',bytes:20000}]}});
  return r.fulfill({json:[]});
 });
 await page.goto('https://192.168.0.231:5190/studio/fixture',{waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:'Render compatible AI project here',exact:true}).click();
 const download=page.getByRole('link',{name:'Download',exact:true});
 try {await download.waitFor({timeout:90000});}
 catch(e){throw new Error((await page.locator('[aria-label="AI project render destination"]').innerText())+'\n'+errors.join('\n'));}
 const data=await download.evaluate(async a=>Array.from(new Uint8Array(await(await fetch(a.href)).arrayBuffer())));
 const folder=mkdtempSync(join(tmpdir(),'editor-ai-render-')),file=join(folder,'output.mp4');writeFileSync(file,Buffer.from(data));
 const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',file],{encoding:'utf8'}));
 assert.equal(probe.streams.find(s=>s.codec_type==='video').width,1080);
 assert.ok(probe.streams.some(s=>s.codec_type==='audio'),'The planned narration must be encoded');
 assert.equal(posts.filter(p=>p.startsWith('/api/studio/')).length,0,`No output upload or server render request: ${JSON.stringify(posts)}`);
 console.log(JSON.stringify({realAICompositionRendered:true,syntheticInput:true,output:file,duration:probe.format.duration,serverRenderCalls:0,outputUploads:0,errors}));
 assert.deepEqual(errors,[]);
}finally{await browser.close();}
