import React from "react";
import { useDismiss } from "./hooks";

/** Small anchored menu with roving arrow-key focus. */
export function Menu({ trigger, children, side = "bottom", align = "start", label }: {
  trigger: (props: { onClick: () => void; "aria-expanded": boolean; "aria-haspopup": "menu"; ref: React.Ref<HTMLButtonElement> }) => React.ReactNode;
  children: (close: () => void) => React.ReactNode;
  side?: "top" | "bottom"; align?: "start" | "end"; label: string;
}) {
  const [open, setOpen] = React.useState(false);
  const wrap = React.useRef<HTMLDivElement>(null);
  const button = React.useRef<HTMLButtonElement>(null);
  const close = React.useCallback(() => { setOpen(false); button.current?.focus({ preventScroll: true }); }, []);
  useDismiss(open, close, wrap);
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
    {open ? <div className="popover" role="menu" aria-label={label} data-side={side} data-align={align}>{children(close)}</div> : null}
  </div>;
}
