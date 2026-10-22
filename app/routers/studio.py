"""Authenticated API for the chat-first Video Studio."""
from __future__ import annotations

import asyncio
import copy
import json
import re
import shutil
from typing import Literal
from pathlib import Path

from fastapi import APIRouter, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings
from app import jobs as jobstore
from app.studio_orchestrator import cancel_project, confirm_action, dispatch_message, resume_project, sync_conversation
from app.studio_store import ROOT, repo
from app.studio_tools import list_tools
from app.job_access import get_job_for_request, is_local_auth_bypass

router = APIRouter(prefix="/studio", tags=["studio"])

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg"}
MAX_BYTES = {"video": 2 * 1024**3, "image": 25 * 1024**2, "audio": 100 * 1024**2}


def _user(request: Request) -> str:
    return str(request.state.user.id)


def _kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in VIDEO_EXTENSIONS: return "video"
    if suffix in IMAGE_EXTENSIONS: return "image"
    if suffix in AUDIO_EXTENSIONS: return "audio"
    raise HTTPException(422, "Only supported video, image and audio files can be attached")


def _public_project(project: dict) -> dict:
    """Remove server-only file paths while preserving asset indices for the UI."""
    result = copy.deepcopy(project)
    state = result.get("state") or {}
    assets = state.get("source_assets") or []
    state["source_assets"] = [{"index": index, "name": Path(str(item)).name} for index, item in enumerate(assets)]
    inspection = state.get("url_inspection")
    if isinstance(inspection, dict):
        for image in inspection.get("images") or []:
            if isinstance(image, dict):
                image.pop("file", None)
    result["state"] = state
    return result


def _public_conversation(conversation: dict) -> dict:
    result = copy.deepcopy(conversation)
    result["projects"] = [_public_project(item) for item in result.get("projects") or []]
    from app.studio_manual import question
    session = result.get('state', {}).get('manual_session')
    result['state']['manual_question'] = question(session) if session and session.get('question_id') else None
    return result


def _public_event(event: dict) -> dict:
    """Scrub legacy and current event payloads before they cross the API boundary."""
    result = copy.deepcopy(event)

    def scrub(value):
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()
                    if key not in {"file", "path", "source_path"}}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    result["data"] = scrub(result.get("data") or {})
    return result


class ConversationCreate(BaseModel):
    title: str = Field(default="گفتگوی جدید", max_length=255)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    status_voice_enabled: bool | None = None
    execution_mode: Literal["auto", "manual"] | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12_000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=20)
    execution_mode: Literal["auto", "manual"] | None = None
    manual_question_id: str | None = Field(default=None, max_length=64)


class StoryboardUpdate(BaseModel):
    scenes: list[dict] = Field(min_length=1, max_length=20)


class LegacyProjectOpen(BaseModel):
    engine: str = Field(pattern="^(motion|talking|localize)$")
    external_ref: str = Field(min_length=4, max_length=64, pattern="^[A-Za-z0-9_-]+$")
    title: str = Field(default="Video project", max_length=255)


@router.post("/conversations", status_code=201)
async def create_conversation(request: Request, body: ConversationCreate):
    return await repo.create_conversation(_user(request), body.title.strip() or "گفتگوی جدید")


@router.get("/conversations")
async def list_conversations(request: Request):
    return await repo.list_conversations(_user(request))


