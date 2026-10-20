import httpx
import pytest
from brain.motion_transport import MotionRelayTransport, relay_url
from app.config import settings


@pytest.mark.parametrize('target,service', [
    ('https://api.motion.so/api/motion/engines', 'rest'),
    ('https://mcp.motion.so/mcp', 'mcp'),
    ('https://storage.googleapis.com/bucket/file?signature=opaque', 'storage'),
])
def test_only_relay_receives_motion_traffic(target, service):
    requests=[]
    def handler(request):
        requests.append(request)
        assert request.url.host == 'editorgpt-motion-relay.vercel.app'
        assert request.headers['host'] == request.url.host
        assert request.url.params['service'] == service
        assert request.headers['x-motion-relay-key'] == 'fake-motion-key'
        if service == 'storage':
            assert 'authorization' not in request.headers
            assert request.url.params['url'] == target
        else:
            assert request.headers['authorization'] == 'Bearer fake-motion-key'
        return httpx.Response(200, json={'ok':True},headers={'mcp-session-id':'session'})
    with httpx.Client(transport=MotionRelayTransport('fake-motion-key', httpx.MockTransport(handler))) as client:
        response=client.get(target, headers={'Authorization':'Bearer fake-motion-key'})
        assert response.headers['mcp-session-id']=='session'
    assert len(requests)==1


@pytest.mark.parametrize('target', ['http://api.motion.so/api/motion/engines',
    'https://127.0.0.1/x', 'https://api.motion.so.evil.org/x',
    'https://user@storage.googleapis.com/bucket'])
def test_rejects_unapproved_upstreams(target):
    def handler(request):pytest.fail('Invalid URL must not access network')
    with httpx.Client(transport=MotionRelayTransport('fake',httpx.MockTransport(handler))) as client:
        with pytest.raises(ValueError):client.get(target)


def test_no_direct_or_automatic_retry():
    calls=[]
    def handler(request):
        calls.append(str(request.url));raise httpx.ReadTimeout('uncertain')
    with httpx.Client(transport=MotionRelayTransport('fake',httpx.MockTransport(handler))) as client:
        with pytest.raises(httpx.ReadTimeout):client.post('https://api.motion.so/api/motion/sessions',json={'prompt':'test'})
    assert len(calls)==1 and '.vercel.app/' in calls[0]


def test_missing_or_insecure_relay_fails_closed(monkeypatch):
    for url in ['', 'http://relay.vercel.app/api/motion','https://api.motion.so/api/motion']:
        monkeypatch.setattr(settings,'MOTION_PROXY_URL',url)
        with pytest.raises(ValueError):relay_url()


def test_download_assembles_validated_ranges_without_direct_fallback(monkeypatch,tmp_path):
    from brain import motion_so
    import engine.probe
    content=b'x'*1048576+b'end'
    requests=[]
    def handler(request):
        requests.append(request)
        start=int(request.headers['range'].split('=')[1].split('-')[0])
        chunk=content[start:start+1048576]
        return httpx.Response(206,content=chunk,headers={
            'content-range':f'bytes {start}-{start+len(chunk)-1}/{len(content)}','etag':'stable'})
    monkeypatch.setattr(motion_so,'client',lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(engine.probe,'video_stream',lambda _: {})
    target=tmp_path/'output.mp4'
    motion_so._download('https://storage.googleapis.com/bucket/file',target)
    assert target.read_bytes()==content and len(requests)==2
    assert requests[1].headers['if-range']=='stable'
    assert not target.with_suffix('.part').exists()


def test_invalid_storage_range_leaves_no_partial_output(monkeypatch,tmp_path):
    from brain import motion_so
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,content=b'unbounded')
    monkeypatch.setattr(motion_so,'client',lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    target=tmp_path/'output.mp4'
    with pytest.raises(ValueError,match='ranged'):motion_so._download('https://storage.googleapis.com/bucket/file',target)
    assert len(calls)==1 and not target.exists() and not target.with_suffix('.part').exists()
