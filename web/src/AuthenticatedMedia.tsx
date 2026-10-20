import React from "react";
import { api } from "./api";
import { friendlyError } from "./ui";

// One authenticated download per URL, shared by every consumer (inline player + preview panel).
const mediaCache = new Map<string, { promise: Promise<string>; refs: number }>();
function acquireMedia(url: string): Promise<string> {
  let entry = mediaCache.get(url);
  if (!entry) { entry = { promise: api.authenticatedObjectUrl(url), refs: 0 }; mediaCache.set(url, entry); entry.promise.catch(() => mediaCache.delete(url)); }
  entry.refs += 1;
  return entry.promise;
}
function releaseMedia(url: string) {
  const entry = mediaCache.get(url);
  if (!entry) return;
  entry.refs -= 1;
  if (entry.refs <= 0) { mediaCache.delete(url); void entry.promise.then(value => URL.revokeObjectURL(value), () => undefined); }
}

function useAuthenticatedMediaState(url: string | null | undefined) {
  const [mediaUrl, setMediaUrl] = React.useState<string>();
  const [error, setError] = React.useState("");
  React.useEffect(() => {
    let active = true;
    setMediaUrl(undefined);
    setError("");
    if (!url) return;
    acquireMedia(url).then(value => { if (active) setMediaUrl(value); }).catch(e => { if (active) setError(friendlyError(e, "load this media preview")); });
    return () => { active = false; releaseMedia(url); };
  }, [url]);
  return { mediaUrl, error };
}

export function useAuthenticatedMediaUrl(url: string | null | undefined): string | undefined {
  return useAuthenticatedMediaState(url).mediaUrl;
}

type Props = { as: "img" | "audio" | "video"; src: string; posterSrc?: string } & Record<string, any>;

export const AuthenticatedMedia = React.forwardRef<any, Props>(({ as, src, posterSrc, ...props }, ref) => {
  const elementRef = React.useRef<HTMLElement | null>(null);
  const [visible, setVisible] = React.useState(as !== "img" || props.loading !== "lazy");
  React.useEffect(() => {
    if (visible || !elementRef.current) return;
    if (!("IntersectionObserver" in window)) { setVisible(true); return; }
    const observer = new IntersectionObserver(entries => { if (entries.some(entry => entry.isIntersecting)) { setVisible(true); observer.disconnect(); } }, { rootMargin: "240px" });
    observer.observe(elementRef.current);
    return () => observer.disconnect();
  }, [visible]);
  const { mediaUrl, error } = useAuthenticatedMediaState(visible ? src : undefined);
  const { mediaUrl: posterUrl } = useAuthenticatedMediaState(
    visible && as === "video" ? posterSrc : undefined,
  );
  if (error) return <div className="notice" data-tone="error" role="alert">{error}</div>;
  return React.createElement(as, {
    ...props, ref: (node: HTMLElement | null): void => { elementRef.current = node; if (typeof ref === "function") ref(node); else if (ref) ref.current = node; }, src: mediaUrl, "aria-busy": !mediaUrl, "data-loading": !mediaUrl,
    ...(as === "video" && posterSrc ? { poster: posterUrl } : {}),
    ...(as === "img" ? { alt: props.alt ?? "Media preview" } : { "aria-label": props["aria-label"] || (as === "audio" ? "Audio preview" : "Video preview") }),
  });
});
