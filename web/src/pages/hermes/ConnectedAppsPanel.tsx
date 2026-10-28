import { useEffect, useRef, useState } from 'react';
import hermesApi from '../../services/hermesApi';
import { message } from './hermesUtils';

type Status = { configured: boolean; enabled: boolean; applications: string[]; external_actions_enabled: boolean };
type AppConnection = { application: string; name: string; connected: boolean; status: string };

export default function ConnectedAppsPanel() {
  const [status, setStatus] = useState<Status | null>(null);
  const [connections, setConnections] = useState<AppConnection[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    hermesApi.getComposioSettings({ signal: controller.signal })
      .then((result: Status) => { if (mounted.current) setStatus(result); })
      .catch((e: unknown) => { if (!controller.signal.aborted) setError(message(e)); });
    return () => { mounted.current = false; controller.abort(); };
  }, []);

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError('');
    try { await action(); }
    catch (e) { if (mounted.current) setError(message(e)); }
    finally { if (mounted.current) setBusy(false); }
  }

  function toggle() {
    void run(async () => {
      const result = await hermesApi.setComposioEnabled(!status?.enabled);
      if (mounted.current) { setStatus(result); setConnections([]); }
    });
  }

  function refresh() {
    void run(async () => {
      const result = await hermesApi.getComposioConnections();
      if (mounted.current) setConnections(result.applications);
    });
  }

  function connect(application: string) {
    void run(async () => {
      const result = await hermesApi.connectComposioApp(application);
      const destination = new URL(result.redirect_url);
      if (destination.protocol !== 'https:' || destination.username || destination.password) {
        throw new Error('The authorization link is invalid.');
      }
      if (mounted.current) window.location.assign(destination.href);
    });
  }

  return <section className="hm-panel hm-form-panel" aria-busy={busy}>
    <div className="hm-section-title"><h3>Connected apps · Composio</h3>
      <span className="hm-muted" role="status" aria-live="polite">
        {busy ? 'Working…' : !status ? 'Checking…' : status.enabled ? 'Enabled' : 'Disabled'}
      </span>
    </div>
    <p className="hm-tiny">Connect supported services through their authorization page. Passwords and API keys are never requested here.</p>
    {error ? <div className="hm-alert" role="alert">{error}</div> : null}
    {status && !status.configured ? <p className="hm-tiny">Server configuration is required before connecting apps.</p> : null}
    <div className="hm-account-actions">
      <button className="hm-btn hm-btn-quiet" type="button" onClick={toggle}
        disabled={busy || !status || (!status.configured && !status.enabled)}>
        {status?.enabled ? 'Disable integration' : 'Enable integration'}
      </button>
      <button className="hm-btn hm-btn-quiet" type="button" onClick={refresh}
        disabled={busy || !status?.enabled || !status.configured}>Check connections</button>
    </div>
    {status?.enabled && status.configured ? status.applications.map(application => {
      const connection = connections.find(item => item.application === application);
      return <div className="hm-section-title" key={application}>
        <div><strong>{connection?.name || application}</strong>
          <p className="hm-tiny">{connection ? connection.connected ? 'Connected' : connection.status : 'Not checked'}</p>
        </div>
        <button className="hm-btn hm-btn-primary" type="button" disabled={busy}
          onClick={() => connect(application)}>{connection?.connected ? 'Connect another account' : 'Connect / reconnect'}</button>
      </div>;
    }) : null}
    <p className="hm-tiny">Disabling stops EditorGPT access; it does not revoke the provider account. External publishing and messaging are not enabled in this integration stage.</p>
  </section>;
}
