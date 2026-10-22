import React from "react";
import { NavLink } from "react-router-dom";
import { api, StudioConversation, StudioProject } from "../api";
import { AuthenticatedMedia } from "../AuthenticatedMedia";
import { Icon } from "../components/Icon";
import { displayTitle } from "../format";
import { renderView } from "./model";
import {MotionScenes} from './MotionScenes';
import { PlanReview } from "./PlanReview";
import { currentVersion, planPhase } from "./plan";
import { TimelineView } from "./TimelineView";
import { ProgressNotice, useProgressAge } from './ProgressNotice';

export type WorkspaceTab = "preview" | "edit";

/** Talking projects carry a Creative Plan, shown at the top of the Edit tab as soon as one is being built. */
export function hasPlan(project?: StudioProject): boolean {
  return project?.engine === "talking" && planPhase(project) !== "none";
}

export function statusMeta(project?: StudioProject): { label: string; tone: "success" | "error" | "warning" | "working" | "neutral" } {
  const status = project?.status || "";
  if (["done", "ready"].includes(status)) return { label: "Ready", tone: "success" };
  if (["error", "failed"].includes(status)) return { label: "Needs attention", tone: "error" };
  if (["awaiting_confirmation", "awaiting_input", "paused"].includes(status)) return { label: "Waiting for you", tone: "warning" };
  if (["running", "rendering", "queued"].includes(status)) return { label: "Working", tone: "working" };
  return { label: "Draft", tone: "neutral" };
}

export function projectOutputUrl(project?: StudioProject) {
  const candidate = project?.state?.candidate_output;
  const output = candidate || project?.state?.last_observed?.output;
  return output && project ? `${api.studioOutputUrl(project.id)}?candidate=${Boolean(candidate)}&version=${encodeURIComponent(output)}` : undefined;
}

function Empty({ icon, title, text }: { icon: "spark" | "advanced"; title: string; text: string }) {
  return <div className="ws-empty"><span className="empty-icon"><Icon name={icon} size={24}/></span><h2>{title}</h2><p>{text}</p></div>;
}

function PreviewPane({ project, conversation, sourceAttachment, onCancel }: { project?: StudioProject; conversation: StudioConversation | null; sourceAttachment?: string; onCancel: () => void }) {
  const phase = renderView(project);
  const rendering = ['queued','rendering','finalizing'].includes(phase.phase);
  const progressAge = useProgressAge(rendering, phase.progress, phase.stageLabel);
  const [versions, setVersions] = React.useState<{file: string; version: number}[]>([]);
  const [selected, setSelected] = React.useState<string | null>(null);
  React.useEffect(() => {
    let active = true;
    setSelected(null);
    setVersions([]);
    if (project) void api.studioOutputs(project.id).then(items => { if (active) setVersions(items); }).catch(() => {});
    return () => { active = false; };
  }, [project?.id, project?.state?.candidate_output, project?.state?.last_observed?.output]);
  if (!project) return <Empty icon="spark" title="Your preview will appear here" text="Describe an edit or add media in the chat. The video shows up here as soon as there is something to watch."/>;
  const selectedFile = selected || versions[versions.length - 1]?.file;
  const output = selectedFile ? `${api.studioOutputUrl(project.id)}?file=${encodeURIComponent(selectedFile)}` : projectOutputUrl(project);
  const view = renderView(project);
  const source = sourceAttachment && conversation ? api.studioAttachmentUrl(conversation.id, sourceAttachment) : undefined;
  const meta = statusMeta(project);
  const version = String(project.state?.last_observed?.output || "").match(/\/v(\d+)(?:_preview)?\.mp4(?:$|\?)/)?.[1] || project.current_version;
  const busy = view.phase === "queued" || view.phase === "rendering" || view.phase === "finalizing";
  return <div className="ws-preview">
    {versions.length ? <div className="ws-actions" role="group" aria-label="نسخه‌های خروجی">{versions.map(item => <button key={item.file} className="btn btn-sm btn-secondary" aria-pressed={selectedFile === item.file} onClick={() => setSelected(item.file)}>نسخهٔ {item.version}</button>)}</div> : null}
    <div className="ws-player">
      {output ? <AuthenticatedMedia as="video" controls playsInline preload="metadata" src={output}/>
        : source ? <AuthenticatedMedia as="video" controls playsInline preload="metadata" src={source}/>
        : <div className="ws-placeholder"><span className="spinner"/><span>{view.stageLabel || "Preparing preview"}</span></div>}
    </div>
    {busy ? <div className="rc-progress">
      <ProgressNotice seconds={progressAge}/>
      <div className="meter" data-indeterminate={typeof view.progress === "number" && progressAge < 30 ? undefined : ""} style={{ ["--value" as string]: `${view.progress ?? 0}%` }} role="progressbar" aria-label="Render progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressAge < 30 ? view.progress : undefined}><span/></div>
      <div className="rc-meta"><span>{view.stageLabel}</span>{typeof view.progress === "number" ? <span>{progressAge >= 30 ? 'آخرین گزارش: ' : ''}{view.progress}%</span> : null}</div>
    </div> : null}
    <div className="ws-meta">
      <span>Version {versions.find(item => item.file === selectedFile)?.version || version}</span>
      <span>{output ? (project.state?.candidate_output && project.state?.creative_review?.status !== 'passed' ? 'Rendered · needs quality review' : 'Final quality') : 'Original upload'}</span>
    </div>
    <div className="ws-actions">
      {output ? <button className="btn btn-sm" onClick={() => void api.downloadAuthenticated(output, `${project.title || "video"}.mp4`)}><Icon name="download" size={15}/>Download video</button> : null}
      {project.status === "running" ? <button className="btn btn-sm btn-secondary" onClick={onCancel}>Cancel</button> : null}
    </div>
  </div>;
}

