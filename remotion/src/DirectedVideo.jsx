import React,{useEffect,useState} from 'react';
import {AbsoluteFill,Audio,Composition,Easing,Img,Sequence,interpolate,random,spring,staticFile,useCurrentFrame,
  delayRender,continueRender,cancelRender} from 'remotion';

// Fixed, seek-safe code driven by approved scene data. No code from the model runs here and no product
// claims, sales labels or CTA are invented: every word on screen is the scene's own overlay or narration.
const FONT='EditorRay, Tahoma, sans-serif';
const OVERLAP=9;                       // frames the next scene wipes in over the previous one
const ease=Easing.bezier(.22,1,.36,1);
const clamp={extrapolateLeft:'clamp',extrapolateRight:'clamp'};

// Camera moves: the same photo reads as different shots (push-in, macro, pans, pull-back, tilt).
const CAMERAS=[
  {s:[1.02,1.22],x:[0,0],y:[0,-18],r:[0,0]},
  {s:[1.7,1.95],x:[70,-50],y:[30,-10],r:[-1.2,.6]},
  {s:[1.32,1.32],x:[-120,90],y:[0,0],r:[0,0]},
  {s:[1.5,1.08],x:[0,0],y:[-40,10],r:[1.2,0]},
  {s:[2.15,2.4],x:[-40,60],y:[60,20],r:[.8,-.6]},
  {s:[1.12,1.28],x:[60,-60],y:[20,-20],r:[-.8,.8]},
];
const hex=(value,fallback='#d9b36c')=>/^#[0-9a-f]{6}$/i.test(value||'')?value:fallback;
const shade=(color,amount)=>{const n=parseInt(color.slice(1),16);const f=c=>Math.max(0,Math.min(255,Math.round(c*amount)));
  return `rgb(${f(n>>16&255)},${f(n>>8&255)},${f(n&255)})`;};

const Sparkles=({accent,frame,seed})=>Array.from({length:9}).map((_,i)=>{
  const x=random(`${seed}x${i}`)*1000+40,y=random(`${seed}y${i}`)*820+250,size=18+random(`${seed}s${i}`)*34;
  const phase=random(`${seed}p${i}`)*Math.PI*2,glow=Math.max(0,Math.sin(frame/9+phase))**3;
  return <div key={i} style={{position:'absolute',left:x,top:y,width:size,height:size,opacity:glow*.95,transform:`rotate(${frame*.6+i*20}deg) scale(${.4+glow})`,
    background:`radial-gradient(circle,#fff 0%,${accent} 28%,transparent 62%)`,clipPath:'polygon(50% 0,60% 40%,100% 50%,60% 60%,50% 100%,40% 60%,0 50%,40% 40%)'}}/>;});

// Caption boundaries are measured against the narration, in scene-local seconds.
const Captions=({text,timed=[],frame,total,accent,lead})=>{
  const words=String(text||'').split(/\s+/).filter(Boolean);
  if(!words.length) return null;
  const weights=words.map(w=>Math.max(2,w.length)+1),sum=weights.reduce((a,b)=>a+b,0);
  const span=Math.max(10,total-lead-14);let at=lead,starts=[];
  words.forEach((w,i)=>{starts.push(timed.length?timed[i].start*30:at);at+=span*weights[i]/sum;});
  const active=starts.reduce((n,s,i)=>frame>=s?i:n,-1);
  const PAGE=4,page=Math.max(0,Math.floor(active/PAGE)),shown=words.slice(page*PAGE,page*PAGE+PAGE);
  if(active<0 || (timed.length && frame>=timed.at(-1).end*30)) return null;
  return <div style={{position:'absolute',left:56,right:56,bottom:250,display:'flex',flexWrap:'wrap',justifyContent:'center',gap:'6px 22px',
      direction:'rtl',fontFamily:FONT,fontWeight:900,fontSize:92,lineHeight:1.32,textAlign:'center'}}>
    {shown.map((w,k)=>{const index=page*PAGE+k,begun=frame>=starts[index],isNow=index===active && (!timed.length || frame<timed[index].end*30);
      const pop=spring({frame:frame-starts[index],fps:30,config:{damping:12,stiffness:210}});
      return <span key={index} style={{display:'inline-block',opacity:begun?1:0,transform:`scale(${begun?(isNow?1+.16*pop:1):.6}) translateY(${begun?(1-pop)*18:0}px)`,
        color:isNow?accent:'#fff',textShadow:'0 6px 26px rgba(0,0,0,.85),0 0 3px rgba(0,0,0,.9)',WebkitTextStroke:'2px rgba(0,0,0,.35)',paintOrder:'stroke fill'}}>{w}</span>;})}
  </div>;
};

