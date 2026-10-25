import type { EditSpec, Progress } from "./render";
export type Companion = { url: string; token: string };
export function workerURL(input: string) {
  const url = new URL(input);
  if (url.username || url.password || url.search || url.hash || url.pathname !== "/") throw new Error("Use only the worker origin, without credentials, path or query");
  if (url.protocol !== "https:" && !(url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname) && location.protocol !== "https:")) throw new Error("A LAN worker requires HTTPS trusted by this device. Production cannot connect to an HTTP worker.");
  return url.origin;
}
export async function workerRequest(worker: Companion, path: string, init: RequestInit = {}) {
  const response = await fetch(worker.url + path, { ...init, signal: init.signal || AbortSignal.timeout(30000), credentials: "omit", cache: "no-store", headers: { ...init.headers, Authorization: `Bearer ${worker.token}` } });
  if (!response.ok) throw new Error(`Worker ${response.status}: ${await response.text()}`);
  return response;
}
export async function pairWorker(url: string, code: string): Promise<Companion> {
  const origin = workerURL(url);
  const response = await fetch(origin + "/pair", { method: "POST", credentials: "omit", cache: "no-store", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code }), signal: AbortSignal.timeout(10000) });
  if (!response.ok) throw new Error("Pairing refused. Check code, trusted TLS, allowed origin and local-network permission.");
  const result = await response.json(); return { url: origin, token: result.token };
}
function hashes(file: File, signal: AbortSignal, progress: (n: number) => void): Promise<string[]> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./hash.worker.ts", import.meta.url), { type: "module" });
    const cleanup = () => { worker.terminate(); signal.removeEventListener("abort", abort); };
    const abort = () => { cleanup(); reject(new DOMException("Cancelled", "AbortError")); };
    worker.onmessage = event => { if (event.data.hashes) { cleanup(); resolve(event.data.hashes); } else if (event.data.error) { cleanup(); reject(new Error(event.data.error)); } else progress(event.data.progress); };
    worker.onerror = () => { cleanup(); reject(new Error("Hash worker failed")); };
    signal.addEventListener("abort", abort, { once: true }); if (signal.aborted) abort(); else worker.postMessage(file);
  });
}
export async function renderLAN(worker: Companion, files: File[], spec: EditSpec, signal: AbortSignal, progress: (p: Progress) => void, onJob: (id: string) => void): Promise<Blob> {
  if (!isSecureContext || !crypto.subtle) throw new Error("Secure LAN transfer hashing requires opening EditorGPT over HTTPS (or localhost on this computer).");
  if (spec.text) throw new Error("LAN subset does not yet support text overlays. Use device export or the existing cloud timeline.");
  const ids: string[] = []; let jid: string | null = null;
  const total = files.reduce((n, f) => n + f.size, 0); let sent = 0;
  try {
    for (const file of files) {
      const chunks = await hashes(file, signal, n => progress({ stage: "Preparing", percent: n, message: `Hashing ${file.name} locally` }));
      const manifest = await (await workerRequest(worker, "/assets", { method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ size: file.size, chunks }) })).json();
      if (!manifest.ready) {
        for (const index of manifest.missing) {
          const blob = file.slice(index * 4 * 1024**2, (index + 1) * 4 * 1024**2);
          await workerRequest(worker, `/assets/${manifest.id}/${index}`, { method: "PUT", signal, body: blob });
          sent += blob.size; progress({ stage: "Preparing", percent: Math.round(sent / total * 100), message: "Transferring missing chunks to your paired computer" });
        }
        await workerRequest(worker, `/assets/${manifest.id}/complete`, { method: "POST", signal });
      }
      ids.push(manifest.id);
    }
    const requestId = crypto.randomUUID();
    const job = await (await workerRequest(worker, "/jobs", { method: "POST", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ request_id: requestId, clips: ids.map(asset => ({ asset, start: spec.start, end: spec.end })), width: spec.width, height: spec.height }) })).json();
    jid = job.id; onJob(job.id);
    while (true) {
      signal.throwIfAborted();
      const state = await (await workerRequest(worker, `/jobs/${jid}`, { signal })).json();
      progress({ stage: state.stage, percent: state.percent, message: state.error || "Native FFmpeg on your paired computer" });
      if (state.stage === "Failed" || state.stage === "Cancelled") throw new Error(state.error || state.stage);
      if (state.stage === "Completed") return await (await workerRequest(worker, `/jobs/${jid}/output`, { signal })).blob();
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  } catch (error) {
    if (signal.aborted && signal.reason !== "detach" && jid) await workerRequest(worker, `/jobs/${jid}`, { method: "DELETE" }).catch(() => {});
    throw error;
  }
}

export async function recoverLAN(worker: Companion, jid: string, signal: AbortSignal, progress: (p: Progress) => void) {
  while (true) {
    signal.throwIfAborted();
    const state = await (await workerRequest(worker, `/jobs/${jid}`, { signal })).json();
    progress({ stage: state.stage, percent: state.percent, message: state.error || "Reconnected to the existing computer render; nothing regenerated." });
    if (state.stage === "Failed" || state.stage === "Cancelled") throw new Error(state.error || state.stage);
    if (state.stage === "Completed") return (await workerRequest(worker, `/jobs/${jid}/output`, { signal })).blob();
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
}
