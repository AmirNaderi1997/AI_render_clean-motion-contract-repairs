import React from "react";
import { useDismiss } from "./hooks";

/** Small anchored menu with roving arrow-key focus. */
export function Menu({ trigger, children, side = "bottom", align = "start", label }: {
  trigger: (props: { onClick: () => void; "aria-expanded": boolean; "aria-haspopup": "menu"; ref: React.Ref<HTMLButtonElement> }) => React.ReactNode;
  children: (close: () => void) => React.ReactNode;
  side?: "top" | "bottom"; align?: "start" | "end"; label: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [placement, setPlacement] = React.useState<{ side: "top" | "bottom"; max: number }>({ side, max: 420 });
  const wrap = React.useRef<HTMLDivElement>(null);
  const button = React.useRef<HTMLButtonElement>(null);
  const close = React.useCallback(() => { setOpen(false); button.current?.focus({ preventScroll: true }); }, []);
  useDismiss(open, close, wrap);
  // Open towards whichever side has room, and cap the height so the menu never leaves the viewport.
  React.useLayoutEffect(() => {
    if (!open || !wrap.current) return;
    const rect = wrap.current.getBoundingClientRect();
    const above = rect.top - 12, below = window.innerHeight - rect.bottom - 12;
    const chosen = side === "top" ? (above >= 240 || above >= below ? "top" : "bottom") : (below >= 240 || below >= above ? "bottom" : "top");
    setPlacement({ side: chosen, max: Math.max(160, (chosen === "top" ? above : below) - 8) });
  }, [open, side]);
  React.useEffect(() => { if (open) wrap.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus({ preventScroll: true }); }, [open]);
  const onKey = (event: React.KeyboardEvent) => {
    if (!open || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const items = Array.from(wrap.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') || []);
    if (!items.length) return;
    event.preventDefault();
    const index = items.indexOf(document.activeElement as HTMLElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next].focus();
  };
  return <div ref={wrap} style={{ position: "relative", display: "inline-flex" }} onKeyDown={onKey}>
    {trigger({ onClick: () => setOpen(value => !value), "aria-expanded": open, "aria-haspopup": "menu", ref: button })}
    {open ? <div className="popover" role="menu" aria-label={label} data-side={placement.side} data-align={align} style={{ maxHeight: placement.max, overflowY: "auto" }}>{children(close)}</div> : null}
  </div>;
}
