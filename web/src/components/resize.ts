/** Pure logic for drag-resizable panels (no React, so it is unit-tested with `node --test`). */

export interface Bounds { min: number; max: number }

export function clampSize(value: number, { min, max }: Bounds): number {
  if (!Number.isFinite(value)) return min;
  return Math.round(Math.max(min, Math.min(Math.max(min, max), value)));
}

/**
 * New width after dragging the panel's edge by `delta` pixels (positive = pointer moved right on screen).
 * `edge`: which side of the panel the handle is on. Dragging the end edge right grows the panel in LTR;
 * in RTL the geometry mirrors, so the sign flips.
 */
export function dragSize(start: number, delta: number, edge: "start" | "end", rtl: boolean, bounds: Bounds): number {
  // A panel whose handle is on its right (end edge in LTR) grows when the pointer moves right.
  const handleOnRight = (edge === "end") !== rtl;
  return clampSize(start + (handleOnRight ? delta : -delta), bounds);
}

export const KEY_STEP = 24;

/** Arrow keys resize the focused handle; Home/End jump to the bounds. Returns null for other keys. */
export function keySize(key: string, current: number, edge: "start" | "end", rtl: boolean, bounds: Bounds, step = KEY_STEP): number | null {
  if (key === "Home") return clampSize(bounds.min, bounds);
  if (key === "End") return clampSize(bounds.max, bounds);
  if (key !== "ArrowLeft" && key !== "ArrowRight") return null;
  return dragSize(current, key === "ArrowRight" ? step : -step, edge, rtl, bounds);
}

export function readSize(raw: string | null, bounds: Bounds): number | null {
  if (raw == null) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? clampSize(value, bounds) : null;
}
