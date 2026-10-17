import React from "react";
import { useSearchParams } from "react-router-dom";
import { AuthenticatedMedia } from "./AuthenticatedMedia";
import { api, MotionRecipe, ProductReelState, ProductScene } from "./api";
import { EmptyState, LoadingState, friendlyError } from "./ui";

export default function ProductReels() {
  const [params, setParams] = useSearchParams();
  const [url, setUrl] = React.useState("");
  const [jobId, setJobId] = React.useState(params.get("project") || "");
  const [state, setState] = React.useState<ProductReelState | null>(null);
  const [recipes, setRecipes] = React.useState<MotionRecipe[]>([]);
  const [recent, setRecent] = React.useState<any[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  React.useEffect(() => {
    void Promise.all([api.motionRecipes(), api.listProductReels()]).then(([r, list]) => { setRecipes(r); setRecent(list); });
  }, []);
  React.useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    const tick = async () => {
      try {
        const next = await api.productReel(jobId); if (!stopped) setState(next);
      } catch (e) { if (!stopped) setError(friendlyError(e, "load product reel")); }
    };
    void tick(); const timer = window.setInterval(tick, state?.status === "rendering" ? 2000 : 3500);
    return () => { stopped = true; window.clearInterval(timer); };
  }, [jobId, state?.status]);

  async function create() {
    if (!url.trim()) { setError("آدرس لندینگ محصول را وارد کنید."); return; }
    setBusy(true); setError("");
    try {
      const result = await api.createProductReel(url.trim()); setJobId(result.job_id); setState(result);
      setParams({ project: result.job_id });
    } catch (e) { setError(friendlyError(e, "analyze landing page")); }
    finally { setBusy(false); }
  }
  function patchScene(index: number, patch: Partial<ProductScene>) {
    if (!state?.storyboard) return;
    const scenes = state.storyboard.scenes.map((scene, i) => i === index ? { ...scene, ...patch } : scene);
    setState({ ...state, storyboard: { ...state.storyboard, scenes } });
  }
  function move(index: number, direction: -1 | 1) {
    if (!state?.storyboard) return; const target = index + direction;
    if (target < 0 || target >= state.storyboard.scenes.length) return;
    const scenes = [...state.storyboard.scenes]; [scenes[index], scenes[target]] = [scenes[target], scenes[index]];
    setState({ ...state, storyboard: { ...state.storyboard, scenes } });
  }
  async function saveAndRender() {
    if (!jobId || !state?.storyboard) return; setBusy(true); setError("");
    try { await api.updateProductReel(jobId, state.storyboard.scenes); setState(await api.renderProductReel(jobId)); }
    catch (e) { setError(friendlyError(e, "render product reel")); } finally { setBusy(false); }
  }

  return <div className="product-reels-page" dir="rtl">
    <h1>ریلز موشن محصول</h1>
    <p className="muted">آدرس لندینگ را بدهید؛ سیستم محتوای واقعی صفحه را تحلیل می‌کند، استوری‌برد قابل ویرایش می‌سازد و بدون ویدیوی ورودی خروجی می‌گیرد.</p>
    <div className="card product-url-card">
      <label>آدرس لندینگ محصول</label>
      <div className="product-url-row" dir="ltr"><input type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://product.example.com" />
        <button onClick={create} disabled={busy}>{busy ? "در حال شروع…" : "تحلیل و ساخت استوری‌برد"}</button></div>
      <small className="muted">فقط اطلاعات عمومی صفحه خوانده می‌شود؛ ادعا یا قابلیت جدید ساخته نمی‌شود.</small>
    </div>
    {error && <div className="errors" role="alert">{error}</div>}
    {!jobId && recent.length > 0 && <div className="card"><h2>پروژه‌های اخیر</h2><div className="jobs-list">
      {recent.map(item => <button className="job-item" key={item.job_id} onClick={() => { setJobId(item.job_id); setParams({ project: item.job_id }); }}>
        <span className="job-thumb job-thumb-placeholder">◆</span><span className="job-meta">{item.name}</span><span className="status-badge">{item.status}</span>
      </button>)}</div></div>}
    {state && ["analyzing", "rendering"].includes(state.status) && <LoadingState label={`${state.stage} — ${state.progress}%`} rows={3} />}
    {state?.source && <div className="card product-source"><div><span className="muted">محصول</span><h2>{state.source.name || state.source.title}</h2><p>{state.source.description}</p></div>
      <div className="brand-swatches">{(state.source.colours || []).map(c => <i key={c} title={c} style={{ background: c }} />)}</div></div>}
    {state?.storyboard && <>
      <div className="section-header"><div><h2>استوری‌برد قبل از رندر</h2><p className="muted">متن، زمان، ترتیب و نوع موشن هر صحنه را تغییر دهید.</p></div><strong>{state.storyboard.scenes.reduce((n, s) => n + s.duration, 0).toFixed(1)}s</strong></div>
      <div className="product-scenes">{state.storyboard.scenes.map((scene, index) => {
        const selected = recipes.find(r => r.id === scene.recipe);
        return <article className="card product-scene" key={scene.id}>
          <header><b>{String(index + 1).padStart(2, "0")}</b><span>{scene.role}</span><div><button className="secondary" onClick={() => move(index, -1)} disabled={!index}>↑</button><button className="secondary" onClick={() => move(index, 1)} disabled={index === state.storyboard!.scenes.length - 1}>↓</button></div></header>
          <label>متن اصلی<input value={scene.title} onChange={e => patchScene(index, { title: e.target.value })} /></label>
          <label>جزئیات کوتاه<input value={scene.items.join(" | ")} onChange={e => patchScene(index, { items: e.target.value.split("|").map(v => v.trim()).filter(Boolean).slice(0, 4) })} /></label>
          <div className="grid2"><label>موشن<select value={scene.recipe} onChange={e => patchScene(index, { recipe: e.target.value })}>{recipes.map(recipe => <option value={recipe.id} key={recipe.id}>{recipe.title}</option>)}</select></label>
            <label>مدت<input type="number" min="2.2" max="5" step="0.1" value={scene.duration} onChange={e => patchScene(index, { duration: Number(e.target.value) })} /></label></div>
          {selected && <p className="recipe-help"><strong>مناسب:</strong> {selected.best_for}<br /><span><strong>نامناسب:</strong> {selected.avoid_when}</span></p>}
        </article>;
      })}</div>
      <div className="action-bar"><button onClick={saveAndRender} disabled={busy || state.status === "rendering"}>{busy ? "در حال ذخیره…" : "ذخیره و رندر"}</button>
        {state.status === "rendering" && <button className="danger" onClick={() => jobId && api.cancelProductReel(jobId).then(setState)}>لغو</button>}</div>
    </>}
    {state?.status === "done" && state.output && jobId && <div className="card product-output"><h2>خروجی آماده است</h2><AuthenticatedMedia as="video" controls playsInline src={api.productReelOutputUrl(jobId)} /></div>}
    {!state && jobId && <EmptyState icon="◆" title="پروژه پیدا نشد" description="صفحه را دوباره بارگذاری کنید." />}
  </div>;
}
