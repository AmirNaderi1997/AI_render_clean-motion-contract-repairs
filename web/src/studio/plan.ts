/**
 * Pure helpers for the Creative Plan review (no React, type imports only) so they can be unit-tested
 * with `node --test`. The plan itself is built by the backend from the real analysis.
 */
import type { PlanContent, PlanEdits, PlanState, PlanVersion, StudioProject } from "../api";

export type PlanPhase = "analyzing" | "awaiting" | "approved" | "rendering" | "review" | "done" | "failed" | "none";

/** Where the project is relative to the approval gate, from persisted backend state only. */
export function planPhase(project?: StudioProject): PlanPhase {
  const workflow = project?.state?.workflow as string | undefined;
  const plan = project?.state?.plan as PlanState | undefined;
  if (workflow === "analyzing") return "analyzing";
  if (!plan?.versions?.length) return "none";
  switch (workflow) {
    case "awaiting_approval": return "awaiting";
    case "approved": return "approved";
    case "production": return "rendering";
    case "quality_evaluation": case "user_review": return "review";
    case "completed": return "done";
    case "failed": return "failed";
    default: return plan.approved_id ? "approved" : "none";
  }
}

export const PHASE_LABEL: Record<PlanPhase, string> = {
  analyzing: "در حال ساخت برنامه", awaiting: "منتظر تأیید شما", approved: "تأیید شد", rendering: "در حال رندر",
  review: "آمادهٔ بازبینی", done: "تحویل شد", failed: "نیازمند بررسی", none: "",
};

export function currentVersion(project?: StudioProject): PlanVersion | undefined {
  const versions = (project?.state?.plan as PlanState | undefined)?.versions || [];
  return versions[versions.length - 1];
}

/** Edits that turn `current` back into `target` (restore an earlier version). Style/concept changes re-analyse. */
export function restoreEdits(current: PlanContent, target: PlanContent): PlanEdits {
  const edits: PlanEdits = {};
  if (target.style.id !== current.style.id) {
    const concept = target.concepts.find(item => item.selected);
    if (concept && current.concepts.some(item => item.id === concept.id)) edits.concept_id = concept.id;
    edits.style = target.style.id;
    return edits; // decisions are rebuilt for that style; text and look follow after re-analysis
  }
  if (target.hook.text !== current.hook.text) { edits.hook = target.hook.text; edits.hook_highlight = target.hook.highlight; }
  else if (!sameList(target.hook.highlight, current.hook.highlight)) edits.hook_highlight = target.hook.highlight;
  if (target.look.preset !== current.look.preset && target.look.preset !== "custom") edits.look = target.look.preset;
  if (target.look.accent_color !== current.look.accent_color) edits.accent_color = target.look.accent_color;
  if (target.look.caption_font !== current.look.caption_font) edits.caption_font = target.look.caption_font;
  if (target.look.zoom !== current.look.zoom) edits.zoom = target.look.zoom;
  if ((target.look.bottom_shade ?? 0) !== (current.look.bottom_shade ?? 0)) edits.bottom_shade = target.look.bottom_shade ?? 0;
  if (target.look.key_moments !== current.look.key_moments) edits.key_moments = target.look.key_moments;
  if (target.brand.logo.enabled !== current.brand.logo.enabled) edits.logo_enabled = target.brand.logo.enabled;
  if (target.brand.logo.enabled && target.brand.logo.motion !== current.brand.logo.motion) edits.logo_motion = target.brand.logo.motion;
  if (target.brand.name !== current.brand.name) edits.name = target.brand.name;
  if (target.brand.tagline !== current.brand.tagline) edits.tagline = target.brand.tagline;
  if (target.brand.cta !== current.brand.cta) edits.cta = target.brand.cta;
  if (JSON.stringify(target.timeline_edits || {}) !== JSON.stringify(current.timeline_edits || {})) edits.timeline_edits = target.timeline_edits || {};
  return edits;
}

function sameList(a: string[], b: string[]) { return a.length === b.length && a.every((item, i) => item === b[i]); }

/** Toggle one hook word in the highlight list; at most two words are coloured, like the engines. */
export function toggleHighlight(highlight: string[], word: string): string[] {
  if (highlight.includes(word)) return highlight.filter(item => item !== word);
  return [...highlight, word].slice(-2);
}

export function minutes(seconds: number): string {
  const value = seconds / 60;
  return value < 1 ? `${Math.max(1, Math.round(seconds))} ثانیه` : `${value.toFixed(value < 10 ? 1 : 0)} دقیقه`;
}

export function estimateText(content: PlanContent): string {
  const render = content.estimate?.render;
  if (!render) return "برای این سبک هنوز رندری روی این سرور اندازه‌گیری نشده؛ زمان دقیق نامشخص است.";
  return `حدود ${minutes(render.low_s)} تا ${minutes(render.high_s)} (بر اساس ${render.samples} رندر واقعی)`;
}

/** The director names beat roles in English; show them in Persian, falling back to the raw role. */
const ROLE_LABEL: Record<string, string> = {
  hook: "هوک", setup: "زمینه‌سازی", claim: "ادعا", proof: "اثبات", turn: "چرخش", payoff: "نتیجه", cta: "دعوت به اقدام",
  problem: "مسئله", solution: "راه‌حل", context: "زمینه", example: "مثال", conclusion: "جمع‌بندی", reveal: "افشا",
};
export function roleLabel(role: string, index: number): string {
  return ROLE_LABEL[role.trim().toLowerCase()] || role || `بخش ${index + 1}`;
}

export const SOURCE_LABEL: Record<string, string> = { agent: "پیشنهاد AI", user: "ویرایش شما", chat: "درخواست در چت" };
