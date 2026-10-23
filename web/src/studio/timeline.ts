/** Pure helpers for the project timeline view (type imports only, unit-tested with `node --test`). */
import type { DocElement, ProjectDocument, TimelineOp } from "../api";

export const TYPE_LABEL: Record<string, string> = {
  clip: "برش تصویر", picture: "تصویر بالا", title: "عنوان", caption: "زیرنویس", card: "کارت متنی", chips: "فهرست",
  moment: "لحظهٔ کلیدی", flash: "فلش نور", motion: "صحنهٔ موشن", audio: "صدا", music: "موسیقی", cta: "دعوت به اقدام", logo: "لوگو",
};
export const VIA_LABEL: Record<string, string> = { plan: "برنامه (تب Edit)", chat: "چت", timeline: "همین‌جا روی تایم‌لاین", advanced: "ویرایشگر پیشرفته" };

/** "0:05.2" style time, tenths only when useful. */
export function clock(seconds: number): string {
  const s = Math.max(0, seconds);
  const minutes = Math.floor(s / 60);
  const rest = s - minutes * 60;
  return `${minutes}:${rest < 10 ? "0" : ""}${rest.toFixed(1)}`;
}

/** Ruler ticks: a readable step for the zoom level, every tick in seconds. */
export function ticks(duration: number, pxPerSecond: number): { at: number; major: boolean }[] {
  const steps = [0.5, 1, 2, 5, 10, 15, 30, 60];
  const step = steps.find(value => value * pxPerSecond >= 48) ?? 60;
  const out: { at: number; major: boolean }[] = [];
  for (let at = 0; at <= duration + 1e-6; at += step) out.push({ at: Math.round(at * 1000) / 1000, major: Math.round(at / step) % 2 === 0 });
  return out;
}

/** Greedy rows so overlapping elements of one track never cover each other. */
export function stackRows(elements: DocElement[]): DocElement[][] {
  const rows: DocElement[][] = [];
  for (const element of [...elements].sort((a, b) => a.start - b.start)) {
    const row = rows.find(items => items[items.length - 1].end <= element.start + 1e-6);
    if (row) row.push(element); else rows.push([element]);
  }
  return rows;
}

export function findElement(doc: ProjectDocument | null, id: string | null): DocElement | undefined {
  if (!doc || !id) return undefined;
  for (const track of doc.tracks) { const found = track.elements.find(item => item.id === id); if (found) return found; }
  return undefined;
}

/** The video under the timeline is known to show this document only when the server says so. */
export function playerMatches(doc: ProjectDocument): boolean {
  return doc.basis.synced === true;
}

/** What to tell the user about the video under the timeline. */
export type SyncNotice = "none" | "no-video" | "different-version" | "unknown";
export function syncNotice(doc: ProjectDocument, hasVideo: boolean): SyncNotice {
  if (!hasVideo) return "no-video";
  if (doc.basis.synced === true) return "none";
  return doc.basis.synced === false ? "different-version" : "unknown";
}

/** What the user typed for a caption. Times are text so a half-typed number does not jump around. */
export interface CaptionForm { text: string; start: string; end: string }

export function captionForm(element: DocElement): CaptionForm {
  return { text: element.text, start: element.start.toFixed(2), end: element.end.toFixed(2) };
}

/** The caption's complete edit for the form (and hidden flag); a form equal to the AI's version is a reset. */
export function captionOp(element: DocElement, form: CaptionForm, deleted = false): TimelineOp {
  const original = element.props.original as { text: string; start: number; end: number };
  const op: TimelineOp = { id: element.id };
  const start = Number(form.start), end = Number(form.end);
  if (form.text.trim() !== original.text) op.text = form.text.trim();
  if (Number.isFinite(start) && Math.abs(start - original.start) > 0.004) op.start = Math.round(start * 100) / 100;
  if (Number.isFinite(end) && Math.abs(end - original.end) > 0.004) op.end = Math.round(end * 100) / 100;
  if (deleted) op.deleted = true;
  return Object.keys(op).length === 1 ? { id: element.id, reset: true } : op;
}

/** Client-side hints only; the server validates everything again. */
export function captionProblem(form: CaptionForm, duration: number): string {
  const start = Number(form.start), end = Number(form.end);
  if (!form.text.trim()) return "متن زیرنویس نباید خالی باشد.";
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "زمان شروع و پایان باید عدد باشد.";
  if (start < 0 || end > duration) return "زمان باید داخل مدت ویدیو باشد.";
  if (end - start < 0.3) return "هر زیرنویس دست‌کم ۰٫۳ ثانیه باید نمایش داده شود.";
  return "";
}