@router.post("/legacy/open")
async def open_legacy_project(request: Request, body: LegacyProjectOpen):
    """Attach an existing owned job to Studio without duplicating the engine job."""
    user_key = _user(request)
    for summary in await repo.list_conversations(user_key):
        conversation = await repo.get_conversation(summary["id"], user_key)
        if any(project.get("external_ref") == body.external_ref for project in conversation.get("projects", [])):
            return _public_conversation(conversation)

    if body.engine == "localize":
        from app import localize
        try:
            legacy = localize.load(body.external_ref)
        except KeyError as exc:
            raise HTTPException(404, "project not found") from exc
        if not is_local_auth_bypass(request) and str(legacy.get("user_id")) != user_key:
            raise HTTPException(403, "You do not have access to this project")
        title = str(legacy.get("title") or legacy.get("name") or body.title)
    else:
        job = get_job_for_request(request, body.external_ref)
        title = str(job.raw_name or (job.plan or {}).get("title") or body.title)

    conversation = await repo.create_conversation(user_key, title)
    project = await repo.create_project(conversation["id"], user_key, body.engine, title,
        {"last_observed": {}, "imported_legacy": True}, body.external_ref)
    await repo.add_message(conversation["id"], user_key, "assistant",
        "این پروژه به Studio اضافه شد. می‌توانید ادامهٔ تدوین و تغییرات بعدی را همین‌جا درخواست کنید.")
    await sync_conversation(conversation["id"], user_key)
    return _public_conversation(await repo.get_conversation(conversation["id"], user_key))


@router.get("/conversations/{conversation_id}")
async def get_conversation(request: Request, conversation_id: str):
    try:
        await sync_conversation(conversation_id, _user(request))
        return _public_conversation(await repo.get_conversation(conversation_id, _user(request)))
    except KeyError:
        raise HTTPException(404, "conversation not found")


@router.patch("/conversations/{conversation_id}")
async def update_conversation(request: Request, conversation_id: str, body: ConversationUpdate):
    try:
        changes = body.model_dump(exclude_unset=True)
        mode = changes.pop("execution_mode", None)
        if mode:
            old = await repo.get_conversation(conversation_id, _user(request))
            changes["state"] = {**old.get("state", {}), "execution_mode": mode}
            if mode == 'auto': changes['state']['manual_session'] = None
        return await repo.set_conversation(conversation_id, _user(request), **changes)
    except KeyError:
        raise HTTPException(404, "conversation not found")


@router.post("/conversations/{conversation_id}/attachments", status_code=201)
async def upload_attachment(request: Request, conversation_id: str, file: UploadFile = File(...)):
    user_key = _user(request)
    try:
        await repo.get_conversation(conversation_id, user_key)
    except KeyError:
        raise HTTPException(404, "conversation not found")
    original = Path(file.filename or "attachment").name
    kind = _kind(original); suffix = Path(original).suffix.lower()
    folder = ROOT / re.sub(r"[^A-Za-z0-9_-]", "_", user_key) / conversation_id / "attachments"
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f"uploading_{id(file)}{suffix}"
    size = 0
    try:
        with open(temporary, "wb") as target:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES[kind]: raise HTTPException(413, f"{kind} attachment is too large")
                target.write(chunk)
        if size == 0: raise HTTPException(422, "attachment is empty")
        # Decode/probe uploads now, before any engine sees them.
        if kind == "image":
            from PIL import Image
            with Image.open(temporary) as image:
                image.verify()
        else:
            from engine.probe import probe
            info = await asyncio.to_thread(probe, temporary)
            streams = info.get("streams", [])
            if kind == "video" and not any(item.get("codec_type") == "video" for item in streams):
                raise ValueError("file has no video stream")
            if kind == "audio" and not any(item.get("codec_type") == "audio" for item in streams):
                raise ValueError("file has no audio stream")
        attachment = await repo.create_attachment(conversation_id, user_key, kind=kind,
            filename=original[:255], path=str(temporary), mime_type=(file.content_type or "application/octet-stream")[:100],
            size_bytes=size, metadata={})
        target = folder / f"{attachment['id']}{suffix}"
        temporary.replace(target)
        if settings.DATABASE_URL:
            from app.database import AsyncSessionLocal
            from app.models import StudioAttachment
            assert AsyncSessionLocal is not None
            async with AsyncSessionLocal() as db:
                row = await db.get(StudioAttachment, attachment["id"]); row.path = str(target); await db.commit()
        else:
            from app import studio_store
            with studio_store._lock:
                data = studio_store._read(); data["attachments"][attachment["id"]]["path"] = str(target); studio_store._write(data)
        attachment["path"] = str(target)
        return {key: attachment[key] for key in ("id", "kind", "filename", "mime_type", "size_bytes")}
    except HTTPException:
        temporary.unlink(missing_ok=True); raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise HTTPException(422, "The attachment could not be validated") from exc


