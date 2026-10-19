import React from "react";
import { NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, StudioAttachment, StudioConversation, StudioEvent, StudioProject } from "./api";
import { AuthenticatedMedia } from "./AuthenticatedMedia";
import { Icon } from "./EditorShell";
import { friendlyError } from "./ui";
import { isAuthenticated } from "./auth";

type PendingFile = { file: File; progress: number; attachment?: StudioAttachment; url: string };
type WorkspaceView = "chat" | "preview" | "edit";

const suggestions = [
  "Edit an Instagram Reel", "Remove pauses and mistakes", "Add engaging Persian captions",
  "Create a product advertisement", "Turn a long video into short clips", "Create a cinematic talking-head video",
];
const templatePrompts: Record<string, string> = {
  talking: "این ویدیوی صحبتی را مثل یک ریلز حرفه‌ای اینستاگرام تدوین کن",
  localize: "این ویدیو را با دوبله و زیرنویس فارسی آماده کن",
  product: "برای این محصول یک تیزر موشن ۳۰ ثانیه‌ای با نریشن فارسی بساز",
  reel: "از این ویدیو یک ریلز جذاب اینستاگرامی بساز",
};
const eventLabels: Record<string, string> = {
  "message.started": "Understanding your request", "tool.started": "Starting the edit",
  "tool.progress": "Editing your video", "storyboard.ready": "Storyboard is ready",
  "render.started": "Rendering your video", "render.progress": "Rendering your video",
  "render.completed": "Video ready", "tool.failed": "This step needs attention",
  "question.required": "A quick choice is needed", "preview.ready": "Preview ready",
};
const stageLabels: Record<string, string> = {
  transcribing: "Transcribing speech", "finding captions": "Finding on-screen captions",
  translating: "Preparing the Persian translation", "generating voice": "Creating the voice-over",
  "choosing style": "Choosing an editing style", "editing text": "Preparing captions and hooks",
  planning: "Planning the edit", generating: "Creating visual assets", "generating assets": "Creating visual assets",
  rendering: "Rendering the video", ready: "Video ready", failed: "Needs attention", pending: "Planning the edit",
  analyzing: "Analyzing your video", transcribed: "Speech transcription is ready", storyboard: "Preparing the storyboard",
};

function projectOutput(project?: StudioProject) {
  const output = project?.state?.last_observed?.output;
  return output && project ? `${api.studioOutputUrl(project.id)}?version=${encodeURIComponent(output)}` : undefined;
}
function statusLabel(status?: string) {
  if (["done", "ready"].includes(status || "")) return "Ready";
  if (["error", "failed"].includes(status || "")) return "Needs attention";
  if (["awaiting_confirmation", "awaiting_input", "paused"].includes(status || "")) return "Waiting for you";
  if (["running", "rendering", "queued"].includes(status || "")) return "Working";
  return "Draft";
}

