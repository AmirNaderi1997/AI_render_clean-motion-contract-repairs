import React from 'react';
import {api} from '../api';
import {AuthenticatedMedia} from '../AuthenticatedMedia';
import {friendlyError} from '../ui';
import {EditCard,EditGrid} from './EditCard';

type Clip={id:string;status:string;ready:boolean;url?:string;remote_job_id?:string};
export function MotionScenes({jobId,onSaved,revision}:{jobId:string;onSaved:()=>void;revision?:string}) {
  const [state,setState]=React.useState<{configured:boolean;timeline_supported:boolean;placement_kind?:string;sentences?:{i:number;text:string}[];items:Clip[]}|null>(null);
  const [sentence,setSentence]=React.useState<number|undefined>();
  const [prompt,setPrompt]=React.useState('');
  const [duration,setDuration]=React.useState(5),[at,setAt]=React.useState(0);
  const [aspect,setAspect]=React.useState('9:16'),[effort,setEffort]=React.useState('light');
  const [error,setError]=React.useState(''),[notice,setNotice]=React.useState(''),[busy,setBusy]=React.useState(false);
  const [refreshTick,setRefreshTick]=React.useState(0);
  React.useEffect(()=>{
    let live=true;
    let timer:ReturnType<typeof setTimeout>|undefined;
    setState(null);setError('');setNotice('');
    const refresh=()=>api.motionScenes(jobId).then(v=>{if(!live)return;setState(v);
      if(v.items.some((item:Clip)=>!item.ready&&['queued','running','pending'].includes(item.status)))timer=setTimeout(()=>void refresh(),5000);
    }).catch(e=>{if(live)setError(friendlyError(e,'load the motion clips'));});
    void refresh();
    return()=>{live=false;if(timer)clearTimeout(timer);};
  },[jobId,revision,refreshTick]);
  async function generate() {
    if (!prompt.trim() || busy) return;
    if (!window.confirm('ساخت کلیپ موشن از اعتبار حساب شما استفاده می‌کند؛ هزینهٔ دقیق مشخص نیست. شرح این صحنه برای سرویس موشن ارسال شود؟ فقط یک درخواست ارسال می‌شود؛ اگر قبلاً همین صحنه ثبت شده باشد، همان جاب پیگیری می‌شود.'))return;
    setBusy(true);setError('');setNotice('');
    try{await api.createMotionScene(jobId,{prompt,duration,aspect,effort,confirmed:true});setRefreshTick(n=>n+1);}
    catch(e){setError(friendlyError(e,'create this motion clip'));}
    finally{setBusy(false);}
  }
  async function place(clip:Clip) {
    setBusy(true);setError('');
    try{await api.placeMotionScene(jobId,clip.id,at,duration,sentence);setNotice('Added to the timeline. Use the existing render controls to export.');onSaved();}
    catch(e){setError(friendlyError(e,'place this clip on the timeline'));}
    finally{setBusy(false);}
  }
  // Only where a motion clip can actually be placed (motion projects and talking style 2); nothing for other videos.
  if (!state || !state.timeline_supported || !state.items.length) return null;
  const top=state.placement_kind==='talking_top';
  const STATUS:Record<string,string>={ready:'آماده',running:'در حال ساخت',queued:'در صف',failed:'ناموفق',error:'ناموفق'};
  return <EditCard title="کلیپ موشن هوشمند" summary={state.items.length?`${state.items.length} کلیپ`:'نمودار، دیاگرام و صحنه‌های بصری بی‌صدا'}
    hint="کلیپ بی‌صدا برای نمودار، دیاگرام و صحنه‌های بصری. نریشن و زیرنویس همچنان در EditorGPT ساخته می‌شود. ویدیوی MP4 پس‌زمینهٔ شفاف تضمین‌شده ندارد و لغو از راه دور ممکن نیست.">
    {!state.configured?<div className="notice" data-tone="warning" role="status">ساخت کلیپ موشن روی این سرور تنظیم نشده است.</div>:null}
    {error?<div className="notice" data-tone="error" role="alert">{error}</div>:null}{notice?<div className="notice" role="status">{notice}</div>:null}
    <div className="field"><label htmlFor="mc-prompt">توضیح تصویر</label>
      <textarea id="mc-prompt" className="input bidi" dir="auto" rows={3} value={prompt} maxLength={10000} onChange={e=>setPrompt(e.target.value)} placeholder="مثلاً: نمودار مقایسهٔ ساده روی پس‌زمینهٔ تیره"/></div>
    <EditGrid>
      <div className="field"><label htmlFor="mc-dur">مدت کلیپ (ثانیه)</label><input id="mc-dur" className="input" type="number" min={.5} max={30} step={.5} value={duration} onChange={e=>setDuration(Number(e.target.value))}/></div>
      <div className="field"><label htmlFor="mc-aspect">نسبت تصویر</label><select id="mc-aspect" className="input" value={aspect} onChange={e=>setAspect(e.target.value)}>{['9:16','16:9','1:1','4:5'].map(v=><option key={v}>{v}</option>)}</select></div>
      <div className="field"><label htmlFor="mc-effort">دقت ساخت</label><select id="mc-effort" className="input" value={effort} onChange={e=>setEffort(e.target.value)}>{[['light','سبک'],['medium','متوسط'],['high','بالا']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></div>
    </EditGrid>
    {top?<div className="field"><label htmlFor="mc-sentence">جملهٔ مربوط به بخش بالا</label>
      <select id="mc-sentence" className="input" value={sentence??''} onChange={e=>setSentence(e.target.value===''?undefined:Number(e.target.value))}><option value="">یک جمله انتخاب کنید</option>{state.sentences?.map(s=><option key={s.i} value={s.i}>{s.i+1}. {s.text}</option>)}</select>
      <small className="field-hint">فقط پنل بالای همین جمله‌ها عوض می‌شود؛ بقیهٔ جمله‌ها گوینده را نشان می‌دهند. زیرنویس و صدای اصلی تغییر نمی‌کنند.</small></div>
      :<div className="field"><label htmlFor="mc-at">جای کلیپ روی تایم‌لاین (ثانیه)</label><input id="mc-at" className="input" type="number" min={0} step={.1} value={at} onChange={e=>setAt(Number(e.target.value))}/></div>}
    <button className="btn" disabled={!state.configured||busy||!prompt.trim()||duration<.5||duration>30} onClick={()=>void generate()}>{busy?'در حال ارسال…':'تأیید و ساخت کلیپ'}</button>
    {state.items.map(clip=><div className="ec-line" key={clip.id}>
      <div className="ec-line-head"><span>کلیپ موشن</span><span className="badge" data-tone={clip.ready?'success':undefined}><i/>{STATUS[clip.status]||clip.status}</span></div>
      {clip.ready&&clip.url?<><AuthenticatedMedia as="video" src={clip.url} controls playsInline preload="metadata" style={{width:'100%',maxHeight:320,borderRadius:'var(--radius-md)'}}/>
        <button className="btn btn-sm btn-secondary" disabled={busy||(top&&sentence===undefined)} onClick={()=>void place(clip)}>{top?'استفاده در بالای قاب برای جملهٔ انتخاب‌شده':'افزودن به تایم‌لاین'}</button></>:null}
    </div>)}
  </EditCard>;
}
