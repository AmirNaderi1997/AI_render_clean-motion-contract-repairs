import React from "react";
import { NavLink } from "react-router-dom";
import { api, LocalizeSummary, StudioConversation, TalkingReelSummary } from "./api";
import { useJobCache } from "./JobCache";
import { AuthenticatedMedia } from "./AuthenticatedMedia";
import { Icon } from "./EditorShell";
import { EmptyState, LoadingState, friendlyError } from "./ui";

type ProjectView = {
  key: string; title: string; type: string; status: string; statusLabel: string;
  progress?: number; updated: number; to: string; thumbnail?: string;
};

function humanStatus(status: string) {
  const value = status.toLowerCase();
  if (["done", "ready", "completed"].includes(value)) return ["Ready", "ready"] as const;
  if (["error", "failed"].includes(value)) return ["Failed", "failed"] as const;
  if (["paused", "awaiting_confirmation", "awaiting_input"].includes(value)) return ["Needs attention", "attention"] as const;
  if (value === "rendering") return ["Rendering", "working"] as const;
  if (["running", "processing", "generating", "analyzing", "queued", "transcribing"].includes(value)) return ["Editing", "working"] as const;
  return ["Draft", "draft"] as const;
}

export default function Projects() {
  const { jobs, loading, error, refetch } = useJobCache();
  const [conversations, setConversations] = React.useState<StudioConversation[]>([]);
  const [localize, setLocalize] = React.useState<LocalizeSummary[]>([]);
  const [talking, setTalking] = React.useState<TalkingReelSummary[]>([]);
  const [secondaryError, setSecondaryError] = React.useState<unknown>(null);
  const [query, setQuery] = React.useState("");
  const [filter, setFilter] = React.useState("all");
  const [sort, setSort] = React.useState("recent");

  const loadSources = React.useCallback(async () => {
    const results = await Promise.allSettled([api.listStudioConversations(), api.listLocalize(), api.listTalkingReels()]);
    if (results[0].status === "fulfilled") setConversations(results[0].value);
    if (results[1].status === "fulfilled") setLocalize(results[1].value);
    if (results[2].status === "fulfilled") setTalking(results[2].value);
    const rejected = results.find(item => item.status === "rejected");
    setSecondaryError(rejected?.status === "rejected" ? rejected.reason : null);
  }, []);

  React.useEffect(() => { void refetch(); void loadSources(); }, [refetch, loadSources]);

  const projects = React.useMemo(() => {
    const items: ProjectView[] = [];
    const linkedRefs = new Set<string>();
    for (const conversation of conversations) {
      const project = conversation.projects?.find(item => item.id === conversation.state?.current_project_id) || conversation.projects?.[conversation.projects.length - 1];
      if (project?.external_ref) linkedRefs.add(project.external_ref);
      const [statusLabel, status] = humanStatus(project?.status || "draft");
      items.push({ key: `studio-${conversation.id}`, title: conversation.title || "Untitled edit", type: project?.engine === "localize" ? "Localization" : project?.engine === "talking" ? "Talking Head" : project?.engine === "motion" ? "Motion video" : "AI edit", status, statusLabel, progress: project?.state?.last_observed?.progress, updated: Date.parse(conversation.updated_at), to: `/studio/${conversation.id}` });
    }
    const talkingIds = new Set(talking.map(item => item.job_id));
    for (const item of talking) if (!linkedRefs.has(item.job_id)) {
      const [statusLabel, status] = humanStatus(item.status);
      items.push({ key: `talking-${item.job_id}`, title: item.name || item.hook || "Talking-head video", type: "Talking Head", status, statusLabel, updated: item.updated_at * 1000, to: `/talking?job=${item.job_id}` });
    }
    for (const item of localize) if (!linkedRefs.has(item.id)) {
      const [statusLabel, status] = humanStatus(item.status);
      items.push({ key: `localize-${item.id}`, title: item.title || item.name || "Localized video", type: "Localization", status, statusLabel, progress: item.progress, updated: (item.updated_at || item.created_at || 0) * 1000, to: `/localize?project=${item.id}` });
    }
    for (const job of jobs) if (!linkedRefs.has(job.id) && !talkingIds.has(job.id)) {
      const active = job.render.status !== "idle" ? job.render.status : job.generate.status;
      const [statusLabel, status] = humanStatus(active);
      items.push({ key: `job-${job.id}`, title: job.raw_name || job.plan?.title || "Video edit", type: job.plan?.content_type === "reel" ? "Social video" : "Video edit", status, statusLabel, progress: job.render.status === "running" ? job.render.progress : undefined, updated: 0, to: `/jobs/${job.id}`, thumbnail: job.render.status === "done" && job.render.output ? api.exportUrl(job.id, job.render.output.replace(/\.mp4$/, "_poster.jpg")) : undefined });
    }
    const normalized = query.trim().toLocaleLowerCase();
    return items.filter(item => (!normalized || `${item.title} ${item.type}`.toLocaleLowerCase().includes(normalized)) && (filter === "all" || item.status === filter)).sort((a, b) => sort === "oldest" ? a.updated - b.updated : b.updated - a.updated);
  }, [conversations, localize, talking, jobs, query, filter, sort]);

  const hasAnything = conversations.length + localize.length + talking.length + jobs.length > 0;
  return <div className="eg-page eg-projects-page">
    <header className="eg-page-header eg-page-header-row"><div><span className="eg-eyebrow">Your work</span><h1>Projects</h1><p>Continue an edit, review progress or download a finished video.</p></div><NavLink className="eg-primary-link" to="/studio"><Icon name="spark" size={18}/>New edit</NavLink></header>
    <div className="eg-project-toolbar"><label className="eg-search-field"><span className="sr-only">Search projects</span><input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search projects"/></label><select value={filter} onChange={event => setFilter(event.target.value)} aria-label="Filter projects"><option value="all">All statuses</option><option value="ready">Ready</option><option value="working">In progress</option><option value="attention">Needs attention</option><option value="failed">Failed</option><option value="draft">Draft</option></select><select value={sort} onChange={event => setSort(event.target.value)} aria-label="Sort projects"><option value="recent">Recently updated</option><option value="oldest">Oldest first</option></select></div>
    {(loading && !hasAnything) ? <LoadingState label="Loading your projects…"/> : (error && !hasAnything) ? <div className="errors">{friendlyError(error, "load projects")}</div> : !hasAnything ? <EmptyState icon="" title="No projects yet" description="Start with a prompt, then add a video, image, audio file or product link." action={<NavLink className="eg-primary-link" to="/studio">Start your first edit</NavLink>}/> : projects.length === 0 ? <EmptyState icon="" title="No matching projects" description="Try a different search or status." action={<button className="secondary" onClick={() => { setQuery(""); setFilter("all"); }}>Clear filters</button>}/> : <div className="eg-project-grid">{projects.map(project => <NavLink to={project.to} className="eg-project-card" key={project.key}>
      <span className="eg-project-thumb">{project.thumbnail ? <AuthenticatedMedia as="img" src={project.thumbnail} alt="" loading="lazy"/> : <Icon name="projects" size={25}/>}</span>
      <span className="eg-project-card-body"><span className="eg-project-card-top"><small>{project.type}</small><span className={`eg-status ${project.status}`}><i/>{project.statusLabel}</span></span><b>{project.title}</b>{typeof project.progress === "number" && project.status === "working" ? <span className="eg-progress"><i style={{ width: `${project.progress}%` }}/><small>{project.progress}%</small></span> : null}<small className="eg-updated">{project.updated ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(project.updated) : "Legacy project"}</small></span><Icon name="chevron" size={18}/>
    </NavLink>)}</div>}
    {(error || secondaryError) && hasAnything ? <p className="eg-inline-warning">Some project sources could not refresh. <button onClick={() => { void refetch(); void loadSources(); }}>Try again</button></p> : null}
  </div>;
}