export default function Studio() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [conversations, setConversations] = React.useState<StudioConversation[]>([]);
  const [conversation, setConversation] = React.useState<StudioConversation | null>(null);
  const [events, setEvents] = React.useState<StudioEvent[]>([]);
  const [text, setText] = React.useState(() => searchParams.get("prompt") || templatePrompts[searchParams.get("template") || ""] || "");
  const [files, setFiles] = React.useState<PendingFile[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const [view, setView] = React.useState<WorkspaceView>("chat");
  const [activitiesOpen, setActivitiesOpen] = React.useState(true);
  const [listening, setListening] = React.useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const cursorRef = React.useRef(0);
  const filesRef = React.useRef<PendingFile[]>([]);
  const voiceEnabledRef = React.useRef(false);
  const legacyOpenRef = React.useRef("");
  const refreshTimerRef = React.useRef<number | null>(null);
  const listTimerRef = React.useRef<number | null>(null);
  const activeId = conversationId || null;
  const authenticated = isAuthenticated();
  const hasSpeech = typeof window !== "undefined" && Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  React.useEffect(() => { voiceEnabledRef.current = Boolean(conversation?.status_voice_enabled); }, [conversation?.status_voice_enabled]);
  React.useEffect(() => { filesRef.current = files; }, [files]);
  const refreshList = React.useCallback(() => authenticated ? api.listStudioConversations().then(setConversations).catch(error => setError(friendlyError(error, "load conversations"))) : Promise.resolve(), [authenticated]);
  const refresh = React.useCallback(async (id = activeId) => { if (!id) return; try { setConversation(await api.getStudioConversation(id)); } catch (error) { setError(friendlyError(error, "load conversation")); } }, [activeId]);
  React.useEffect(() => { void refreshList(); }, [refreshList]);
  React.useEffect(() => { if (authenticated && activeId) void refresh(activeId); else setConversation(null); setEvents([]); cursorRef.current = 0; }, [authenticated, activeId, refresh]);
  React.useEffect(() => {
    const legacy = searchParams.get("legacy");
    if (!legacy || !authenticated) return;
    if (legacyOpenRef.current === legacy) return;
    const [engine, externalRef] = legacy.split(":", 2);
    if (!externalRef || !["motion", "talking", "localize"].includes(engine)) return;
    legacyOpenRef.current = legacy;
    setBusy(true);
    void api.openLegacyInStudio(engine as "motion" | "talking" | "localize", externalRef, searchParams.get("title") || "Video project")
      .then(value => { setConversation(value); navigate(`/studio/${value.id}`, { replace:true }); })
      .catch(error => setError(friendlyError(error, "open project"))).finally(() => setBusy(false));
  }, [authenticated, navigate, searchParams]);
  React.useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController(); let stopped = false;
    const connect = async () => { while (!stopped) { try { await api.streamStudioEvents(activeId, cursorRef.current, event => {
      cursorRef.current = Math.max(cursorRef.current, event.seq);
      setEvents(value => value.some(item => item.seq === event.seq) ? value : [...value, event]);
      if (refreshTimerRef.current != null) window.clearTimeout(refreshTimerRef.current);
      refreshTimerRef.current = window.setTimeout(() => void refresh(activeId), 180);
      if (listTimerRef.current == null) listTimerRef.current = window.setTimeout(() => {
        listTimerRef.current = null;
        void refreshList();
        window.dispatchEvent(new Event("editorgpt:conversations-updated"));
      }, 1200);
      if (event.type === "narration.ready" && voiceEnabledRef.current) void api.authenticatedObjectUrl(api.studioEventAudioUrl(activeId, event.data.event_seq)).then(url => { const audio = new Audio(url); void audio.play().finally(() => URL.revokeObjectURL(url)); });
    }, controller.signal); } catch { if (!controller.signal.aborted) await new Promise(resolve => setTimeout(resolve, 1200)); } } };
    void connect(); return () => {
      stopped = true; controller.abort();
      if (refreshTimerRef.current != null) window.clearTimeout(refreshTimerRef.current);
      if (listTimerRef.current != null) window.clearTimeout(listTimerRef.current);
      refreshTimerRef.current = null; listTimerRef.current = null;
    };
  }, [activeId, refresh, refreshList]);
  React.useEffect(() => { if (view === "chat") bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [conversation?.messages?.length, events.length, view]);
  React.useEffect(() => () => filesRef.current.forEach(item => URL.revokeObjectURL(item.url)), []);

  function requireLogin() { navigate("/login", { state:{ from: window.location.pathname + window.location.search } }); }
  function selectConversation(id: string) { navigate(`/studio/${id}`); }
  async function ensureConversation(title = "گفتگوی جدید") { if (activeId) return activeId; const created = await api.createStudioConversation(title); setConversations(value => [created, ...value]); navigate(`/studio/${created.id}`, { replace: true }); return created.id; }
  async function addFiles(list: FileList | File[]) {
    if (!authenticated) { requireLogin(); return; }
    const id = await ensureConversation("New media edit");
    for (const file of Array.from(list).slice(0, 12)) { const pending: PendingFile = { file, progress: 0, url: URL.createObjectURL(file) }; setFiles(value => [...value, pending]); try { const attachment = await api.uploadStudioAttachment(id, file, progress => setFiles(value => value.map(item => item === pending ? { ...item, progress } : item))); setFiles(value => value.map(item => item === pending ? { ...item, progress: 100, attachment } : item)); } catch (error) { setError(friendlyError(error, "upload attachment")); setFiles(value => value.filter(item => item !== pending)); URL.revokeObjectURL(pending.url); } }
  }
  async function send(content = text) {
    if (!authenticated) { requireLogin(); return; }
    const finalText = content.trim() || (files.length ? "این فایل را بررسی کن و برای تدوین آماده کن" : "");
    if (!finalText || busy) return;
    const id = await ensureConversation(finalText.slice(0, 70));
    if (files.some(item => !item.attachment)) { setError("Please wait for the uploads to finish."); return; }
    setBusy(true); setError("");
    try { await api.sendStudioMessage(id, finalText, files.map(item => item.attachment!.id)); files.forEach(item => URL.revokeObjectURL(item.url)); setFiles([]); setText(""); await refresh(id); }
    catch (error) { setError(friendlyError(error, "send message")); } finally { setBusy(false); }
  }
  function startVoiceInput() {
    const Speech = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Speech) return;
    const recognition = new Speech(); recognition.lang = document.documentElement.lang === "en" ? "en-US" : "fa-IR"; recognition.interimResults = true;
    recognition.onstart = () => setListening(true); recognition.onend = () => setListening(false);
    recognition.onresult = (event: any) => setText(Array.from(event.results).map((result: any) => result[0].transcript).join(" "));
    recognition.onerror = () => { setListening(false); setError("Voice input could not start. Check microphone access."); }; recognition.start();
  }

  const projects = conversation?.projects || [];
  const current = projects.find(item => item.id === conversation?.state?.current_project_id) || projects[projects.length - 1];
  const pendingAction = (conversation?.actions || []).find(item => item.project_id === current?.id && item.status === "pending");
  const styles = current?.state?.styles || [];
  const sourceAttachment = current?.state?.attachment_ids?.[0];
  const activity = events.filter(item => ["tool.progress", "tool.started", "tool.failed", "render.started", "render.progress", "render.completed", "storyboard.ready"].includes(item.type)).slice(-12);
  const isHome = !conversation;

  return <div className={`eg-studio ${isHome ? "home" : "active"} view-${view}`} dir="auto">
    <section className="eg-conversation">
      <div className="eg-view-tabs" role="tablist">{(["chat", "preview", "edit"] as WorkspaceView[]).map(item => <button key={item} className={view === item ? "active" : ""} onClick={() => setView(item)} role="tab">{item[0].toUpperCase() + item.slice(1)}</button>)}</div>
      <div className={`eg-chat-view ${view !== "chat" ? "eg-view-hidden" : ""}`}>
        <div className="eg-message-scroll">
          {isHome ? <HomeWelcome conversations={conversations} onSuggestion={setText} onOpen={selectConversation} guest={!authenticated} composer={<Composer text={text} setText={setText} files={files} busy={busy} error={error} hasSpeech={hasSpeech} listening={listening} onListen={startVoiceInput} onFiles={addFiles} onSend={send} onRequireLogin={!authenticated ? requireLogin : undefined}/>}/> : <>
            {conversation.messages?.map(message => <article key={`${message.role}-${message.id}`} className={`eg-message ${message.role}`}><div className="eg-message-role">{message.role === "assistant" ? <span className="eg-mark"><Icon name="spark" size={15}/></span> : null}</div><div className="eg-message-content"><p>{message.content}</p>{message.attachments?.length ? <div className="eg-message-files">{message.attachments.map(id => <span key={id}>Attached media</span>)}</div> : null}</div></article>)}
            {activity.length ? <section className="eg-activity"><button className="eg-activity-summary" onClick={() => setActivitiesOpen(value => !value)} aria-expanded={activitiesOpen}><span><i className={current?.status === "running" ? "pulse" : ""}/>{current?.status === "done" ? "Edit complete" : current?.status === "error" ? "Needs attention" : "Editing activity"}</span><Icon name="chevron" size={16}/></button>{activitiesOpen ? <div className="eg-activity-list">{activity.map(event => <ActivityItem event={event} key={event.seq}/>)}</div> : null}</section> : null}
            {styles.length > 0 && current?.status === "awaiting_input" ? <div className="eg-action-card"><span className="eg-eyebrow">Choose a style</span><h3>How should this video feel?</h3><div className="eg-style-options">{styles.map((style: any) => <button key={style.id || style.key} onClick={() => void send(`سبک ${style.id || style.key}`)}><b>{style.label || style.title || style.name}</b><small>{style.description || "Talking Reel style"}</small></button>)}</div></div> : null}
            {pendingAction ? <div className="eg-action-card"><span className="eg-eyebrow">Ready to create</span><h3>Approve this plan?</h3><p>EditorGPT will create the media, voice-over and final render using the plan above.</p>{pendingAction.estimated_cost_usd != null ? <small>Recorded estimate: ${pendingAction.estimated_cost_usd.toFixed(4)}</small> : null}<div className="eg-action-buttons"><button onClick={() => api.confirmStudioAction(pendingAction.id).then(() => refresh())}>Approve and continue</button><button className="secondary" onClick={() => api.cancelStudioAction(pendingAction.id).then(() => refresh())}>Cancel</button></div></div> : null}
          </>}
          <div ref={bottomRef}/>
        </div>
        {!isHome ? <Composer text={text} setText={setText} files={files} busy={busy} error={error} hasSpeech={hasSpeech} listening={listening} onListen={startVoiceInput} onFiles={addFiles} onSend={send}/> : null}
      </div>
      <div className={`eg-preview-view ${view !== "preview" ? "eg-view-hidden" : ""}`}><Preview project={current} conversation={conversation} sourceAttachment={sourceAttachment} onCancel={() => current && api.cancelStudioProject(current.id).then(() => refresh())}/></div>
      <div className={`eg-edit-view ${view !== "edit" ? "eg-view-hidden" : ""}`}><EditWorkspace project={current} onSaved={() => refresh()}/></div>
    </section>
    {!isHome ? <aside className="eg-desktop-preview"><Preview project={current} conversation={conversation} sourceAttachment={sourceAttachment} onCancel={() => current && api.cancelStudioProject(current.id).then(() => refresh())}/></aside> : null}
  </div>;
}

