import React from "react";
import { api, EffectOption, EffectSpec, TalkingEffect, TalkingEffects } from "../api";
import { Icon } from "../components/Icon";
import { friendlyError } from "../ui";
import { EditCard } from "./EditCard";

const seconds = (value: number) => `${(Math.round(value * 10) / 10).toLocaleString("fa-IR")}`;

function OptionField({ option, value, onChange, disabled }: { option: EffectOption; value: string | number | undefined; onChange: (value: string | number | undefined) => void; disabled: boolean }) {
  const shown = value ?? option.default ?? "";
  if (option.type === "choice") {
    return <label className="field"><span className="field-label">{option.label}</span>
      <select className="input" disabled={disabled} value={String(shown)} onChange={event => onChange(event.target.value)}>{(option.choices || []).map(choice => <option key={choice} value={choice}>{choice}</option>)}</select></label>;
  }
  if (option.type === "color") {
    return <label className="field"><span className="field-label">{option.label}</span>
      <input className="input" type="color" disabled={disabled} value={String(shown || "#FFFFFF")} onChange={event => onChange(event.target.value)}/></label>;
  }
  return <label className="field"><span className="field-label">{option.label}</span>
    <input className="input" type="number" inputMode="decimal" dir="ltr" disabled={disabled} min={option.min} max={option.max} step={option.step ?? 0.05} value={shown === "" ? "" : Number(shown)}
      onChange={event => onChange(event.target.value === "" ? undefined : Number(event.target.value))}/></label>;
}

/** Effects that follow the speaker (orbit, spotlight, slow push...), laid over the finished video at the times chosen here. */
export function EffectsEditor({ jobId, onSaved }: { jobId: string; onSaved: () => void }) {
  const [data, setData] = React.useState<TalkingEffects | null>(null);
  const [fx, setFx] = React.useState("");
  const [start, setStart] = React.useState(1);
  const [end, setEnd] = React.useState(4);
  const [text, setText] = React.useState("");
  const [options, setOptions] = React.useState<Record<string, string | number | undefined>>({});
  const [busy, setBusy] = React.useState("");
  const [error, setError] = React.useState("");
  const [frame, setFrame] = React.useState("");
  React.useEffect(() => { let active = true; void api.getTalkingEffects(jobId).then(value => { if (active) { setData(value); setFx(value.catalog[0]?.id || ""); } }).catch(() => { if (active) setError("فهرست افکت‌ها دریافت نشد."); }); return () => { active = false; }; }, [jobId]);
  React.useEffect(() => () => { if (frame) URL.revokeObjectURL(frame); }, [frame]);
  if (!data) return error ? <p className="notice" data-tone="error" role="alert" dir="rtl">{error}</p> : null;
  const spec: EffectSpec | undefined = data.catalog.find(item => item.id === fx);
  const title = (id: string) => data.catalog.find(item => item.id === id)?.title || id;
  const item = (): TalkingEffect => ({ fx, start, end, ...(text.trim() ? { text: text.trim() } : {}), ...Object.fromEntries(Object.entries(options).filter(([, value]) => value !== undefined && value !== "")) });
  const valid = Boolean(spec) && end > start && end - start <= 8 && end - start >= 0.4;

  async function save(next: TalkingEffect[], label: string) {
    setBusy(label); setError("");
    try {
      const latest = await api.getTalkingReel(jobId);
      if (!latest.render_settings) throw new Error("no settings");
      const saved = await api.editTalkingReel(jobId, { render_settings: { ...latest.render_settings, effects: next } });
      setData(current => current ? { ...current, plan: saved.render_settings?.effects || [] } : current);
      onSaved();
    } catch (e) { setError(friendlyError(e, "save the effects")); } finally { setBusy(""); }
  }
  async function look() {
    setBusy("preview"); setError("");
    try { const url = await api.previewTalkingEffect(jobId, item(), (start + end) / 2); setFrame(url); }
    catch (e) { setError(friendlyError(e, "preview the effect")); } finally { setBusy(""); }
  }
  const disabled = Boolean(busy) || !data.available;
  return <EditCard title="افکت‌ها" summary={data.plan.length ? `${data.plan.length.toLocaleString("fa-IR")} افکت روی ویدیو` : "بدون افکت"}
    hint="افکت‌هایی که صورتت را دنبال می‌کنند و روی ویدیوی نهایی در بازهٔ دلخواه اضافه می‌شوند. روی رندر بعدی اعمال می‌شود. زمان‌ها ثانیه‌ی ویدیوی خروجی‌اند.">
    {!data.available ? <p className="notice" role="status">موتور افکت‌ها روی این سرور هنوز نصب نشده است.</p> : null}
    {data.error ? <p className="notice" data-tone="error" role="alert">آخرین رندر افکت‌ها اعمال نشد: {data.error}</p> : null}
    {data.plan.length ? <ul className="fx-list">{data.plan.map((entry, index) => <li key={`${entry.fx}-${index}`}>
      <span><b>{title(entry.fx)}</b><small> {seconds(entry.start)} تا {seconds(entry.end)} ثانیه{entry.text ? ` · ${entry.text}` : ""}</small></span>
      <button type="button" className="icon-btn" aria-label="برداشتن افکت" disabled={disabled} onClick={() => void save(data.plan.filter((_, i) => i !== index), "remove")}><Icon name="close" size={16}/></button>
    </li>)}</ul> : null}
    <div className="fx-form">
      <label className="field"><span className="field-label">افکت</span>
        <select className="input" value={fx} disabled={disabled} onChange={event => { setFx(event.target.value); setOptions({}); setText(""); setFrame(""); }}>{data.catalog.map(entry => <option key={entry.id} value={entry.id}>{entry.title}</option>)}</select>
        {spec ? <small className="field-hint">{spec.description}</small> : null}</label>
      <div className="fx-times">
        <label className="field"><span className="field-label">از ثانیه</span><input className="input" type="number" inputMode="decimal" dir="ltr" min={0} step={0.1} value={start} disabled={disabled} onChange={event => setStart(Number(event.target.value))}/></label>
        <label className="field"><span className="field-label">تا ثانیه</span><input className="input" type="number" inputMode="decimal" dir="ltr" min={0} step={0.1} value={end} disabled={disabled} onChange={event => setEnd(Number(event.target.value))}/></label>
      </div>
      {spec?.text ? <label className="field"><span className="field-label">{spec.text.label}</span><input className="input" type="text" dir="rtl" maxLength={40} value={text} disabled={disabled} onChange={event => setText(event.target.value)}/></label> : null}
      {spec?.options.map(option => <OptionField key={option.key} option={option} value={options[option.key]} disabled={disabled} onChange={value => setOptions(current => ({ ...current, [option.key]: value }))}/>)}
      {!valid ? <small className="field-hint">مدت هر افکت باید بین ۰٫۴ تا ۸ ثانیه باشد.</small> : null}
      <div className="fx-actions">
        <button type="button" className="btn btn-sm btn-secondary" disabled={disabled || !valid} onClick={() => void look()}>{busy === "preview" ? "در حال ساخت فریم…" : "پیش‌نمایش فریم"}</button>
        <button type="button" className="btn btn-sm" disabled={disabled || !valid || data.plan.length >= 12} onClick={() => void save([...data.plan, item()], "add")}>{busy === "add" ? "در حال ذخیره…" : "افزودن افکت"}</button>
      </div>
      {frame ? <img className="fx-frame" src={frame} alt="پیش‌نمایش افکت"/> : null}
    </div>
    {error ? <p className="notice" data-tone="error" role="alert">{error}</p> : null}
  </EditCard>;
}
