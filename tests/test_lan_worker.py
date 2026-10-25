import hashlib
import shutil
import subprocess
import time
import pytest
from fastapi.testclient import TestClient
from app.lan_worker import create_worker, CHUNK, asset_id

@pytest.fixture
def client(tmp_path):
    return TestClient(create_worker(tmp_path/'worker','pair-me',['http://localhost:5187'],['testserver']))

def token(client):
    result=client.post('/pair',json={'code':'pair-me'})
    assert result.status_code==200
    return {'Authorization':'Bearer '+result.json()['token']}

def upload(client,headers,data):
    chunks=[hashlib.sha256(data[n:n+CHUNK]).hexdigest() for n in range(0,len(data),CHUNK)]
    registered=client.post('/assets',headers=headers,json={'size':len(data),'chunks':chunks})
    assert registered.status_code==200
    record=registered.json()
    if not record['ready']:
        for n in record['missing']:
            assert client.put(f'/assets/{record["id"]}/{n}',headers=headers,content=data[n*CHUNK:(n+1)*CHUNK]).status_code==200
        assert client.post(f'/assets/{record["id"]}/complete',headers=headers).status_code==200
    return record

def test_pairing_auth_origin_limits(client):
    assert client.get('/health').status_code==401
    assert client.post('/pair',json={'code':'bad'}).status_code==401
    assert client.post('/pair',headers={'Origin':'https://evil.example'},json={'code':'pair-me'}).status_code==403
    headers=token(client)
    assert client.get('/health',headers=headers).status_code==200
    assert client.get('/health',headers={**headers,'Origin':'https://evil.example'}).status_code==403
    assert client.post('/jobs',headers=headers,json={'request_id':'request-0001','clips':[],'width':720,'height':1280,'command':'rm'}).status_code==422
    assert client.get('/health',headers={**headers,'Host':'evil.example'}).status_code==400

def test_resumable_chunks_and_per_pair_isolation(client):
    headers=token(client); data=b'hello world'
    digest=hashlib.sha256(data).hexdigest()
    body={'size':len(data),'chunks':[digest]}
    record=client.post('/assets',headers=headers,json=body).json()
    assert record['id']==asset_id(len(data),[digest])
    path=f'/assets/{record["id"]}/0'
    assert client.put(path,headers=headers,content=b'bad').status_code==422
    assert client.put(path,headers=headers,content=data).status_code==200
    assert client.post('/assets',headers=headers,json=body).json()['missing']==[]
    assert client.post(f'/assets/{record["id"]}/complete',headers=token(client)).status_code==404
    assert client.post(f'/assets/{record["id"]}/complete',headers=headers).status_code==200
    assert client.post('/assets',headers=headers,json=body).json()['ready']

def test_real_native_render_dedup_and_private_output(client,tmp_path):
    if not shutil.which('ffmpeg'): pytest.skip('Native FFmpeg is required')
    source=tmp_path/'input.mp4'
    subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-f','lavfi','-i','color=c=blue:s=160x120:r=30:d=1','-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
    headers=token(client); record=upload(client,headers,source.read_bytes())
    assert upload(client,headers,source.read_bytes())['ready']
    body={'request_id':'render-test-0001','clips':[{'asset':record['id'],'start':0,'end':.6}],'width':160,'height':120}
    first=client.post('/jobs',headers=headers,json=body); assert first.status_code==200
    jid=first.json()['id']
    assert client.post('/jobs',headers=headers,json=body).json()['id']==jid
    assert client.post('/jobs',headers=headers,json={**body,'width':162}).status_code==409
    for _ in range(200):
        state=client.get('/jobs/'+jid,headers=headers).json()
        if state['stage'] in {'Completed','Failed'}: break
        time.sleep(.05)
    assert state['stage']=='Completed',state
    assert client.get(f'/jobs/{jid}/output',headers=token(client)).status_code==404
    output=client.get(f'/jobs/{jid}/output',headers=headers)
    assert output.status_code==200 and output.content[4:8]==b'ftyp'
    assert output.headers['cache-control']=='no-store'
    target=tmp_path/'output.mp4';target.write_bytes(output.content)
    probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(target)],capture_output=True,text=True,check=True)
    assert .5<float(probe.stdout)<1
    assert client.delete('/assets',headers=headers).status_code==200
    assert client.get(f'/jobs/{jid}/output',headers=headers).status_code==404