function HomeWelcome({ conversations, onSuggestion, onOpen, guest, composer }: { conversations: StudioConversation[]; onSuggestion: (value: string) => void; onOpen: (id: string) => void; guest: boolean; composer: React.ReactNode }) {
  return <div className="eg-home-welcome"><h1>EditorGPT</h1><p className="eg-home-tagline">Your AI video editor</p>{composer}<div className="eg-suggestion-row">{suggestions.slice(0, 4).map(item => <button key={item} onClick={() => onSuggestion(item)}>{item}</button>)}</div>{!guest && conversations.length ? <div className="eg-recent"><div><b>Recent projects</b><NavLink to="/projects">View all</NavLink></div>{conversations.slice(0, 3).map(item => <button key={item.id} onClick={() => onOpen(item.id)}><span>{item.title}</span><small>{new Intl.DateTimeFormat(undefined, { month: "short", day:"numeric" }).format(Date.parse(item.updated_at))}</small><Icon name="chevron" size={16}/></button>)}</div> : null}</div>;
}

function Composer({ text, setText, files, busy, error, hasSpeech, listening, onListen, onFiles, onSend, onRequireLogin }: { text: string; setText: (value: string) => void; files: PendingFile[]; busy: boolean; error: string; hasSpeech: boolean; listening: boolean; onListen: () => void; onFiles: (files: FileList | File[]) => void; onSend: (text?: string) => void; onRequireLogin?: () => void }) {
  return <div className="eg-composer-wrap"><div className="eg-composer" onDragOver={event => event.preventDefault()} onDrop={event => { event.preventDefault(); void onFiles(event.dataTransfer.files); }}>
    {files.length ? <div className="eg-attachments">{files.map((item, index) => <div key={`${item.file.name}-${index}`}>{item.file.type.startsWith("image/") ? <img src={item.url} alt=""/> : <span>{item.file.type.startsWith("video/") ? "Video" : "Audio"}</span>}<small>{item.file.name}</small><i style={{ width: `${item.progress}%` }}/></div>)}</div> : null}
    {error ? <div className="eg-composer-error" role="alert">{error}</div> : null}
    <textarea value={text} onFocus={() => onRequireLogin?.()} onChange={event => setText(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void onSend(); } }} placeholder="Describe the video you want to create or edit…" rows={1}/>
    <div className="eg-composer-tools"><div><label className="eg-tool-button" aria-label="Attach media"><span>+</span><input type="file" multiple accept="video/*,image/*,audio/*" onChange={event => event.target.files && void onFiles(event.target.files)}/></label><select aria-label="Editing template" onChange={event => event.target.value && setText(templatePrompts[event.target.value] || "")} defaultValue=""><option value="">Choose template</option><option value="talking">Talking Head</option><option value="reel">Instagram Reel</option><option value="localize">Video Localization</option><option value="product">Product Commercial</option></select>{hasSpeech ? <button className={`eg-tool-button ${listening ? "active" : ""}`} onClick={onListen} aria-label="Use voice input">Mic</button> : null}</div><button className="eg-send" onClick={() => void onSend()} disabled={busy || (!text.trim() && !files.length)} aria-label="Send request">{busy ? <i/> : "↑"}</button></div>
  </div><small className="eg-composer-note">EditorGPT can make mistakes. Review important details before exporting.</small></div>;
}