@router.get("/conversations/{conversation_id}/attachments/{attachment_id}")
async def get_attachment(request: Request, conversation_id: str, attachment_id: str):
    try:
        item = (await repo.get_attachments([attachment_id], conversation_id, _user(request)))[0]
    except (KeyError, IndexError):
        raise HTTPException(404, "attachment not found")
    path = Path(item["path"])
    if not path.is_file(): raise HTTPException(404, "attachment file is missing")
    return FileResponse(path, media_type=item.get("mime_type"), filename=item["filename"])


@router.post("/conversations/{conversation_id}/messages", status_code=202)
async def send_message(request: Request, conversation_id: str, body: MessageCreate):
    user_key = _user(request)
    try:
        conversation = await repo.get_conversation(conversation_id, user_key)
        if body.execution_mode:
            await repo.set_conversation(conversation_id, user_key, state={**conversation.get("state", {}), "execution_mode": body.execution_mode})
        await repo.get_attachments(body.attachment_ids, conversation_id, user_key)
        display = body.content.strip()
        session = conversation.get('state', {}).get('manual_session')
        if session and session.get('question_id') and session['question_id'] == body.manual_question_id:
            from app.studio_manual import question
            spec = question(session)
            selected = next((c for c in spec['choices'] if c['value'] == display), None)
            if selected: display = spec['title'] + ': ' + selected['label']
        message = await repo.add_message(conversation_id, user_key, "user", display, body.attachment_ids)
        if not body.manual_question_id:
            await repo.emit(conversation_id, 'agent.narration', {
                'narration_id': f'received:{message["id"]}',
                'message': 'درخواستت را گرفتم. فایل‌ها و وضعیت همین پروژه را بررسی می‌کنم تا قدم بعدی را مشخص کنم.'},
                source_event_id=f'received:{message["id"]}')
    except KeyError:
        raise HTTPException(404, "conversation or attachment not found")
    dispatch_message(conversation_id, user_key, message["id"], body.content.strip(), body.attachment_ids, body.manual_question_id)
    return message


