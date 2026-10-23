import React, {useEffect, useState} from "react";
import {
  AbsoluteFill, Audio, Composition, Img, Sequence, interpolate,
  spring, staticFile, useCurrentFrame, useVideoConfig, delayRender, continueRender, cancelRender,
} from "remotion";

const font = "EditorRay, Tahoma, Arial, sans-serif";

const ProductScene = ({scene, index, count, resolveAsset = staticFile}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = spring({frame, fps, config: {damping: 16, stiffness: 110}});
  const leave = interpolate(frame, [scene.frames - 12, scene.frames], [1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
  const scale = interpolate(frame, [0, scene.frames], index % 2 ? [1.02, 1.09] : [1.08, 1.01]);
  const accent = scene.accent || "#e6222d";
  const isHero = index === 0;
  const isCta = index === count - 1;
  const gallery = !isHero && !isCta && index % 3 === 2 && scene.supporting_assets?.length > 1;
  const spotlight = !isHero && !isCta && index % 3 === 1;
  const heroNumber = isHero ? scene.title.match(/[۰-۹\d]+/)?.[0] : null;
  return <AbsoluteFill style={{background: "#f4f4f1", overflow: "hidden", fontFamily: font, opacity: leave}}>
    <AbsoluteFill style={{opacity: 0.14, filter: "blur(34px)", transform: `scale(${scale * 1.16})`}}>
      <Img src={resolveAsset(scene.asset)} style={{width: "100%", height: "100%", objectFit: "cover"}}/>
    </AbsoluteFill>
    <div style={{position: "absolute", inset: 28, borderRadius: 44, background: "rgba(255,255,255,.92)", boxShadow: "0 24px 70px rgba(10,18,32,.12)"}}/>
    {spotlight ? <div style={{position: "absolute", top: 28, left: 28, right: 28, height: 550, borderRadius: "44px 44px 100px 100px", background: accent, transform: `translateY(${(1-enter)*-100}px)`}}/> : null}
    <div style={{position: "absolute", top: 64, left: 70, right: 70, display: "flex", alignItems: "center", justifyContent: "space-between", direction: "ltr"}}>
      <div style={{width: 72, height: 6, background: accent, borderRadius: 6}}/>
      <div style={{fontSize: 20, color: "#6b7280"}}>{String(index + 1).padStart(2, "0")} / {String(count).padStart(2, "0")}</div>
    </div>
    <div style={{position: "absolute", top: isHero ? 180 : 165, left: 70, right: 70, textAlign: "right", direction: "rtl", transform: `translateY(${(1-enter)*38}px)`, opacity: enter}}>
      <div style={{display: "inline-block", padding: "10px 20px", borderRadius: 999, background: accent, color: "white", fontSize: 24, fontWeight: 800, marginBottom: 22}}>{isHero ? "انتخاب حرفه‌ای" : isCta ? "همین حالا" : "ویژگی محصول"}</div>
      <div style={{fontSize: isHero ? 86 : 76, lineHeight: 1.28, fontWeight: 950, color: spotlight ? "white" : "#101827", textWrap: "balance"}}>{scene.title.split(" ").map((word, wordIndex) => <span key={wordIndex} style={{display: "inline-block", whiteSpace: "pre", opacity: interpolate(frame-wordIndex*3, [0, 12], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}), transform: `translateY(${interpolate(frame-wordIndex*3, [0, 16], [24, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"})}px)`}}>{word}{" "}</span>)}</div>
    </div>
    {heroNumber ? <div style={{position: "absolute", top: 420, left: 70, right: 70, textAlign: "center", fontSize: 300, lineHeight: 1, fontWeight: 950, color: accent, opacity: .13, transform: `scale(${enter})`}}>{heroNumber}</div> : null}
    <div style={{position: "absolute", top: isHero ? 610 : spotlight ? 650 : 440, left: 70, right: 70, bottom: isCta ? 330 : 190, display: "flex", alignItems: "center", justifyContent: "center", overflow: "hidden"}}>
      {gallery ? <div style={{width: "100%", height: "100%", display: "flex", flexDirection: "column", gap: 22}}>{scene.supporting_assets.slice(0,3).map((asset, assetIndex) => <div key={asset} style={{flex: 1, minHeight: 0, borderRadius: 28, overflow: "hidden", background: "#fff", border: "1px solid #e5e7eb", transform: `translateX(${(1-spring({frame: frame-assetIndex*10, fps, config: {damping: 18}})) * (assetIndex%2 ? -900 : 900)}px)`}}><Img src={staticFile(asset)} style={{width:"100%",height:"100%",objectFit:"contain"}}/></div>)}</div> : <Img src={staticFile(scene.asset)} style={{width: "100%", height: "100%", objectFit: "contain", transform: `scale(${scale * .93}) translateX(${Math.sin(frame / scene.frames * Math.PI) * (index%2 ? 14 : -14)}px)`, filter: "drop-shadow(0 30px 25px rgba(10,18,32,.18))"}}/>}
    </div>
    {isCta ? <div style={{position: "absolute", left: 85, right: 85, bottom: 125, borderRadius: 28, padding: "27px 36px", background: accent, color: "white", textAlign: "center", direction: "rtl", fontSize: 50, fontWeight: 900, transform: `scale(${.92 + enter*.08})`}}>مشاهده جزئیات و سفارش</div> : null}
    <div style={{position: "absolute", left: 70, right: 70, bottom: 72, height: 5, background: "#e5e7eb", borderRadius: 4}}><div style={{height: "100%", width: `${((index+1)/count)*100}%`, background: accent, borderRadius: 4}}/></div>
  </AbsoluteFill>;
};

export const Reel = ({scenes = [], music, font: fontFile, resolveAsset = staticFile, AudioComponent = Audio}) => {
  const [fontHandle] = useState(() => delayRender("Loading Ray font"));
  useEffect(() => {
    if (!fontFile) {continueRender(fontHandle); return;}
    const face = new FontFace("EditorRay", `url(${resolveAsset(fontFile)})`, {weight: "100 950"});
    face.load().then(loaded => {document.fonts.add(loaded); continueRender(fontHandle);}).catch(cancelRender);
  }, [fontFile, fontHandle, resolveAsset]);
  let cursor = 0;
  return <AbsoluteFill style={{background: "#f4f4f1"}}>
    {fontFile ? <style>{`@font-face {font-family: EditorRay; src: url('${resolveAsset(fontFile)}'); font-weight: 100 950;}`}</style> : null}
    {scenes.map((scene, index) => {
      const start = cursor; cursor += scene.frames;
      return <Sequence key={`${index}-${scene.asset}`} from={start} durationInFrames={scene.frames} premountFor={30}>
        <ProductScene scene={scene} index={index} count={scenes.length} resolveAsset={resolveAsset}/>
        {scene.narration ? <AudioComponent src={resolveAsset(scene.narration)} volume={1}/> : null}
      </Sequence>;
    })}
    {music ? <AudioComponent src={resolveAsset(music)} volume={0.08} loop/> : null}
  </AbsoluteFill>;
};

export const EditorGPTVideo = () => <Composition
  id="ProductReel"
  component={Reel}
  width={1080}
  height={1920}
  fps={30}
  durationInFrames={900}
  defaultProps={{scenes: []}}
  calculateMetadata={({props}) => ({durationInFrames: Math.max(1, props.scenes.reduce((sum, scene) => sum + scene.frames, 0))})}
/>;
