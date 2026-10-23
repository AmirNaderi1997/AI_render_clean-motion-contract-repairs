/** Pure helpers for the long-video discovery panel (unit-tested with `node --test`). */
import type { CandidateStatus, DiscoveryCandidate, StudioEvent } from "../api";

export const STATUS_LABEL: Record<CandidateStatus, string> = {
  discovered: "پیشنهاد جدید", selected: "تدوین شروع شد", editing: "در حال تدوین", rendering: "در حال رندر", completed: "تکمیل شد", failed: "ناموفق",
};
export const STATUS_TONE: Record<CandidateStatus, "success" | "error" | "warning" | "working" | undefined> = {
  discovered: undefined, selected: "warning", editing: "warning", rendering: "working", completed: "success", failed: "error",
};
export const STAGE_LABEL: Record<string, string> = {
  queued: "در صف", transcribing: "گوش دادن و تبدیل گفتار به متن", enhancing: "اصلاح و بهبود متن", understanding: "فهمیدن ساختار کل ویدیو",
  finding: "جست‌وجوی محتوای مستقل", validating: "بازبینی پیشنهادها", done: "تمام شد", stopped: "متوقف شد", failed: "ناموفق", interrupted: "قطع شده",
};

export function clock(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  const two = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${two(m)}:${two(s)}` : `${two(m)}:${two(s)}`;
}

export function rangeText(candidate: Pick<DiscoveryCandidate, "ranges">): string {
  return candidate.ranges.map(([a, b]) => `${clock(a)} – ${clock(b)}`).join(" + ");
}

export function etaText(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return "";
  if (seconds < 90) return `حدود ${Math.max(1, Math.round(seconds))} ثانیه مانده`;
  return `حدود ${Math.round(seconds / 60)} دقیقه مانده`;
}

export type SortKey = "time" | "score";

export function visibleCandidates(items: DiscoveryCandidate[], category: string | null, sort: SortKey, showHidden = false): DiscoveryCandidate[] {
  const filtered = items.filter(c => (showHidden || !c.hidden) && (!category || c.category === category));
  return [...filtered].sort((a, b) => sort === "score" ? b.score - a.score || a.ranges[0][0] - b.ranges[0][0] : a.ranges[0][0] - b.ranges[0][0]);
}

export function categoriesOf(items: DiscoveryCandidate[]): { name: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const item of items) if (!item.hidden) counts.set(item.category, (counts.get(item.category) ?? 0) + 1);
  return [...counts].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);
}

/** Real transcript lines: what the server saved at the end of each chunk, then the segments published since (nothing is typed out). */
export function liveLines(tail: { id: string; start: number; end: number; text: string }[], events: Pick<StudioEvent, "type" | "data">[], analysisId: string, limit = 6) {
  const byId = new Map<string, { id: string; start: number; end: number; text: string }>();
  for (const line of tail) byId.set(line.id, line);
  for (const event of events) {
    if (event.type !== "transcription.segment.completed" || event.data.analysis_id !== analysisId) continue;
    for (const line of event.data.segments ?? []) byId.set(line.id, line);
  }
  return [...byId.values()].sort((a, b) => a.start - b.start).slice(-limit);
}

export function isActive(status: CandidateStatus): boolean { return status === "selected" || status === "editing" || status === "rendering"; }

/** Time inputs → a validated range, or an error text. */
export function parseRange(startText: string, endText: string, duration: number): { range?: [number, number]; error?: string } {
  const parse = (value: string) => {
    const parts = value.trim().replace(/[۰-۹]/g, d => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))).split(":").map(Number);
    if (!parts.length || parts.length > 3 || parts.some(n => !Number.isFinite(n) || n < 0)) return NaN;
    return parts.reduce((total, n) => total * 60 + n, 0);
  };
  const a = parse(startText), b = parse(endText);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return { error: "زمان را به شکل 12:30 یا 750 بنویسید." };
  if (b - a < 5) return { error: "کلیپ باید دست‌کم ۵ ثانیه باشد." };
  if (b - a > 300) return { error: "کلیپ نباید بیشتر از ۵ دقیقه باشد." };
  if (b > duration + 0.5) return { error: "پایان از مدت ویدیو بیشتر است." };
  return { range: [Math.round(a * 100) / 100, Math.round(b * 100) / 100] };
}
