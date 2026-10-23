import React from "react";
import { Icon } from "../components/Icon";

/**
 * One group of settings in the Edit tab: a card with a title, a one-line summary of what is set now, and the controls
 * behind it. Every engine's settings (talking plan, Localize, explainer scenes, Motion clips) use this, so the tab looks
 * and behaves the same whatever the video is.
 */
export function EditCard({ title, summary, hint, open, children, tone }: {
  title: string; summary?: React.ReactNode; hint?: React.ReactNode; open?: boolean; children: React.ReactNode; tone?: "warning";
}) {
  return <details className="ec" dir="rtl" open={open} data-tone={tone}>
    <summary>
      <span className="ec-text"><b>{title}</b>{summary ? <small className="bidi" dir="auto">{summary}</small> : null}</span>
      <Icon name="chevronDown" size={16} className="ec-chev"/>
    </summary>
    <div className="ec-body">{hint ? <p className="ec-hint">{hint}</p> : null}{children}</div>
  </details>;
}

/** A row of labelled fields that wraps on narrow panels. */
export function EditGrid({ children }: { children: React.ReactNode }) {
  return <div className="ec-grid">{children}</div>;
}

/** A switch row: label and explanation on one side, the checkbox on the other. */
export function EditSwitch({ label, hint, checked, disabled, onChange }: {
  label: string; hint?: string; checked: boolean; disabled?: boolean; onChange: (value: boolean) => void;
}) {
  return <label className="ec-switch">
    <span><b>{label}</b>{hint ? <small>{hint}</small> : null}</span>
    <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={event => onChange(event.target.checked)}/>
  </label>;
}
