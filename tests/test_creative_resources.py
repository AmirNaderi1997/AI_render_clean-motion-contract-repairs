"""Real metadata/API/tool tests. No paid models, media generation or downloads."""
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from creative.resources import providers, registry
from app.routers.creative_resources import router


def test_resource_selection_never_switches_engines_or_promotes_unknown_capabilities():
    from creative.resources.selection import ResourceRequirements, assess_resource
    requirements = ResourceRequirements(context="edit-plan", engine="mlt", kind="transition")
    assert assess_resource("editorgpt-transition:crossfade", requirements)["eligible"]
    assert not assess_resource("hyperframes:data-chart", requirements)["eligible"]
    assert assess_resource("missing:resource", requirements)["reasons"] == ["unknown-resource"]
    strict = requirements.model_copy(update={"require_rtl": True, "require_alpha": True,
                                              "require_commercial_approval": True})
    result = assess_resource("editorgpt-transition:crossfade", strict)
    assert not result["eligible"]
    assert set(result["reasons"]) == {"unverified-supports_rtl", "unverified-transparent", "commercial-license-not-approved"}


def test_snapshot_indexes_existing_sources_without_claiming_execution():
    from engine.hyperframes.catalog import load_catalog
    from engine.effects_v4 import EFFECT_CATALOG_V4
    from engine.motion_recipes import RECIPES
    summary = registry.registry_summary()
    assert summary["total"] == len(load_catalog()["items"]) + len(EFFECT_CATALOG_V4) + 4 + len(RECIPES)
    rows = registry.search_resources(limit=100)["items"]
    assert len({r["id"] for r in rows}) == len(rows)
    assert all(r["render_time_ms"] is None and r["peak_memory_mb"] is None for r in rows)
    assert all(not r["license"]["verified"] for r in rows)


def test_only_real_hyperframes_adapters_are_connected():
    from engine.hyperframes.registry_runtime import SUPPORTED_REGISTRY_ADAPTERS
    rows = registry.search_resources(engine="hyperframes", provider="hyperframes-official",
                                     availability="existing-pipeline")["items"]
    assert {r["legacy_id"] for r in rows} == SUPPORTED_REGISTRY_ADAPTERS
    assert all(r["contexts"] == ["talking_2"] for r in rows)
    assert registry.get_resource("hyperframes:data-chart")["availability"] == "catalog-only"


def test_unsupported_effects_not_silently_promoted():
    row = registry.get_resource("editorgpt:speed_ramp")
    assert row["availability"] == row["integration_status"] == "unsupported"
    assert "timing" in row["limitations"][0]


def test_transition_mapping_preserves_legacy_renderer():
    row = registry.get_resource("editorgpt-transition:crossfade")
    assert row["engine"] == "mlt"  # do not mislabel existing MLT as native xfade
    assert row["legacy_id"] == "crossfade"


def test_snapshot_metadata_does_not_certify_rtl_from_orientation():
    row = registry.get_resource("hyperframes:caption-kinetic-slam")
    assert row["capabilities"]["supports_rtl"] is None
    assert row["capabilities"]["supports_vertical"] is None
    assert all(not p["editable"] for p in row["parameters"])


def test_search_filter_pagination_and_stable_revision():
    full = registry.search_resources(engine="hyperframes", limit=100)
    first = registry.search_resources(engine="hyperframes", limit=3)
    second = registry.search_resources(engine="hyperframes", limit=3, offset=3)
    assert first["items"] + second["items"] == full["items"][:6]
    assert first["total"] == second["total"]
    assert registry.search_resources("nonexistentxyz")["items"] == []
    assert registry.registry_summary()["revision"] == registry.registry_summary()["revision"]
    assert "kinetic" in json.dumps(registry.search_resources("kinetic typography")["items"]).lower()


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10001}, {"query": "x" * 301}])
def test_boundaries(kwargs):
    with pytest.raises(ValueError):
        registry.search_resources(**kwargs)


def test_snapshot_cannot_be_mutated_through_public_dict():
    row = registry.get_resource("hyperframes:data-chart")
    row["license"]["verified"] = True
    row["tags"].append("secret")
    again = registry.get_resource("hyperframes:data-chart")
    assert not again["license"]["verified"] and "secret" not in again["tags"]


@pytest.mark.parametrize("value", ["http://127.0.0.1/file", "https://evil.example/video.mp4", "javascript:alert(1)",
                                   "https://static.heygen.ai.evil/hyperframes/file", "https://static.heygen.ai/hyperframes/v.mp4?key=secret"])
def test_preview_rejects_untrusted_urls(value):
    assert providers._preview_url(value) is None


def test_discovery_never_runs_network_shell_or_mutates_project(monkeypatch):
    import subprocess
    import httpx
    def forbidden(*args, **kwargs):
        pytest.fail("Discovery must be read-only, local metadata")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(httpx, "get", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    registry._snapshot.cache_clear()
    assert registry.registry_summary()["total"] > 400


def test_http_contract_bounds_details_and_no_store():
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/creative-resources?q=kinetic&limit=2")
    assert response.status_code == 200 and len(response.json()["items"]) == 2
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/creative-resources?limit=101").status_code == 422
    assert client.get("/creative-resources/unknown:thing").status_code == 404
    assert client.get("/creative-resources/summary").json()["total"] > 400
    assert client.get("/creative-resources/hyperframes:data-chart").json()["id"] == "hyperframes:data-chart"
    assert client.post("/creative-resources/hyperframes:data-chart", json={"install": True}).status_code == 405


def test_app_auth_not_bypassed_for_resource_routes():
    from app.main import app
    # No lifespan: don't start real workers or recover the developer's jobs.
    client = TestClient(app, base_url="https://lan.editor.invalid")
    assert client.get("/creative-resources").status_code == 401
    assert client.get("/creative-resources/summary").status_code == 401


def test_shared_and_medium_tool_validation_without_mutation():
    from app import studio_tools
    from app.agents.medium import tools
    result = studio_tools.execute("search_creative_resources", {"query": "chart", "limit": 2})
    assert len(result["items"]) == 2
    assert "search_creative_resources" in tools.READ_ONLY
    spec = next(t for t in tools.catalog() if t["name"] == "search_creative_resources")
    assert not spec["requires_approval"]
    assert tools.execute({"id": "test"}, {"tool": "search_creative_resources", "arguments": {"query": "chart", "limit": 2}}) == result
    with pytest.raises(ValueError):
        studio_tools.execute("search_creative_resources", {"query": "chart", "path": "/etc/passwd"})
    with pytest.raises(KeyError):
        registry.get_resource("../../etc/passwd")
