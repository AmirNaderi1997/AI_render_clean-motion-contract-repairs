"""Additive authenticated resource discovery. No download or code execution API."""
from fastapi import APIRouter, HTTPException, Query, Response
from creative.resources.registry import get_resource, registry_summary, search_resources

router = APIRouter(prefix="/creative-resources", tags=["creative-resources"])


@router.get("")
def search(response: Response, q: str = Query("", max_length=300), engine: str | None = None,
           provider: str | None = None, kind: str | None = None, availability: str | None = None,
           limit: int = Query(24, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
    response.headers["Cache-Control"] = "no-store"
    return search_resources(q, engine=engine, provider=provider, kind=kind,
                            availability=availability, limit=limit, offset=offset)


@router.get("/summary")
def summary(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return registry_summary()


@router.get("/{resource_id}")
def detail(resource_id: str, response: Response):
    response.headers["Cache-Control"] = "no-store"
    try:
        return get_resource(resource_id)
    except KeyError:
        raise HTTPException(404, "Creative resource not found") from None
