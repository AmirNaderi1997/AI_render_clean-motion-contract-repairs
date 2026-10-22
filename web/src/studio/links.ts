/** Display evidence-backed titles; never fetch arbitrary URLs from the browser. */
export function readableLink(raw: string, titles: Record<string, string> = {}): string {
  try {
    const url = new URL(raw);
    const title = titles[raw];
    if (title?.trim()) return title.trim().slice(0, 120);
    let path = url.pathname;
    try { path = decodeURIComponent(path); } catch { /* malformed encoding: keep a safe host label */ }
    const subject = path.split('/').filter(Boolean).pop()?.replace(/_/g, ' ');
    const host = url.hostname.replace(/^www\./, '');
    if (host.endsWith('.wikipedia.org') && subject) return `${subject.slice(0, 90)} — ویکی‌پدیا`;
    return subject && !/%[0-9a-f]{2}/i.test(subject) ? `${host} · ${subject.slice(0, 70)}` : host;
  } catch { return 'لینک منبع'; }
}
