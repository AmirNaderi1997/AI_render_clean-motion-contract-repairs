import React,{useEffect,useState} from 'react';
import {AbsoluteFill,Audio,Composition,Img,Sequence,interpolate,staticFile,useCurrentFrame,
  delayRender,continueRender,cancelRender} from 'remotion';

// Fixed, seek-safe code driven by approved scene data. No code from the model
// runs here and no product claims, sales labels or CTA are invented by the UI.
const Scene = ({scene}) => {
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

const Reel = ({scenes=[],music,font}) => {
  const [handle]=useState(()=>delayRender('Loading approved Persian font'));
  useEffect(()=>{
    if (!font){continueRender(handle);return;}
    const face=new FontFace('EditorRay',`url(${staticFile(font)})`,{weight:'900'});
    face.load().then(loaded=>{document.fonts.add(loaded);continueRender(handle);}).catch(cancelRender);
  },[font,handle]);
  let cursor=0;
  return <AbsoluteFill>
    {font?<style>{`@font-face{font-family:EditorRay;src:url('${staticFile(font)}');font-weight:900;}`}</style>:null}
    {scenes.map((scene,index)=>{
      const from=cursor;cursor+=scene.frames;
      return <Sequence key={index} from={from} durationInFrames={scene.frames}>
        <Scene scene={scene}/>{scene.narration?<Audio src={staticFile(scene.narration)}/>:null}
      </Sequence>;
    })}
    {music?<Audio src={staticFile(music)} volume={.08} loop/>:null}
  </AbsoluteFill>;
};

export const DirectedVideo = ()=><Composition id="DirectedReel" component={Reel} width={1080} height={1920}
  fps={30} durationInFrames={900} defaultProps={{scenes:[]}}
  calculateMetadata={({props})=>({durationInFrames:Math.max(1,props.scenes.reduce((sum,s)=>sum+s.frames,0))})}/>;
