"""Motion REST scene adapter: one submission, durable polling, owned local MP4.

Motion is a composition service, not an LLM or an audio provider. Its MP4 is
silent before entering the existing timeline; captions/TTS remain Editor-owned.
"""
from __future__ import annotations
import fcntl
import hashlib
import json
import math
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from app.config import settings
from brain.http_ssl import ssl_context
from brain.media_provider import MediaResult, _parse_resolution

BASE='https://api.motion.so/api/motion'


def secret():
    path=Path(settings.MOTION_API_KEY_FILE)
    return path.read_text().strip() if path.is_file() else ''


def configured():
    return bool(settings.MOTION_ENABLED and secret())


def client():
    return httpx.Client(verify=ssl_context(),timeout=httpx.Timeout(300,connect=10),follow_redirects=False)


def call(method,path,body=None):
    key=secret()
    if not key:raise ValueError('Motion API key is not configured')
    started=time.monotonic();r=None;result={};failure=None
    try:
        with client() as http:
            try:r=http.request(method,BASE+path,headers={'Authorization':'Bearer '+key},json=body)
            except httpx.HTTPError:
                raise RuntimeError('Motion connection uncertain; no automatic retry or new submission') from None
        if not r.is_success:raise RuntimeError(f'Motion HTTP {r.status_code}; no automatic retry')
        result=r.json();return result
    except Exception as exc:
        failure=str(exc);raise
    finally:
        # Log composition calls, not every polling tick. Signed URLs and bearer
        # credentials never enter the audit record.
        if path=='/sessions' and method=='POST':
            try:
                from .lm_gateway import safe,job_context,user_context,conversation_context
                from app import lm_store
                from datetime import datetime,timezone
                import uuid
                request={**(body or {})}
                request['attachments']=[{'name':v.get('name'),'type':v.get('type')} for v in request.get('attachments',[])]
                lm_store.log({'id':str(uuid.uuid4()),'timestamp':datetime.now(timezone.utc).isoformat(),
                    'user_id':user_context.get(),'job_id':job_context.get(),'conversation_id':conversation_context.get(),
                    'route':'motion_composition','task_id':'motion_composition','endpoint':'/sessions',
                    'requested_model':'motion/'+str((body or {}).get('effort','light')),'actual_model':result.get('engine'),
                    'provider':'motion_so','status':'failed' if failure else 'accepted','http_status':r.status_code if r is not None else None,
                    'latency_ms':round((time.monotonic()-started)*1000),'input_tokens':None,'output_tokens':None,'cost':None,
                    'request_message':safe(request,12000),'response_message':safe({k:result.get(k) for k in ('job_id','status','engine','effort')},12000),
                    'error':failure,'retry_count':0,'fallback_count':0})
            except Exception:
                import logging
                logging.getLogger(__name__).warning('Motion audit write failed; request was not repeated')


def discover():
    return call('GET','/engines')


def _storage_url(url):
    # Signed GCS upload/download URLs are the documented transport. Never forward
    # the API bearer token to storage, private hosts, redirects or arbitrary URLs.
    p=urlparse(url)
    if p.scheme!='https' or p.hostname!='storage.googleapis.com' or p.username or p.password or p.port not in (None,443):
        raise ValueError('Motion storage URL is not on the approved HTTPS host')
    return url


def upload(path):
    import mimetypes
    mime=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    limit=50*1024*1024 if mime.startswith('image/') else 500*1024*1024
    if path.stat().st_size>limit:raise ValueError('Motion reference exceeds upload limit')
    ticket=call('POST','/uploads',{'filename':path.name,'content_type':mime})
    if ticket.get('upload_method')!='POST':raise ValueError('Unsupported Motion upload contract')
    url=_storage_url(ticket['upload_url']);_storage_url(ticket['attachment_url'])
    with client() as http, path.open('rb') as file:
        result=http.post(url,data=ticket['upload_fields'],files={'file':(path.name,file,mime)})
        if not result.is_success:raise RuntimeError('Motion reference upload failed; not retried')
    return {'url':ticket['attachment_url'],'name':path.name,'type':mime.split('/')[0],'content_type':mime}


def _write(path,data):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(data,ensure_ascii=False));temporary.replace(path)


def _download(url,target):
    url=_storage_url(url)
    partial=target.with_suffix('.part')
    try:
        with client() as http, http.stream('GET',url) as response:
            response.raise_for_status()
            size=0
            with partial.open('wb') as out:
                for chunk in response.iter_bytes():
                    size+=len(chunk)
                    if size>500*1024*1024:raise ValueError('Motion output exceeds 500 MB')
                    out.write(chunk)
        from engine.probe import video_stream
        video_stream(partial)
        partial.replace(target)
    finally:partial.unlink(missing_ok=True)


