/**
 * Geometry for editing a caption directly on the video frame (pure, unit-tested with `node --test`).
 * Frame coordinates are the render's 1080x1920 pixels; screen coordinates are CSS pixels inside the displayed video.
 */
export const FRAME_W = 1080;
export const FRAME_H = 1920;
export const SCALE_MIN = 0.4;
export const SCALE_MAX = 3;

export interface Rect { x: number; y: number; w: number; h: number }
export interface Look { x?: number; y?: number; scale?: number; color?: string }
export interface CaptionFrame { font?: string; font_file?: string | null; x: number; y: number; size: number; boxed: boolean; x_locked: boolean; rect: Rect; now: Rect }

const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));

/** The video area inside its element (object-fit: contain letterboxes it). */
export function fitFrame(boxW: number, boxH: number): { left: number; top: number; width: number; height: number } {
  const ratio = FRAME_W / FRAME_H;
  const width = Math.min(boxW, boxH * ratio);
  const height = width / ratio;
  return { left: (boxW - width) / 2, top: (boxH - height) / 2, width, height };
}

/** CSS pixels per frame pixel for a displayed frame width. */
export const pxPerFramePx = (displayedWidth: number) => displayedWidth / FRAME_W;

export function toScreen(rect: Rect, displayed: { left: number; top: number; width: number }): Rect {
  const k = pxPerFramePx(displayed.width);
  return { x: displayed.left + rect.x * k, y: displayed.top + rect.y * k, w: rect.w * k, h: rect.h * k };
}

/** Moving by a pointer delta (screen px) moves the anchor by delta / k frame px, kept on the frame. */
export function moveLook(frame: CaptionFrame, look: Look, dxScreen: number, dyScreen: number, displayedWidth: number): Look {
  const k = pxPerFramePx(displayedWidth);
  const x = frame.x_locked ? undefined : clamp((look.x ?? frame.x) + dxScreen / k, 0, FRAME_W);
  const y = clamp((look.y ?? frame.y) + dyScreen / k, 0, FRAME_H);
  return { ...look, ...(x === undefined ? {} : { x: round(x) }), y: round(y) };
}

/** Dragging the bottom-right handle: the width follows the pointer, so scale = new width / current width. */
export function resizeLook(look: Look, currentRectWidth: number, dxScreen: number, displayedWidth: number): Look {
  const k = pxPerFramePx(displayedWidth);
  const base = look.scale ?? 1;
  const nextWidth = Math.max(8, currentRectWidth + dxScreen / k);
  return { ...look, scale: round2(clamp(base * nextWidth / Math.max(8, currentRectWidth), SCALE_MIN, SCALE_MAX)) };
}

const round = (v: number) => Math.round(v * 10) / 10;
const round2 = (v: number) => Math.round(v * 100) / 100;

/** The edit op for a caption's look; empty fields mean "the style's own". */
export function lookIsEmpty(look: Look): boolean {
  return look.x === undefined && look.y === undefined && look.scale === undefined && !look.color;
}

/** Whether a caption is on screen at `t` (the playhead decides which captions can be grabbed on the frame). */
export function visibleAt(element: { start: number; end: number }, t: number): boolean {
  return element.start - 1e-6 <= t && t < element.end;
}
