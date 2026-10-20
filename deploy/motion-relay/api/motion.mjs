import { createHash, timingSafeEqual } from 'node:crypto';
import { once } from 'node:events';

export const config = { api: { bodyParser: false } };

function authorized(req) {
  const key = req.headers['x-motion-relay-key'];
  const expected = process.env.MOTION_RELAY_KEY_SHA256 || '';
  if (typeof key !== 'string' || !/^[a-f0-9]{64}$/.test(expected)) return false;
  return timingSafeEqual(createHash('sha256').update(key).digest(), Buffer.from(expected, 'hex'));
}

export default async function handler(req, res) {
  if (!authorized(req)) return res.status(401).json({ error: 'unauthorized' });
  const query = new URL(req.url, 'https://relay.invalid').searchParams;
  const service = query.get('service');
  const method = req.method;
  let target;
  if (service === 'rest') {
    const path = query.get('path') || '';
    if (!((method === 'GET' && /^\/(engines|sessions\/[A-Za-z0-9_-]{1,128})$/.test(path)) ||
          (method === 'POST' && /^\/(sessions|uploads)$/.test(path)))) {
      return res.status(403).json({ error: 'path_not_allowed' });
    }
    target = 'https://api.motion.so/api/motion' + path;
  } else if (service === 'mcp' && method === 'POST') {
    target = 'https://mcp.motion.so/mcp';
  } else if (service === 'storage' && ['GET', 'POST'].includes(method)) {
    try {
      const url = new URL(query.get('url'));
      if (url.protocol !== 'https:' || url.hostname !== 'storage.googleapis.com' ||
          url.username || url.password || (url.port && url.port !== '443')) throw Error();
      target = url.href;
    } catch { return res.status(403).json({ error: 'storage_not_allowed' }); }
    // Bound every media response below Vercel's function payload limit.
    if (method === 'GET') {
      const match = /^bytes=(\d+)-(\d+)$/.exec(req.headers.range || '');
      if (!match || Number(match[2]) < Number(match[1]) || Number(match[2]) - Number(match[1]) >= 1048576) {
        return res.status(400).json({ error: 'bounded_range_required' });
      }
    }
  } else return res.status(403).json({ error: 'service_not_allowed' });

  const headers = new Headers();
  for (const name of ['content-type', 'accept', 'range', 'if-range', 'mcp-session-id', 'mcp-protocol-version']) {
    if (typeof req.headers[name] === 'string') headers.set(name, req.headers[name]);
  }
  if (service !== 'storage') headers.set('authorization', 'Bearer ' + req.headers['x-motion-relay-key']);
  let body;
  if (method === 'POST') {
    const chunks = []; let size = 0;
    for await (const chunk of req) {
      size += chunk.length;
      if (size > 4_000_000) return res.status(413).json({ error: 'reference_too_large' });
      chunks.push(chunk);
    }
    body = Buffer.concat(chunks);
    if (service === 'mcp') {
      try {
        const rpc = JSON.parse(body.toString());
        if (!['initialize', 'notifications/initialized', 'tools/list'].includes(rpc.method) &&
            !(rpc.method === 'tools/call' && rpc.params?.name === 'list_chat_messages')) {
          return res.status(403).json({ error: 'read_only_mcp' });
        }
      } catch { return res.status(400).json({ error: 'invalid_json' }); }
    }
  }
  try {
    const upstream = await fetch(target, { method, headers, body, redirect: 'manual', signal: AbortSignal.timeout(280_000) });
    if (upstream.status >= 300 && upstream.status < 400) return res.status(502).json({ error: 'redirect_refused' });
    if (service === 'storage' && method === 'GET' && upstream.status !== 206) {
      return res.status(502).json({ error: 'storage_range_not_supported' });
    }
    res.statusCode = upstream.status;
    for (const name of ['content-type', 'content-range', 'etag', 'mcp-session-id', 'mcp-protocol-version']) {
      const value = upstream.headers.get(name); if (value) res.setHeader(name, value);
    }
    res.setHeader('cache-control', 'no-store');
    res.setHeader('x-editorgpt-relay', 'motion-vercel');
    let size = 0;
    if (upstream.body) for await (const chunk of upstream.body) {
      size += chunk.length;
      if (size > 4_000_000) { res.destroy(); return; }
      if (!res.write(chunk)) await once(res, 'drain');
    }
    res.end();
  } catch (error) {
    console.warn('motion_relay_transport_failure', { name: error?.name, code: error?.cause?.code });
    if (res.headersSent) res.destroy();
    else res.status(502).json({ error: 'upstream_uncertain_no_retry' });
  }
}