def generate_scene(scene,job_dir,aspect,*,on_status=None,max_wait=1800):
    if not configured():raise ValueError('Motion is disabled or its server key is missing')
    duration=float(scene.duration_s)
    if not math.isfinite(duration) or not .5<=duration<=30:raise ValueError('Motion scene must be 0.5–30 seconds')
    root=Path(job_dir).resolve()
    references=[]
    if scene.source_asset:
        source=(root/scene.source_asset).resolve()
        if not source.is_relative_to(root) or not source.is_file():raise ValueError('Motion reference must belong to this job')
        references=[source]
    prompt=(f'Create exactly {duration:g} seconds of silent code-based motion graphics only. '
        f'Flat solid background {scene.motion_background}; one clear visual idea, restrained line art, '
        'shapes, charts and purposeful transitions. No AI image/video generation, no web search, '
        'no music, voiceover, sound effects, captions, titles, logos or text. Do not edit source footage. '
        'Use supplied reference images only if present. Keep important elements in central safe area. '
        f'Visual direction: {scene.media_prompt or scene.description}')
    body={'prompt':prompt[:12000],'engine':'motion','effort':scene.motion_effort,
          'duration':'<10s' if duration<10 else '10-30s','aspect_ratio':aspect}
    identity={**body,'references':[hashlib.sha256(p.read_bytes()).hexdigest() for p in references]}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:24]
    folder=root/'generated'/'motion_so';folder.mkdir(parents=True,exist_ok=True)
    state_file=folder/(key+'.json');output=folder/(key+'.mp4')
    with (folder/(key+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(state_file.read_text()) if state_file.exists() else {}
        cached_output=output.exists()
        if not cached_output:
            if not state:
                # Persist BEFORE the paid POST. An ambiguous response never creates another job.
                state={'status':'submitting','request':{**identity},'job_id':None}
                _write(state_file,state)
                try:
                    if references:body['attachments']=[upload(p) for p in references]
                    result=call('POST','/sessions',body)
                    remote=result.get('job_id','')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',remote):raise ValueError('Invalid Motion job ID')
                    state.update(job_id=remote,status=result.get('status','queued'))
                    _write(state_file,state)
                except Exception:
                    state['status']='submission_uncertain';_write(state_file,state);raise
            if not state.get('job_id'):
                raise ValueError('Motion submission is uncertain. Inspect Motion before any new paid attempt.')
            deadline=time.monotonic()+max(300,min(3600,max_wait))
            from .motion_messages import start_reader
            start_reader(state['job_id'],state_file,secret(),max_wait)
            while time.monotonic()<deadline:
                try:status=call('GET','/sessions/'+state['job_id'])
                except Exception:
                    state['status']='polling_paused';_write(state_file,state);raise
                state['status']=status.get('status');state['sources']=status.get('sources',[])
                _write(state_file,state)
                if on_status:on_status({'engine':'motion_so','job_id':state['job_id'],'status':state['status']})
                export=status.get('output') or {}
                if state['status'] in {'failed','awaiting_user_input'} or export.get('status')=='failed':
                    raise ValueError('Motion needs attention; open the existing Motion job. No resubmission performed.')
                if export.get('status')=='completed' and export.get('download_url'):
                    original=folder/(key+'.source.mp4')
                    if not original.exists():_download(export['download_url'],original)
                    width,height=_parse_resolution(aspect)
                    temporary=folder/(key+'.normalized.mp4')
                    subprocess.run(['ffmpeg','-y','-v','error','-i',str(original),'-map','0:v:0','-an',
                        '-vf',f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={scene.motion_background},fps=30,tpad=stop_mode=clone:stop_duration=30',
                        '-t',str(duration),'-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(temporary)],
                        check=True,capture_output=True,timeout=300)
                    from engine.probe import probe_duration,has_audio
                    if abs(probe_duration(temporary)-duration)>.1 or has_audio(temporary):raise ValueError('Motion normalization failed validation')
                    temporary.replace(output)
                    state['status']='ready';_write(state_file,state);break
                time.sleep(5)
            if not output.exists():raise TimeoutError('Motion is still processing; continue polling this same job, not a new generation')
        from engine.probe import probe
        info=probe(output);video=next(v for v in info['streams'] if v['codec_type']=='video')
        return MediaResult(file_path=str(output),source='motion_so',cost_usd=None,
            generation_id=state['job_id'],width=int(video['width']),height=int(video['height']),
            duration_s=duration,fps=30,metadata={'motion_job_id':state['job_id'],'engine':'motion',
                'effort':scene.motion_effort,'background':scene.motion_background,'audio_removed':True,
                'sources':state.get('sources',[]),'reused':cached_output})
