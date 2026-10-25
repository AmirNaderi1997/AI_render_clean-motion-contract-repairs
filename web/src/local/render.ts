export type RenderStage = "Preparing" | "Processing" | "Encoding" | "Finalizing" | "Completed" | "Failed" | "Cancelled";
export type Progress = { stage: RenderStage; percent: number; message: string };
export type EditSpec = { width: number; height: number; start: number; end: number; text: string; operations: string[] };
export const DEVICE_OPERATIONS = ["trim", "concat", "resize", "crop", "text"];
export function unsupported(operations: string[]) { return operations.filter(op => !DEVICE_OPERATIONS.includes(op)); }
export function recommendation(capable: boolean, seconds: number, bytes: number, operations: string[], worker: boolean) {
  if (capable && seconds <= 120 && bytes <= 512 * 1024**2 && !unsupported(operations).length) return "device";
  return worker && operations.every(op => ["trim","concat","resize","crop"].includes(op)) ? "lan" : "cloud";
}
export function capabilities() {
  const mime = typeof MediaRecorder !== "undefined" ? ["video/mp4;codecs=avc1.42E01E,mp4a.40.2", "video/mp4", "video/webm;codecs=vp8,opus"].find(t => MediaRecorder.isTypeSupported(t)) : undefined;
  return { available: Boolean(mime && typeof HTMLCanvasElement.prototype.captureStream === "function" && typeof window.AudioContext === "function"), mime,
    secure: isSecureContext, webCodecs: "VideoEncoder" in window, offscreenCanvas: "OffscreenCanvas" in window,
    reason: mime ? "Real-time export; keep this app visible and the screen unlocked." : "No supported MediaRecorder output codec." };
}
const waitEvent = (target: EventTarget, event: string, signal: AbortSignal, timeout = 15000) => new Promise<void>((resolve, reject) => {
  const cleanup = () => { clearTimeout(timer); target.removeEventListener(event, done); target.removeEventListener("error", failed); signal.removeEventListener("abort", aborted); };
  const done = () => { cleanup(); resolve(); }; const failed = () => { cleanup(); reject(new Error("Media cannot be decoded on this device")); };
  const aborted = () => { cleanup(); reject(new DOMException("Cancelled", "AbortError")); };
  const timer = setTimeout(() => { cleanup(); reject(new Error(`Timed out waiting for media ${event}`)); }, timeout);
  target.addEventListener(event, done, { once: true }); target.addEventListener("error", failed, { once: true }); signal.addEventListener("abort", aborted, { once: true });
  if (signal.aborted) aborted();
});

