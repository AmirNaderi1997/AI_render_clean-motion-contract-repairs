// Only one 4 MB chunk is materialized at once; File uses structured cloning, not a full-file copy.
const hex = (bytes: ArrayBuffer) => [...new Uint8Array(bytes)].map(n => n.toString(16).padStart(2, "0")).join("");
self.onmessage = async (event: MessageEvent<File>) => {
  try {
    const file = event.data; const hashes: string[] = [];
    for (let offset = 0; offset < file.size; offset += 4 * 1024**2) {
      hashes.push(hex(await crypto.subtle.digest("SHA-256", await file.slice(offset, offset + 4 * 1024**2).arrayBuffer())));
      self.postMessage({ progress: Math.round(Math.min(offset + 4 * 1024**2, file.size) / file.size * 100) });
    }
    self.postMessage({ hashes });
  } catch (error) { self.postMessage({ error: String(error) }); }
};