@router.get("/conversations/{conversation_id}/events")
async def stream_events(request: Request, conversation_id: str,
                        after: int = Query(0, ge=0), last_event_id: str | None = Header(None, alias="Last-Event-ID")):
    user_key = _user(request)
    try: await repo.get_conversation(conversation_id, user_key)
    except KeyError: raise HTTPException(404, "conversation not found")
    try: cursor = max(after, int(last_event_id or 0))
    except ValueError: cursor = after

    async def generate():
        nonlocal cursor
        idle = 0
        while not await request.is_disconnected():
            await sync_conversation(conversation_id, user_key)
            events = await repo.events(conversation_id, user_key, cursor)
            if events:
                idle = 0
                for event in events:
                    cursor = event["seq"]
                    public_event = _public_event(event)
                    yield f"id: {cursor}\nevent: {event['type']}\ndata: {json.dumps(public_event, ensure_ascii=False)}\n\n"
            else:
                idle += 1
                if idle % 15 == 0: yield ": keep-alive\n\n"
            # Two seconds is responsive enough for user-facing progress while
            # avoiding a database poll storm across several open browser tabs.
            await asyncio.sleep(2)
    return StreamingResponse(generate(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations/{conversation_id}/events/{event_seq}/audio")
async def event_audio(request: Request, conversation_id: str, event_seq: int):
    try: await repo.get_conversation(conversation_id, _user(request))
    except KeyError: raise HTTPException(404, "conversation not found")
    folder = Path(settings.JOBS_DIR).expanduser() / "studio" / "status_audio" / conversation_id / str(event_seq)
    path = next((item for item in folder.glob("status.*") if item.is_file()), None) if folder.is_dir() else None
    if path is None: raise HTTPException(404, "status narration is not ready")
    return FileResponse(path, media_type="audio/mpeg")


@router.get("/conversations/{conversation_id}/projects")
async def conversation_projects(request: Request, conversation_id: str):
    try: return [_public_project(item) for item in (await repo.get_conversation(conversation_id, _user(request)))["projects"]]
    except KeyError: raise HTTPException(404, "conversation not found")


@router.get("/projects/{project_id}")
async def get_project(request: Request, project_id: str):
    try:
        project = await repo.get_project(project_id, _user(request))
        await sync_conversation(project["conversation_id"], _user(request))
        return _public_project(await repo.get_project(project_id, _user(request)))
    except KeyError: raise HTTPException(404, "project not found")


@router.patch("/projects/{project_id}/storyboard")
async def update_storyboard(request: Request, project_id: str, body: StoryboardUpdate):
    user_key = _user(request)
    try: project = await repo.get_project(project_id, user_key)
    except KeyError: raise HTTPException(404, "project not found")
    if project["engine"] != "motion" or not project.get("external_ref"):
        raise HTTPException(409, "project has no editable storyboard")
    job = jobstore.get(project["external_ref"])
    if not job: raise HTTPException(404, "render job not found")
    from brain.content_creator import update_storyboard
    try: storyboard = update_storyboard(job, body.scenes)
    except ValueError as exc: raise HTTPException(422, str(exc))
    state = {**project["state"], "storyboard": storyboard}
    return _public_project(await repo.update_project(project_id, user_key, state=state, source="user_ui"))


@router.post("/actions/{action_id}/confirm")
async def confirm(request: Request, action_id: str):
    try: return await asyncio.to_thread(confirm_action, action_id, _user(request))
    except KeyError: raise HTTPException(404, "action not found")
    except ValueError as exc: raise HTTPException(409, str(exc))


@router.post("/actions/{action_id}/cancel")
async def cancel_action(request: Request, action_id: str):
    try:
        action = await repo.get_action(action_id, _user(request))
        if action["status"] != "pending": raise HTTPException(409, "action is already running or finished")
        return await repo.update_action(action_id, "canceled")
    except KeyError: raise HTTPException(404, "action not found")


@router.post("/projects/{project_id}/cancel")
async def cancel_running_project(request: Request, project_id: str):
    try: return await asyncio.to_thread(cancel_project, project_id, _user(request))
    except KeyError: raise HTTPException(404, "project not found")
    except ValueError as exc: raise HTTPException(409, str(exc))


class ResumeRequest(BaseModel):
    retry_confirmed: bool = Field(default=False,strict=True)


@router.post('/projects/{project_id}/resume')
async def resume_stopped_project(request: Request, project_id: str, body: ResumeRequest | None = None):
    confirmed=bool(body and body.retry_confirmed)
    try: return await asyncio.to_thread(resume_project, project_id, _user(request),retry_confirmed=confirmed)
    except KeyError: raise HTTPException(404, 'project not found')
    except ValueError as exc: raise HTTPException(409, str(exc))


class AcceptOutputRequest(BaseModel):
    candidate: str


@router.post('/projects/{project_id}/accept-output')
async def accept_output(request: Request, project_id: str, body: AcceptOutputRequest):
    user = _user(request)
    try:
        project = await repo.get_project(project_id, user)
    except KeyError:
        raise HTTPException(404, 'project not found')
    if project['engine'] != 'talking':
        raise HTTPException(409, 'No reviewable talking output')
    from app import talking_reel
    job = jobstore.get(project.get('external_ref'))
    state = talking_reel.load(job.dir) if job else {}
    candidate = state.get('candidate_output')
    if not candidate or candidate != body.candidate or state.get('status') not in {'error', 'done'}:
        raise HTTPException(409, 'Output changed or rendering is still active')
    path = (job.dir / candidate).resolve()
    if not path.is_relative_to((job.dir / 'exports').resolve()) or not path.is_file():
        raise HTTPException(404, 'output not found')
    report = state.get('creative_review') or {}
    if not report:
        raise HTTPException(409, 'No quality review to override')
    # Preserve the reviewer verdict. User acceptance is not a fabricated QC pass.
    state.update(output=candidate, status='done', stage='', message='', progress=100,
                 quality_accepted_by_user=True)
    talking_reel.save(job.dir, state)
    await sync_conversation(project['conversation_id'], user)
    await repo.add_message(project['conversation_id'], user, 'assistant',
        'خروجی موجود با تأیید شما تحویل شد؛ نتیجهٔ بازبینی کیفیت حفظ شده و رندر مجدد انجام نشد.')
    return {'accepted': True}



@router.get("/projects/{project_id}/output")
async def project_output(request: Request, project_id: str, candidate: bool = False, file: str | None = None):
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, "project not found")
    ref = project.get("external_ref")
    path = None
    if project["engine"] == "localize" and ref:
        from app import localize
        state = localize.load(ref)
        path = localize.LOCALIZE_ROOT / ref / state.get("output", "")
    elif project["engine"] == "talking" and ref:
        from app import talking_reel
        job = jobstore.get(ref); state = talking_reel.load(job.dir) if job else {}
        relative = state.get('candidate_output') if candidate else state.get('output')
        if file:
            if not re.fullmatch(r'talking_reel_v[0-9]+\.mp4', file):
                raise HTTPException(404, 'version not found')
            relative = 'exports/' + file
        path = (job.dir / relative).resolve() if job and relative else None
        if path and not path.is_relative_to((job.dir / 'exports').resolve()):
            raise HTTPException(404, 'output not found')
    elif project["engine"] == "motion" and ref:
        job = jobstore.get(ref)
        path = job.dir / "exports" / job.render.output if job and job.render.output else None
    if not path or not path.is_file(): raise HTTPException(404, "output is not ready")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@router.get("/projects/{project_id}/assets/{index}")
async def project_asset(request: Request, project_id: str, index: int):
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, "project not found")
    assets = project.get("state", {}).get("source_assets") or []
    if index < 0 or index >= len(assets): raise HTTPException(404, "asset not found")
    path = Path(assets[index]).resolve()
    allowed = [
        (ROOT / re.sub(r"[^A-Za-z0-9_-]", "_", _user(request))).resolve(),
        (Path(settings.JOBS_DIR).expanduser()).resolve(),
    ]
    if not any(path.is_relative_to(root) for root in allowed) or not path.is_file():
        raise HTTPException(404, "asset not found")
    return FileResponse(path)


