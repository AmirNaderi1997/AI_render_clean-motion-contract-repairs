import React from "react";
import { NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, StudioConversation, StudioEvent } from "./api";
import { useAuth } from "./auth/AuthContext";
import { Icon } from "./components/Icon";
import { useStudioLayout } from "./components/hooks";
import { useTopbarTitle } from "./components/ShellContext";
import { displayTitle, parseTime, relativeTime } from "./format";
import { friendlyError } from "./ui";
import { Composer, PendingFile } from "./studio/Composer";
import { ManualQuestion } from "./studio/ManualQuestion";
import { Thread, LocalFileInfo } from "./studio/Thread";
import { Workspace, WorkspaceTab, advancedEditorUrl } from "./studio/Workspace";
import { PendingMessage, activeStep, buildTimeline, isProcessing, renderView, thinkingLabel } from "./studio/model";
import { suggestions, templatePrompts } from "./templateData";

type MobileView = "chat" | "preview" | "edit";
const lsGet = (key: string, fallback: string) => { try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; } };
const lsSet = (key: string, value: string) => { try { localStorage.setItem(key, value); } catch { /* storage unavailable */ } };

export default function Studio() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { authenticated, openAuth } = useAuth();
  const layout = useStudioLayout();

  const [conversations, setConversations] = React.useState<StudioConversation[]>([]);
  const [conversation, setConversation] = React.useState<StudioConversation | null>(null);
  const [events, setEvents] = React.useState<StudioEvent[]>([]);
  const [text, setText] = React.useState(() => searchParams.get("prompt") || templatePrompts[searchParams.get("template") || ""] || "");
  const [files, setFiles] = React.useState<PendingFile[]>([]);
  const [sending, setSending] = React.useState(false);
  const [error, setError] = React.useState("");
  const [pending, setPending] = React.useState<PendingMessage | null>(null);
  const [localFiles, setLocalFiles] = React.useState<LocalFileInfo[]>([]);
  const [listening, setListening] = React.useState(false);
  const [manualDraft, setManualDraft] = React.useState(false);
  const [modeSaving, setModeSaving] = React.useState(false);
  const [wsTab, setWsTab] = React.useState<WorkspaceTab>("preview");
  const [desktopOpen, setDesktopOpen] = React.useState(() => lsGet("editorgpt.workspace", "open") !== "closed");
  const [overlayOpen, setOverlayOpen] = React.useState(false);
  const [mobileView, setMobileView] = React.useState<MobileView>("chat");
  const [selectedProject, setSelectedProject] = React.useState<string | null>(null);
  const [stuck, setStuck] = React.useState(true);
  const [now, setNow] = React.useState(() => Date.now());

  const scrollRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);
  const cursorRef = React.useRef(0);
  const filesRef = React.useRef<PendingFile[]>([]);
  const voiceEnabledRef = React.useRef(false);
  const legacyOpenRef = React.useRef("");
  const refreshTimerRef = React.useRef<number | null>(null);
  const listTimerRef = React.useRef<number | null>(null);
  const lastSendRef = React.useRef<{ text: string; ids: string[] } | null>(null);
  // Conversation created only so attachments have somewhere to upload; we don't navigate until the user sends.
  const draftIdRef = React.useRef<string | null>(null);
  const activeId = conversationId || null;
  const hasSpeech = typeof window !== "undefined" && Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  React.useEffect(() => { voiceEnabledRef.current = Boolean(conversation?.status_voice_enabled); }, [conversation?.status_voice_enabled]);
  React.useEffect(() => { filesRef.current = files; }, [files]);
  React.useEffect(() => { const id = window.setInterval(() => setNow(Date.now()), 15000); return () => window.clearInterval(id); }, []);

  const refreshList = React.useCallback(() => authenticated ? api.listStudioConversations().then(setConversations).catch(() => undefined) : Promise.resolve(), [authenticated]);
  const refresh = React.useCallback(async (id = activeId) => {
    if (!id) return;
    try { setConversation(await api.getStudioConversation(id)); } catch (e) { setError(friendlyError(e, "load conversation")); }
  }, [activeId]);
  React.useEffect(() => { void refreshList(); }, [refreshList]);
  React.useEffect(() => {
    setEvents([]); cursorRef.current = 0; setSelectedProject(null);
    if (authenticated && activeId) void refresh(activeId); else setConversation(null);
  }, [authenticated, activeId, refresh]);

  React.useEffect(() => {
    const legacy = searchParams.get("legacy");
    if (!legacy || !authenticated || legacyOpenRef.current === legacy) return;
    const [engine, externalRef] = legacy.split(":", 2);
    if (!externalRef || !["motion", "talking", "localize"].includes(engine)) return;
    legacyOpenRef.current = legacy;
    setSending(true);
    void api.openLegacyInStudio(engine as "motion" | "talking" | "localize", externalRef, searchParams.get("title") || "Video project")
      .then(value => { setConversation(value); navigate(`/studio/${value.id}`, { replace: true }); })
      .catch(e => setError(friendlyError(e, "open project"))).finally(() => setSending(false));
  }, [authenticated, navigate, searchParams]);

  // Live events (SSE) with cursor-based reconnect.
  React.useEffect(() => {
    if (!activeId) return;
    const controller = new AbortController(); let stopped = false;
    const connect = async () => {
      while (!stopped) {
        try {
          await api.streamStudioEvents(activeId, cursorRef.current, event => {
            cursorRef.current = Math.max(cursorRef.current, event.seq);
            setEvents(value => value.some(item => item.seq === event.seq) ? value : [...value, event]);
            if (refreshTimerRef.current != null) window.clearTimeout(refreshTimerRef.current);
            refreshTimerRef.current = window.setTimeout(() => void refresh(activeId), 180);
            if (listTimerRef.current == null) listTimerRef.current = window.setTimeout(() => {
              listTimerRef.current = null; void refreshList(); window.dispatchEvent(new Event("editorgpt:conversations-updated"));
            }, 1200);
            if (event.type === "narration.ready" && voiceEnabledRef.current) void api.authenticatedObjectUrl(api.studioEventAudioUrl(activeId, event.data.event_seq)).then(url => { const audio = new Audio(url); void audio.play().finally(() => URL.revokeObjectURL(url)); });
          }, controller.signal);
        } catch { if (!controller.signal.aborted) await new Promise(resolve => setTimeout(resolve, 1200)); }
      }
    };
    void connect();
    return () => {
      stopped = true; controller.abort();
      if (refreshTimerRef.current != null) window.clearTimeout(refreshTimerRef.current);
      if (listTimerRef.current != null) window.clearTimeout(listTimerRef.current);
      refreshTimerRef.current = null; listTimerRef.current = null;
    };
  }, [activeId, refresh, refreshList]);
  React.useEffect(() => () => filesRef.current.forEach(item => URL.revokeObjectURL(item.url)), []);

  // ── derived state ────────────────────────────────────────────
  const projects = conversation?.projects || [];
  const current = projects.find(item => item.id === (selectedProject || conversation?.state?.current_project_id)) || projects[projects.length - 1];
  const manual = conversation ? conversation.state.execution_mode === "manual" : manualDraft;
  const manualQuestion = current?.state?.manual_checkpoint || (manual ? conversation?.state?.manual_question : null);
  const toggleManual = async () => {
    if (modeSaving) return;
    if (!authenticated) { openAuth("login"); return; }
    if (!conversation) { setManualDraft(!manualDraft); return; }
    setModeSaving(true);
    try { await api.updateStudioConversation(conversation.id, { execution_mode: manual ? "auto" : "manual" }); await refresh(); }
    catch (e) { setError(friendlyError(e, "change execution mode")); }
    finally { setModeSaving(false); }
  };
  const pendingAction = (conversation?.actions || []).find(item => item.project_id === current?.id && item.status === "pending");
  const [resuming, setResuming] = React.useState(false);
  const resume = async () => {
    if (!current || resuming) return;
    const warning = 'تحلیل و دارایی‌های آماده دوباره تولید نمی‌شوند. تکمیل مراحل ناقص ممکن است هزینهٔ API داشته باشد، حتی اگر تلاش قبلی timeout شده باشد. هر تصویر و صدا جداگانه محاسبه می‌شود و هزینهٔ دقیق در دسترس نیست. برای ادامه و هر مدیای ناقص فقط یک تلاش انجام شود؟';
    if (!window.confirm(warning)) return;
    setResuming(true); setError("");
    try { await api.resumeStudioProject(current.id,true); await refresh(); }
    catch (e) { setError(friendlyError(e, "continue this project")); }
    finally { setResuming(false); }
  };
  const styles = current?.state?.styles || [];
  const sourceAttachment = current?.state?.attachment_ids?.[0];
  const messages = conversation?.messages || [];
  const lastUserMessage = [...messages].reverse().find(message => message.role === 'user');
  const processing = isProcessing({ sending, messages, events, project: current, now });
  const items = React.useMemo(() => buildTimeline({ messages, events, projects, pending, processing }), [messages, events, projects, pending, processing]);
  const step = activeStep(items);
  // A live render card is its own progress indicator; otherwise show what the assistant is doing.
  const renderLive = items.some(item => item.kind === "render" && ["queued", "rendering", "finalizing"].includes(renderView(projects.find(p => p.id === item.projectId)).phase));
  const thinking = processing && !step && !renderLive ? thinkingLabel(events, messages) : undefined;
  const showConversation = Boolean(activeId) || Boolean(pending);
  const title = conversation?.title ? displayTitle(conversation.title, 60) : "New edit";
  useTopbarTitle(showConversation ? title : "");
  const announcement = step ? `${step.label}` : thinking ? `${thinking}` : processing ? "Working" : "";
  const sourceUrl = conversation && sourceAttachment ? api.studioAttachmentUrl(conversation.id, sourceAttachment) : undefined;
  const canStop = current?.status === "running";

  // ── scrolling: stick to bottom unless the reader scrolled up ──
  const onScroll = () => { const node = scrollRef.current; if (node) setStuck(node.scrollHeight - node.scrollTop - node.clientHeight < 140); };
  React.useLayoutEffect(() => {
    const node = scrollRef.current; if (!node || !stuck) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "auto" });
  }, [items, thinking, stuck, pendingAction, mobileView]);
  const jumpToLatest = () => { setStuck(true); scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }); };

  // ── actions ──────────────────────────────────────────────────
  const requireLogin = () => openAuth("login");
  async function ensureConversation(titleText = "گفتگوی جدید", go = true) {
    if (activeId) return activeId;
    let id = draftIdRef.current;
    if (!id) { id = (await api.createStudioConversation(titleText)).id; draftIdRef.current = id; }
    if (go) { draftIdRef.current = null; navigate(`/studio/${id}`, { replace: true }); void refreshList(); }
    return id;
  }
  async function addFiles(input: FileList | File[]) {
    const list = Array.from(input); // snapshot: a live FileList can be emptied while we await
    if (!authenticated) { requireLogin(); return; }
    setError("");
    let id: string;
    try { id = await ensureConversation("New media edit", false); } catch (e) { setError(friendlyError(e, "start the conversation")); return; }
    for (const file of list.slice(0, 12)) {
      const key = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      const entry: PendingFile = { key, file, progress: 0, url: URL.createObjectURL(file) };
      setFiles(value => [...value, entry]);
      try {
        const attachment = await api.uploadStudioAttachment(id, file, progress => setFiles(value => value.map(item => item.key === key ? { ...item, progress } : item)));
        setFiles(value => value.map(item => item.key === key ? { ...item, progress: 100, attachmentId: attachment.id } : item));
      } catch (e) { setError(friendlyError(e, "upload attachment")); setFiles(value => value.filter(item => item.key !== key)); URL.revokeObjectURL(entry.url); }
    }
  }
  function removeFile(file: PendingFile) { setFiles(value => value.filter(item => item.key !== file.key)); URL.revokeObjectURL(file.url); }

  async function send(override?: string, resend?: { text: string; ids: string[] }) {
    if (!authenticated) { requireLogin(); return; }
    const source = resend?.text ?? override ?? text;
    const ids = resend?.ids ?? files.map(item => item.attachmentId!).filter(Boolean);
    const finalText = source.trim() || (ids.length ? (manualQuestion?.key === "logo_asset" ? "attached" : "این فایل را بررسی کن و برای تدوین آماده کن") : "");
    if (!finalText || sending) return;
    if (!resend && files.some(item => !item.attachmentId)) { setError("Please wait for the uploads to finish."); return; }
    // Show the message and the processing state immediately.
    setError(""); setSending(true); setStuck(true);
    if (!resend) {
      setLocalFiles(files.map(item => ({ name: item.file.name, type: item.file.type, url: item.url })));
      setFiles([]); setText("");
    }
    setPending({ id: `pending-${Date.now()}`, content: finalText, attachments: ids, createdAt: Date.now() });
    lastSendRef.current = { text: finalText, ids };
    try {
      const id = await ensureConversation(finalText.slice(0, 70));
      await api.sendStudioMessage(id, finalText, ids, { execution_mode: conversation || !activeId ? (manual ? "manual" : "auto") : undefined, manual_question_id: manualQuestion?.id });
      await refresh(id);
      setPending(null); setLocalFiles(list => { list.forEach(file => URL.revokeObjectURL(file.url)); return []; });
    } catch (e) {
      setPending(value => value ? { ...value, failed: true } : value);
      setError(friendlyError(e, "send message"));
    } finally { setSending(false); }
  }
  const retryMessage = () => { if (lastSendRef.current) void send(undefined, lastSendRef.current); };
  const stop = () => { if (current) void api.cancelStudioProject(current.id).then(() => refresh()).catch(e => setError(friendlyError(e, "cancel"))); };

  function startVoiceInput() {
    const Speech = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!Speech) return;
    const recognition = new Speech(); recognition.lang = document.documentElement.lang === "en" ? "en-US" : "fa-IR"; recognition.interimResults = true;
    recognition.onstart = () => setListening(true); recognition.onend = () => setListening(false);
    recognition.onresult = (event: any) => setText(Array.from(event.results).map((result: any) => result[0].transcript).join(" "));
    recognition.onerror = () => { setListening(false); setError("Voice input could not start. Check microphone access."); };
    recognition.start();
  }

  // ── workspace visibility per layout ──────────────────────────
  const openWorkspace = (tab: WorkspaceTab, projectId?: string) => {
    if (projectId) setSelectedProject(projectId);
    setWsTab(tab);
    if (layout === "desktop") { setDesktopOpen(true); lsSet("editorgpt.workspace", "open"); }
    else if (layout === "tablet") setOverlayOpen(true);
    else setMobileView(tab);
  };
  const closeWorkspace = () => {
    if (layout === "desktop") { setDesktopOpen(false); lsSet("editorgpt.workspace", "closed"); }
    else if (layout === "tablet") setOverlayOpen(false);
    else setMobileView("chat");
  };
  React.useEffect(() => { if (layout !== "tablet") setOverlayOpen(false); if (layout !== "mobile") setMobileView("chat"); }, [layout]);
  React.useEffect(() => {
    if (!overlayOpen || layout !== "tablet") return;
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") setOverlayOpen(false); };
    document.addEventListener("keydown", key); return () => document.removeEventListener("keydown", key);
  }, [overlayOpen, layout]);
  const editAgain = (projectId: string) => { openWorkspace("edit", projectId); };
  const wsVisible = layout === "desktop" ? desktopOpen : layout === "tablet" ? overlayOpen : mobileView !== "chat";
  const mobileTab = layout === "mobile" ? (mobileView === "chat" ? "chat" : wsTab) : null;

  const composer = (variant: "home" | "dock") => <Composer variant={variant} text={text} setText={setText} files={files} onRemoveFile={removeFile} onFiles={addFiles}
    manual={manual} onManualChange={modeSaving ? undefined : () => void toggleManual()}
    processing={processing} onStop={canStop ? stop : undefined} onSend={() => void send()} error={error} onDismissError={() => setError("")}
    hasSpeech={hasSpeech} listening={listening} onListen={startVoiceInput} textareaRef={textareaRef} autoFocus={variant === "home" && layout !== "mobile"}/>;

  if (!showConversation) return <div className="studio-home">
    <div className="home-inner">
      <h1>What would you like to create?</h1>
      {composer("home")}
      <div className="chip-row home-chips">{suggestions.map(item => <button key={item} className="chip" onClick={() => { setText(item); textareaRef.current?.focus(); }}>{item}</button>)}</div>
      {authenticated && conversations.length ? <section className="home-recent" aria-label="Recent projects">
        <div className="home-recent-head"><h2>Recent</h2><NavLink to="/projects">View all</NavLink></div>
        <ul>{[...conversations].sort((a, b) => parseTime(b.updated_at) - parseTime(a.updated_at)).slice(0, 3).map(item => <li key={item.id}><NavLink to={`/studio/${item.id}`} title={item.title}><span className="bidi wrap-safe" dir="auto">{displayTitle(item.title, 60)}</span><small>{relativeTime(parseTime(item.updated_at), now)}</small><Icon name="chevron" size={16}/></NavLink></li>)}</ul>
      </section> : null}
      {!authenticated ? <p className="home-note">Log in to save projects and start creating.</p> : null}
    </div>
  </div>;

  return <div className="studio" data-layout={layout} data-ws={wsVisible ? "open" : "closed"} data-view={mobileView}>
    <section className="chat-col" aria-label="Conversation" hidden={layout === "mobile" && mobileView !== "chat"}>
      {layout !== "mobile" ? <header className="chat-head">
        <h1 className="chat-title bidi wrap-safe" dir="auto" title={conversation?.title}>{title}</h1>
        {!wsVisible ? <button className="btn btn-sm btn-secondary" onClick={() => openWorkspace(wsTab)}><Icon name="panelRight" size={16}/>Preview</button> : null}
      </header> : null}
      <div className="chat-scroll" ref={scrollRef} onScroll={onScroll}>
        <div className="chat-inner">
          {!conversation && !pending ? <div className="thread-loading" role="status" aria-label="Loading conversation"><span className="skeleton"/><span className="skeleton"/><span className="skeleton"/></div> : null}
          <Thread items={items} conversation={conversation} projects={projects} localFiles={localFiles} thinking={thinking} sourceUrl={sourceUrl} compactRender={layout === "desktop" && desktopOpen}
            onOpenPreview={id => openWorkspace("preview", id)} onEditAgain={editAgain}
            retryHref={current?.status === "error" ? advancedEditorUrl(current) || undefined : undefined}
            onChoice={choice => void send(choice)} onRetryMessage={retryMessage}/>
          {current && (["talking", "localize"].includes(current.engine) || (current.engine === "motion" && current.state?.confirmed)) && ["error", "canceled", "paused"].includes(current.status) ? <button className="btn btn-secondary" disabled={resuming} onClick={() => void resume()}><Icon name="play" size={14}/>{resuming ? "در حال ادامه…" : "ادامه از مرحلهٔ متوقف‌شده"}</button> : null}
          {!current && !processing && !pending && lastUserMessage && messages[messages.length - 1]?.content.startsWith('عملیات متوقف شد:') ? <button className="btn btn-secondary" disabled={sending} onClick={() => {
            if (window.confirm('هنوز پروژه‌ای ساخته نشده است. درخواست اصلی با همان فایل‌ها دوباره بررسی شود؟ این کار ممکن است هزینهٔ API داشته باشد؛ تولید نهایی همچنان نیازمند تأیید برنامه است.')) void send(undefined, { text: lastUserMessage.content, ids: lastUserMessage.attachments || [] });
          }}><Icon name="play" size={14}/>تلاش مجدد درخواست</button> : null}
          {styles.length > 0 && current?.status === "awaiting_input" ? <div className="action-card"><h3>Choose a style</h3><p>How should this video feel?</p><div className="style-options">{styles.map((style: any) => <button key={style.id || style.key} onClick={() => void send(`سبک ${style.id || style.key}`)}><b className="bidi" dir="auto">{style.label || style.title || style.name}</b><small className="bidi" dir="auto">{style.description || "Talking Reel style"}</small></button>)}</div></div> : null}
          {manualQuestion ? <ManualQuestion key={manualQuestion.id} question={manualQuestion} busy={processing || sending} onAnswer={value => void send(value)}/> : null}
          {pendingAction ? <div className="action-card"><h3>Approve this plan?</h3><p>EditorGPT will create the media, voice-over and final render using the plan above.</p>{pendingAction.estimated_cost_usd != null ? <small className="muted-text">Recorded estimate: ${pendingAction.estimated_cost_usd.toFixed(4)}</small> : null}
            <div className="action-buttons"><button className="btn" onClick={() => void api.confirmStudioAction(pendingAction.id).then(() => refresh()).catch(e => setError(friendlyError(e, "approve the plan")))}>Approve and continue</button><button className="btn btn-secondary" onClick={() => void api.cancelStudioAction(pendingAction.id).then(() => refresh()).catch(e => setError(friendlyError(e, "cancel the plan")))}>Cancel</button></div></div> : null}
        </div>
      </div>
      <div className="dock">
        {!stuck ? <button className="jump-latest icon-btn" onClick={jumpToLatest} aria-label="Jump to latest"><Icon name="chevronDown" size={18}/></button> : null}
        {composer("dock")}
      </div>
      <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">{announcement}</div>
    </section>

    {layout === "tablet" && overlayOpen ? <button className="ws-backdrop" onClick={() => setOverlayOpen(false)} aria-label="Close workspace" tabIndex={-1}/> : null}
    <Workspace conversation={conversation} project={current} projects={projects} onSelectProject={setSelectedProject} tab={wsTab} onTab={setWsTab}
      sourceAttachment={sourceAttachment} onCancel={stop} onSaved={() => void refresh()} showTabs={layout !== "mobile"} onCollapse={layout === "mobile" ? undefined : closeWorkspace}/>

    {layout === "mobile" ? <nav className="studio-tabs" aria-label="Studio views">
      {([["chat", "Chat", "spark"], ["preview", "Preview", "eye"], ["edit", "Edit", "edit"]] as const).map(([id, label, icon]) => <button key={id} aria-current={mobileTab === id ? "page" : undefined}
        onClick={() => { if (id === "chat") setMobileView("chat"); else { setWsTab(id); setMobileView(id); } }}><Icon name={icon} size={20}/><span>{label}</span></button>)}
    </nav> : null}
  </div>;
}
