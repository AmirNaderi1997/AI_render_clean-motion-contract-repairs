"""API for source-less motion reels generated from public product pages."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

from app import jobs as jobstore
from app import product_reel as store
from app.job_access import get_job_for_request, is_local_auth_bypass
from engine.motion_recipes import public_recipes

router = APIRouter(prefix="/product-reels", tags=["product-reels"])


class CreateProductReel(BaseModel):
    url: str


class StoryboardEdit(BaseModel):
    scenes: list[dict]


@router.get("/recipes")
def recipes(): return public_recipes()


@router.post("", status_code=201)
def create(body: CreateProductReel, request: Request):
    try:
        job, state = store.create(str(request.state.user.id), body.url)
        return {"job_id": job.id, **state}
    except ValueError as exc: raise HTTPException(422, str(exc))


@router.get("")
def list_reels(request: Request):
    user_id, local = str(request.state.user.id), is_local_auth_bypass(request)
    items = []
    for job in jobstore.list_jobs():
        if not local and job.user_id is not None and str(job.user_id) != user_id: continue
        try: state = store.load(job.dir)
        except FileNotFoundError: continue
        items.append({"job_id": job.id, "name": (state.get("source") or {}).get("name") or state.get("url"),
                      "status": state.get("status"), "stage": state.get("stage"), "progress": state.get("progress", 0),
                      "output": state.get("output"), "updated_at": state.get("updated_at", 0)})
    return sorted(items, key=lambda item: item["updated_at"], reverse=True)


def _job(request: Request, job_id: str): return get_job_for_request(request, job_id)


@router.get("/{job_id}")
def status(job_id: str, request: Request):
    try: return store.load(_job(request, job_id).dir)
    except FileNotFoundError: raise HTTPException(404, "product reel not found")


@router.patch("/{job_id}")
def edit(job_id: str, body: StoryboardEdit, request: Request):
    try: return store.update(_job(request, job_id).dir, body.model_dump())
    except ValueError as exc: raise HTTPException(409 if "busy" in str(exc) else 422, str(exc))


@router.post("/{job_id}/render")
def render(job_id: str, request: Request):
    try: return store.start_render(_job(request, job_id))
    except (ValueError, FileNotFoundError) as exc: raise HTTPException(409, str(exc))


@router.post("/{job_id}/cancel")
def cancel(job_id: str, request: Request): return store.cancel(_job(request, job_id).dir)


@router.get("/{job_id}/output")
def output(job_id: str, request: Request):
    job = _job(request, job_id); state = store.load(job.dir); name = state.get("output")
    path = (job.dir / "exports" / str(name)).resolve() if name else None
    if not path or not path.is_relative_to(job.dir.resolve()) or not path.is_file(): raise HTTPException(404, "not rendered yet")
    return FileResponse(path, media_type="video/mp4", filename=path.name)