function ActivityItem({ event }: { event: StudioEvent }) {
  const failed = event.type === "tool.failed";
  const stage = String(event.data.stage || "").toLocaleLowerCase();
  const message = String(event.data.message || "");
  const normalizedMessage = message.toLocaleLowerCase().replace(/[._-]+/g, " ");
  const label = stageLabels[stage] || stageLabels[normalizedMessage] || eventLabels[event.type] || "Working on your edit";
  return <details className={failed ? "failed" : ""}><summary><i/><span>{label}</span>{typeof event.data.progress === "number" ? <small>{event.data.progress}%</small> : null}</summary><div><span>{new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(Date.parse(event.created_at))}</span>{event.data.message && event.data.message !== label ? <p>{String(event.data.message)}</p> : null}</div></details>;
}

function Preview({ project, conversation, sourceAttachment, onCancel }: { project?: StudioProject; conversation: StudioConversation | null; sourceAttachment?: string; onCancel: () => void }) {
  const output = projectOutput(project);
  if (!project) return <div className="eg-empty-workspace"><span className="eg-mark"><Icon name="spark"/></span><h2>Your preview will appear here</h2><p>Start in Chat by describing an edit or uploading media.</p></div>;
  const progress = project.state?.last_observed?.progress;
  return <div className="eg-preview-panel"><header><div><span className="eg-eyebrow">Preview</span><h2>{project.title}</h2></div><span className={`eg-status ${project.status === "done" ? "ready" : project.status === "error" ? "failed" : "working"}`}><i/>{statusLabel(project.status)}</span></header>
    <div className="eg-player">{output ? <AuthenticatedMedia as="video" controls src={api.studioOutputUrl(project.id)}/> : sourceAttachment && conversation ? <AuthenticatedMedia as="video" controls src={api.studioAttachmentUrl(conversation.id, sourceAttachment)}/> : <div className="eg-player-placeholder"><Icon name="spark" size={28}/><span>{stageLabels[project.state?.last_observed?.stage] || "Preparing preview"}</span></div>}</div>
    {typeof progress === "number" && project.status === "running" ? <div className="eg-render-progress"><span><b>{stageLabels[project.state?.last_observed?.stage] || "Working"}</b><small>{progress}%</small></span><i><b style={{ width: `${progress}%` }}/></i></div> : null}
    <div className="eg-preview-meta"><span>Version {project.current_version}</span><span>{output ? "Final quality" : "Source preview"}</span></div>
    <div className="eg-preview-actions">{output ? <button onClick={() => void api.downloadAuthenticated(api.studioOutputUrl(project.id), `${project.title}.mp4`)}>Download video</button> : null}{project.status === "running" ? <button className="secondary" onClick={onCancel}>Cancel</button> : null}</div>
  </div>;
}

