"""Owned Motion scene assets. No arbitrary URLs, shell, or unconfirmed generation."""
import copy
import json
import re
import threading
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,ConfigDict
from app.job_access import get_job_for_request
from brain.storyboard import Scene
from brain import motion_so

router=APIRouter(prefix='/jobs',tags=['Motion scenes'])
_active=set()
_guard=threading.Lock()
_slots=threading.BoundedSemaphore(2)


class SceneRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    prompt:str=Field(min_length=3,max_length=10000)
    duration:float=Field(default=5,ge=.5,le=30,allow_inf_nan=False)
    aspect:Literal['9:16','16:9','1:1','4:5']='9:16'
    effort:Literal['light','medium','high']='light'
    background:str=Field(default='#101010',pattern=r'^#[0-9a-fA-F]{6}$')
    reference:str=''
    confirmed:bool=Field(default=False,strict=True)


def inventory(job):
    folder=job.dir/'generated'/'motion_so'
    rows=[]
    for file in sorted(folder.glob('*.json'))[:200]:
        if not re.fullmatch(r'[a-f0-9]{24}',file.stem):continue
        state=json.loads(file.read_text())
        ready=(folder/(file.stem+'.mp4')).is_file()
        rows.append({'id':file.stem,'status':'ready' if ready else state.get('status'),
            'remote_job_id':state.get('job_id'),'ready':ready,
            'url':f'/api/jobs/{job.id}/motion-scenes/{file.stem}/video' if ready else None})
    return rows


@router.get('/{job_id}/motion-scenes')
def list_scenes(job_id:str,request:Request):
    job=get_job_for_request(request,job_id)
    talking={}
    if (job.dir/'talking_reel.json').is_file():
        from app import talking_reel
        talking=talking_reel.public(talking_reel.load(job.dir))
    top=talking.get('style')=='talking_2'
    return {'configured':motion_so.configured(),'items':inventory(job),
            'timeline_supported':bool(job.plan_data) or top,'placement_kind':'talking_top' if top else 'broll',
            'sentences':talking.get('captions',[]) if top else [],'remote_cancel_supported':False}


@router.post('/{job_id}/motion-scenes',status_code=202)
def create_scene(job_id:str,body:SceneRequest,request:Request):
    job=get_job_for_request(request,job_id)
    if not body.confirmed:raise HTTPException(409,'Explicit approval of Motion credits and reference upload is required')
    if not motion_so.configured():raise HTTPException(409,'Motion is disabled or server key is missing')
    if body.reference:
        path=(job.dir/body.reference).resolve()
        if not path.is_relative_to(job.dir.resolve()) or not path.is_file() or path.suffix.lower() not in {'.png','.jpg','.jpeg','.webp'}:
            raise HTTPException(422,'Reference must be an image belonging to this job')
    with _guard:
        if job_id in _active:return {'status':'running'}
        if not _slots.acquire(blocking=False):raise HTTPException(429,'Motion worker is busy; no submission performed')
        _active.add(job_id)
    def run():
        from brain.lm_gateway import job_context,user_context
        job_token=job_context.set(job.id)
        user_token=user_context.set(str(request.state.user.id))
        try:
            scene=Scene(index=0,description=body.prompt,duration_s=body.duration,motion_engine='motion_so',
                motion_effort=body.effort,motion_background=body.background,source_asset=body.reference)
            motion_so.generate_scene(scene,job.dir,body.aspect)
        except Exception:
            # Durable per-session state remains available; never auto-retry paid work.
            import logging
            logging.getLogger(__name__).warning('Motion scene stopped for job %s; inspect persisted status',job_id)
        finally:
            job_context.reset(job_token);user_context.reset(user_token)
            with _guard:_active.discard(job_id)
            _slots.release()
    threading.Thread(target=run,daemon=True).start()
    return {'status':'accepted'}


def clip(job,key):
    if not re.fullmatch(r'[a-f0-9]{24}',key):raise HTTPException(404,'Motion clip not found')
    path=job.dir/'generated'/'motion_so'/(key+'.mp4')
    if not path.is_file():raise HTTPException(404,'Motion clip is not ready')
    return path


@router.get('/{job_id}/motion-scenes/{key}/video')
def video(job_id:str,key:str,request:Request):
    return FileResponse(clip(get_job_for_request(request,job_id),key),media_type='video/mp4')


class Placement(BaseModel):
    model_config=ConfigDict(extra='forbid')
    at:float=Field(default=0,ge=0,allow_inf_nan=False)
    duration:float=Field(default=5,gt=0,le=30,allow_inf_nan=False)
    sentence_index:int|None=Field(default=None,ge=0)


@router.post('/{job_id}/motion-scenes/{key}/timeline')
def timeline(job_id:str,key:str,body:Placement,request:Request):
    from app import jobs
    job=get_job_for_request(request,job_id);path=clip(job,key)
    if (job.dir/'talking_reel.json').is_file():
        from app import talking_reel
        state=talking_reel.load(job.dir)
        if state.get('style')=='talking_2':
            if state.get('status') in {'running','paused'}:raise HTTPException(409,'Wait for the active talking render')
            allowed={row['i'] for row in talking_reel.public(state).get('captions',[])}
            if body.sentence_index not in allowed:raise HTTPException(422,'Choose an existing sentence')
            manifest=path.parent/'talking_panels.json'
            current=json.loads(manifest.read_text()) if manifest.is_file() else {'panels':[],'history':[]}
            rows=[row for row in current['panels'] if row['sentence']!=body.sentence_index]
            current['history'].append(current['panels'])
            current['panels']=rows+[{'sentence':body.sentence_index,'clip':key}]
            motion_so._write(manifest,current)
            return {'ok':True,'placement':'talking_top','message':'Upper panel assigned. Render Talking 2 normally; no new media generation.'}
    if not job.plan_data:raise HTTPException(409,'This engine has no compatible generic timeline; use the downloaded clip in a supported editor')
    if job.render.status in {'running','queued'}:raise HTTPException(409,'Wait for the active render')
    plan=copy.deepcopy(job.plan_data)
    entry={'at':body.at,'duration':body.duration,'file':str(path.relative_to(job.dir)),'in':0.0}
    if entry in plan.get('broll',[]):return {'ok':True,'reused':True}
    plan.setdefault('broll',[]).append(entry)
    _,errors=jobs.save_plan(job,plan,source='user_ui')
    if errors:raise HTTPException(422,errors)
    return {'ok':True,'reused':False}
