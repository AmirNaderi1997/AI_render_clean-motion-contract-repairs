import React from "react";
import { api } from "./api";
import { friendlyError } from "./ui";
import { EditCard } from "./studio/EditCard";
import { Icon } from "./components/Icon";

type Context = Awaited<ReturnType<typeof api.planCreativeResources>>;
type Operation = Record<string, any>;
type Props = {
  jobId: string; plan: any; savedPlanText: string; dirty: boolean; disabled: boolean;
  onApplied: (plan: any, expectedDraft: string) => void;
  onBusyChange: (busy: boolean) => void;
};
export function samePlan(a: any, b: any): boolean {
  if (a === b) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object" || Array.isArray(a) !== Array.isArray(b)) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every(key => Object.prototype.hasOwnProperty.call(b, key) && samePlan(a[key], b[key]));
}
const TRANSITIONS: Record<string, string> = {hard_cut:"برش مستقیم",crossfade:"محو نرم",directional:"حرکت کشویی",zoom:"زوم"};
const MOTIONS: Record<string,string> = {steady:"قاب ثابت",hold_close:"نمای بسته",punch:"زوم ضربه‌ای",slow_push:"نزدیک‌شدن آرام",slow_pull:"دورشدن آرام",pan_left:"حرکت به چپ",pan_right:"حرکت به راست",tilt_up:"حرکت به بالا",tilt_down:"حرکت به پایین",drift_diag:"حرکت مورب"};
const LIGHTS: Record<string,string> = {neutral:"",lift_soft:"روشنایی ملایم",lift_medium:"روشنایی بیشتر",dim_soft:"تیرگی ملایم",dim_medium:"تیرگی بیشتر",pulse_start:"تأکید نور اول",pulse_end:"تأکید نور آخر",fade_in:"ورود نرم",fade_out:"خروج نرم",breath:"نور تنفسی",desaturate:"سیاه‌وسفید"};
export function effectLabel(item:{id:string;name:string}):string {
  const [motion,light]=item.id.split(":")[1].split("__");
  return MOTIONS[motion]&&light in LIGHTS?[MOTIONS[motion],LIGHTS[light]].filter(Boolean).join(" · "):item.name;
}
const COMMON=["slow_push__neutral","slow_pull__neutral","steady__neutral","punch__neutral","steady__fade_in"];

