"""Opt-in render companion. Not mounted in the cloud API. No shell/URL inputs.

Run through scripts/lan_worker.py, with TLS for non-loopback connections.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from fastapi import FastAPI, Header, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict

CHUNK = 4 * 1024**2
MAX_ASSET = 2 * 1024**3
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
class Pair(Strict):
    code: str = Field(max_length=128)
class Asset(Strict):
    size: int = Field(gt=0, le=MAX_ASSET)
    chunks: list[str] = Field(min_length=1, max_length=512)
class Clip(Strict):
    asset: str = Field(pattern=r'^[a-f0-9]{64}$')
    start: float = Field(ge=0, le=7200)
    end: float = Field(gt=0, le=7200)
class Job(Strict):
    request_id: str = Field(pattern=r'^[a-zA-Z0-9-]{8,80}$')
    clips: list[Clip] = Field(min_length=1, max_length=8)
    width: int = Field(ge=64, le=1920, multiple_of=2)
    height: int = Field(ge=64, le=1920, multiple_of=2)

def asset_id(size, chunks):
    return hashlib.sha256((str(size)+':'+','.join(chunks)).encode()).hexdigest()

def create_worker(root: Path, pairing_code: str, origins: list[str], hosts: list[str]):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = root.resolve()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET','POST','PUT','DELETE'], allow_headers=['Authorization','Content-Type'], allow_credentials=False)
    @app.middleware('http')
    async def private_responses(request: Request, call_next):
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response
    lock = threading.RLock(); pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lan-render')
    sessions = {}; jobs = {}; attempts = {}; expires = time.time()+300
    processes = {}; manifests = {}
    def owner(authorization: str = Header(default=''), request: Request = None):
        token = authorization.removeprefix('Bearer ')
        key = hashlib.sha256(token.encode()).hexdigest()
        if not token or sessions.get(key, 0) < time.time(): raise HTTPException(401, 'Pair this device again')
        if request and request.headers.get('origin') and request.headers['origin'] not in origins: raise HTTPException(403, 'Origin not allowed')
        return key
    def directory(user):
        folder=root/user; folder.mkdir(exist_ok=True,mode=0o700); return folder
    def owned_job(user, jid):
        value=jobs.get(jid)
        if not value or value['owner']!=user: raise HTTPException(404,'Job not found')
        return value
    def disk_budget(extra=0):
        if shutil.disk_usage(root).free < extra + 512*1024**2: raise HTTPException(507,'Worker disk space is low')
        if sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) + extra > 10*1024**3: raise HTTPException(507,'Worker storage limit reached; clean completed jobs')
    @app.post('/pair')
    def pair(body: Pair, request: Request):
        if request.headers.get('origin') and request.headers['origin'] not in origins: raise HTTPException(403,'Origin not allowed')
        ip=request.client.host; now=time.time()
        with lock:
            recent=[t for t in attempts.get(ip,[]) if t>now-60]; attempts[ip]=recent+[now]
            if len(recent)>=6: raise HTTPException(429,'Too many pairing attempts')
            if now>expires or not hmac.compare_digest(body.code,pairing_code): raise HTTPException(401,'Invalid or expired pairing code')
            if len(sessions)>=32: raise HTTPException(429,'Restart companion to reset pairings')
            token=secrets.token_urlsafe(32); sessions[hashlib.sha256(token.encode()).hexdigest()]=now+86400
        return {'token':token,'expires_in':86400}
    @app.get('/health')
    def health(user=Depends(owner)):
        return {'ok':bool(shutil.which('ffmpeg') and shutil.which('ffprobe')),'operations':['trim','concat','resize','crop'],'max_asset_bytes':MAX_ASSET,'chunk_bytes':CHUNK,'time':time.time()}
    @app.post('/assets')
    def register(body: Asset,user=Depends(owner)):
        if len(body.chunks)!=(body.size+CHUNK-1)//CHUNK or any(len(x)!=64 or any(c not in '0123456789abcdef' for c in x) for x in body.chunks): raise HTTPException(422,'Invalid chunk manifest')
        aid=asset_id(body.size,body.chunks)
        with lock:
            if len(manifests)>=256 and (user,aid) not in manifests: raise HTTPException(429,'Too many pending assets')
            disk_budget(); folder=directory(user)/aid; folder.mkdir(exist_ok=True)
            manifests[(user,aid)]=body
            missing=[n for n in range(len(body.chunks)) if not (folder/f'{n}.part').exists()]
        return {'id':aid,'ready':(folder/'media').is_file(),'missing':missing}
    @app.put('/assets/{aid}/{index}')
    async def put_chunk(aid: str,index: int,request: Request,user=Depends(owner)):
        body=manifests.get((user,aid))
        if not body or index<0 or index>=len(body.chunks): raise HTTPException(404,'Asset not registered')
        expected=min(CHUNK,body.size-index*CHUNK)
        raw=bytearray()
        async for part in request.stream():
            if len(raw)+len(part)>expected: raise HTTPException(413,'Chunk too large')
            raw.extend(part)
        if len(raw)!=expected or hashlib.sha256(raw).hexdigest()!=body.chunks[index]: raise HTTPException(422,'Chunk hash mismatch')
        with lock:
            disk_budget(len(raw)); path=directory(user)/aid/f'{index}.part'; temp=path.with_suffix('.pending'); temp.write_bytes(raw); temp.replace(path)
        return {'ok':True}
    @app.post('/assets/{aid}/complete')
    def complete(aid: str,user=Depends(owner)):
        body=manifests.get((user,aid))
        if not body: raise HTTPException(404,'Asset not registered')
        folder=directory(user)/aid
        with lock:
            if (folder/'media').exists(): return {'ready':True}
            disk_budget(body.size)
            try:
                with (folder/'media.pending').open('wb') as output:
                    for n,digest in enumerate(body.chunks):
                        data=(folder/f'{n}.part').read_bytes()
                        if hashlib.sha256(data).hexdigest()!=digest: raise ValueError('Chunk mismatch')
                        output.write(data)
                (folder/'media.pending').replace(folder/'media')
                for n in range(len(body.chunks)): (folder/f'{n}.part').unlink()
            except (OSError,ValueError): raise HTTPException(409,'Upload incomplete; register again to resume')
        return {'ready':True}
    def execute(jid, user, spec):
        state=jobs[jid]; folder=directory(user)/jid; folder.mkdir(exist_ok=True)
        def run(command, seconds, base=0, span=95):
            if state['stage']=='Cancelled': raise RuntimeError('Cancelled')
            log=(folder/'ffmpeg.log').open('wb')
            process=subprocess.Popen(command, stdout=subprocess.PIPE,stderr=log)
            processes[jid]=process; deadline=time.monotonic()+1800
            try:
                # Poll progress without ever blocking cancellation on an unread stderr pipe.
                import queue
                lines=queue.Queue()
                def read_lines():
                    for line in process.stdout: lines.put(line)
                threading.Thread(target=read_lines,daemon=True).start()
                while process.poll() is None:
                    if state['stage']=='Cancelled' or time.monotonic()>deadline: process.terminate(); raise RuntimeError('Cancelled' if state['stage']=='Cancelled' else 'Render timeout')
                    try: line=lines.get(timeout=.3).decode(errors='replace').strip()
                    except queue.Empty: continue
                    if line.startswith('out_time_us='):
                        state['percent']=min(99,round(base+min(1,float(line.split('=')[1])/1e6/max(seconds,.1))*span))
                if process.returncode: raise RuntimeError('Native FFmpeg could not process this file')
            finally:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
                processes.pop(jid,None)
                log.close()
        try:
            state.update(stage='Processing',percent=0)
            paths=[]
            for n,clip in enumerate(spec.clips):
                source=directory(user)/clip.asset/'media'
                # Validate real media and restrict protocols; no URL/playlist/command from the client.
                probe=subprocess.run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,webm,avi','-show_streams','-show_format','-of','json',str(source)],capture_output=True,timeout=30,check=True)
                info=json.loads(probe.stdout)
                if not any(s.get('codec_type')=='video' for s in info.get('streams',[])) or clip.end>float(info['format']['duration'])+.05: raise ValueError('Invalid video or trim range')
                target=folder/f'clip-{n}.mp4'; paths.append(target)
                command=['ffmpeg','-nostdin','-y','-threads','2','-filter_threads','1','-protocol_whitelist','file,pipe','-format_whitelist','mov,matroska,webm,avi','-ss',str(clip.start),'-i',str(source)]
                if not any(s.get('codec_type')=='audio' for s in info['streams']): command+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
                command+=['-t',str(clip.end-clip.start),'-vf',f'scale={spec.width}:{spec.height}:force_original_aspect_ratio=increase,crop={spec.width}:{spec.height},setsar=1,format=yuv420p','-r','30','-map','0:v:0','-map','0:a:0' if any(s.get('codec_type')=='audio' for s in info['streams']) else '1:a:0','-c:v','libx264','-threads','2','-preset','veryfast','-c:a','aac','-ar','48000','-ac','2','-progress','pipe:1','-nostats',str(target)]
                state['stage']='Encoding'; run(command,clip.end-clip.start,n/len(spec.clips)*95,95/len(spec.clips))
            state.update(stage='Finalizing',percent=96)
            listing=folder/'concat.txt'; listing.write_text('\n'.join(f"file '{p.name}'" for p in paths))
            run(['ffmpeg','-nostdin','-y','-f','concat','-safe','1','-i',str(listing),'-c','copy','-movflags','+faststart','-progress','pipe:1','-nostats',str(folder/'output.mp4')],sum(c.end-c.start for c in spec.clips),96,0)
            if state['stage']!='Cancelled': state.update(stage='Completed',percent=100)
        except Exception as exc:
            if state['stage']!='Cancelled': state.update(stage='Failed',error=str(exc)[:300])
        finally:
            (folder/'state.json').write_text(json.dumps({k:v for k,v in state.items() if k!='owner'}))
            for part in folder.glob('clip-*.mp4'): part.unlink(missing_ok=True)
    @app.post('/jobs')
    def submit(body: Job,user=Depends(owner)):
        if any(c.end<=c.start for c in body.clips) or sum(c.end-c.start for c in body.clips)>600 or body.width*body.height>1920*1080: raise HTTPException(422,'Invalid duration or output dimensions')
        digest=hashlib.sha256((user+body.request_id).encode()).hexdigest()[:32]
        with lock:
            spec_hash=hashlib.sha256(body.model_dump_json().encode()).hexdigest()
            if digest in jobs:
                if jobs[digest]['spec_hash']!=spec_hash: raise HTTPException(409,'Request id already used for a different edit')
                return {k:v for k,v in jobs[digest].items() if k not in {'owner','spec_hash'}}
            if any(v['owner']==user and v['stage'] in {'Preparing','Processing','Encoding','Finalizing'} for v in jobs.values()): raise HTTPException(409,'A render is already active for this device')
            if any(not (directory(user)/c.asset/'media').is_file() for c in body.clips): raise HTTPException(422,'Upload assets first')
            disk_budget(); jobs[digest]={'id':digest,'owner':user,'stage':'Preparing','percent':0,'created':time.time(),'spec_hash':spec_hash}
            pool.submit(execute,digest,user,body)
        return {k:v for k,v in jobs[digest].items() if k!='owner'}
    @app.get('/jobs/{jid}')
    def status(jid: str,user=Depends(owner)): return {k:v for k,v in owned_job(user,jid).items() if k!='owner'}
    @app.delete('/jobs/{jid}')
    def cancel(jid: str,user=Depends(owner)):
        value=owned_job(user,jid)
        if value['stage'] not in {'Completed','Failed'}: value['stage']='Cancelled'
        return {'ok':True}
    @app.get('/jobs/{jid}/output')
    def output(jid: str,user=Depends(owner)):
        value=owned_job(user,jid)
        if value['stage']!='Completed': raise HTTPException(409,'Output not ready')
        return FileResponse(directory(user)/jid/'output.mp4',media_type='video/mp4',filename='EditorGPT.mp4',headers={'Cache-Control':'no-store'})
    @app.delete('/assets')
    def cleanup(user=Depends(owner)):
        with lock:
            if any(v['owner']==user and v['stage'] in {'Preparing','Processing','Encoding','Finalizing'} for v in jobs.values()): raise HTTPException(409,'Wait for active renders')
            shutil.rmtree(directory(user))
            for key in [k for k,v in jobs.items() if v['owner']==user]: jobs.pop(key)
            for key in [k for k in manifests if k[0]==user]: manifests.pop(key)
        return {'ok':True}
    return app
