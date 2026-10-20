import React from "react";

/** Subscribe to a CSS media query. */
export function useMediaQuery(query: string): boolean {
  const get = () => typeof window !== "undefined" && window.matchMedia(query).matches;
  const [matches, setMatches] = React.useState(get);
  React.useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

export type StudioLayout = "desktop" | "tablet" | "mobile";
/** Studio layout mode: two panels, slide-over workspace, or one view at a time. */
export function useStudioLayout(): StudioLayout {
  const desktop = useMediaQuery("(min-width: 1100px)");
  const tablet = useMediaQuery("(min-width: 701px)");
  return desktop ? "desktop" : tablet ? "tablet" : "mobile";
}

/** Keep --app-h equal to the visual viewport so fixed bottom UI stays above the virtual keyboard (iOS Safari). */
export function useVisualViewportHeight() {
  React.useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;
    const root = document.documentElement;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        root.style.setProperty("--app-h", `${Math.round(vv.height)}px`);
        if (vv.offsetTop > 0) window.scrollTo(0, 0);
      });
    };
    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => { vv.removeEventListener("resize", update); vv.removeEventListener("scroll", update); root.style.removeProperty("--app-h"); cancelAnimationFrame(frame); };
  }, []);
}

/** Close on Escape and on outside pointer-down. */
export function useDismiss(open: boolean, onClose: () => void, ref: React.RefObject<HTMLElement>) {
  React.useEffect(() => {
    if (!open) return;
    const key = (event: KeyboardEvent) => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } };
    const down = (event: PointerEvent) => { if (ref.current && !ref.current.contains(event.target as Node)) onClose(); };
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", down);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("pointerdown", down); };
  }, [open, onClose, ref]);
}

/** Trap Tab focus inside a container while active; restore focus on unmount. */
export function useFocusTrap(active: boolean, ref: React.RefObject<HTMLElement>) {
  React.useEffect(() => {
    if (!active || !ref.current) return;
    const node = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    const focusable = () => Array.from(node.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])')).filter(el => el.offsetParent !== null);
    const first = focusable()[0];
    (first || node).focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) { event.preventDefault(); return; }
      const head = items[0], tail = items[items.length - 1];
      if (event.shiftKey && document.activeElement === head) { event.preventDefault(); tail.focus(); }
      else if (!event.shiftKey && document.activeElement === tail) { event.preventDefault(); head.focus(); }
    };
    node.addEventListener("keydown", onKey);
    return () => { node.removeEventListener("keydown", onKey); previous?.focus?.({ preventScroll: true }); };
  }, [active, ref]);
}
