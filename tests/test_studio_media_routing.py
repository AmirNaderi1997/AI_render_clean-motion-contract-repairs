import base64
import io
from PIL import Image
from brain import lm_gateway as gateway, lm_adapters
from brain.media_provider import get_provider


def test_configured_image_generation_uses_database_gateway_route(monkeypatch,tmp_path):
    monkeypatch.setattr(gateway,'configured',lambda:True)
    monkeypatch.setattr(gateway,'defaults',lambda:{'photorealistic_image':{'enabled':True}})
    image=io.BytesIO();Image.new('RGB',(32,32),'blue').save(image,format='PNG')
    calls=[]
    def complete(route,prompt,**kwargs):
        calls.append((route,prompt,kwargs))
        return {'model':'tested-image','data':[{'b64_json':base64.b64encode(image.getvalue()).decode()}]},{'requested_model':'tested-image','cost':None}
    monkeypatch.setattr(gateway,'complete',complete)
    provider=get_provider('arvan_image')
    assert provider.name=='lm_gateway'
    result=provider.generate_image('A landscape','9:16',tmp_path)
    assert Image.open(result.file_path).size==(32,32)
    assert calls[0][0]=='photorealistic_image'
    assert calls[0][2]['endpoint']=='image'


def test_media_payload_and_redaction():
    payload=lm_adapters.payload('image','exact-model','prompt',extra={'n':1,'size':'1024x1024'})
    assert payload=={'model':'exact-model','prompt':'prompt','n':1,'size':'1024x1024'}
    assert 'ABCDEF' not in gateway.safe({'b64_json':'ABCDEF'})


def test_tts_uses_gateway_instead_of_direct_transport(monkeypatch,tmp_path):
    from brain.tts import _generate_elevenlabs
    monkeypatch.setattr(gateway,'configured',lambda:True)
    calls=[]
    def speech(route,text,voice):
        calls.append((route,text,voice));return b'tested-audio'
    monkeypatch.setattr(gateway,'speech',speech)
    output=tmp_path/'sample.mp3'
    _generate_elevenlabs('سلام',str(output),voice_id='existing-voice')
    assert output.read_bytes()==b'tested-audio'
    assert calls==[('narration','سلام','existing-voice')]
