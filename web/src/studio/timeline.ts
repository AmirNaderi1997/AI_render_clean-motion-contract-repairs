/** Pure helpers for the project timeline view (type imports only, unit-tested with `node --test`). */
import type { DocElement, ProjectDocument } from "../api";

export const TYPE_LABEL: Record<string, string> = {
  clip: "برش تصویر", picture: "تصویر بالا", title: "عنوان", caption: "زیرنویس", card: "کارت متنی", chips: "فهرست",
  moment: "لحظهٔ کلیدی", flash: "فلش نور", motion: "صحنهٔ موشن", audio: "صدا", music: "موسیقی", cta: "دعوت به اقدام", logo: "لوگو",
};
export const VIA_LABEL: Record<string, string> = { plan: "برنامه (تب Edit)", chat: "چت" };

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

/** The video under the timeline shows this document only when it was rendered from the same plan version. */
export function playerMatches(doc: ProjectDocument): boolean {
  const { plan_version, rendered_version } = doc.basis;
  return plan_version != null && plan_version === rendered_version;
}
