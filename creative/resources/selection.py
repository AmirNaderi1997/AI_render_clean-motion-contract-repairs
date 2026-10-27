"""Deterministic resource eligibility, not an agent/model/engine router.

Callers supply the already selected rendering context. Unknown capabilities
fail closed when explicitly required. This module never installs or executes.
"""
from typing import Literal

from pydantic import Field

from .models import ManifestModel
from .registry import get_resource


class ResourceRequirements(ManifestModel):
    context: str = Field(min_length=1, max_length=80)
    engine: Literal["hyperframes", "ffmpeg", "mlt", "html", "webgl", "asset", "skill"]
    kind: str = Field(min_length=1, max_length=80)
    require_rtl: bool = False
    require_alpha: bool = False
    require_seekable: bool = False
    require_vertical: bool = False
    require_commercial_approval: bool = False


def assess_resource(resource_id: str, requirements: ResourceRequirements) -> dict:
    """Return explicit rejection reasons; never substitute another resource."""
    try:
        row = get_resource(resource_id)
    except KeyError:
        return {"resource_id": resource_id, "eligible": False, "reasons": ["unknown-resource"]}
    reasons = []
    if row["availability"] != "existing-pipeline" or row["integration_status"] != "native":
        reasons.append("no-native-adapter")
    if requirements.context not in row["contexts"]:
        reasons.append("unsupported-context")
    if row["engine"] != requirements.engine:
        reasons.append("different-engine")
    if row["type"] != requirements.kind:
        reasons.append("different-resource-type")
    for required, capability in (
        (requirements.require_rtl, "supports_rtl"),
        (requirements.require_alpha, "transparent"),
        (requirements.require_seekable, "seekable"),
        (requirements.require_vertical, "supports_vertical"),
    ):
        if required and row["capabilities"][capability] is not True:
            reasons.append(f"unverified-{capability}")
    if requirements.require_commercial_approval and not (
        row["license"]["verified"] and row["license"]["commercial_use_approved"]
    ):
        reasons.append("commercial-license-not-approved")
    return {"resource_id": resource_id, "eligible": not reasons, "reasons": reasons}
