"""Mandatory Vercel relay for Motion REST, MCP and signed storage traffic.

No direct-network fallback and no retries, including on uncertain POSTs.
"""
from urllib.parse import urlencode, urlsplit
import httpx
from app.config import settings
from brain.http_ssl import ssl_context


def relay_url():
    value = settings.MOTION_PROXY_URL.strip().rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or
            not parsed.hostname.endswith('.vercel.app') or parsed.username or
            parsed.password or parsed.port not in (None, 443) or parsed.query or parsed.fragment):
        raise ValueError('MOTION_PROXY_URL must configure an HTTPS Vercel relay')
    return value


class MotionRelayTransport(httpx.BaseTransport):
    def __init__(self, key, upstream=None):
        self.key = key
        self.base = relay_url()
        self.upstream = upstream or httpx.HTTPTransport(verify=ssl_context(), retries=0)

    def handle_request(self, request):
        url = request.url
        if url.scheme != 'https' or url.port not in (None, 443) or url.userinfo:
            raise ValueError('Unapproved Motion upstream')
        if url.host == 'api.motion.so' and url.path.startswith('/api/motion/'):
            params = {'service': 'rest', 'path': url.path.removeprefix('/api/motion')}
        elif url.host == 'mcp.motion.so' and url.path == '/mcp':
            params = {'service': 'mcp'}
        elif url.host == 'storage.googleapis.com':
            params = {'service': 'storage', 'url': str(url)}
        else:
            raise ValueError('Unapproved Motion upstream')
        headers = dict(request.headers)
        headers['host'] = urlsplit(self.base).netloc
        headers['x-motion-relay-key'] = self.key
        if params['service'] == 'storage':
            headers.pop('authorization', None)
        forwarded = httpx.Request(request.method, self.base + '?' + urlencode(params),
            headers=headers, stream=request.stream, extensions=request.extensions)
        return self.upstream.handle_request(forwarded)

    def close(self):
        self.upstream.close()


def client(key, timeout=300):
    return httpx.Client(transport=MotionRelayTransport(key),
        timeout=httpx.Timeout(timeout, connect=10), follow_redirects=False, trust_env=False)
