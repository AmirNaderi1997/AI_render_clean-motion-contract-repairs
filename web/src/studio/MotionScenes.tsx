import React from 'react';
import {api} from '../api';
import {AuthenticatedMedia} from '../AuthenticatedMedia';
import {friendlyError} from '../ui';

type Clip={id:string;status:string;ready:boolean;url?:string;remote_job_id?:string};
export function MotionScenes({jobId,onSaved}:{jobId:string;onSaved:()=>void}) {
  const [state,setState]=React.useState<{configured:boolean;timeline_supported:boolean;placement_kind?:string;sentences?:{i:number;text:string}[];items:Clip[]}|null>(null);
  const [sentence,setSentence]=React.useState<number|undefined>();
  const [prompt,setPrompt]=React.useState('');
  const [duration,setDuration]=React.useState(5),[at,setAt]=React.useState(0);
  const [aspect,setAspect]=React.useState('9:16'),[effort,setEffort]=React.useState('light');
  const [error,setError]=React.useState(''),[notice,setNotice]=React.useState(''),[busy,setBusy]=React.useState(false);
  React.useEffect(()=>{
    let live=true;
    const refresh=()=>api.motionScenes(jobId).then(v=>{if(live)setState(v);}).catch(e=>{if(live)setError(friendlyError(e,'load Motion clips'));});
    void refresh();const timer=window.setInterval(()=>void refresh(),5000);
    return()=>{live=false;window.clearInterval(timer);};
  },[jobId]);
  async function generate() {
    if (!prompt.trim() || busy) return;
    if (!window.confirm('Motion.so از اعتبار حساب شما استفاده می‌کند؛ هزینه دقیق مشخص نیست. شرح این صحنه برای Motion ارسال شود؟ فقط یک درخواست ارسال می‌شود؛ اگر قبلاً همین صحنه ثبت شده باشد، همان جاب پیگیری می‌شود.'))return;
    setBusy(true);setError('');setNotice('');
    try{await api.createMotionScene(jobId,{prompt,duration,aspect,effort,confirmed:true});setNotice('Request accepted. Existing sessions are reused; no automatic paid retries.');}
    catch(e){setError(friendlyError(e,'create this Motion scene'));}
    finally{setBusy(false);}
  }
  async function place(clip:Clip) {
    setBusy(true);setError('');
    try{await api.placeMotionScene(jobId,clip.id,at,duration,sentence);setNotice('Added to the timeline. Use the existing render controls to export.');onSaved();}
    catch(e){setError(friendlyError(e,'place this clip on the timeline'));}
    finally{setBusy(false);}
  }
  return <details className="sb"><summary>Motion.so · motion clips</summary>
    <p className="eg-muted">Silent charts, diagrams and visual scenes. EditorGPT keeps narration and captions. MP4 has no guaranteed transparent background. Remote cancellation is not supported.</p>
    {state&&!state.configured?<p>Motion is not configured on this server.</p>:null}
    {error?<p role="alert">{error}</p>:null}{notice?<p role="status">{notice}</p>:null}
    <label>Visual direction<textarea className="input" value={prompt} maxLength={10000} onChange={e=>setPrompt(e.target.value)} placeholder="A minimal animated comparison chart on a plain dark background…"/></label>
    <label>Clip duration (seconds)<input className="input" type="number" min={.5} max={30} step={.5} value={duration} onChange={e=>setDuration(Number(e.target.value))}/></label>
    <label>Aspect ratio<select className="input" value={aspect} onChange={e=>setAspect(e.target.value)}>{['9:16','16:9','1:1','4:5'].map(v=><option key={v}>{v}</option>)}</select></label>
    <label>Effort<select className="input" value={effort} onChange={e=>setEffort(e.target.value)}>{['light','medium','high'].map(v=><option key={v}>{v}</option>)}</select></label>
    <button className="btn" disabled={!state?.configured||busy||!prompt.trim()||duration<.5||duration>30} onClick={()=>void generate()}>Approve Motion request / continue same scene</button>
    {state?.placement_kind==='talking_top'?<label>Talking 2 · speaker below, Motion above<select className="input" value={sentence??''} onChange={e=>setSentence(e.target.value===''?undefined:Number(e.target.value))}><option value="">Choose sentence</option>{state.sentences?.map(s=><option key={s.i} value={s.i}>{s.i+1}. {s.text}</option>)}</select><small>This explicitly replaces HyperFrames for these selected panels; other sentences keep the speaker. Ray captions and the source voice remain unchanged.</small></label>:state?.timeline_supported?<label>Place at timeline second<input className="input" type="number" min={0} step={.1} value={at} onChange={e=>setAt(Number(e.target.value))}/></label>:null}
    {state?.items.map(clip=><article key={clip.id}><p>Motion · {clip.status}</p>{clip.ready&&clip.url?<><AuthenticatedMedia as="video" src={clip.url} controls playsInline preload="metadata" style={{width:'100%',maxHeight:360}}/>{state.timeline_supported?<button className="btn btn-secondary" disabled={busy||(state.placement_kind==='talking_top'&&sentence===undefined)} onClick={()=>void place(clip)}>{state.placement_kind==='talking_top'?'Use above speaker for this sentence':'Add as timeline B-roll'}</button>:<p>This engine does not expose a compatible generic timeline. The clip remains available for reuse.</p>}</>:null}</article>)}
  </details>;
}
