import React from "react";

type Doc = Document & { webkitFullscreenElement?: Element | null; webkitExitFullscreen?: () => Promise<void> | void };
type Box = HTMLElement & { webkitRequestFullscreen?: () => Promise<void> | void };
type Media = HTMLVideoElement & { webkitEnterFullscreen?: () => void };

/**
 * Fullscreen for a media container. The container (not just the video) goes fullscreen so overlay controls
 * stay on screen; iPhone Safari only fullscreens the <video> itself, so that is the fallback.
 */
export function useFullscreen(container: React.RefObject<HTMLElement | null>, video: React.RefObject<HTMLVideoElement | null>) {
  const [active, setActive] = React.useState(false);
  React.useEffect(() => {
    const sync = () => {
      const doc = document as Doc;
      setActive(Boolean(container.current) && (doc.fullscreenElement === container.current || doc.webkitFullscreenElement === container.current));
    };
    document.addEventListener("fullscreenchange", sync);
    document.addEventListener("webkitfullscreenchange", sync);
    return () => { document.removeEventListener("fullscreenchange", sync); document.removeEventListener("webkitfullscreenchange", sync); };
  }, [container]);
  const toggle = React.useCallback(async () => {
    const doc = document as Doc, box = container.current as Box | null, media = video.current as Media | null;
    try {
      if (doc.fullscreenElement || doc.webkitFullscreenElement) { await (doc.exitFullscreen?.() ?? doc.webkitExitFullscreen?.()); return; }
      if (box?.requestFullscreen) await box.requestFullscreen();
      else if (box?.webkitRequestFullscreen) await box.webkitRequestFullscreen();
      else media?.webkitEnterFullscreen?.();
    } catch { /* the browser refused (no user gesture, or blocked by policy); the controls stay as they are */ }
  }, [container, video]);
  const supported = typeof document !== "undefined" &&
    Boolean(document.fullscreenEnabled || (document as Doc & { webkitFullscreenEnabled?: boolean }).webkitFullscreenEnabled || (video.current as Media | null)?.webkitEnterFullscreen);
  return { active, toggle, supported };
}