function EditWorkspace({ project, onSaved }: { project?: StudioProject; onSaved: () => void }) {
  if (!project) return <div className="eg-empty-workspace"><Icon name="advanced" size={28}/><h2>Nothing to edit yet</h2><p>Once EditorGPT creates a project, relevant controls will appear here.</p></div>;
  const advanced = project.engine === "talking" ? `/talking?job=${project.external_ref}` : project.engine === "localize" ? `/localize?project=${project.external_ref}` : project.external_ref ? `/jobs/${project.external_ref}/render` : "";
  return <div className="eg-edit-panel"><header><span className="eg-eyebrow">Edit</span><h2>Refine this video</h2><p>Use Chat for caption, pacing, color and audio requests. Controls appear here only when the current engine supports them.</p></header>{project.state?.storyboard?.scenes?.length ? <StoryboardEditor project={project} onSaved={onSaved}/> : null}<div className="eg-edit-tools">{advanced ? <NavLink to={advanced}><Icon name="advanced"/><span><b>Advanced editor</b><small>Timeline, audio and detailed controls</small></span><Icon name="chevron" size={17}/></NavLink> : <p className="eg-empty-note">Ask for a change in Chat and a new version will be created without overwriting this one.</p>}</div></div>;
}

function StoryboardEditor({ project, onSaved }: { project: StudioProject; onSaved: () => void }) {
  const [scenes, setScenes] = React.useState<any[]>(project.state.storyboard.scenes || []);
  const [saving, setSaving] = React.useState(false);
  React.useEffect(() => setScenes(project.state.storyboard.scenes || []), [project.id, project.current_version, project.state.storyboard]);
  const update = (index: number, patch: any) => setScenes(value => value.map((scene, itemIndex) => itemIndex === index ? { ...scene, ...patch } : scene));
  async function save() { setSaving(true); try { await api.updateStudioStoryboard(project.id, scenes); onSaved(); } finally { setSaving(false); } }
  return <section className="eg-storyboard"><div className="eg-section-title"><div><h3>Storyboard</h3><p>Adjust on-screen text, narration and scene length.</p></div><button className="secondary" disabled={saving} onClick={() => void save()}>{saving ? "Saving…" : "Save changes"}</button></div>{scenes.map((scene, index) => <details className="eg-scene" key={scene.index ?? index}><summary><span>{index + 1}</span><b>{scene.text_overlay || `Scene ${index + 1}`}</b><small>{scene.duration_s}s</small></summary><div><label>On-screen text<input value={scene.text_overlay || ""} onChange={event => update(index, { text_overlay: event.target.value })}/></label><label>Narration<textarea value={scene.narration_text || ""} onChange={event => update(index, { narration_text: event.target.value })}/></label><label>Duration<input type="number" min="0.5" max="30" step="0.5" value={scene.duration_s} onChange={event => update(index, { duration_s: Number(event.target.value) })}/></label></div></details>)}</section>;
}