@router.get("/tools")
def tools(): return list_tools()


@router.get("/capabilities")
def capabilities():
    from brain.media_provider import list_providers
    from engine.talking_reel import style_list
    return {"engines": ["localize", "talking", "motion"], "talking_styles": style_list(),
            "media_providers": list_providers(), "aspect_ratios": {"localize": ["source"], "talking": ["9:16"], "motion": ["9:16"]},
            "live_events": "sse", "status_voice": True, "cancel": {"localize": True, "talking": True, "motion": False}}


@router.get('/projects/{project_id}/outputs')
async def project_outputs(request: Request, project_id: str):
    try: project = await repo.get_project(project_id, _user(request))
    except KeyError: raise HTTPException(404, 'project not found')
    job = jobstore.get(project.get('external_ref')) if project['engine'] == 'talking' else None
    if not job: return []
    files = [p for p in (job.dir/'exports').glob('talking_reel_v*.mp4')
             if re.fullmatch(r'talking_reel_v[0-9]+\.mp4', p.name) and p.is_file()
             and p.resolve().is_relative_to((job.dir/'exports').resolve())]
    return [{'file': p.name, 'version': int(re.search(r'_v([0-9]+)', p.name)[1])}
            for p in sorted(files, key=lambda p: int(re.search(r'_v([0-9]+)', p.name)[1]))]

