/** Origin/user scoped local drafts. Large files are streamed to OPFS, never arrayBuffer(). */
export type LocalAsset = { id: string; owner: string; name: string; type: string; size: number; modified: number; created: number; project: string; storage: "opfs" | "idb"; blob?: Blob };
const database = () => new Promise<IDBDatabase>((resolve, reject) => {
  const request = indexedDB.open("editorgpt-local-v1", 1);
  request.onupgradeneeded = () => { request.result.createObjectStore("assets", { keyPath: "id" }); request.result.createObjectStore("drafts"); };
  request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
});
async function operation<T>(store: string, mode: IDBTransactionMode, action: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await database();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(store, mode); const request = action(tx.objectStore(store));
    tx.oncomplete = () => { db.close(); resolve(request.result); };
    tx.onerror = tx.onabort = () => { db.close(); reject(tx.error || new Error("Local storage unavailable")); };
  });
}
export async function quota() {
  const value = await navigator.storage?.estimate?.() || {};
  return { used: value.usage || 0, limit: value.quota || 0, persistent: await navigator.storage?.persisted?.() || false };
}
async function directory() { return (await navigator.storage.getDirectory()).getDirectoryHandle("editorgpt-assets-v1", { create: true }); }
export async function saveAsset(file: File, owner: string, project: string): Promise<LocalAsset> {
  const space = await quota();
  if (space.limit && space.limit - space.used < file.size * 1.15 + 16 * 1024**2) throw new Error("Not enough browser storage. Free space or keep this file for this session only.");
  const id = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2,"0")).join("");
  const record: LocalAsset = { id, owner, project, name: file.name, size: file.size, type: file.type, modified: file.lastModified, created: Date.now(), storage: "idb" };
  if (typeof navigator.storage?.getDirectory === "function") {
    const dir = await directory();
    try {
      const handle = await dir.getFileHandle(id, { create: true });
      await file.stream().pipeTo(await handle.createWritable());
      record.storage = "opfs";
      await operation("assets", "readwrite", s => s.put(record));
    } catch (error) { await dir.removeEntry(id).catch(() => {}); throw error; }
  } else {
    if (file.size > 128 * 1024**2) throw new Error("This browser cannot persist large files. Kept in this session; reselect it after closing.");
    await operation("assets", "readwrite", s => s.put({ ...record, blob: file }));
  }
  return record;
}
export async function listAssets(owner: string, project?: string): Promise<LocalAsset[]> {
  const all = await operation<LocalAsset[]>("assets", "readonly", s => s.getAll());
  return all.filter(a => a.owner === owner && (!project || a.project === project));
}
export async function readAsset(record: LocalAsset): Promise<File> {
  const blob = record.storage === "opfs" ? await (await (await directory()).getFileHandle(record.id)).getFile() : record.blob;
  if (!blob) throw new Error("Local media was evicted; please select the original again.");
  return new File([blob], record.name, { type: record.type, lastModified: record.modified });
}
export async function removeAsset(id: string, owner: string) {
  const record = await operation<LocalAsset | undefined>("assets", "readonly", s => s.get(id));
  if (!record || record.owner !== owner) return;
  if (record.storage === "opfs") await (await directory()).removeEntry(id).catch(() => {});
  await operation("assets", "readwrite", s => s.delete(id));
}
export async function saveDraft(key: string, text: string) { await operation("drafts", "readwrite", s => s.put(text, key)); }
export async function loadDraft(key: string) { return await operation<string | undefined>("drafts", "readonly", s => s.get(key)) || ""; }

export async function mediaMetadata(file: File) {
  const url = URL.createObjectURL(file);
  try {
    if (file.type.startsWith("image/")) {
      const image = new Image(); image.src = url; await image.decode();
      return { width: image.naturalWidth, height: image.naturalHeight, duration: 0 };
    }
    return await new Promise<{ width: number; height: number; duration: number }>((resolve, reject) => {
      const element = document.createElement("video"); element.preload = "metadata"; element.playsInline = true;
      const timer = setTimeout(() => finish(new Error("Metadata unavailable; original file is still usable")), 10000);
      const finish = (error?: Error) => { clearTimeout(timer); const result = { width: element.videoWidth, height: element.videoHeight, duration: element.duration }; element.removeAttribute("src"); element.load(); error ? reject(error) : resolve(result); };
      element.onloadedmetadata = () => finish(); element.onerror = () => finish(new Error("Codec preview not supported on this device")); element.src = url;
    });
  } finally { URL.revokeObjectURL(url); }
}