function StoryboardEditor({ project, onSaved }: { project: StudioProject; onSaved: () => void }) {
  const [scenes, setScenes] = React.useState<any[]>(project.state.storyboard.scenes || []);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState("");
  const [saved, setSaved] = React.useState(false);
  React.useEffect(() => setScenes(project.state.storyboard.scenes || []), [project.id, project.current_version, project.state.storyboard]);
  const update = (index: number, patch: any) => { setSaved(false); setScenes(value => value.map((scene, i) => i === index ? { ...scene, ...patch } : scene)); };
  async function save() {
    setSaving(true); setError("");
    try { await api.updateStudioStoryboard(project.id, scenes); setSaved(true); onSaved(); }
    catch { setError("We could not save the storyboard. Please try again."); }
    finally { setSaving(false); }
  }
  return <section className="sb">
    <header className="sb-head2"><div><h3>Storyboard</h3><p>Adjust on-screen text, narration and scene length.</p></div>
      <button className="btn btn-sm" disabled={saving} onClick={() => void save()}>{saving ? "Saving…" : saved ? "Saved" : "Save changes"}</button></header>
    {error ? <div className="notice" data-tone="error" role="alert">{error}</div> : null}
    {scenes.map((scene, index) => <details className="scene" key={scene.index ?? index}>
      <summary><span className="scene-n">{index + 1}</span><b className="wrap-safe bidi" dir="auto">{scene.text_overlay || `Scene ${index + 1}`}</b><small>{scene.duration_s}s</small><Icon name="chevronDown" size={16} className="scene-chev"/></summary>
      <div className="scene-body">
        <div className="field"><label htmlFor={`s-engine-${index}`}>Motion tool</label><select id={`s-engine-${index}`} className="input" value={scene.motion_engine || 'default'} onChange={event=>update(index,{motion_engine:event.target.value})}><option value="default">Existing engine</option><option value="motion_so">Motion.so · uses account credits</option></select></div>
        {scene.motion_engine==='motion_so' ? <><p className="eg-muted">Silent motion clip. Captions and narration stay in EditorGPT. References are sent to Motion only after approval. Exact credit cost is unknown; no automatic retry.</p><div className="field"><label htmlFor={`s-visual-${index}`}>Visual direction</label><textarea id={`s-visual-${index}`} className="input" value={scene.media_prompt || scene.description || ''} onChange={event=>update(index,{media_prompt:event.target.value})}/></div><div className="field"><label htmlFor={`s-effort-${index}`}>Motion effort</label><select id={`s-effort-${index}`} className="input" value={scene.motion_effort || 'light'} onChange={event=>update(index,{motion_effort:event.target.value})}>{['light','medium','high'].map(e=><option key={e} value={e}>{e}</option>)}</select></div><div className="field"><label htmlFor={`s-bg-${index}`}>Solid background</label><input id={`s-bg-${index}`} type="color" value={scene.motion_background || '#101010'} onChange={event=>update(index,{motion_background:event.target.value})}/></div></> : null}
        <div className="field"><label htmlFor={`s-text-${index}`}>On-screen text</label><input id={`s-text-${index}`} className="input bidi" dir="auto" value={scene.text_overlay || ""} onChange={event => update(index, { text_overlay: event.target.value })}/></div>
        <div className="field"><label htmlFor={`s-nar-${index}`}>Narration</label><textarea id={`s-nar-${index}`} className="input bidi" dir="auto" rows={3} value={scene.narration_text || ""} onChange={event => update(index, { narration_text: event.target.value })}/></div>
        <div className="field"><label htmlFor={`s-dur-${index}`}>Duration (seconds)</label><input id={`s-dur-${index}`} className="input" type="number" min="0.5" max="30" step="0.5" value={scene.duration_s} onChange={event => update(index, { duration_s: Number(event.target.value) })}/></div>
      </div>
    </details>)}
  </section>;
}

/** The existing specialist editor for this project, where failed runs can be re-analyzed. */
export function advancedEditorUrl(project?: StudioProject): string {
  if (!project) return "";
  return project.engine === "talking" ? `/talking?job=${project.external_ref}` : project.engine === "localize" ? `/localize?project=${project.external_ref}` : project.external_ref ? `/jobs/${project.external_ref}/render` : "";
}

