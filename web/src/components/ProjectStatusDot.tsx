import React from "react";

export type ProjectStatus = { label: string; tone: "success" | "error" | "warning" | "working" | "neutral" };

/** No visible status copy; keep an accessible name and hover description. */
export function ProjectStatusDot({status}:{status:ProjectStatus}) {
  return <span className="project-status-dot" data-tone={status.tone} role="status"
    aria-label={`وضعیت پروژه: ${status.label}`} title={status.label}/>;
}
