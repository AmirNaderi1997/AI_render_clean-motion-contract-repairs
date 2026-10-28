"""Authenticated Composio settings and explicit user-initiated OAuth links."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from hermes.security import current_user
from hermes.services import composio_sessions as service

router = APIRouter(prefix="/api/hermes/composio", tags=["hermes-connected-apps"])


class EnableInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class ConnectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")


class DiscoverInput(ConnectInput):
    query: str = Field(min_length=1, max_length=1000, description="A specific use case, preferably in English; not credentials or private message contents.")


@router.get("")
async def status(user=Depends(current_user)):
    return await service.status(str(user.id))


@router.put("")
async def configure(body: EnableInput, user=Depends(current_user)):
    return await service.set_enabled(str(user.id), body.enabled)


@router.get("/connections")
async def connections(user=Depends(current_user)):
    return await service.connections(str(user.id))


@router.post("/connect")
async def connect(body: ConnectInput, user=Depends(current_user)):
    return await service.connect(str(user.id), body.application)


@router.post("/discover")
async def discover(body: DiscoverInput, user=Depends(current_user)):
    return await service.discover(str(user.id), body.application, body.query)
