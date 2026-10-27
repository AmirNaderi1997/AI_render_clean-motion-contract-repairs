import React from "react";
import { api, type StudioProject } from "../api";
import { ResourceEffectEditor } from "../ResourceEffectEditor";
import { friendlyError } from "../ui";
import { EditCard } from "./EditCard";

/** EditPlan resources belong to motion jobs, not Talking/Localize plan schemas. */
export function CreativeResources({ project, onSaved, disabled = false }: {
  project: StudioProject; onSaved: () => void | Promise<unknown>; disabled?: boolean;
}) {
  const [plan, setPlan] = React.useState<any>(null);
  const [error, setError] = React.useState("");
  const [retry, setRetry] = React.useState(0);
  const [busy, setBusy] = React.useState(false);
  const supported = project.engine === "motion" && Boolean(project.external_ref);
  React.useEffect(() => {
    if (!supported || !project.external_ref) return;
    const controller = new AbortController();
    setError("");
    api.planCreativeResources(project.external_ref, controller.signal).then(context => {
      if (!controller.signal.aborted) setPlan(context.plan);
    }).catch(error => {
      if (!controller.signal.aborted) setError(friendlyError(error, "load creative resources"));
    });
    return () => controller.abort();
  }, [supported, project.external_ref, project.updated_at, retry]);
  if (!supported) return null;
  if (!plan) return <EditCard title="افکت از کتابخانهٔ مشترک" summary={error ? "خواندن برنامه انجام نشد" : "در حال خواندن برنامه…"}>
    {error ? <><p role="alert">{error}</p><button type="button" className="btn" onClick={() => setRetry(n => n + 1)}>تلاش دوباره</button></>
      : <p role="status">در حال خواندن برنامهٔ ذخیره‌شدهٔ همین پروژه…</p>}
  </EditCard>;
  return <>{error && <p role="alert">{error}</p>}<ResourceEffectEditor key={project.external_ref} jobId={project.external_ref!} plan={plan}
    savedPlanText={JSON.stringify(plan)} dirty={false}
    disabled={disabled || busy || ["running", "rendering", "queued"].includes(project.status)}
    onBusyChange={setBusy} onApplied={next => {
      setPlan(next);
      void Promise.resolve().then(onSaved).catch(error => setError(friendlyError(error, "refresh project")));
    }}/></>;
}