/** A real bounded canvas/audio export. Not a replacement for FFmpeg or the AI timeline. */
export async function renderDevice(files: File[], spec: EditSpec, signal: AbortSignal, progress: (p: Progress) => void): Promise<Blob> {
  const cap = capabilities();
  if (!cap.available || !cap.mime) throw new Error(cap.reason);
  if (unsupported(spec.operations).length) throw new Error(`Unsupported operations: ${unsupported(spec.operations).join(", ")}`);
  if (!files.length || files.length > 8 || files.some(f => !f.type.startsWith("video/")) || files.reduce((n, f) => n + f.size, 0) > 512 * 1024**2) throw new Error("Device export supports up to 8 videos / 512 MB. Use an explicitly selected computer/cloud for other media.");
  if (![spec.width, spec.height, spec.start, spec.end].every(Number.isFinite) || spec.width < 64 || spec.height < 64 || spec.width > 1280 || spec.height > 1280 || spec.width * spec.height > 1280 * 720 || spec.start < 0 || spec.end <= spec.start || spec.end > 120) throw new Error("Device export requires a valid range (up to 120s) and dimensions up to 720p.");
  progress({ stage: "Preparing", percent: 0, message: "Decoding local media; nothing is uploaded." });
  const audio = new AudioContext(); await audio.resume();
  const destination = audio.createMediaStreamDestination();
  const canvas = document.createElement("canvas"); canvas.width = spec.width; canvas.height = spec.height;
  const context = canvas.getContext("2d"); if (!context) { await audio.close(); throw new Error("Canvas unavailable"); }
  context.fillStyle = "black"; context.fillRect(0, 0, canvas.width, canvas.height);
  const stream = canvas.captureStream(30); const videoTrack = stream.getVideoTracks()[0] as CanvasCaptureMediaStreamTrack;
  destination.stream.getAudioTracks().forEach(t => stream.addTrack(t));
  const recorder = new MediaRecorder(stream, { mimeType: cap.mime, videoBitsPerSecond: 3000000 });
  const chunks: Blob[] = []; let bytes = 0; let failure: Error | null = null; let video: HTMLVideoElement | null = null;
  const hidden = () => { if (document.hidden) failure = new Error("Device render interrupted because the app was backgrounded. Keep the screen unlocked and retry; no automatic upload occurred."); };
  document.addEventListener("visibilitychange", hidden);
  let recorderFailure: (error: Error) => void = () => {};
  const stopped = new Promise<void>((resolve, reject) => {
    recorder.onstop = () => resolve(); recorder.onerror = () => { const error = new Error("Encoder failed or ran out of resources"); failure = error; recorderFailure(error); reject(error); };
  });
  // Observe failures immediately, even while the playback loop is running.
  void stopped.catch(() => {});
  recorder.ondataavailable = event => { bytes += event.data.size; if (bytes > 96 * 1024**2) failure = new Error("Encoded output exceeded the 96 MB device safety limit"); else if (event.data.size) chunks.push(event.data); };
  try {
    let elapsed = 0; const total = (spec.end - spec.start) * files.length;
    if (total > 120) throw new Error("Combined device output must be at most 120 seconds");
    for (const file of files) {
      const url = URL.createObjectURL(file); video = document.createElement("video"); video.playsInline = true; video.preload = "auto";
      video.style.cssText = "position:fixed;width:1px;height:1px;opacity:.001;pointer-events:none;bottom:0";
      document.body.append(video);
      let source: MediaElementAudioSourceNode | undefined;
      try {
        const loaded = waitEvent(video, "loadedmetadata", signal); video.src = url; await loaded;
        if (spec.end > video.duration + .05) throw new Error(`End time exceeds ${file.name} duration (${video.duration.toFixed(1)}s)`);
        source = audio.createMediaElementSource(video); source.connect(destination);
        if (spec.start > 0) { const seeked = waitEvent(video, "seeked", signal); video.currentTime = spec.start; await seeked; }
        await video.play();
        if (recorder.state === "inactive") recorder.start(1000); else recorder.resume();
        const current = video; let last = performance.now(); let mediaTime = current.currentTime;
        await new Promise<void>((resolve, reject) => {
          recorderFailure = reject;
          const frame = () => {
            if (signal.aborted) { reject(new DOMException("Cancelled", "AbortError")); return; }
            if (failure) { reject(failure); return; }
            if (current.error) { reject(new Error("Media decoding failed")); return; }
            if (current.currentTime !== mediaTime) { last = performance.now(); mediaTime = current.currentTime; }
            if (performance.now() - last > 15000) { reject(new Error("Playback stalled; try a smaller supported file")); return; }
            const scale = Math.max(canvas.width / current.videoWidth, canvas.height / current.videoHeight);
            const w = current.videoWidth * scale, h = current.videoHeight * scale;
            context.drawImage(current, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
            if (spec.text) { context.fillStyle = "rgba(0,0,0,.75)"; context.fillRect(0, canvas.height * .82, canvas.width, canvas.height * .14); context.fillStyle = "white"; context.textAlign = "center"; context.font = `${Math.round(canvas.width / 24)}px sans-serif`; context.fillText(spec.text.slice(0, 180), canvas.width / 2, canvas.height * .91, canvas.width * .94); }
            videoTrack.requestFrame?.();
            progress({ stage: "Encoding", percent: Math.min(99, Math.round((elapsed + current.currentTime - spec.start) / total * 100)), message: "Encoding on this device (real time)" });
            if (current.currentTime >= spec.end || current.ended) { current.pause(); recorder.pause(); resolve(); return; }
            requestAnimationFrame(frame);
          }; frame();
        });
        elapsed += spec.end - spec.start;
      } finally { source?.disconnect(); video.pause(); video.removeAttribute("src"); video.load(); video.remove(); URL.revokeObjectURL(url); }
    }
    progress({ stage: "Finalizing", percent: 99, message: "Finalizing local output" });
    recorder.stop(); await stopped;
    const output = new Blob(chunks, { type: recorder.mimeType });
    if (!output.size) throw new Error("Encoder returned an empty output");
    progress({ stage: "Completed", percent: 100, message: "Saved locally; no cloud upload" }); return output;
  } finally {
    if (recorder.state !== "inactive") recorder.stop();
    document.removeEventListener("visibilitychange", hidden); stream.getTracks().forEach(t => t.stop()); await audio.close();
  }
}
