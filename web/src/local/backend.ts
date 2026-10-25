/** Verify this origin before sending original media to a claimed LAN installation. */
export async function verifyLocalBackend() {
  const response = await fetch('/api/health', {cache:'no-store', signal: AbortSignal.timeout(5000)});
  if (!response.ok) throw new Error('Local backend is not responding. Nothing was uploaded.');
  const health = await response.json();
  if (health.local_installation === true) return;
  const runtime = await fetch('/__local/runtime', {cache:'no-store', signal: AbortSignal.timeout(5000)});
  if (runtime.ok && health.ok === true && (await runtime.json()).localBackend === true) return;
  throw new Error('This origin is not a verified local EditorGPT installation. Open your Mac’s EditorGPT address first.');
}
