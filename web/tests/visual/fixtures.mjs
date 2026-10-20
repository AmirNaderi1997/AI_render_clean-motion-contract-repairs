// Test fixtures for the visual regression run. They are served ONLY by Playwright's
// network interception; the application itself never contains mock data.
const iso = (offsetSeconds) => new Date(Date.now() + offsetSeconds * 1000).toISOString();

export function makeConversation(kind) {
  const base = { id: "c1", title: "Create a video for this product, instagram reel with comprehensive hook https://store.rafiei.co/store/reza/product/5fc2befa-2765-40a6-ac74-9399eca4ea98", language: "fa", status_voice_enabled: false, state: { current_project_id: "p1" }, created_at: iso(-600), updated_at: iso(-5) };
  const user = { id: 1, role: "user", content: "Create a video for this product, instagram reel with comprehensive hook\nhttps://store.rafiei.co/store/reza/product/5fc2befa-2765-40a6-ac74-9399eca4ea98", attachments: [], created_at: iso(-120) };
  const assistant = { id: 2, role: "assistant", content: "استوری‌بورد آماده است: ۶ صحنه، حدود ۳۰ ثانیه. قبل از تولید دارایی‌ها، نریشن و رندر سنگین آن را تأیید یا اصلاح کنید.", attachments: [], created_at: iso(-100) };
  const project = (status, observed) => ({ id: "p1", conversation_id: "c1", engine: "motion", title: "4-in-1 Velvet-Feel Single Chair Bed, With Pillow - Navy Blue", status, external_ref: "job1", current_version: 1, state: { last_observed: observed, attachment_ids: [] }, created_at: iso(-110), updated_at: iso(-3) });
  if (kind === "processing") return { ...base, messages: [user], projects: [], actions: [] };
  if (kind === "rendering") return { ...base, messages: [user, assistant], projects: [project("running", { status: "running", stage: "rendering", progress: 78, output: null })], actions: [] };
  if (kind === "done") return { ...base, messages: [user, assistant, { id: 3, role: "assistant", content: "ویدیو آماده شد. می‌توانید آن را پخش یا دانلود کنید و اصلاح بعدی را همین‌جا بگویید.", attachments: [], created_at: iso(-2) }], projects: [project("done", { status: "done", stage: "", progress: 100, output: "exports/v1.mp4" })], actions: [] };
  if (kind === "approve") return { ...base, messages: [user, assistant], projects: [{ ...project("awaiting_confirmation", {}), state: { storyboard: { scenes: [{ index: 0, text_overlay: "راحتی بی‌نظیر", narration_text: "تخت‌خواب تاشو", duration_s: 4 }, { index: 1, text_overlay: "Velvet feel", narration_text: "", duration_s: 5 }] } } }], actions: [{ id: "a1", project_id: "p1", kind: "generate", status: "pending", payload: {}, estimated_cost_usd: 0.42 }] };
  return { ...base, messages: [], projects: [], actions: [] };
}

export function makeEvents(kind) {
  let seq = 0;
  const ev = (type, offset, data = {}) => ({ id: ++seq, seq, type, data, created_at: iso(offset) });
  if (kind === "processing") return [ev("message.started", -100, { message_id: 1 }), ev("agent.thinking_summary", -99, { message: "دارم درخواست و فایل‌ها را با قابلیت‌های واقعی پروژه تطبیق می‌دهم." }), ev("tool.started", -90, { tool: "inspect_url", message: "در حال خواندن محتوای واقعی صفحه و دریافت تصاویر محصول هستم." })];
  if (kind === "rendering") return [ev("message.started", -118), ev("tool.started", -110, { tool: "inspect_url", message: "در حال خواندن محتوای واقعی صفحه." }), ev("tool.completed", -105, { tool: "inspect_url", message: "صفحه بررسی شد و ۵ تصویر معتبر دریافت شد." }), ev("tool.started", -100, { tool: "create_storyboard", message: "در حال ساخت سناریو." }), ev("storyboard.ready", -95, { project_id: "p1", message: "استوری‌بورد آماده است" }), ev("tool.progress", -60, { project_id: "p1", stage: "generating assets", progress: 40, message: "در حال ساخت تصاویر" }), ev("tool.progress", -50, { project_id: "p1", stage: "generating assets", progress: 90, message: "در حال ساخت تصاویر" }), ...[88, 90, 93, 95, 96, 98].map((p, i) => ev("tool.progress", -30 + i * 4, { project_id: "p1", stage: "rendering", progress: Math.min(p, 78), message: "در حال رندر ویدیو" }))];
  if (kind === "done") return [ev("message.started", -118), ev("tool.started", -110, { tool: "create_storyboard", message: "در حال ساخت سناریو." }), ev("storyboard.ready", -95, { project_id: "p1" }), ev("tool.progress", -30, { project_id: "p1", stage: "rendering", progress: 50 }), ev("render.completed", -3, { project_id: "p1", output_url: "/api/x" })];
  return [];
}

export const projectsList = [
  { id: "c1", title: "Create a video for this product, instagram reel with comprehensive hook https://store.rafiei.co/store/reza/product/5fc2befa-2765-40a6-ac74-9399eca4ea98", language: "fa", status_voice_enabled: false, state: { current_project_id: "p1" }, created_at: iso(-86400 * 2), updated_at: iso(-3600), projects: [{ id: "p1", engine: "motion", status: "done", state: {}, title: "x", conversation_id: "c1", current_version: 1, created_at: iso(0), updated_at: iso(0) }] },
  { id: "c2", title: "فارسی‌سازی ویدیوی آموزشی محصول با دوبله و زیرنویس کامل برای فروشگاه اینستاگرام", language: "fa", status_voice_enabled: false, state: { current_project_id: "p2" }, created_at: iso(-86400), updated_at: iso(-600), projects: [{ id: "p2", engine: "localize", status: "running", state: { last_observed: { progress: 42 } }, title: "y", conversation_id: "c2", current_version: 1, created_at: iso(0), updated_at: iso(0) }] },
  { id: "c3", title: "Remove pauses and mistakes", language: "en", status_voice_enabled: false, state: {}, created_at: iso(-86400 * 9), updated_at: iso(-86400 * 8), projects: [{ id: "p3", engine: "talking", status: "error", state: {}, title: "z", conversation_id: "c3", current_version: 1, created_at: iso(0), updated_at: iso(0) }] },
];
