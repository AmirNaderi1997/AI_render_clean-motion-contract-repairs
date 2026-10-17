import React from "react";
import { NavLink } from "react-router-dom";
import { useJobCache } from "./JobCache";
import { EmptyState, LoadingState, friendlyError } from "./ui";
import { AuthenticatedMedia } from "./AuthenticatedMedia";
import { api, type LocalizeSummary } from "./api";

export default function Jobs() {
  const { jobs, loading, error, refetch } = useJobCache();
  const [localizeJobs, setLocalizeJobs] = React.useState<LocalizeSummary[]>([]);
  const [localizeLoading, setLocalizeLoading] = React.useState(true);
  const [localizeError, setLocalizeError] = React.useState<unknown>(null);
  const [productJobs, setProductJobs] = React.useState<any[]>([]);
  const [query, setQuery] = React.useState("");
  const [search, setSearch] = React.useState("");
  React.useEffect(() => { const timer = window.setTimeout(() => setSearch(query.trim().toLocaleLowerCase()), 250); return () => window.clearTimeout(timer); }, [query]);
  const productIds = React.useMemo(() => new Set(productJobs.map(job => job.job_id)), [productJobs]);
  const visible = React.useMemo(() => jobs.filter(job => !productIds.has(job.id) && `${job.raw_name || ""} ${job.id}`.toLocaleLowerCase().includes(search)), [jobs, productIds, search]);
  const visibleLocalize = React.useMemo(() => localizeJobs.filter(job => `${job.name} ${job.title || ""} ${job.id}`.toLocaleLowerCase().includes(search)), [localizeJobs, search]);
  const visibleProducts = React.useMemo(() => productJobs.filter(job => `${job.name || ""} ${job.job_id}`.toLocaleLowerCase().includes(search)), [productJobs, search]);

  const refetchLocalize = React.useCallback(async () => {
    try {
      setLocalizeError(null);
      setLocalizeJobs(await api.listLocalize());
    } catch (nextError) {
      setLocalizeError(nextError);
    } finally {
      setLocalizeLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refetch();
    void refetchLocalize();
    void api.listProductReels().then(setProductJobs).catch(() => {});
    const handleFocus = () => { void refetch(); void refetchLocalize(); void api.listProductReels().then(setProductJobs).catch(() => {}); };
    window.addEventListener("focus", handleFocus);
    return () => window.removeEventListener("focus", handleFocus);
  }, [refetch, refetchLocalize]);

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refetchLocalize();
    }, 10000);
    return () => window.clearInterval(timer);
  }, [refetchLocalize]);

  const statusColor = (status: string) =>
    status === "done" || status === "ready" ? "done" : ["running", "queued", "analyzing", "rendering"].includes(status) ? "running" : status === "error" ? "error" : "";

  const hasJobs = jobs.length + localizeJobs.length + productJobs.length > 0;
  const isLoading = loading || localizeLoading;
  const combinedError = error || localizeError;

  return (
    <div>
      <h1>Jobs</h1>
      {hasJobs && <label className="jobs-search">Search jobs<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search by name or ID" /></label>}
      {isLoading && hasJobs && <LoadingState label="Refreshing your jobs…" rows={1} />}
      {isLoading && !hasJobs ? <LoadingState label="Loading your jobs…" /> : combinedError && !hasJobs ? (
        <div className="errors" role="alert">{friendlyError(combinedError, "load your jobs")} <button className="secondary" onClick={() => { void refetch(); void refetchLocalize(); }}>Try again</button></div>
      ) : !hasJobs ? (
        <EmptyState icon="🎬" title="No jobs yet" description="Start with a video or create content from a prompt."
          action={<NavLink className="button-link" to="/new">Create your first reel</NavLink>} />
      ) : (
        <>
          {combinedError && <div className="errors" role="alert">{friendlyError(combinedError, "refresh your jobs")} <button className="secondary" onClick={() => { void refetch(); void refetchLocalize(); }}>Try again</button></div>}
          {visible.length + visibleLocalize.length + visibleProducts.length === 0 ? <EmptyState icon="⌕" title="No matching jobs" description="Try a different name or job ID." action={<button className="secondary" onClick={() => setQuery("")}>Clear search</button>} /> : <div className="jobs-list">
            {visible.map(job => (
              <NavLink key={job.id} to={`/jobs/${job.id}`} className="job-item">
                {job.render.status === "done" && job.render.output ? <AuthenticatedMedia as="img" className="job-thumb" loading="lazy" decoding="async" alt={`Poster for ${job.raw_name || job.id}`} src={api.exportUrl(job.id, job.render.output.replace(/\.mp4$/, "_poster.jpg"))} /> : <span className="job-thumb job-thumb-placeholder" aria-hidden="true">▶</span>}
                <span className="job-id" dir="ltr">{job.id}</span>
                <span className="job-meta"><span dir="auto">{job.raw_name || "Untitled"}</span></span>
                <span className={`status-badge ${statusColor(job.render.status)}`}>{job.render.status}</span>
              </NavLink>
            ))}
            {visibleLocalize.map(job => (
              <NavLink key={`localize-${job.id}`} to={`/localize?project=${job.id}`} className="job-item">
                <span className="job-thumb job-thumb-placeholder" aria-hidden="true">🌐</span>
                <span className="job-id" dir="ltr">{job.id}</span>
                <span className="job-meta"><span dir="auto">{job.title || job.name}</span><span className="muted">Dropshipping{job.stage ? ` · ${job.stage}` : ""}</span></span>
                <span className={`status-badge ${statusColor(job.status)}`}>{job.status}{["analyzing", "rendering"].includes(job.status) && job.progress ? ` ${job.progress}%` : ""}</span>
              </NavLink>
            ))}
            {visibleProducts.map(job => (
              <NavLink key={`product-${job.job_id}`} to={`/product-reels?project=${job.job_id}`} className="job-item">
                <span className="job-thumb job-thumb-placeholder" aria-hidden="true">◆</span>
                <span className="job-id" dir="ltr">{job.job_id}</span>
                <span className="job-meta"><span dir="auto">{job.name || "Product reel"}</span><span className="muted">ریلز موشن محصول{job.stage ? ` · ${job.stage}` : ""}</span></span>
                <span className={`status-badge ${statusColor(job.status)}`}>{job.status}{["analyzing", "rendering"].includes(job.status) && job.progress ? ` ${job.progress}%` : ""}</span>
              </NavLink>
            ))}
          </div>}
        </>
      )}
    </div>
  );
}
