import React from "react";
import type { PendingFile } from "../studio/Composer";
import { capabilities, recommendation, renderDevice, type Progress } from "./render";
import { renderLAN, recoverLAN, workerRequest, type Companion } from "./lan";
import { getUser } from "../auth";
import { processingPreferences } from "./preferences";
import { completionFeedback } from "./AppFeatures";

export function LocalExport({ files }: { files: PendingFile[] }) {
  const sessionKey = `editorgpt.worker.${getUser()?.id || "guest"}`;
  const jobKey = sessionKey + ".job";
  const cap = capabilities(); const mode = processingPreferences().engine;
  const [start, setStart] = React.useState(0), [end, setEnd] = React.useState(5), [text, setText] = React.useState("");
  const [size, setSize] = React.useState("720x1280");
  const [worker, setWorker] = React.useState<Companion | null>(() => { try { return JSON.parse(sessionStorage.getItem(sessionKey) || "null"); } catch { return null; } }), [online, setOnline] = React.useState(false);
  const [status, setStatus] = React.useState<Progress | null>(null), [result, setResult] = React.useState<{ url: string; type: string } | null>(null), [error, setError] = React.useState("");
  const controller = React.useRef<AbortController | null>(null);
  const busy = Boolean(status && !["Completed","Failed","Cancelled"].includes(status.stage));
  const bytes = files.reduce((n, f) => n + f.file.size, 0);
  const recommended = recommendation(cap.available, (end-start)*files.length, bytes, text ? ["text"] : [], online);
  const selected = mode === "auto" ? recommended : mode;
  // Navigating away detaches monitoring, not the independent LAN job. Explicit Cancel still cancels it.
  React.useEffect(() => () => { controller.current?.abort("detach"); }, []);
  React.useEffect(() => () => { if (result) URL.revokeObjectURL(result.url); }, [result]);
  React.useEffect(() => {
    if (!worker) return;
    const check = () => { void workerRequest(worker,"/health",{signal:AbortSignal.timeout(5000)}).then(r=>r.json()).then(r=>setOnline(r.ok)).catch(()=>setOnline(false)); };
    check(); const timer=setInterval(check,10000); return ()=>clearInterval(timer);
  }, [worker]);
  const run = async () => {
    if (busy) return;
    if (selected === "cloud") { setError("Cloud AI editing uses Send message and your existing workflow. No file has been uploaded by this selector."); return; }
    if (selected === "lan" && (!worker || !online)) { setError("Pair an available computer first."); return; }
    if (!confirm(selected === "lan" ? `Transfer up to ${Math.ceil(bytes/1024**2)} MB to ${worker!.url} and render there? Already uploaded chunks are reused.` : "Render locally? Keep this app visible and your screen unlocked until completion. No upload is needed.")) return;
    controller.current = new AbortController(); setError(""); setResult(null);
    setStatus({stage:"Preparing",percent:0,message:"Preparing export"});
    const [width,height]=size.split("x").map(Number); const spec={width,height,start,end,text,operations:["trim","concat","resize",...(text?["text"]:[])]};
    try {
      const blob = selected === "lan" ? await renderLAN(worker!,files.map(f=>f.file),spec,controller.current.signal,setStatus,id=>{
        // Only the opaque job id is saved. Pairing secrets never enter localStorage or server logs.
        sessionStorage.setItem(jobKey,JSON.stringify({id,url:worker!.url}));
      }) : await renderDevice(files.map(f=>f.file),spec,controller.current.signal,setStatus);
      setResult({url:URL.createObjectURL(blob),type:blob.type}); setStatus({stage:"Completed",percent:100,message:"Output ready"}); completionFeedback();
    } catch (e) { const cancelled=controller.current.signal.aborted; setStatus({stage:cancelled?"Cancelled":"Failed",percent:0,message:String(e)}); setError(String(e)); }
  };
  const recover = async () => {
    if (!worker || busy) return;
    controller.current = new AbortController(); setError("");
    try {
      const saved = JSON.parse(sessionStorage.getItem(jobKey) || "null");
      if (!saved || saved.url !== worker.url) throw new Error("No recoverable job in this paired browser session");
      setStatus({stage:"Preparing",percent:0,message:"Reconnecting"});
      const blob = await recoverLAN(worker,saved.id,controller.current.signal,setStatus);
      setResult({url:URL.createObjectURL(blob),type:blob.type});
    } catch (e) { setStatus({stage:"Failed",percent:0,message:String(e)});setError(String(e)); }
  };
  return <details className="local-export"><summary>Quick source export · not the AI project</summary>
    <p>Basic edits of the selected local videos only, not the existing AI timeline. Same trim range applies to each clip. Device: ≤120s combined, 720p, 512 MB; LAN: ≤10 minutes, 1080p. No advanced transitions, HDR preservation, AI effects or motion engines.</p>
    <details><summary>Preview local sources</summary>{files.slice(0,8).map(item=><div key={item.key}><p>{item.file.name}</p>{item.file.type.startsWith("image/")?<img src={item.url} alt={item.file.name} style={{maxWidth:"100%",maxHeight:180}}/>:item.file.type.startsWith("audio/")?<audio controls preload="metadata" src={item.url}/>:<video controls playsInline preload="metadata" src={item.url} style={{maxWidth:"100%",maxHeight:180}}/>}</div>)}</details>
    <p>Render engine: {selected} {mode === "auto" ? "(recommended)" : ""} · <a href="/settings">Change in Settings</a></p>
    <p>{selected === "device" ? cap.reason : selected === "lan" ? `Upload: up to ${Math.ceil(bytes/1024**2)} MB to the paired computer. ${online?"Connected":"Not connected"}` : "Cloud upload requires separate confirmation when sending."}</p>
    <div className="mg-actions"><label>Start (s) <input type="number" min="0" value={start} onChange={e=>setStart(Number(e.target.value))} disabled={busy}/></label><label>End (s) <input type="number" min="0" value={end} onChange={e=>setEnd(Number(e.target.value))} disabled={busy}/></label>
      <label>Size <select aria-label="Size" value={size} onChange={e=>setSize(e.target.value)} disabled={busy}><option>720x1280</option><option>1280x720</option><option>640x640</option><option>360x640</option></select></label></div>
    <label>Text overlay (device only) <input value={text} maxLength={180} onChange={e=>setText(e.target.value)} disabled={busy}/></label>
    {selected === "lan" ? <fieldset disabled={busy}><legend>Trusted computer</legend>
      <p>Pair your computer in Settings using trusted HTTPS. Allow local-network access if the browser asks. No HTTP mixed-content bypass is used.</p>
      {worker ? <button className="btn btn-sm btn-secondary" onClick={()=>void recover()}>Reconnect to last job</button> : null}
      {worker ? <button className="btn btn-sm btn-secondary" onClick={()=>{if(confirm("Delete this pairing’s uploaded media and outputs from the computer?"))void workerRequest(worker,"/assets",{method:"DELETE"}).catch(e=>setError(String(e)));}}>Clean worker files</button> : null}
    </fieldset> : null}
    <div className="mg-actions"><button className="btn btn-sm" disabled={busy} onClick={()=>void run()}>Export selected media</button>{busy ? <button className="btn btn-sm btn-secondary" onClick={()=>controller.current?.abort()}>Cancel</button> : null}</div>
    {status ? <p role="status">{status.stage} · {status.percent}% · {status.message}</p> : null}
    {error ? <p role="alert">{error}</p> : null}
    {result ? <><video controls playsInline src={result.url} style={{maxWidth:"100%",maxHeight:240}}/><a className="btn btn-sm" href={result.url} download={`EditorGPT.${result.type.includes("mp4")?"mp4":"webm"}`}>Save video</a></> : null}
  </details>;
}