const ClassicScene = ({scene}) => {
  const frame=useCurrentFrame();
  const entry=interpolate(frame,[0,14],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
  const drift=interpolate(frame,[0,scene.frames],[1.03,1.09]);
  const statement=scene.visual_type==='kinetic_type';
  const detail=['spec_callout','ui_showcase'].includes(scene.visual_type);
  const dark=['contrast','turn','hook'].includes(scene.role);
  return <AbsoluteFill style={{background:dark?'#121813':'#f3f0e7',color:dark?'#f5f1e8':'#121813',
      fontFamily:'EditorRay, Tahoma, sans-serif',direction:'rtl',overflow:'hidden'}}>
    <div style={{position:'absolute',inset:detail?'100px 64px 620px':'600px 64px 200px',overflow:'hidden',
        borderRadius:28,opacity:entry,transform:`translateY(${(1-entry)*40}px)`}}>
      <Img src={staticFile(scene.asset)} style={{width:'100%',height:'100%',objectFit:'contain',
        transform:`scale(${drift})`}}/>
    </div>
    <div style={{position:'absolute',left:72,right:72,top:detail?'auto':100,bottom:detail?210:'auto',
        fontSize:scene.title.length>45?64:statement?104:80,fontWeight:900,lineHeight:1.45,letterSpacing:0,
        opacity:entry,transform:`translateX(${(1-entry)*-48}px)`}}>{scene.title}</div>
    <div style={{position:'absolute',width:72,height:5,right:72,bottom:110,background:dark?'#b7db8d':'#36562a',
        transform:`scaleX(${entry})`,transformOrigin:'right'}}/>
  </AbsoluteFill>;
};


const Scene=({scene,index,count,lead,total})=>{
  const frame=useCurrentFrame();                         // 0 at the start of the wipe-in; the scene's own time starts at `lead`
  const t=Math.max(0,frame-lead);
  const accent=hex(scene.accent);
  const cam=CAMERAS[(index*2+(scene.visual_type==='spec_callout'?1:0))%CAMERAS.length];
  const progress=interpolate(frame,[0,total],[0,1],clamp);
  const lerp=pair=>pair[0]+(pair[1]-pair[0])*Easing.inOut(Easing.quad)(progress);
  const zoom=()=>Math.min(cutout?1.45:1.12,lerp(cam.s));      // a cut-out has a hard outline: keep it inside the frame
  const wipe=index===0?1:ease(interpolate(frame,[0,OVERLAP],[0,1],clamp));
  const enter=index>0?1:spring({frame:t,fps:30,config:{damping:15,stiffness:130}});
  const cutout=scene.kind==='cutout';
  const flash=index===0?0:interpolate(frame,[0,3,9],[0,.55,0],clamp);
  const sweep=interpolate(t,[18,60],[-40,140],clamp);
  const headline=String(scene.title||'');
  const headWords=headline.split(/\s+/).filter(Boolean);
  const isLast=index===count-1;
  const pulse=isLast?1+Math.sin(t/6)*.035:1;
  return <AbsoluteFill style={{clipPath:`inset(0 0 0 ${(1-wipe)*100}%)`,background:'#08060b',overflow:'hidden',fontFamily:FONT,direction:'rtl'}}>
    {/* colour world: a deep accent gradient with a breathing glow behind the product */}
    <AbsoluteFill style={{background:`radial-gradient(120% 70% at 50% 40%,${shade(accent,.42)} 0%,${shade(accent,.14)} 48%,#07050a 100%)`}}/>
    <div style={{position:'absolute',left:'50%',top:790,width:1300,height:1300,marginLeft:-650,marginTop:-650,borderRadius:'50%',
      background:`radial-gradient(circle,${accent}66 0%,${accent}22 38%,transparent 66%)`,transform:`scale(${.92+Math.sin(frame/22)*.06+progress*.12})`}}/>
    {/* the product, filmed with a different camera move in every scene */}
    <div style={{position:'absolute',left:0,right:0,top:245,height:1090,display:'flex',alignItems:'center',justifyContent:'center'}}>
      <div style={{width:1080,height:1080,position:'relative',opacity:Math.min(1,enter*1.4),
        transform:`translate(${cutout?lerp(cam.x):0}px,${cutout?lerp(cam.y):-10*progress}px) rotate(${cutout?lerp(cam.r):0}deg) scale(${zoom()*(.9+.1*enter)})`}}>
        <Img src={staticFile(scene.asset)} style={{width:'100%',height:'100%',objectFit:'contain',
          filter:cutout?`drop-shadow(0 40px 50px #000c) drop-shadow(0 0 40px ${accent}55)`:'saturate(1.08) contrast(1.05)',
          padding:cutout?0:72,boxSizing:'border-box',borderRadius:32}}/>
        {cutout?<div style={{position:'absolute',inset:0,mixBlendMode:'screen',pointerEvents:'none',
          background:`linear-gradient(105deg,transparent ${sweep-14}%,#ffffffcc ${sweep}%,transparent ${sweep+14}%)`,
          ...(cutout?{WebkitMaskImage:`url(${staticFile(scene.asset)})`,maskImage:`url(${staticFile(scene.asset)})`,WebkitMaskSize:'contain',maskSize:'contain',
                      WebkitMaskRepeat:'no-repeat',maskRepeat:'no-repeat',WebkitMaskPosition:'center',maskPosition:'center'}
                   :{WebkitMaskImage:'radial-gradient(circle at 50% 50%,#000 38%,transparent 68%)',maskImage:'radial-gradient(circle at 50% 50%,#000 38%,transparent 68%)'})}}/>:null}
      </div>
    </div>
    <Sparkles accent={accent} frame={frame} seed={`${scene.asset}${index}`}/>
    <AbsoluteFill style={{background:'radial-gradient(90% 60% at 50% 45%,transparent 45%,#000a 100%)'}}/>
    <AbsoluteFill style={{background:'linear-gradient(180deg,#000b 0%,transparent 22%,transparent 52%,#000c 100%)'}}/>
    {/* headline: the scene's own overlay text, popping in word by word */}
    <div style={{position:'absolute',left:60,right:60,top:104,display:'flex',flexWrap:'wrap',justifyContent:'center',gap:'0 20px',
        fontSize:headline.length>26?78:104,fontWeight:900,lineHeight:1.3,color:'#fff',textShadow:`0 0 30px ${accent}aa,0 8px 28px #000c`}}>
      {headWords.map((word,i)=>{const p=index>0?1:spring({frame:t-i*4,fps:30,config:{damping:13,stiffness:170}});
        return <span key={i} style={{display:'inline-block',opacity:p,transform:`translateY(${(1-p)*-46}px) scale(${.85+.15*p})`,filter:`blur(${(1-p)*8}px)`}}>{word}</span>;})}
    </div>
    <div style={{position:'absolute',top:headline.length>26?236:262,left:'50%',height:7,width:220*enter,marginLeft:-110*enter,borderRadius:7,background:accent,boxShadow:`0 0 22px ${accent}`}}/>
    <Captions text={scene.narration_text} timed={scene.caption_words} frame={frame-lead} total={total-lead} accent={accent} lead={5}/>
    {isLast?<div style={{position:'absolute',left:'50%',bottom:96,width:140,height:14,marginLeft:-70,borderRadius:14,background:accent,transform:`scaleX(${pulse*2.4})`,boxShadow:`0 0 30px ${accent}`}}/>:null}
    {/* progress ticks */}
    <div style={{position:'absolute',left:60,right:60,top:48,display:'flex',gap:8,direction:'ltr'}}>
      {Array.from({length:count}).map((_,i)=><div key={i} style={{flex:1,height:6,borderRadius:6,background:'#ffffff30',overflow:'hidden'}}>
        <div style={{width:i<index?'100%':i===index?`${progress*100}%`:'0%',height:'100%',background:accent}}/></div>)}
    </div>
    <AbsoluteFill style={{background:'#fff',opacity:flash,mixBlendMode:'overlay'}}/>
    {index>0?<div style={{position:'absolute',top:0,bottom:0,left:`${(1-wipe)*100}%`,width:wipe<1?18:0,background:accent,boxShadow:`0 0 60px 10px ${accent}`,opacity:.9}}/>:null}
  </AbsoluteFill>;
};

const Reel=({scenes=[],music,font,look='classic'})=>{
  const [handle]=useState(()=>delayRender('Loading approved Persian font'));
  useEffect(()=>{
    if (!font){continueRender(handle);return;}
    const face=new FontFace('EditorRay',`url(${staticFile(font)})`,{weight:'900'});
    face.load().then(loaded=>{document.fonts.add(loaded);continueRender(handle);}).catch(cancelRender);
  },[font,handle]);
  if(look!=='cinematic'){
    let at=0;
    return <AbsoluteFill>
      {font?<style>{`@font-face{font-family:EditorRay;src:url('${staticFile(font)}');font-weight:900;}`}</style>:null}
      {scenes.map((scene,index)=>{
        const from=at;at+=scene.frames;
        return <Sequence key={index} from={from} durationInFrames={scene.frames}>
          <ClassicScene scene={scene}/>{scene.narration?<Audio src={staticFile(scene.narration)}/>:null}
        </Sequence>;
      })}
      {music?<Audio src={staticFile(music)} volume={.08} loop/>:null}
    </AbsoluteFill>;
  }
  let cursor=0;
  return <AbsoluteFill style={{background:'#08060b'}}>
    {font?<style>{`@font-face{font-family:EditorRay;src:url('${staticFile(font)}');font-weight:900;}`}</style>:null}
    {scenes.map((scene,index)=>{
      const from=cursor;cursor+=scene.frames;
      const lead=index===0?0:OVERLAP;
      return <React.Fragment key={index}>
        <Sequence from={from-lead} durationInFrames={scene.frames+lead} premountFor={20}>
          <Scene scene={scene} index={index} count={scenes.length} lead={lead} total={scene.frames+lead}/></Sequence>
        {scene.narration?<Sequence from={from} durationInFrames={scene.frames}><Audio src={staticFile(scene.narration)}/></Sequence>:null}
      </React.Fragment>;
    })}
    {music?<Audio src={staticFile(music)} volume={.1} loop/>:null}
  </AbsoluteFill>;
};

export const DirectedVideo = ()=><Composition id="DirectedReel" component={Reel} width={1080} height={1920}
  fps={30} durationInFrames={900} defaultProps={{scenes:[]}}
  calculateMetadata={({props})=>({durationInFrames:Math.max(1,props.scenes.reduce((sum,s)=>sum+s.frames,0))})}/>;