/** Single atomic save for selected segments/boundaries; sample animations are illustrative, not rendered media. */
export function ResourceEffectEditor({jobId,plan,savedPlanText,dirty,disabled,onApplied,onBusyChange}:Props) {
  const initialTransition=(plan?.transitions||[]).find((t:any)=>t.from_segment_id===plan?.segments?.[0]?.id&&t.to_segment_id===plan?.segments?.[1]?.id);
  const [open,setOpen]=React.useState(false),[context,setContext]=React.useState<Context|null>(null);
  const [mode,setMode]=React.useState<"effect"|"transition">("effect");
  const [selected,setSelected]=React.useState<string[]>(()=>plan?.segments?.slice(0,1).map((s:any)=>s.id)||[]);
  const [boundaries,setBoundaries]=React.useState<number[]>(()=>plan?.segments?.length>1?[0]:[]);
  const [operations,setOperations]=React.useState<Record<string,Operation>>({});
  const [draftBase,setDraftBase]=React.useState<any>(null);
  const [search,setSearch]=React.useState(""),[limit,setLimit]=React.useState(5);
  const [transition,setTransition]=React.useState(initialTransition?.type||"hard_cut");
  const [frames,setFrames]=React.useState(initialTransition?.duration_frames||6),[direction,setDirection]=React.useState(initialTransition?.direction||"left");
  const [intensity,setIntensity]=React.useState(initialTransition?.intensity??1),[zoomMode,setZoomMode]=React.useState(initialTransition?.zoom_mode||"zoom_in"),[zoomScale,setZoomScale]=React.useState(initialTransition?.zoom_scale??1.15);
  const [busy,setBusy]=React.useState(false),[loading,setLoading]=React.useState(false);
  const [error,setError]=React.useState(""),[message,setMessage]=React.useState(""),[retry,setRetry]=React.useState(0);
  const pending=React.useRef(false),alive=React.useRef(true);
  const activeJob=React.useRef(jobId);activeJob.current=jobId;
  React.useEffect(()=>{alive.current=true;return()=>{alive.current=false;onBusyChange(false);};},[onBusyChange]);
  React.useEffect(()=>{
    if(!open)return;
    const controller=new AbortController();setLoading(true);setError("");
    api.planCreativeResources(jobId,controller.signal).then(v=>{if(!controller.signal.aborted)setContext(v);})
      .catch(e=>{if(!controller.signal.aborted)setError(friendlyError(e,"load creative resources"));})
      .finally(()=>{if(!controller.signal.aborted)setLoading(false);});
    return()=>controller.abort();
  },[open,jobId,savedPlanText,retry]);
  const segments:{id:string;in?:number;out?:number}[]=plan?.segments||[];
  const targets=selected.filter(id=>segments.some(s=>s.id===id));
  const pairs=boundaries.filter(i=>i>=0&&i<segments.length-1);
  const count=Object.keys(operations).length;
  const stale=!!context&&(!samePlan(plan,context.plan)||(draftBase&&!samePlan(draftBase,context.plan)));
  const blocked=disabled||dirty||busy||loading||!context||stale;
  const toggle=<T,>(items:T[],value:T)=>items.includes(value)?items.filter(x=>x!==value):[...items,value];
  function stage(batch:Record<string,Operation>){
    if(blocked||!Object.keys(batch).length)return;
    if(!draftBase)setDraftBase(context!.plan);
    setOperations(old=>({...old,...batch}));setMessage("");
  }
  function effect(resource:string|null){
    stage(Object.fromEntries(targets.map(id=>[`effect:${id}`,resource?{op:"set_resource_effect",segment_id:id,resource_id:resource}:{op:"remove_effect",segment_id:id}])));
  }
  function transitionOps(kind:string,settings:Record<string,unknown>={}){
    stage(Object.fromEntries(pairs.map(i=>[`transition:${JSON.stringify([segments[i].id,segments[i+1].id])}`,{
      op:"set_resource_transition",resource_id:`editorgpt-transition:${kind}`,from_segment_id:segments[i].id,to_segment_id:segments[i+1].id,
      settings:{duration_frames:kind==="hard_cut"?0:frames,...settings}
    }])));
  }
  const settings=transition==="directional"?{direction,intensity}:transition==="zoom"?{zoom_mode:zoomMode,zoom_scale:zoomScale}:{};
  const valid=transition==="hard_cut"||(Number.isInteger(frames)&&frames>=2&&frames<=30&&
    (transition!=="directional"||(intensity>=.5&&intensity<=1))&&(transition!=="zoom"||(zoomScale>=1.02&&zoomScale<=1.5)));
  async function save(){
    if(blocked||pending.current||!count)return;
    pending.current=true;setBusy(true);onBusyChange(true);setError("");setMessage("");
    const expected=JSON.stringify(plan),submittedJob=jobId;
    try{
      const result=await api.applyResourceOperations(jobId,Object.values(operations),context!.version,draftBase);
      if(!alive.current||activeJob.current!==submittedJob)return;
      setContext(old=>old&&({...old,plan:result.plan,version:result.version}));setOperations({});setDraftBase(null);
      onApplied(result.plan,expected);setMessage("همهٔ تغییرات ذخیره شد؛ ویدیوی قبلی دست‌نخورده است. نتیجه در رندر بعدی دیده می‌شود.");
    }catch(e){if(alive.current&&activeJob.current===submittedJob)setError(friendlyError(e,"save creative resources"));}
    finally{pending.current=false;if(alive.current){setBusy(false);onBusyChange(false);}}
  }
  const catalog=(context?.effects||[]).filter(item=>`${effectLabel(item)} ${item.name} ${item.id}`.toLowerCase().includes(search.toLowerCase()))
    .sort((a,b)=>(COMMON.indexOf(a.id.split(":")[1])<0?100:COMMON.indexOf(a.id.split(":")[1]))-(COMMON.indexOf(b.id.split(":")[1])<0?100:COMMON.indexOf(b.id.split(":")[1])));
  const effectName=(id:string)=>{
    const op=operations[`effect:${id}`];
    const rid=op?(op.resource_id||""):"editorgpt:"+(plan?.visual_effects||[]).find((e:any)=>e.segment_id===id)?.type;
    const item=context?.effects.find(e=>e.id===rid);return item?effectLabel(item):"بدون افکت";
  };
  return <EditCard title="افکت و ترنزیشن" icon="wand" summary={count?`${count} تغییر ذخیره‌نشده`:"انتخاب بصری · یک قطعه، چند قطعه یا همه"} onToggle={setOpen}>
    {open&&<>
      <div className="segmented" role="group" aria-label="نوع جلوه">
        <button type="button" aria-pressed={mode==="effect"} onClick={()=>setMode("effect")}><Icon name="wand" size={16}/> افکت تصویر</button>
        <button type="button" aria-pressed={mode==="transition"} onClick={()=>setMode("transition")}><Icon name="motion" size={16}/> ترنزیشن</button>
      </div>
      <div className="cr-target-head"><b>{mode==="effect"?"روی کدام قطعه‌ها؟":"بین کدام قطعه‌ها؟"}</b>
        <button className="btn btn-sm btn-secondary" type="button" disabled={busy} onClick={()=>mode==="effect"?setSelected(segments.map(s=>s.id)):setBoundaries(segments.slice(0,-1).map((_,i)=>i))}>انتخاب همه</button>
      </div>
      <div className="cr-targets" role="group" aria-label={mode==="effect"?"قطعه‌های هدف":"اتصال‌های هدف"}>
        {mode==="effect"?segments.map((s,i)=><label key={s.id} className="cr-target"><input type="checkbox" checked={targets.includes(s.id)} disabled={busy} onChange={()=>setSelected(old=>toggle(old,s.id))}/><span><b>قطعه {i+1}</b><small dir="auto">{effectName(s.id)}</small></span></label>)
          :segments.slice(0,-1).map((s,i)=><label key={s.id} className="cr-target"><input type="checkbox" checked={pairs.includes(i)} disabled={busy} onChange={()=>setBoundaries(old=>toggle(old,i))}/><span><b>قطعه {i+1} به {i+2}</b><small>{TRANSITIONS[(operations[`transition:${JSON.stringify([s.id,segments[i+1].id])}`]?.resource_id||"").split(":")[1]]||TRANSITIONS[(plan.transitions||[]).find((t:any)=>t.from_segment_id===s.id&&t.to_segment_id===segments[i+1].id)?.type]||"برش مستقیم"}</small></span></label>)}
      </div>
      <small className="ec-hint">{mode==="effect"?targets.length:pairs.length} مورد انتخاب شده · نمونه‌ها شماتیک‌اند، نه رندر ویدیوی شما.</small>
      {mode==="effect"?<>
        <input className="input" aria-label="جستجوی افکت" placeholder="جستجوی افکت…" value={search} onChange={e=>{setSearch(e.target.value);setLimit(5);}}/>
        <div className="cr-options">
          <button type="button" className="cr-option" disabled={blocked||!targets.length} onClick={()=>effect(null)}><span className="cr-mini"><Icon name="eyeOff" size={24}/></span><b>بدون افکت</b></button>
          {catalog.slice(0,limit).map(item=><button key={item.id} type="button" className="cr-option" aria-pressed={targets.length>0&&targets.every(id=>operations[`effect:${id}`]?.resource_id===item.id||(!operations[`effect:${id}`]&&(plan.visual_effects||[]).some((e:any)=>e.segment_id===id&&item.id===`editorgpt:${e.type}`)))} disabled={blocked||!targets.length} onClick={()=>effect(item.id)}>
            <span className="cr-mini" aria-hidden="true" data-motion={item.id.split(":")[1].split("__")[0]} data-light={item.id.split("__")[1]}><span className="cr-sample"><i/><i/><i/></span></span><b dir="auto">{effectLabel(item)}</b>
          </button>)}
        </div>
        {catalog.length>limit&&<button className="btn btn-sm btn-secondary" type="button" onClick={()=>setLimit(n=>n+8)}>نمایش افکت‌های بیشتر ({catalog.length-limit})</button>}
      </>:<>
        {!pairs.length&&<small className="ec-hint">حداقل یک اتصال انتخاب کنید؛ ترنزیشن به دو قطعه نیاز دارد.</small>}
        <div className="cr-options">{(context?.transitions||[]).map(item=>{
          const kind=item.id.split(":")[1];return <button type="button" className="cr-option" key={item.id} aria-pressed={transition===kind} disabled={blocked||!pairs.length} onClick={()=>{setTransition(kind);transitionOps(kind,kind==="directional"?{direction,intensity}:kind==="zoom"?{zoom_mode:zoomMode,zoom_scale:zoomScale}:{});}}>
            <span className="cr-mini" data-transition={kind}><span className="cr-sample"><i/><i/><i/></span><span className="cr-incoming"/></span><b>{TRANSITIONS[kind]||item.name}</b>
          </button>;
        })}</div>
        <details className="cr-advanced"><summary>تنظیم دقیق ترنزیشن</summary><div className="ec-grid">
          {transition!=="hard_cut"&&<label className="field">مدت: {frames} فریم<input aria-label="مدت ترنزیشن" type="range" min={2} max={30} step={1} disabled={blocked} value={frames} onChange={e=>{const n=Number(e.target.value);setFrames(n);transitionOps(transition,{...settings,duration_frames:n});}}/></label>}
          {transition==="directional"&&<><label className="field">جهت<select className="input" aria-label="جهت ترنزیشن" value={direction} disabled={blocked} onChange={e=>{setDirection(e.target.value);transitionOps(transition,{direction:e.target.value,intensity});}}>{[["left","چپ"],["right","راست"],["up","بالا"],["down","پایین"]].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
            <label className="field">شدت<input aria-label="شدت ترنزیشن" type="range" min={.5} max={1} step={.05} value={intensity} disabled={blocked} onChange={e=>{const n=Number(e.target.value);setIntensity(n);transitionOps(transition,{direction,intensity:n});}}/></label></>}
          {transition==="zoom"&&<><label className="field">حرکت<select className="input" aria-label="حرکت زوم" value={zoomMode} disabled={blocked} onChange={e=>{setZoomMode(e.target.value);transitionOps(transition,{zoom_mode:e.target.value,zoom_scale:zoomScale});}}><option value="zoom_in">نزدیک‌شدن</option><option value="zoom_out">دورشدن</option></select></label>
            <label className="field">ضریب زوم: {zoomScale}<input aria-label="ضریب زوم ترنزیشن" type="range" min={1.02} max={1.5} step={.01} disabled={blocked} value={zoomScale} onChange={e=>{const n=Number(e.target.value);setZoomScale(n);transitionOps(transition,{zoom_mode:zoomMode,zoom_scale:n});}}/></label></>}
        </div><small className="ec-hint">هم‌پوشانی ترنزیشن ممکن است زمان خروجی را کوتاه کند.</small></details>
      </>}
      {loading&&<p role="status">در حال خواندن برنامه…</p>}
      {dirty&&<p role="status">ابتدا پیش‌نویس برنامه را ذخیره کنید.</p>}
      {stale&&<p role="status">نسخهٔ برنامه تغییر کرده است. تغییرات این بخش حفظ شده‌اند؛ برای شروع از نسخهٔ تازه «لغو تغییرات» را بزنید.</p>}
      {error&&<p role="alert">{error} <button type="button" className="btn btn-sm btn-secondary" disabled={busy} onClick={()=>setRetry(n=>n+1)}>بازخوانی</button></p>}
      <div className="cr-save"><button className="btn" type="button" disabled={blocked||!count||!valid} onClick={()=>void save()}>{busy?"در حال ذخیره…":count?`ذخیرهٔ ${count} تغییر`:"ذخیرهٔ تغییرات"}</button>
        {count>0&&<button className="btn btn-secondary" type="button" disabled={busy} onClick={()=>{setOperations({});setDraftBase(null);setMessage("");}}>لغو تغییرات</button>}</div>
      {message&&<p role="status">{message}</p>}
    </>}
  </EditCard>;
}
