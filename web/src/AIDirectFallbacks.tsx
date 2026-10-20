import React from "react";
import { aiAdminRequest } from "./api";

type Provider = {
  id: string; title: string; enabled: boolean; base_url: string; model: string; format: "openai" | "gemini";
  extra_header_name: string; configured: boolean; key_hint: string; key_source: "saved" | "environment" | null; extra_header_set: boolean;
};
type Status = { enabled: boolean; providers: Provider[]; stt?: {enabled: boolean; model: string; improve_low_quality: boolean} };
type TestResult = { ok: boolean; model: string; latency_ms: number; reply?: string; error?: string };

const json = (body: unknown, method = "PUT"): RequestInit => ({ method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
const message = (error: unknown) => (error instanceof Error ? error.message : String(error));

/** Admin tab: keys (write-only), order, on/off and a test button for the direct provider fallbacks. */
export default function DirectFallbacks() {
  const [state, setState] = React.useState<Status | null>(null);
  const [keys, setKeys] = React.useState<Record<string, string>>({});
  const [headers, setHeaders] = React.useState<Record<string, string>>({});
  const [tests, setTests] = React.useState<Record<string, TestResult | "running">>({});
  const [busy, setBusy] = React.useState("");
  const [notice, setNotice] = React.useState("");
  const [error, setError] = React.useState("");
  const [dirty, setDirty] = React.useState(false);

  const load = React.useCallback(() => aiAdminRequest<Status>("/direct").then(value => { setState(value); setDirty(false); }).catch(e => setError(message(e))), []);
  React.useEffect(() => { void load(); }, [load]);

  async function run(name: string, task: () => Promise<unknown>, done: string) {
    setBusy(name); setError(""); setNotice("");
    try { await task(); setNotice(done); } catch (e) { setError(message(e)); } finally { setBusy(""); }
  }
  const change = (id: string, patch: Partial<Provider>) => { setDirty(true); setState(value => value && { ...value, providers: value.providers.map(p => p.id === id ? { ...p, ...patch } : p) }); };
  const move = (index: number, delta: number) => setState(value => {
    if (!value) return value;
    const next = [...value.providers]; const target = index + delta;
    if (target < 0 || target >= next.length) return value;
    [next[index], next[target]] = [next[target], next[index]]; setDirty(true);
    return { ...value, providers: next };
  });
  const saveConfig = () => run("config", async () => {
    if (!state) return;
    const body = { enabled: state.enabled, stt: state.stt, providers: state.providers.map(({ id, enabled, base_url, model, format, extra_header_name }) => ({ id, enabled, base_url, model, format, extra_header_name })) };
    setState(await aiAdminRequest<Status>("/direct", json(body))); setDirty(false);
  }, "Settings saved. New requests use them immediately.");
  const saveSecret = (id: string, kind: "key" | "header", value: string | null) => run(`${kind}-${id}`, async () => {
    setState(await aiAdminRequest<Status>(`/direct/${id}/${kind}`, json({ value })));
    (kind === "key" ? setKeys : setHeaders)(current => ({ ...current, [id]: "" }));
  }, value ? "Saved. The value is write-only and is not shown again." : "Removed.");
  const test = async (id: string) => {
    setTests(current => ({ ...current, [id]: "running" }));
    try { const result = await aiAdminRequest<TestResult>(`/direct/${id}/test`, { method: "POST" }); setTests(current => ({ ...current, [id]: result })); }
    catch (e) { setTests(current => ({ ...current, [id]: { ok: false, model: "", latency_ms: 0, error: message(e) } })); }
  };

  if (!state) return <section>{error ? <p role="alert" className="ai-alert">{error}</p> : <p role="status">Loading…</p>}</section>;
  return <section className="ai-direct">
    <h2>Direct fallbacks</h2>
    <p className="eg-muted">When LM API fails (timeout, rate limit, server error, no usable model), a text request is sent straight to the providers below, in this order, until one answers. Images, speech and video are not affected. Keys are write-only: they are stored privately on the server and never shown again.</p>
    {error && <p role="alert" className="ai-alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {state.stt && <section className="ai-direct-card">
      <h3>Speech-to-text fallback · Local Whisper</h3>
      <p className="eg-muted">Runs locally after the primary STT fails. No second paid transcription request. Low-confidence text can be corrected through the configured AI route; raw words and timestamps remain recoverable.</p>
      <label><input type="checkbox" checked={state.stt.enabled} onChange={e=>{setDirty(true);setState({...state,stt:{...state.stt!,enabled:e.target.checked}});}}/> Enable local STT fallback</label>
      <label>Whisper model<select value={state.stt.model} onChange={e=>{setDirty(true);setState({...state,stt:{...state.stt!,model:e.target.value}});}}>{['base','small','medium','large-v3'].map(m=><option key={m}>{m}</option>)}</select></label>
      <label><input type="checkbox" checked={state.stt.improve_low_quality} onChange={e=>{setDirty(true);setState({...state,stt:{...state.stt!,improve_low_quality:e.target.checked}});}}/> Improve low-confidence text with AI</label>
    </section>}

    <label className="ai-direct-master">
      <input type="checkbox" checked={state.enabled} onChange={event => { setDirty(true); setState({ ...state, enabled: event.target.checked }); }}/>
      <span><b>Use direct provider fallbacks</b><small>{state.enabled ? "On: used only after LM API fails." : "Off: LM API errors are returned as they are."}</small></span>
    </label>

    <ol className="ai-direct-list">
      {state.providers.map((provider, index) => {
        const result = tests[provider.id];
        return <li key={provider.id} className="ai-direct-card" data-off={!state.enabled || !provider.enabled || undefined}>
          <header>
            <b>{index + 1}. {provider.title}</b>
            <span className="ai-badge">{provider.configured ? `Key ${provider.key_hint} · ${provider.key_source}` : "No key"}</span>
            <span className="ai-direct-actions">
              <button type="button" aria-label={`Move ${provider.title} up`} disabled={index === 0} onClick={() => move(index, -1)}>↑</button>
              <button type="button" aria-label={`Move ${provider.title} down`} disabled={index === state.providers.length - 1} onClick={() => move(index, 1)}>↓</button>
            </span>
          </header>
          <div className="ai-form-grid">
            <label>Base URL<input value={provider.base_url} onChange={event => change(provider.id, { base_url: event.target.value })} dir="ltr" spellCheck={false}/></label>
            <label>Model<input value={provider.model} onChange={event => change(provider.id, { model: event.target.value })} dir="ltr" spellCheck={false}/></label>
            <label>API format<select value={provider.format} onChange={event => change(provider.id, { format: event.target.value as Provider["format"] })}><option value="openai">OpenAI-compatible (chat/completions)</option><option value="gemini">Gemini native (generateContent)</option></select></label>
            <label>Extra header name (optional)<input value={provider.extra_header_name} onChange={event => change(provider.id, { extra_header_name: event.target.value })} placeholder="e.g. x-relay-secret" dir="ltr" spellCheck={false}/></label>
          </div>
          <div className="ai-toolbar">
            <input type="password" autoComplete="off" aria-label={`${provider.title} API key`} placeholder={provider.configured ? "Paste a new key to replace" : "Paste API key"} value={keys[provider.id] || ""} onChange={event => setKeys({ ...keys, [provider.id]: event.target.value })} dir="ltr"/>
            <button type="button" disabled={!keys[provider.id] || !!busy} onClick={() => void saveSecret(provider.id, "key", keys[provider.id])}>Save key</button>
            <button type="button" disabled={provider.key_source !== "saved" || !!busy} onClick={() => void saveSecret(provider.id, "key", null)}>Remove saved key</button>
          </div>
          {provider.extra_header_name && <div className="ai-toolbar">
            <input type="password" autoComplete="off" aria-label={`${provider.title} extra header value`} placeholder={provider.extra_header_set ? "Header value is set; paste to replace" : "Header value"} value={headers[provider.id] || ""} onChange={event => setHeaders({ ...headers, [provider.id]: event.target.value })} dir="ltr"/>
            <button type="button" disabled={!headers[provider.id] || !!busy} onClick={() => void saveSecret(provider.id, "header", headers[provider.id])}>Save header value</button>
          </div>}
          <div className="ai-direct-foot">
            <label><input type="checkbox" checked={provider.enabled} onChange={event => change(provider.id, { enabled: event.target.checked })}/> Enabled</label>
            <button type="button" disabled={!provider.configured || result === "running"} onClick={() => void test(provider.id)}>{result === "running" ? "Testing…" : "Test"}</button>
            {result && result !== "running" && <span role="status" className={result.ok ? "ok" : "errors"}>{result.ok ? `Works · ${result.model} · ${result.latency_ms} ms` : `Failed · ${result.error}`}</span>}
          </div>
        </li>;
      })}
    </ol>
    <p className="eg-muted">Gemini defaults to the Vercel AI Gateway (OpenAI-compatible, model prefix <code>google/</code>). For your own Vercel-hosted relay of the Google API, set its URL and choose “Gemini native”. Arvan, OpenAI and Gemini keys already in the server environment are reused automatically.</p>
    <button type="button" disabled={!dirty || busy === "config"} onClick={() => void saveConfig()}>{busy === "config" ? "Saving…" : "Save settings"}</button>
  </section>;
}
