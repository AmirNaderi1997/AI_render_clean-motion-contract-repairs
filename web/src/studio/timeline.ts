/** Pure helpers for the project timeline view (type imports only, unit-tested with `node --test`). */
import type { DocElement, MusicMix, PictureOp, PictureSource, ProjectDocument, TimelineOp } from "../api";

export const TYPE_LABEL: Record<string, string> = {
  clip: "برش تصویر", picture: "تصویر بالا", title: "عنوان", caption: "زیرنویس", card: "کارت متنی", chips: "فهرست",
  moment: "لحظهٔ کلیدی", flash: "فلش نور", motion: "صحنهٔ موشن", audio: "صدا", music: "موسیقی", cta: "دعوت به اقدام", logo: "لوگو", effect: "افکت تصویر", transition: "ترنزیشن",
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

/** The caption's complete edit for the form, hidden flag and on-frame look; equal to the AI's version = a reset. */
export function captionOp(element: DocElement, form: CaptionForm, deleted = false, look: { x?: number; y?: number; scale?: number; color?: string } = {}): TimelineOp {
  const original = element.props.original as { text: string; start: number; end: number };
  const op: TimelineOp = { id: element.id };
  const start = Number(form.start), end = Number(form.end);
  if (form.text.trim() !== original.text) op.text = form.text.trim();
  if (Number.isFinite(start) && Math.abs(start - original.start) > 0.004) op.start = Math.round(start * 100) / 100;
  if (Number.isFinite(end) && Math.abs(end - original.end) > 0.004) op.end = Math.round(end * 100) / 100;
  if (look.x !== undefined) op.x = look.x;
  if (look.y !== undefined) op.y = look.y;
  if (look.scale !== undefined) op.scale = look.scale;
  if (look.color) op.color = look.color;
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

/** What the user chose for a picture slot. Only the field of the chosen source is used. */
export interface PictureForm { source: PictureSource; media: string; library: string; visual: string }

export function pictureForm(element: DocElement): PictureForm {
  const current = element.props.current as Partial<PictureForm> | null | undefined;
  return { source: current?.source ?? (element.props.hidden ? "hidden" : "ai"), media: current?.media ?? "", library: current?.library ?? "",
           visual: current?.visual ?? String(element.props.original?.visual ?? element.props.prompt ?? "") };
}

/** The op for a slot, or a reset when the form is exactly the AI's own prompt (nothing to override). */
export function pictureOp(element: DocElement, form: PictureForm): PictureOp {
  const slot = Number(element.props.sentence);
  const original = element.props.original as { source: string; visual: string };
  if (form.source === "ai" && form.visual.trim() === original.visual.trim() && original.source.startsWith("ai")) return { slot, reset: true };
  if (form.source === "ai") return { slot, source: "ai", visual: form.visual.trim() };
  if (form.source === "upload") return { slot, source: "upload", media: form.media };
  if (form.source === "library") return { slot, source: "library", library: form.library };
  return { slot, source: "hidden" };
}

export function pictureProblem(form: PictureForm): string {
  if (form.source === "ai" && form.visual.trim().length < 3) return "توضیح تصویر را بنویسید.";
  if (form.source === "upload" && !form.media) return "یک تصویر انتخاب یا آپلود کنید.";
  if (form.source === "library" && !form.library) return "یک تصویر از کتابخانه انتخاب کنید.";
  return "";
}


export interface MusicForm { path: string; volume_db: number; fade_in: number; fade_out: number; duck: boolean }
export const MUSIC_LIMITS = { volume_db: [-40, -3], fade_in: [0, 5], fade_out: [0, 8] } as const;

/** The music element's current choice and mix (what the render will use). */
export function musicForm(element: { props: Record<string, any> }): MusicForm {
  const p = element.props;
  return { path: p.path ?? "", volume_db: Number(p.volume_db), fade_in: Number(p.fade_in), fade_out: Number(p.fade_out), duck: p.duck !== false };
}

/** Plan edits for a changed form: the track only when it changed, and only the mix fields that differ from the style's own. */
export function musicEdits(form: MusicForm, element: { props: Record<string, any> }): { music?: string; music_mix: Partial<MusicMix> } {
  const defaults = element.props.defaults as MusicMix;
  const mix: Partial<MusicMix> = {};
  for (const key of ["volume_db", "fade_in", "fade_out"] as const) if (Math.abs(form[key] - defaults[key]) > 1e-9) mix[key] = form[key];
  if (form.duck !== defaults.duck) mix.duck = form.duck;
  const edits: { music?: string; music_mix: Partial<MusicMix> } = { music_mix: mix };
  if (form.path !== (element.props.path ?? "")) edits.music = form.path;
  return edits;
}

export function musicProblem(form: MusicForm): string {
  for (const [key, [low, high]] of Object.entries(MUSIC_LIMITS) as [keyof typeof MUSIC_LIMITS, readonly [number, number]][]) {
    const value = form[key];
    if (!Number.isFinite(value) || value < low || value > high) return "مقدار موسیقی خارج از محدودهٔ مجاز است.";
  }
  return "";
}

export const musicChanged = (form: MusicForm, element: { props: Record<string, any> }) => {
  const saved = musicForm(element);
  return form.path !== saved.path || form.volume_db !== saved.volume_db || form.fade_in !== saved.fade_in || form.fade_out !== saved.fade_out || form.duck !== saved.duck;
};
