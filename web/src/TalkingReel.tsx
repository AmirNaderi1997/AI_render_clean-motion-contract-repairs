import React from "react";
import { api, TalkingReelState } from "./api";
import { AuthenticatedMedia } from "./AuthenticatedMedia";
import { friendlyError, notify } from "./ui";

const DEFAULT_MUSIC = "assets/music/motivational_piano_beat.mp3";
const STAGES: Record<string, string> = {
  queued: "در صف", transcribing: "تشخیص گفتار", "editing text": "اصلاح متن و تیتر",
  "choosing style": "انتخاب هوشمند استایل", "tracking the face": "تشخیص صورت",
  "finding pictures": "پیدا کردن و ساختن تصویرها", rendering: "رندر",
};

/** Talking-head reel (podcast clip -> styled vertical reel) for one job. */
export function TalkingReelCard({ jobId, onChanged }: { jobId: string; onChanged?: () => void }) {
  const [state, setState] = React.useState<TalkingReelState | null>(null);
  const [draft, setDraft] = React.useState<TalkingReelState | null>(null);
  const [error, setError] = React.useState("");
  const running = state?.status === "running";
  const [styles, setStyles] = React.useState<{ id: string; label: string }[]>([]);
  const [media, setMedia] = React.useState<string[]>([]);
  React.useEffect(() => { api.talkingReelStyles().then(setStyles).catch(() => setStyles([])); }, []);
  React.useEffect(() => { api.talkingReelMedia(jobId).then(setMedia).catch(() => setMedia([])); }, [jobId]);

  React.useEffect(() => {
    let active = true;
    async function poll() {
      try {
        const next = await api.getTalkingReel(jobId);
        if (!active) return;
        setState(prev => { if (prev && prev.status !== next.status) onChanged?.(); return next; });
        setDraft(d => (d && next.status === "running" ? d : next));
      } catch (err) { if (active) setError(friendlyError(err, "load the talking reel")); }
    }
    void poll();
    const iv = setInterval(() => { if (running) void poll(); }, 2000);
    return () => { active = false; clearInterval(iv); };
  }, [jobId, running]);

  if (!state || !draft) return null;
  const enhanced = ["talking_2", "talking_3", "talking_4"].includes(draft.style || "talking_1");
  const hasVisuals = ["talking_2", "talking_3"].includes(draft.style || "talking_1");
  const SOURCES: Record<string, string> = { upload: "آپلود خودت", library: "کتابخونه", ai: "هوش مصنوعی", card: "کارت متنی" };

  async function addMedia(files: FileList | null) {
    if (!files || !files.length) return;
    try { setMedia((await api.uploadTalkingReelMedia(jobId, Array.from(files))).media); notify("تصویرها آپلود شدن"); }
    catch (err) { setError(friendlyError(err, "upload the pictures")); }
  }

  async function render(regenerate: boolean) {
    if (!draft) return;
    setError("");
    try {
      if (!regenerate) {
        await api.editTalkingReel(jobId, {
          hook: draft.hook, hook_highlight: draft.hook_highlight, name: draft.name, title: draft.title, music: draft.music,
          cta: draft.cta ?? "", style: draft.style || "talking_1", hook2: draft.hook2 ?? "", captions: draft.captions ?? [],
        });
      }
      setState(await api.renderTalkingReel(jobId, regenerate));
      notify("ساخت ویدیوی صحبتی شروع شد");
    } catch (err) { setError(friendlyError(err, "start the talking reel")); }
  }

  async function analyze(style?: string) {
    setError("");
    try {
      if (style) await api.editTalkingReel(jobId, { style });
      setState(await api.analyzeTalkingReel(jobId, style));
      notify("تحلیل و پیشنهادهای قبل از رندر شروع شد");
    } catch (err) { setError(friendlyError(err, "analyze the talking reel")); }
  }

  async function chooseStyle(style: string) {
    setDraft({ ...draft!, style });
    await analyze(style);
  }

  return (
    <div className="card" dir="rtl">
      <div className="section-header">
        <h2>ویدیوی صحبتی (پادکست ← ریل عمودی)</h2>
        <span className="tag">
          {running ? `${STAGES[state.stage] || state.stage} ${state.progress}%` : state.status === "ready" ? "آماده‌ی بازبینی" : state.status === "done" ? "آماده" : state.status === "error" ? "خطا" : ""}
        </span>
      </div>
      <p className="muted">اول ترنسکریب و تحلیل انجام می‌شود. استایل پیشنهادی، تیتر قلاب، کلمات برجسته و زیرنویس‌ها را بازبینی کن؛ سپس رندر را شروع کن.</p>
      {state.status === "error" && <div className="errors">{state.message}</div>}
      {error && <div className="errors">{error}</div>}
      {state.output && state.status === "done" && (
        <div className="row" style={{ alignItems: "flex-start" }}>
          <AuthenticatedMedia as="video" src={`${api.talkingReelOutputUrl(jobId)}?v=${encodeURIComponent(state.output)}`} controls style={{ maxHeight: 520, borderRadius: 8 }} />
          <button className="btn-secondary" onClick={() => api.downloadAuthenticated(api.talkingReelOutputUrl(jobId), `${jobId}_talking_reel.mp4`)}>دانلود ویدیو</button>
        </div>
      )}
      <div className="row">
        <label>استایل تدوین
          <select value={draft.style || "talking_1"} disabled={running} onChange={e => { void chooseStyle(e.target.value); }}>
            {styles.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
        {state.suggested_style && <span className="tag">پیشنهاد سیستم: {styles.find(s => s.id === state.suggested_style)?.label || state.suggested_style}</span>}
      </div>
      {state.suggested_style_reason && <p className="muted">دلیل پیشنهاد: {state.suggested_style_reason}</p>}
      {enhanced ? (
        <>
          <div className="row">
            <label style={{ flex: 1 }}>هوک ۳ ثانیه‌ی اول (۲ تا ۴ کلمه)
              <input value={draft.hook2 ?? ""} disabled={running} placeholder="بعد از اولین ساخت، هوش مصنوعی پیشنهاد می‌ده"
                onChange={e => setDraft({ ...draft, hook2: e.target.value })} style={{ width: "100%" }} />
            </label>
          </div>
          {hasVisuals && <div className="row" style={{ alignItems: "flex-start" }}>
              <label>تصویرهای بی‌رول خودت (اختیاری، هوش مصنوعی هر کدوم رو سر جای مناسبش می‌ذاره)
                <input type="file" accept="image/*" multiple disabled={running} onChange={e => { void addMedia(e.target.files); e.target.value = ""; }} />
              </label>
              {media.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {media.map(name => (
                    <span key={name} className="tag">{name}
                      <button className="btn-secondary" disabled={running} style={{ marginInlineStart: 6, padding: "0 6px" }}
                        onClick={() => { api.deleteTalkingReelMedia(jobId, name).then(() => setMedia(m => m.filter(x => x !== name))).catch(err => setError(friendlyError(err, "remove the picture"))); }}>×</button>
                    </span>
                  ))}
                </div>
              )}
            </div>}
          {hasVisuals && state.slots && state.slots.length > 0 && (
            <div className="muted" style={{ fontSize: 13 }}>
              بی‌رول‌ها: {state.slots.map(slot => `${slot.label || `جمله‌ی ${slot.i + 1}`} ← ${SOURCES[slot.source] || slot.source}`).join("  •  ")}
            </div>
          )}
        </>
      ) : (
        <div className="row">
          <label style={{ flex: 1 }}>تیتر قلاب (ثابت روی ویدیو)
            <input value={draft.hook} disabled={running} placeholder="بعد از اولین ساخت، هوش مصنوعی پیشنهاد می‌ده"
              onChange={e => setDraft({ ...draft, hook: e.target.value })} style={{ width: "100%" }} />
          </label>
          <label>کلمه‌های زرد (با , جدا کن)
            <input value={draft.hook_highlight.join(", ")} disabled={running}
              onChange={e => setDraft({ ...draft, hook_highlight: e.target.value.split(/[,،]/).map(v => v.trim()).filter(Boolean) })} />
          </label>
        </div>
      )}
      {draft.captions && draft.captions.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h3>بازبینی زیرنویس‌ها قبل از رندر</h3>
          <div style={{ display: "grid", gap: 8, maxHeight: 360, overflowY: "auto" }}>
            {draft.captions.map((caption, index) => (
              <label key={caption.i} className="row" style={{ alignItems: "center" }}>
                <span className="tag">{caption.i + 1}</span>
                <input value={caption.text} disabled={running} style={{ flex: 1 }}
                  onChange={e => setDraft({ ...draft, captions: draft.captions!.map((item, i) => i === index ? { ...item, text: e.target.value } : item) })} />
              </label>
            ))}
          </div>
        </div>
      )}
      <div className="row">
        <label>اسم <input dir="ltr" value={draft.name} disabled={running} onChange={e => setDraft({ ...draft, name: e.target.value })} /></label>
        <label>سمت <input dir="ltr" value={draft.title} disabled={running} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label>
        <label>
          <input type="checkbox" checked={!!draft.music} disabled={running} onChange={e => setDraft({ ...draft, music: e.target.checked ? DEFAULT_MUSIC : null })} />
          موزیک ملایم زیر صدا
        </label>
      </div>
      <div className="row">
        <label style={{ flex: 1 }}>کال تو اکشن آخر ویدیو (خالی = فقط موشن لوگو)
          <input value={draft.cta ?? ""} disabled={running} placeholder="برای اینکه یاد بگیری چطور محصول بفروشی عدد ۲۰ رو کامنت کن"
            onChange={e => setDraft({ ...draft, cta: e.target.value })} style={{ width: "100%" }} />
        </label>
      </div>
      <div className="row">
        <button disabled={running || !state.analysis_ready} onClick={() => { void render(false); }}>{state.output ? "رندر دوباره با این تنظیمات" : "تأیید تنظیمات و شروع رندر"}</button>
        <button className="btn-secondary" disabled={running} onClick={() => { void analyze(draft.style || "talking_1"); }}>پیشنهاد دوباره‌ی تیتر و زیرنویس (بدون رندر)</button>
      </div>
    </div>
  );
}
