import React from "react";
import { api, DocElement, ProjectDocument, StudioProject } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { friendlyError } from "../ui";
import { TYPE_LABEL, VIA_LABEL, clock, findElement, playerMatches, stackRows, ticks } from "./timeline";

const HEADER = 92;   // px, sticky track labels

/**
 * The project timeline: every element of the video on its track, built by the backend from the exact
 * render plan. Read-only for now — each element says how it can be changed today (plan or chat).
 */
export function TimelineView({ project }: { project: StudioProject }) {
  const [doc, setDoc] = React.useState<ProjectDocument | null>(null);
  const [error, setError] = React.useState("");
  const [selected, setSelected] = React.useState<string | null>(null);
  const [zoom, setZoom] = React.useState(36);   // px per second
  const [time, setTime] = React.useState(0);
  const [latestFile, setLatestFile] = React.useState<string | null>(null);
  const videoRef = React.useRef<HTMLVideoElement>(null);
  const laneRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    let active = true;
    setError("");
    api.studioDocument(project.id).then(value => { if (active) setDoc(value); })
      .catch(e => { if (active) { setDoc(null); setError(friendlyError(e, "load the timeline")); } });
    // The newest rendered file, listed directly: a plan version awaiting approval does not hide it.
    api.studioOutputs(project.id).then(items => { if (active) setLatestFile(items[items.length - 1]?.file ?? null); }).catch(() => undefined);
    return () => { active = false; };
  }, [project.id, project.current_version, project.updated_at]);

  if (error) return <div className="notice" role="status" dir="rtl">{error}</div>;
  if (!doc) return <div className="tl-loading" role="status"><span className="spinner"/>در حال ساخت تایم‌لاین…</div>;

  const output = latestFile ? `${api.studioOutputUrl(project.id)}?file=${encodeURIComponent(latestFile)}` : undefined;
  const synced = Boolean(output) && playerMatches(doc);
  const width = Math.max(1, doc.duration * zoom);
  const element = findElement(doc, selected);
  const seek = (seconds: number) => {
    setTime(seconds);
    if (synced && videoRef.current) videoRef.current.currentTime = seconds;
  };
  const pick = (item: DocElement) => { setSelected(item.id); seek(item.start); };
  const onRuler = (event: React.MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    seek(Math.max(0, Math.min(doc.duration, (event.clientX - box.left) / zoom)));
  };

  return <div className="tl" dir="rtl">
    {output ? <div className="tl-player">
      <AuthenticatedMedia as="video" ref={videoRef} controls playsInline preload="metadata" src={output}
        onTimeUpdate={(event: React.SyntheticEvent<HTMLVideoElement>) => { if (synced) setTime(event.currentTarget.currentTime); }}/>
    </div> : null}
    {!output ? <div className="notice" role="status">ویدیو هنوز رندر نشده؛ تایم‌لاین نشان می‌دهد بعد از تأیید برنامه چه چیزی ساخته می‌شود.</div>
      : !synced ? <div className="notice" data-tone="warning" role="status">
          این تایم‌لاین نسخهٔ {doc.basis.plan_version ?? "فعلی"} برنامه است{doc.basis.rendered_version ? `؛ ویدیوی بالا از نسخهٔ ${doc.basis.rendered_version} رندر شده` : "؛ ویدیوی بالا از نسخهٔ دیگری رندر شده"} و زمان‌ها ممکن است با آن یکی نباشند.
        </div> : null}

    <div className="tl-toolbar">
      <span className="tl-time">{clock(time)} / {clock(doc.duration)}</span>
      <label className="tl-zoom">بزرگ‌نمایی<input type="range" min={12} max={160} value={zoom} onChange={event => setZoom(Number(event.target.value))} aria-label="بزرگ‌نمایی تایم‌لاین"/></label>
    </div>

    <div className="tl-scroll" dir="ltr" ref={laneRef}>
      <div className="tl-grid" style={{ width: width + HEADER }}>
        <div className="tl-row tl-ruler-row">
          <div className="tl-head"/>
          <div className="tl-ruler" style={{ width }} onClick={onRuler} role="slider" aria-label="زمان" aria-valuemin={0} aria-valuemax={doc.duration} aria-valuenow={time}>
            {ticks(doc.duration, zoom).map(tick => <span key={tick.at} className="tl-tick" data-major={tick.major || undefined} style={{ left: tick.at * zoom }}>{tick.major ? clock(tick.at).replace(/\.0$/, "") : ""}</span>)}
            <span className="tl-content-end" style={{ left: doc.content_duration * zoom }} title="پایان محتوا، شروع پایان‌بندی"/>
          </div>
        </div>
        {doc.tracks.map(track => <div key={track.id} className="tl-track" data-kind={track.kind}>
          {stackRows(track.elements).map((row, rowIndex) => <div key={rowIndex} className="tl-row">
            <div className="tl-head" dir="rtl">{rowIndex === 0 ? track.label : ""}</div>
            <div className="tl-lane" style={{ width }}>
              {row.map(item => <button key={item.id} type="button" className="tl-el" data-type={item.type} aria-pressed={item.id === selected}
                style={{ left: item.start * zoom, width: Math.max(4, (item.end - item.start) * zoom) }}
                title={`${item.label}${item.text ? ` — ${item.text}` : ""}`} onClick={() => pick(item)}>
                <span dir="auto">{item.text || item.label}</span>
              </button>)}
            </div>
          </div>)}
        </div>)}
        <span className="tl-playhead" style={{ left: HEADER + time * zoom }} aria-hidden="true"/>
      </div>
    </div>

    {element ? <section className="tl-detail" aria-label="جزئیات عنصر">
      <header><b>{TYPE_LABEL[element.type] || element.type}</b><span>{element.label}</span><small dir="ltr">{clock(element.start)} – {clock(element.end)}</small></header>
      {element.text ? <p className="bidi" dir="auto">{element.text}</p> : null}
      {element.source?.label ? <p className="tl-meta">منبع: {element.source.label}{element.source.file ? ` · ${element.source.file}` : ""}
        {element.source.in != null ? <span dir="ltr"> ({clock(element.source.in)}–{clock(element.source.out || 0)} در فایل اصلی)</span> : null}</p> : null}
      <p className="tl-meta">تغییر: {element.edit.via.length ? element.edit.via.map(item => VIA_LABEL[item] || item).join("، ") : "فعلاً قابل تغییر نیست"}</p>
      {element.edit.note ? <small className="tl-note">{element.edit.note}</small> : null}
      <small className="tl-note">ویرایش مستقیم روی تایم‌لاین در مرحلهٔ بعد اضافه می‌شود.</small>
    </section> : <p className="tl-hint">روی هر بخش بزنید تا جزئیات آن و راه تغییرش را ببینید.</p>}
  </div>;
}
