"""Shared strict inputs for authenticated APIs and Studio tools; no authority IDs."""
import json

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConnectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    application: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")


class DiscoverInput(ConnectInput):
    query: str = Field(min_length=1, max_length=1000, description="A specific use case, preferably in English; not credentials or private message contents.")


class ReadInput(ConnectInput):
    tool: str = Field(min_length=2, max_length=200, pattern=r"^[A-Z][A-Z0-9_]+$")
    arguments: dict = Field(default_factory=dict, max_length=100)

    @field_validator("arguments")
    @classmethod
    def bounded_arguments(cls, value):
        if len(json.dumps(value, allow_nan=False)) > 20_000:
            raise ValueError("Arguments are too large")
        return value
