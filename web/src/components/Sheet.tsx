import React from "react";
import { createPortal } from "react-dom";
import { useFocusTrap } from "./hooks";

/**
 * Bottom sheet on phones, centred dialog on larger screens.
 * Dismiss: backdrop, Escape, close button, or swipe the handle down.
 */
export function Sheet({ open, onClose, label, children }: { open: boolean; onClose: () => void; label: string; children: React.ReactNode }) {
  const ref = React.useRef<HTMLDivElement>(null);
  const [closing, setClosing] = React.useState(false);
  const drag = React.useRef<{ y: number } | null>(null);
  const close = React.useCallback(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) { onClose(); return; }
    setClosing(true); window.setTimeout(() => { setClosing(false); onClose(); }, 200);
  }, [onClose]);
  useFocusTrap(open, ref);
  React.useEffect(() => {
    if (!open || !window.visualViewport) return;
    const viewport = window.visualViewport;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const sheet = ref.current;
        if (!sheet) return;
        sheet.style.setProperty("--sheet-visible-height", `${viewport.height}px`);
        sheet.style.setProperty("--sheet-visible-center", `${viewport.offsetTop + viewport.height / 2}px`);
        sheet.style.setProperty("--sheet-keyboard-inset", `${Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop)}px`);
        const active = document.activeElement;
        if (active instanceof HTMLInputElement && sheet.contains(active)) {
          active.scrollIntoView({ block: "nearest", behavior: "instant" });
        }
      });
    };
    update();
    viewport.addEventListener("resize", update);
    viewport.addEventListener("scroll", update);
    return () => { cancelAnimationFrame(frame); viewport.removeEventListener("resize", update); viewport.removeEventListener("scroll", update); };
  }, [open]);
  React.useEffect(() => {
    if (!open) return;
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    document.addEventListener("keydown", key);
    const { overflow } = document.body.style; document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", key); document.body.style.overflow = overflow; };
  }, [open, close]);
  if (!open) return null;
  const onDown = (event: React.PointerEvent) => { drag.current = { y: event.clientY }; (event.target as Element).setPointerCapture?.(event.pointerId); };
  const onMove = (event: React.PointerEvent) => {
    if (!drag.current || !ref.current) return;
    const dy = Math.max(0, event.clientY - drag.current.y);
    ref.current.style.transition = "none"; ref.current.style.transform = `translateY(${dy}px)`;
  };
  const onUp = (event: React.PointerEvent) => {
    if (!drag.current || !ref.current) return;
    const dy = event.clientY - drag.current.y; drag.current = null;
    ref.current.style.transition = ""; ref.current.style.transform = "";
    if (dy > 90) close();
  };
  return createPortal(<>
    <div className="sheet-overlay" onClick={close} aria-hidden="true"/>
    <div ref={ref} className="sheet" role="dialog" aria-modal="true" aria-label={label} tabIndex={-1} data-closing={closing || undefined}>
      <div className="sheet-handle" onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp} aria-hidden="true"/>
      <div className="sheet-body">{children}</div>
    </div>
  </>, document.body);
}
