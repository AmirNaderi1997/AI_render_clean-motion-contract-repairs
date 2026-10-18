import React from "react";
import { api, StudioAction, StudioAttachment, StudioConversation, StudioEvent, StudioProject } from "./api";
import { AuthenticatedMedia } from "./AuthenticatedMedia";
import { friendlyError } from "./ui";

type PendingFile = { file: File; progress: number; attachment?: StudioAttachment; url: string };

function projectOutput(project?: StudioProject) {
  return project?.state?.last_observed?.output ? api.studioOutputUrl(project.id) : undefined;
}

export default function Studio() {
  const [conversations, setConversations] = React.useState<StudioConversation[]>([]);
  const [activeId, setActiveId] = React.useState<string | null>(new URLSearchParams(location.search).get("conversation"));
  const [conversation, setConversation] = React.useState<StudioConversation | null>(null);
  const [events, setEvents] = React.useState<StudioEvent[]>([]);
  const [text, setText] = React.useState("");
  const [files, setFiles] = React.useState<PendingFile[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [mobilePanel, setMobilePanel] = React.useState<"chat" | "preview">("chat");
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const cursorRef = React.useRef(0);
  const filesRef = React.useRef<PendingFile[]>([]);
  const voiceEnabledRef = React.useRef(false);
  React.useEffect(() => { voiceEnabledRef.current = Boolean(conversation?.status_voice_enabled); }, [conversation?.status_voice_enabled]);
  React.useEffect(() => { filesRef.current = files; }, [files]);

  const refreshList = React.useCallback(() => api.listStudioConversations().then(setConversations).catch(e => setError(friendlyError(e, "load conversations"))), []);
  const refresh = React.useCallback(async (id = activeId) => {
    if (!id) return;
    try { setConversation(await api.getStudioConversation(id)); } catch (e) { setError(friendlyError(e, "load conversation")); }
  }, [activeId]);

  React.useEffect(() => { void refreshList(); }, [refreshList]);
  React.useEffect(() => { if (activeId) void refresh(activeId); else setConversation(null); setEvents([]); cursorRef.current = 0; }, [activeId, refresh]);
  React.useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController(); let stopped = false;
    const connect = async () => {
      while (!stopped) {
        try {
          await api.streamStudioEvents(activeId, cursorRef.current, event => {
            cursorRef.current = Math.max(cursorRef.current, event.seq);
            setEvents(value => value.some(item => item.seq === event.seq) ? value : [...value, event]);
            void refresh(activeId); void refreshList();
            if (event.type === "narration.ready" && voiceEnabledRef.current) {
              void api.authenticatedObjectUrl(api.studioEventAudioUrl(activeId, event.data.event_seq)).then(url => {
                const audio = new Audio(url); void audio.play().finally(() => URL.revokeObjectURL(url));
              });
            }
          }, controller.signal);
        } catch (e) {
          if (!controller.signal.aborted) await new Promise(resolve => setTimeout(resolve, 1200));
        }
      }
    };
    void connect();
    return () => { stopped = true; controller.abort(); };
  }, [activeId]);
  React.useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [conversation?.messages?.length, events.length]);
  React.useEffect(() => () => filesRef.current.forEach(item => URL.revokeObjectURL(item.url)), []);

  async function createConversation() {
    setError("");
    const created = await api.createStudioConversation(); setConversations(value => [created, ...value]); setActiveId(created.id);
    history.replaceState(null, "", `/studio?conversation=${created.id}`);
  }

  function selectConversation(id: string) { setActiveId(id); history.replaceState(null, "", `/studio?conversation=${id}`); }

  async function addFiles(list: FileList | File[]) {
    let id = activeId;
    if (!id) { const created = await api.createStudioConversation(); id = created.id; setActiveId(id); setConversations(value => [created, ...value]); }
    for (const file of Array.from(list).slice(0, 12)) {
      const pending: PendingFile = { file, progress: 0, url: URL.createObjectURL(file) };
      setFiles(value => [...value, pending]);
      try {
        const attachment = await api.uploadStudioAttachment(id, file, progress => setFiles(value => value.map(item => item === pending ? { ...item, progress } : item)));
        setFiles(value => value.map(item => item === pending ? { ...item, progress: 100, attachment } : item));
      } catch (e) { setError(friendlyError(e, "upload attachment")); setFiles(value => value.filter(item => item !== pending)); }
    }
  }

  async function send(content = text) {
    if (!content.trim() || busy) return;
    let id = activeId;
    if (!id) { const created = await api.createStudioConversation(content.trim().slice(0, 70)); id = created.id; setActiveId(id); setConversations(value => [created, ...value]); }
    if (files.some(item => !item.attachment)) { setError("صبر کنید آپلود فایل‌ها کامل شود."); return; }
    setBusy(true); setError("");
    try {
      await api.sendStudioMessage(id, content.trim(), files.map(item => item.attachment!.id));
      files.forEach(item => URL.revokeObjectURL(item.url)); setFiles([]); setText(""); await refresh(id);
    } catch (e) { setError(friendlyError(e, "send message")); } finally { setBusy(false); }
  }

  const projects = conversation?.projects || [];
  const currentId = conversation?.state?.current_project_id;
  const current = projects.find(item => item.id === currentId) || projects[projects.length - 1];
  const pendingAction = (conversation?.actions || []).find(item => item.project_id === current?.id && item.status === "pending");
  const styles = current?.state?.styles || [];
  const storyboard = current?.state?.storyboard;
  const sourceAttachment = current?.state?.attachment_ids?.[0];
  const visibleConversations = conversations.filter(item => item.title.toLowerCase().includes(search.toLowerCase()));

  return <div className="studio-shell" dir="rtl">
    <aside className="studio-sidebar">
      <button className="studio-new" onClick={() => void createConversation()}>＋ پروژه جدید</button>
      <input className="studio-search" value={search} onChange={e => setSearch(e.target.value)} placeholder="جستجوی گفتگوها" />
      <div className="studio-conversations">
        {visibleConversations.map(item => <button key={item.id} className={item.id === activeId ? "active" : ""} onClick={() => selectConversation(item.id)}>
          <span>{item.title}</span><small>{new Date(item.updated_at).toLocaleDateString("fa-IR")}</small>
        </button>)}
      </div>
      <div className="studio-processing">{projects.filter(item => item.status === "running").length ? "● پردازش فعال" : "همه پردازش‌ها پایدارند"}</div>
    </aside>

    <section className="studio-chat">
      <header className="studio-chat-header"><div><b>{conversation?.title || "Video Studio"}</b><small>با فارسی یا انگلیسی درخواستتان را بنویسید</small></div>
        {conversation && <button className="secondary small" onClick={() => api.updateStudioConversation(conversation.id, { status_voice_enabled: !conversation.status_voice_enabled }).then(setConversation)}>{conversation.status_voice_enabled ? "🔊 گزارش صوتی" : "🔇 گزارش صوتی"}</button>}
        <div className="studio-mobile-tabs"><button onClick={() => setMobilePanel("chat")} className={mobilePanel === "chat" ? "active" : ""}>چت</button><button onClick={() => setMobilePanel("preview")} className={mobilePanel === "preview" ? "active" : ""}>پیش‌نمایش</button></div>
      </header>
      <div className={`studio-chat-body ${mobilePanel !== "chat" ? "mobile-hidden" : ""}`}>
        {!conversation?.messages?.length && <div className="studio-welcome"><span>✦</span><h1>چه ویدیویی بسازیم؟</h1><p>ویدیو، عکس یا لینک محصول را بفرستید و نتیجه را با گفتگو اصلاح کنید.</p><div className="studio-suggestions">
          {["این ویدیو رو فارسی کن", "مثل ریلز حرفه‌ای اینستاگرام تدوینش کن", "از این لینک یک تیزر ۳۰ ثانیه‌ای با نریشن فارسی بساز", "از این عکس‌ها یک تبلیغ اینستاگرامی بساز"].map(value => <button key={value} onClick={() => setText(value)}>{value}</button>)}
        </div></div>}
        {conversation?.messages?.map(message => <div key={`${message.role}-${message.id}`} className={`studio-message ${message.role}`}><div>{message.content}</div></div>)}
        {events.filter(item => ["tool.progress", "tool.started", "tool.failed", "render.completed"].includes(item.type)).slice(-8).map(event => <div key={event.seq} className={`studio-event ${event.type.includes("failed") ? "error" : ""}`}>
          <span className="studio-event-dot"/><div><b>{event.data.message || event.type}</b>{event.data.stage && <small>{event.data.stage}{typeof event.data.progress === "number" ? ` · ${event.data.progress}%` : ""}</small>}</div>
        </div>)}
        {styles.length > 0 && current?.status === "awaiting_input" && <div className="studio-inline-card"><h3>سبک تدوین را انتخاب کنید</h3><div className="studio-style-grid">{styles.map((style: any) => <button key={style.id || style.key} onClick={() => void send(`سبک ${style.id || style.key}`)}><b>{style.label || style.title || style.name}</b><span>{style.description || "سبک واقعی Talking Reel"}</span></button>)}</div></div>}
        {pendingAction && <div className="studio-inline-card"><h3>تأیید اجرای برنامه</h3><p>پس از تأیید، تولید دارایی، گویندگی و رندر شروع می‌شود.</p>{pendingAction.estimated_cost_usd != null && <p>تخمین ثبت‌شده: ${pendingAction.estimated_cost_usd.toFixed(4)}</p>}<div className="row"><button onClick={() => api.confirmStudioAction(pendingAction.id).then(() => refresh())}>تأیید و اجرا</button><button className="secondary" onClick={() => api.cancelStudioAction(pendingAction.id).then(() => refresh())}>لغو</button></div></div>}
        <div ref={bottomRef}/>
      </div>
      <div className={`studio-composer ${mobilePanel !== "chat" ? "mobile-hidden" : ""}`} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); void addFiles(e.dataTransfer.files); }}>
        {files.length > 0 && <div className="studio-attachments">{files.map((item, index) => <div key={`${item.file.name}-${index}`}>{item.file.type.startsWith("image/") ? <img src={item.url}/> : <span>▶</span>}<small>{item.file.name}</small><i style={{ width: `${item.progress}%` }}/></div>)}</div>}
        {error && <div className="errors">{error}</div>}
        <div className="studio-composer-row"><label className="studio-attach">＋<input type="file" multiple accept="video/*,image/*,audio/*" onChange={e => e.target.files && void addFiles(e.target.files)}/></label><textarea value={text} onChange={e => setText(e.target.value)} onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }} placeholder="مثلاً: این ویدیو رو فارسی کن…"/><button onClick={() => void send()} disabled={busy || !text.trim()}>↑</button></div>
        <small>گزارش‌ها از رویدادهای واقعی موتور نمایش داده می‌شوند.</small>
      </div>
    </section>

    <aside className={`studio-workspace ${mobilePanel !== "preview" ? "mobile-hidden" : ""}`}>
      <header><div><b>Workspace</b><small>{current ? `${current.engine} · نسخه ${current.current_version}` : "هنوز پروژه‌ای ساخته نشده"}</small></div>{current?.status === "running" && <button className="danger small" onClick={() => api.cancelStudioProject(current.id).then(() => refresh())}>لغو</button>}</header>
      {!current && <div className="studio-empty-preview">فایل یا خروجی پروژه اینجا نمایش داده می‌شود.</div>}
      {current && <>
        <div className="studio-project-status"><span className={`status-badge ${current.status === "done" ? "done" : "running"}`}>{current.status}</span><h2>{current.title}</h2><p>{current.state?.last_observed?.message || current.state?.last_observed?.stage}</p></div>
        {projectOutput(current) ? <div className="studio-video"><AuthenticatedMedia as="video" controls src={api.studioOutputUrl(current.id)}/><button onClick={async () => { const url = await api.authenticatedObjectUrl(api.studioOutputUrl(current.id)); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${current.title}.mp4`; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }}>دانلود خروجی</button></div>
          : sourceAttachment && <AuthenticatedMedia as="video" controls src={api.studioAttachmentUrl(conversation!.id, sourceAttachment)}/>}
        {current.state?.source_assets?.length > 0 && <div className="studio-asset-grid">{current.state.source_assets.map((_item: string, index: number) => <AuthenticatedMedia key={index} as="img" src={api.studioAssetUrl(current.id, index)} alt={`Product asset ${index + 1}`}/>)}</div>}
        {storyboard?.scenes?.length > 0 && <StoryboardEditor project={current} onSaved={() => refresh()} />}
      </>}
    </aside>
  </div>;
}

function StoryboardEditor({ project, onSaved }: { project: StudioProject; onSaved: () => void }) {
  const [scenes, setScenes] = React.useState<any[]>(project.state.storyboard.scenes || []);
  React.useEffect(() => setScenes(project.state.storyboard.scenes || []), [project.id, project.current_version, project.state.storyboard]);
  const update = (index: number, patch: any) => setScenes(value => value.map((scene, i) => i === index ? { ...scene, ...patch } : scene));
  return <div className="studio-storyboard"><div className="section-header"><h3>استوری‌بورد</h3><button className="secondary small" onClick={() => api.updateStudioStoryboard(project.id, scenes).then(onSaved)}>ذخیره</button></div>{scenes.map((scene, index) => <div className="studio-scene" key={scene.index ?? index}><b>{index + 1}</b><input value={scene.text_overlay || ""} onChange={e => update(index, { text_overlay: e.target.value })}/><textarea value={scene.narration_text || ""} onChange={e => update(index, { narration_text: e.target.value })}/><label>ثانیه <input type="number" min="0.5" max="30" step="0.5" value={scene.duration_s} onChange={e => update(index, { duration_s: Number(e.target.value) })}/></label></div>)}</div>;
}
