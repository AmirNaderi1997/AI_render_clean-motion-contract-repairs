import React from "react";
import {api, type StudioProject} from "../api";
import {verifyLocalBackend} from "./backend";

/** Render the approved AI project, never substitute a trim of the original upload. */
export function ProjectRender({project,onChanged}:{project:StudioProject;onChanged:()=>void}) {
  const [busy,setBusy]=React.useState(false),[message,setMessage]=React.useState("");
  const [result,setResult]=React.useState<{blob:Blob;url:string;revision:string}|null>(null);
  const controller=React.useRef<AbortController|null>(null);
  React.useEffect(()=>()=>controller.current?.abort(),[]);
  React.useEffect(()=>()=>{if(result)URL.revokeObjectURL(result.url);},[result]);
  const select=async(target:"server"|"browser",local=false)=>{
    if(!confirm(target==='browser' ? 'Use this device? Only verified compatible AI compositions can render here. Unsupported projects will wait; they will not render on a server automatically.' : `Render the existing AI project on ${local?'this local Mac':'the current backend'} (${location.origin})? No new media generation is requested by this selection.`))return;
    setBusy(true);setMessage('Checking render destination…');
    try{if(local)await verifyLocalBackend();await api.setProjectRenderTarget(project.id,target);setMessage('Render destination saved. Approve or continue the existing plan to proceed.');onChanged();}
    catch(e){setMessage(e instanceof Error?e.message:String(e));}finally{setBusy(false);}
  };
  const render=async()=>{
    setBusy(true);setResult(null);setMessage('Checking the actual AI composition and browser codecs…');
    controller.current=new AbortController();
    const urls:string[]=[];
    try{
      if(!isSecureContext)throw new Error('Device rendering requires trusted HTTPS.');
      const manifest=await api.browserProject(project.id);
      if(manifest.renderer!=='remotion-product-v1')throw new Error('This composition has no verified device renderer. Choose the local Mac to preserve its effects.');
      if(!('VideoEncoder' in window))throw new Error('WebCodecs encoding is unavailable. Nothing was rendered on the backend.');
      if(!confirm(`Render this ${Math.ceil(manifest.durationInFrames/manifest.fps)}s AI composition here? Download up to ${Math.ceil(manifest.assets.reduce((sum,a)=>sum+a.bytes,0)/1024**2)} MB of prepared assets from ${location.origin}. Keep the app visible. Remotion sends license telemetry (origin/IP, not media); its license terms apply. No output is uploaded unless you separately choose Save to project.`))return;
      const [{renderMediaOnWeb,canRenderMediaOnWeb},{BrowserReel}]=await Promise.all([import('@remotion/web-renderer'),import('./BrowserReel')]);
      const capable=await canRenderMediaOnWeb({width:manifest.width,height:manifest.height,container:'mp4',videoCodec:'h264',audioCodec:'aac'});
      if(!capable.canRender)throw new Error(capable.issues.map(i=>i.message).join('; '));
      const assets:Record<string,string>={};
      for(const asset of manifest.assets){
        if(controller.current.signal.aborted)throw new DOMException('Cancelled','AbortError');
        const url=await api.authenticatedObjectUrl(`/api/studio/projects/${project.id}/browser-render/assets/${asset.id}?revision=${encodeURIComponent(manifest.revision)}`);
        urls.push(url);assets[asset.id]=url;
      }
      const resolve=(id:unknown)=>{if(!id)return null;if(typeof id!=='string'||!assets[id])throw new Error('Project asset missing');return assets[id];};
      const props={...manifest.props,font:resolve(manifest.props.font),music:resolve(manifest.props.music),scenes:(manifest.props.scenes as Record<string,unknown>[]).map(scene=>({...scene,asset:resolve(scene.asset),narration:resolve(scene.narration),supporting_assets:((scene.supporting_assets||[]) as string[]).map(resolve)}))};
      const hide=()=>{if(document.hidden)controller.current?.abort('App moved to background. Resume only after returning.');};
      document.addEventListener('visibilitychange',hide);
      try{
        const output=await renderMediaOnWeb({composition:{id:'ProductReel',component:BrowserReel,width:manifest.width,height:manifest.height,fps:manifest.fps,durationInFrames:manifest.durationInFrames,defaultProps:props},inputProps:props,
          container:'mp4',videoCodec:'h264',audioCodec:'aac',signal:controller.current.signal,
          onProgress:p=>setMessage(`Encoding the AI project on this device · ${Math.round(p.progress*100)}%`)});
        const blob=await output.getBlob();setResult({blob,url:URL.createObjectURL(blob),revision:manifest.revision});setMessage('Rendered on this device. Output has not been uploaded.');
      }finally{document.removeEventListener('visibilitychange',hide);}
    }catch(e){setMessage(e instanceof Error?e.message:String(e));}finally{urls.forEach(url=>URL.revokeObjectURL(url));setBusy(false);}
  };
  return <section className="action-card" aria-label="AI project render destination">
    <b>AI project · render destination</b>
    <p>{project.state?.render_target==='browser'?'This device selected. AI analysis is available; unsupported render engines stay paused.':'Full native rendering on the backend serving this app. On verified LAN this is your Mac, not the EditorGPT cloud.'}</p>
    <div className="action-buttons">
      <button className="btn btn-sm btn-secondary" disabled={busy} onClick={()=>void select('browser')}>This device</button>
      <button className="btn btn-sm btn-secondary" disabled={busy} onClick={()=>void select('server',true)}>Local Mac · full AI project</button>
      <button className="btn btn-sm btn-secondary" disabled={busy} onClick={()=>void select('server')}>Current backend</button>
      {project.state?.render_target==='browser'?<button className="btn btn-sm" disabled={busy} onClick={()=>void render()}>Render compatible AI project here</button>:null}
      {busy?<button className="btn btn-sm" onClick={()=>controller.current?.abort()}>Cancel device render</button>:null}
    </div>
    {message?<p role="status" dir="auto">{message}</p>:null}
    {result?<><video controls playsInline src={result.url} style={{maxHeight:260}}/><a className="btn btn-sm" download="EditorGPT-AI.mp4" href={result.url}>Download</a><button className="btn btn-sm" disabled={busy} onClick={()=>{
      if(!confirm(`Upload only this completed output to ${location.origin} and attach it to the existing project?`))return;
      setBusy(true);void api.saveBrowserProject(project.id,result.revision,result.blob).then(()=>{setMessage('Output saved to this project.');onChanged();}).catch(e=>setMessage(String(e))).finally(()=>setBusy(false));
    }}>Save to project</button></>:null}
  </section>;
}
