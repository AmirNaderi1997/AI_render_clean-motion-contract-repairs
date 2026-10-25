// Which addresses the page renderer may reach: public ones only. Shared by the function and its test (no browser needed to run it).
import net from 'node:net';
import dns from 'node:dns/promises';

export function isPublicAddress(address) {
  if (net.isIPv4(address)) {
    const [a, b] = address.split('.').map(Number);
    if (a === 0 || a === 10 || a === 127 || a >= 224) return false;
    if (a === 100 && b >= 64 && b <= 127) return false;
    if (a === 169 && b === 254) return false;
    if (a === 172 && b >= 16 && b <= 31) return false;
    if (a === 192 && (b === 168 || (b === 0 && address.startsWith('192.0.0.')))) return false;
    if (a === 198 && (b === 18 || b === 19)) return false;
    return true;
  }
  if (net.isIPv6(address)) {
    const value = address.toLowerCase();
    if (value === '::' || value === '::1' || value.startsWith('fe8') || value.startsWith('fe9') || value.startsWith('fea') || value.startsWith('feb')) return false;
    if (value.startsWith('fc') || value.startsWith('fd')) return false;
    const mapped = value.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
    return mapped ? isPublicAddress(mapped[1]) : true;
  }
  return false;
}

const known = new Map();
export async function isPublicHost(hostname) {
  if (!hostname) return false;
  if (net.isIP(hostname)) return isPublicAddress(hostname);
  if (known.has(hostname)) return known.get(hostname);
  let allowed = false;
  try {
    const found = await dns.lookup(hostname, {all: true});
    allowed = found.length > 0 && found.every(item => isPublicAddress(item.address));
  } catch { allowed = false; }
  known.set(hostname, allowed);
  return allowed;
}

export async function isPublicUrl(value) {
  let parsed;
  try { parsed = new URL(value); } catch { return false; }
  if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) return false;
  return isPublicHost(parsed.hostname.replace(/^\[|\]$/g, ''));
}
