import React from "react";
import { Bounds, KEY_STEP, clampSize, dragSize, keySize, readSize } from "./resize";

/** A saved panel width: restored from localStorage, clamped to the bounds on every use. */
export function usePanelWidth(key: string, bounds: Bounds): [number | null, (value: number | null) => void] {
  const [width, set] = React.useState<number | null>(() => {
    try { return readSize(localStorage.getItem(key), bounds); } catch { return null; }
  });
  const save = React.useCallback((value: number | null) => {
    set(value);
    try { if (value == null) localStorage.removeItem(key); else localStorage.setItem(key, String(value)); } catch { /* storage unavailable */ }
  }, [key]);
  return [width, save];
}

interface Props {
  /** The panel being resized (its measured width is the drag's starting point). */
  panel: React.RefObject<HTMLElement | null>;
  edge: "start" | "end";          // which edge of the panel carries the handle
  bounds: () => Bounds;           // evaluated when a drag starts, so max can follow the container
  width: number | null;           // current saved width, null = the layout's default
  onResize: (value: number) => void;
  onCommit: (value: number | null) => void;   // pointer released / key pressed (persist); null = reset to default
  label: string;
  onDragState?: (dragging: boolean) => void;
}

/** Thin draggable divider on a panel's edge. Pointer-drag, arrow keys, Home/End, double-click to reset. */
export function Resizer({ panel, edge, bounds, width, onResize, onCommit, label, onDragState }: Props) {
  const drag = React.useRef<{ x: number; start: number; bounds: Bounds; rtl: boolean } | null>(null);
  const [active, setActive] = React.useState(false);
  const rtl = () => (panel.current ? getComputedStyle(panel.current).direction === "rtl" : false);
  const measured = () => panel.current?.getBoundingClientRect().width ?? 0;

  const down = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !panel.current) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { x: event.clientX, start: measured(), bounds: bounds(), rtl: rtl() };
    setActive(true); onDragState?.(true);
  };
  const move = (event: React.PointerEvent<HTMLDivElement>) => {
    const state = drag.current;
    if (!state) return;
    onResize(dragSize(state.start, event.clientX - state.x, edge, state.rtl, state.bounds));
  };
  const up = (event: React.PointerEvent<HTMLDivElement>) => {
    const state = drag.current;
    if (!state) return;
    drag.current = null;
    setActive(false); onDragState?.(false);
    onCommit(dragSize(state.start, event.clientX - state.x, edge, state.rtl, state.bounds));
  };
  const key = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const range = bounds();
    const next = keySize(event.key, width ?? measured(), edge, rtl(), range);
    if (next == null) return;
    event.preventDefault();
    onResize(next); onCommit(next);
  };
  const range = bounds();
  const now = clampSize(width ?? measured(), range);
  return <div className="resizer" data-edge={edge} data-active={active || undefined} role="separator" aria-orientation="vertical"
    aria-label={label} aria-valuemin={range.min} aria-valuemax={range.max} aria-valuenow={now} tabIndex={0}
    title={`${label} — بکشید، یا با کلیدهای جهت‌دار (${KEY_STEP}px)؛ دو بار کلیک: اندازهٔ پیش‌فرض`}
    onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onKeyDown={key} onDoubleClick={() => onCommit(null)}/>;
}
