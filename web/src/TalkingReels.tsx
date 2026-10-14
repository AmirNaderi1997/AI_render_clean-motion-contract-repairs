import React from "react";
import { api, TalkingReelSummary } from "./api";
import { TalkingReelCard } from "./TalkingReel";
import { friendlyError, notify } from "./ui";

const STATUS: Record<string, string> = { idle: "آماده‌ی ساخت", running: "در حال ساخت", done: "آماده", error: "خطا" };

/** Talking-head videos: upload a podcast clip, get a styled vertical reel. */
export default function TalkingReels() {
  const [items, setItems] = React.useState<TalkingReelSummary[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [progress, setProgress] = React.useState<number | null>(null);
  const [error, setError] = React.useState("");

  const refresh = React.useCallback(async () => {
    try {
      const list = await api.listTalkingReels();
      setItems(list);
      setSelected(s => s ?? list[0]?.job_id ?? null);
    } catch (err) { setError(friendlyError(err, "load talking videos")); }
  }, []);
  React.useEffect(() => { void refresh(); }, [refresh]);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setError("یک ویدیو انتخاب کنید."); return; }
    setError("");
    setProgress(0);
    try {
      const { job } = await api.createJob(file, undefined, setProgress);
      await api.renderTalkingReel(job.id, true);
      notify("ساخت ویدیوی صحبتی شروع شد");
      setFile(null);
      setSelected(job.id);
      await refresh();
    } catch (err) { setError(friendlyError(err, "upload the video")); }
    finally { setProgress(null); }
  }

  return (
    <div dir="rtl">
      <h1>ویدیو صحبتی</h1>
      <p className="muted">ویدیوی پادکست یا صحبت (افقی یا عمودی) رو آپلود کن. خودش متن رو درمیاره و اصلاح می‌کنه، تیتر قلاب و هوک شروع می‌سازه، روی سکوت‌ها کات می‌زنه، زوم و رنگ و موزیک و پایان‌بندی لوگو اضافه می‌کنه. بعد از ساخت، تیتر و زیرنویس و بقیه‌ی تنظیمات قابل ویرایشه.</p>
      <form className="card row" onSubmit={upload}>
        <input type="file" accept="video/*" onChange={e => setFile(e.target.files?.[0] || null)} disabled={progress !== null} />
        <button type="submit" disabled={!file || progress !== null}>
          {progress !== null ? `در حال آپلود ${progress}%` : "آپلود و ساخت ویدیوی صحبتی"}
        </button>
      </form>
      {error && <div className="errors">{error}</div>}
      {items.length > 0 && (
        <div className="card">
          <h2>ویدیوهای صحبتی</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {items.map(item => (
              <button key={item.job_id} className={item.job_id === selected ? "" : "btn-secondary"} onClick={() => setSelected(item.job_id)}>
                {item.name || item.job_id} — {STATUS[item.status] || item.status}
              </button>
            ))}
          </div>
        </div>
      )}
      {selected && <TalkingReelCard key={selected} jobId={selected} onChanged={() => { void refresh(); }} />}
    </div>
  );
}