function EditPane({ project, onSaved }: { project?: StudioProject; onSaved: () => void }) {
  const [view, setView] = React.useState<"plan" | "timeline">("plan");
  if (!project) return <Empty icon="advanced" title="Nothing to edit yet" text="Once EditorGPT creates a project, the controls that apply to it appear here."/>;
  const advanced = advancedEditorUrl(project);
  // The timeline exists once a plan does: it is built from the same analysis the plan describes.
  const timeline = hasPlan(project) && Boolean(currentVersion(project));
  const shown = timeline ? view : "plan";
  return <div className="ws-edit">
    {timeline ? <div className="segmented ws-edit-views" role="group" aria-label="نمای ویرایش" dir="rtl">
      <button type="button" aria-pressed={shown === "plan"} onClick={() => setView("plan")}>برنامه</button>
      <button type="button" aria-pressed={shown === "timeline"} onClick={() => setView("timeline")}>تایم‌لاین</button>
    </div> : null}
    {shown === "timeline" ? <TimelineView project={project} onChanged={onSaved}/>
      : hasPlan(project) ? <PlanReview project={project} onChanged={onSaved}/>
      : <header><h2>Refine this video</h2><p>Ask for caption, pacing, colour or audio changes in the chat. Controls appear here when the current engine supports them.</p></header>}
    {project.state?.storyboard?.scenes?.length ? <StoryboardEditor project={project} onSaved={onSaved}/> : null}
    {project.external_ref && project.engine!=='localize' ? <MotionScenes jobId={project.external_ref} onSaved={onSaved}/> : null}
    {advanced
      ? <NavLink className="adv-link" to={advanced}><Icon name="advanced" size={20}/><span><b>Advanced editor</b><small>Timeline, audio and detailed controls</small></span><Icon name="chevron" size={18}/></NavLink>
      : <p className="ws-hint">Ask for a change in the chat and a new version is created without overwriting this one.</p>}
  </div>;
}

export function Workspace({ conversation, project, projects, onSelectProject, tab, onTab, sourceAttachment, onCancel, onSaved, onCollapse, showTabs, panelRef }: {
  conversation: StudioConversation | null; project?: StudioProject; projects: StudioProject[]; onSelectProject: (id: string) => void;
  tab: WorkspaceTab; onTab: (tab: WorkspaceTab) => void; sourceAttachment?: string; onCancel: () => void; onSaved: () => void;
  onCollapse?: () => void; showTabs: boolean; panelRef?: React.Ref<HTMLElement>;
}) {
  const meta = statusMeta(project);
  return <section className="workspace" ref={panelRef} aria-label="Video workspace">
    <header className="ws-head">
      {showTabs ? <div className="tabs-bar" role="tablist" aria-label="Workspace">
        {(["preview", "edit"] as WorkspaceTab[]).map(item => <button key={item} role="tab" id={`ws-tab-${item}`} aria-controls={`ws-panel-${item}`} aria-selected={tab === item} tabIndex={tab === item ? 0 : -1} className="tab"
          onClick={() => onTab(item)}
          onKeyDown={event => { if (event.key === "ArrowRight" || event.key === "ArrowLeft") { onTab(item === "preview" ? "edit" : "preview"); } }}>
          <Icon name={item === "preview" ? "eye" : "edit"} size={15}/>{item === "preview" ? "Preview" : "Edit"}</button>)}
      </div> : <h2 className="ws-title-solo">{tab === "preview" ? "Preview" : "Edit"}</h2>}
      <span className="grow"/>
      {projects.length > 1 ? <select className="input ws-select" aria-label="Project" value={project?.id} onChange={event => onSelectProject(event.target.value)}>{projects.map(item => <option key={item.id} value={item.id}>{displayTitle(item.title, 32)}</option>)}</select> : null}
      {onCollapse ? <button className="icon-btn" onClick={onCollapse} aria-label="Hide workspace" data-tip="Hide workspace"><Icon name="panelRight" size={19}/></button> : null}
    </header>
    {project ? <div className="ws-titlebar"><h2 className="bidi wrap-safe" dir="auto" title={project.title}>{displayTitle(project.title, 80)}</h2><span className="badge" data-tone={meta.tone === "neutral" ? undefined : meta.tone}><i/>{meta.label}</span></div> : null}
    <div className="ws-body">
      <div role="tabpanel" id="ws-panel-preview" aria-labelledby="ws-tab-preview" hidden={tab !== "preview"}><PreviewPane project={project} conversation={conversation} sourceAttachment={sourceAttachment} onCancel={onCancel}/></div>
      <div role="tabpanel" id="ws-panel-edit" aria-labelledby="ws-tab-edit" hidden={tab !== "edit"}><EditPane project={project} onSaved={onSaved}/></div>
    </div>
  </section>;
}
