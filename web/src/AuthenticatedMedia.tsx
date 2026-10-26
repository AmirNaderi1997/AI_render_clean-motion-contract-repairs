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

const DownloadedMedia = React.forwardRef<any, Props>(({ as, src, posterSrc, ...props }, ref) => {
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

const StreamingVideo = React.forwardRef<any, Props>(({src, posterSrc, as, ...props}, ref) => {
  const video = React.useRef<HTMLVideoElement | null>(null);
  const inFlight = React.useRef(false);
  const [ready, setReady] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState('');
  const poster = useAuthenticatedMediaUrl(posterSrc);
  const wantsPlay = React.useRef(false);
  const prepare = async () => {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setError('');
    try { await api.prepareMediaPlayback(); setReady(true); }
    catch (e) { setError(friendlyError(e, 'play video')); }
    finally { inFlight.current = false; setBusy(false); }
  };
  // The player is prepared as soon as it appears: the browser then fetches only the start of the file (the first frame and the length),
  // and streams the rest by ranges when the person presses play.
  React.useEffect(() => { wantsPlay.current = false; setReady(false); setError(''); if (src && !props['aria-hidden']) void prepare(); }, [src]);
  React.useEffect(() => { if (ready && wantsPlay.current) void video.current?.play().catch(() => {}); }, [ready]);
  const play = async () => { wantsPlay.current = true; if (ready) void video.current?.play().catch(() => {}); else await prepare(); };
  return <div className="streaming-preview">
    <video {...props} aria-label={props['aria-label'] || 'Video preview'} preload="metadata" playsInline autoPlay={false} src={ready ? `${src}#t=0.1` : undefined} poster={poster}
      ref={node => { video.current=node; if(typeof ref==='function') ref(node); else if(ref) ref.current=node; }}
      onError={() => { setReady(false); setError('پخش ویدیو انجام نشد؛ برای تلاش دوباره روی پخش بزنید.'); }}/>
    {!ready && !props['aria-hidden'] ? <button type="button" className="btn btn-secondary streaming-play" disabled={busy} onClick={() => void play()}>{busy ? 'در حال اتصال…' : 'پخش ویدیو'}</button> : null}
    {error ? <p role="alert">{error}</p> : null}
  </div>;
});

export const AuthenticatedMedia = React.forwardRef<any, Props>((props, ref) => props.as === 'video'
  ? <StreamingVideo key={props.src} {...props} ref={ref}/>
  : <DownloadedMedia {...props} ref={ref}/>);
