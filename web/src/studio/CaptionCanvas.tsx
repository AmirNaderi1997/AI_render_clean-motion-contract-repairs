import React from "react";
import { DocElement } from "../api";
import { CaptionFrame, FRAME_H, FRAME_W, Look, fitFrame, lookIsEmpty, moveLook, resizeLook, toScreen, visibleAt } from "./canvas";

interface Props {
  /** The element the video box wraps, to size the overlay to the displayed frame. */
  boxRef: React.RefObject<HTMLElement | null>;
  captions: DocElement[];          // all captions of the timeline
  time: number;                    // playhead
  selectedId: string | null;
  draft: Look;                     // the look being edited for the selected caption
  onSelect: (id: string) => void;
  onDraft: (look: Look) => void;
  onCommit: (look: Look) => void;  // pointer released: ready to save
  disabled?: boolean;
  /** Drawn over a caption-free video: the boxes are the captions themselves, not outlines of burned-in ones. */
  live?: boolean;
}

/**
 * An editing layer over the video: the captions that are on screen at the playhead, each as its exact rectangle on the
 * 1080x1920 frame. Drag to move, drag the corner to resize. The text is only a stand-in (the browser does not have the
 * style's font); the position and size are the real ones the render will use.
 */
export function CaptionCanvas({ boxRef, captions, time, selectedId, draft, onSelect, onDraft, onCommit, disabled, live }: Props) {
  const [size, setSize] = React.useState({ w: 0, h: 0 });
  const drag = React.useRef<{ mode: "move" | "resize"; x: number; y: number; look: Look; rect: number } | null>(null);
  React.useLayoutEffect(() => {
    const node = boxRef.current;
    if (!node) return;
    const measure = () => setSize({ w: node.clientWidth, h: node.clientHeight });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [boxRef]);
  const shown = captions.filter(item => visibleAt(item, time) && !item.props.deleted && item.props.frame);
  if (!size.w || !shown.length) return null;
  const displayed = fitFrame(size.w, size.h);
  const selected = shown.find(item => item.id === selectedId);

  const rectOf = (item: DocElement) => {
    const frame = item.props.frame as CaptionFrame;
    return item.id === selectedId && !lookIsEmpty(draft) ? previewRect(frame, draft) : frame.now;
  };
  const down = (event: React.PointerEvent, item: DocElement, mode: "move" | "resize") => {
    if (disabled) return;
    event.preventDefault(); event.stopPropagation();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    onSelect(item.id);
    const start = item.id === selectedId ? draft : (item.props.look as Look) ?? {};
    drag.current = { mode, x: event.clientX, y: event.clientY, look: start, rect: rectOf(item).w };
  };
  const move = (event: React.PointerEvent, item: DocElement) => {
    const state = drag.current;
    if (!state) return;
    const frame = item.props.frame as CaptionFrame;
    const dx = event.clientX - state.x, dy = event.clientY - state.y;
    onDraft(state.mode === "move" ? moveLook(frame, state.look, dx, dy, displayed.width) : resizeLook(state.look, state.rect, dx, displayed.width));
  };
  const up = (event: React.PointerEvent, item: DocElement) => {
    const state = drag.current;
    if (!state) return;
    const frame = item.props.frame as CaptionFrame;
    const dx = event.clientX - state.x, dy = event.clientY - state.y;
    drag.current = null;
    onCommit(state.mode === "move" ? moveLook(frame, state.look, dx, dy, displayed.width) : resizeLook(state.look, state.rect, dx, displayed.width));
  };

  return <div className="cc" data-live={live || undefined} style={{ left: displayed.left, top: displayed.top, width: displayed.width, height: displayed.height }} aria-label="ویرایش زیرنویس روی تصویر">
    {shown.map(item => {
      const screen = toScreen(rectOf(item), { left: 0, top: 0, width: displayed.width });
      const active = item.id === selected?.id;
      const frame = item.props.frame as CaptionFrame;
      const color = active && draft.color ? draft.color : (item.props.look as Look)?.color;
      return <div key={item.id} className="cc-box" data-active={active || undefined} data-locked={disabled || undefined}
        style={{ left: screen.x, top: screen.y, width: screen.w, height: screen.h, color: color || undefined,
                 fontSize: Math.max(8, frame.size * (displayed.width / FRAME_W) * ((active ? draft.scale : (item.props.look as Look)?.scale) ?? 1) * 0.9) }}
        role="button" tabIndex={0} aria-label={`زیرنویس: ${item.text}`} aria-pressed={active}
        onPointerDown={event => down(event, item, "move")} onPointerMove={event => move(event, item)} onPointerUp={event => up(event, item)}
        onKeyDown={event => { if (event.key === "Enter" || event.key === " ") onSelect(item.id); }}>
        <span dir="auto" data-boxed={(live && frame.boxed) || undefined}>{item.text}</span>
        {active && !disabled ? <i className="cc-handle" aria-label="تغییر اندازه"
          onPointerDown={event => down(event, item, "resize")} onPointerMove={event => move(event, item)} onPointerUp={event => up(event, item)}/> : null}
      </div>;
    })}
  </div>;
}

/** The rectangle while a draft look is being dragged (the server computes the saved one the same way). */
function previewRect(frame: CaptionFrame, look: Look) {
  const scale = look.scale ?? 1;
  const base = frame.rect;                       // geometry without any look
  const ax = look.x ?? frame.x, ay = look.y ?? frame.y;
  if (frame.boxed) return { x: ax + scale * (base.x - frame.x), y: ay + scale * (base.y - frame.y), w: base.w * scale, h: base.h * scale };
  const w = base.w * scale, h = base.h * scale;
  return { x: ax - w / 2, y: ay - h / 2, w, h };
}
export const FRAME_SIZE = { w: FRAME_W, h: FRAME_H };
