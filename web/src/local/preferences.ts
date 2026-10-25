export type ProcessingMode = "online" | "device" | "lan";
export type ProcessingPreferences = { mode: ProcessingMode; localApp: string; worker: string; engine: "auto" | "device" | "lan" | "cloud" };
const KEY = "editorgpt.processing.v1";
export function processingPreferences(): ProcessingPreferences {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) || "{}");
    return { mode: ["online","device","lan"].includes(saved.mode) ? saved.mode : "online", localApp: typeof saved.localApp === "string" ? saved.localApp : "", worker: typeof saved.worker === "string" ? saved.worker : "", engine: ["auto","device","lan","cloud"].includes(saved.engine) ? saved.engine : "auto" };
  } catch { return { mode: "online", localApp: "", worker: "", engine: "auto" }; }
}
export function setProcessingPreferences(value: ProcessingPreferences) {
  localStorage.setItem(KEY, JSON.stringify(value));
  window.dispatchEvent(new Event("editorgpt-processing"));
}
export function localApplicationURL(input: string) {
  const url = new URL(input);
  const parts=url.hostname.split('.').map(Number);
  const ipv4=parts.length===4 && parts.every(n=>Number.isInteger(n)&&n>=0&&n<=255);
  const privateHost = (ipv4&&(parts[0]===127||parts[0]===10||(parts[0]===192&&parts[1]===168)||(parts[0]===172&&parts[1]>=16&&parts[1]<=31))) || url.hostname === "localhost" || url.hostname.endsWith(".local");
  if (!privateHost) throw new Error("LAN mode requires a private-network address or .local hostname, not the cloud domain");
  if (url.username || url.password || url.search || url.hash || !["/", "/studio", "/settings"].includes(url.pathname)) throw new Error("Use the local EditorGPT origin, without credentials or query");
  if (!["https:","http:"].includes(url.protocol)) throw new Error("Use an HTTP or HTTPS local installation address");
  return url.origin;
}
