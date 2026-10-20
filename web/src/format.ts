/** Presentation helpers. They never change stored data, only how it is displayed. */

const URL_RE = /https?:\/\/[^\s]+/gi;

/** Turn a long prompt-derived title into something scannable. The full text stays available via `title` attributes. */
export function displayTitle(raw: string | undefined | null, max = 56): string {
  let text = (raw || "").replace(/[‌‏‎]/g, "").replace(/\s+/g, " ").trim();
  if (!text) return "Untitled edit";
  text = text.replace(/^[\s>#*_`"'“”«»-]+/, "").replace(URL_RE, url => {
    try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return "link"; }
  });
  if (text.length <= max) return text;
  const slice = text.slice(0, max);
  const lastSpace = slice.lastIndexOf(" ");
  return `${(lastSpace > max * 0.55 ? slice.slice(0, lastSpace) : slice).replace(/[\s,.;:،؛-]+$/, "")}…`;
}

export function parseTime(value: string | number | undefined | null): number {
  if (value == null || value === "") return 0;
  if (typeof value === "number") return value;
  const time = Date.parse(value);
  return Number.isNaN(time) ? 0 : time;
}

const rtf = typeof Intl !== "undefined" && "RelativeTimeFormat" in Intl ? new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }) : null;
export function relativeTime(time: number, now = Date.now()): string {
  if (!time) return "";
  const seconds = Math.round((time - now) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return "Just now";
  if (!rtf) return new Date(time).toLocaleDateString();
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
  if (abs < 86400 * 7) return rtf.format(Math.round(seconds / 86400), "day");
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: new Date(time).getFullYear() === new Date(now).getFullYear() ? undefined : "numeric" }).format(time);
}

export function clock(time: number): string {
  return time ? new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(time) : "";
}

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(total / 60), s = total % 60;
  return m ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}
