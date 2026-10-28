"""Registry operations use real plan validation/history; no model calls."""
import copy
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError

from engine.operations import LockedError, OperationError, OpContext, apply_operations


@pytest.fixture
def plan():
    return {"canvas": {"width": 1080, "height": 1920, "fps": 30}, "source": "video.mp4",
            "segments": [{"id": "a", "in": 0, "out": 1}, {"id": "b", "in": 1, "out": 2},
                         {"id": "c", "in": 2, "out": 3}],
            "visual_effects": [{"segment_id": "b", "type": "steady__neutral"}],
            "captions": [{"start": 0, "end": 0.8, "text": "آزمون فارسی"}],
            "export": {"file": "out.mp4"}}


def effect(resource="editorgpt:slow_push__neutral", segment="a"):
    return {"op": "set_resource_effect", "resource_id": resource, "segment_id": segment}


def test_resource_applies_exact_existing_renderer_plan(plan):
    original = copy.deepcopy(plan)
    result = apply_operations(plan, [effect()])
    legacy = apply_operations(plan, [{"op": "set_effect", "segment_id": "a", "effect": "slow_push__neutral"}])
    assert result.plan == legacy.plan
    assert result.operations[0]["resource_id"] == "editorgpt:slow_push__neutral"
    assert plan == original
    assert result.plan["captions"] == plan["captions"]


@pytest.mark.parametrize("rid", ["hyperframes:data-chart", "hyperframes:caption-kinetic-slam",
                                 "editorgpt:speed_ramp", "editorgpt-transition:crossfade", "../../etc/passwd"])
def test_no_execution_of_catalog_or_wrong_context(plan, rid):
    with pytest.raises(OperationError): apply_operations(plan, [effect(rid)])


def test_no_ignored_effect_parameters_or_paths(plan):
    with pytest.raises(ValidationError):
        apply_operations(plan, [{**effect(), "parameters": {"command": "invalid"}}])


def test_resource_replacement_removal_and_locks(plan):
    plan["visual_effects"][0]["locked"] = True
    ai = OpContext(actor="ai", respect_locks=True)
    with pytest.raises(LockedError): apply_operations(plan, [effect(segment="b")], ai)
    with pytest.raises(LockedError): apply_operations(plan, [{"op": "remove_effect", "segment_id": "b"}], ai)
    replaced = apply_operations(plan, [effect(segment="b")]).plan
    assert replaced["visual_effects"][0]["locked"]
    removed = apply_operations(replaced, [{"op": "remove_effect", "segment_id": "b"}]).plan
    assert removed["visual_effects"] == []
    assert removed["segments"] == plan["segments"] and removed["captions"] == plan["captions"]


def test_failed_batch_does_not_apply_partial_resource_changes(plan):
    original = copy.deepcopy(plan)
    with pytest.raises(OperationError):
        apply_operations(plan, [effect(), effect("hyperframes:data-chart", segment="b")])
    assert plan == original


def test_transition_settings_flow_to_existing_boundary_renderer(plan):
    operation = {"op": "set_resource_transition", "resource_id": "editorgpt-transition:zoom",
                 "from_segment_id": "a", "to_segment_id": "b",
                 "settings": {"duration_frames": 8, "zoom_mode": "zoom_out", "zoom_scale": 1.2}}
    result = apply_operations(plan, [operation])
    transition = result.plan["transitions"][0]
    assert transition["type"] == "zoom" and transition["duration_frames"] == 8
    assert transition["zoom_mode"] == "zoom_out" and transition["locked"]
    from engine.build_mlt import _transition_rect
    from engine.schema import BoundaryTransition
    assert "1296" in _transition_rect(BoundaryTransition(**transition), 1080, 1920)
    cut = apply_operations(result.plan, [{**operation, "resource_id": "editorgpt-transition:hard_cut"}]).plan
    assert cut["transitions"][0]["duration_frames"] == 0


@pytest.mark.parametrize("settings", [{"zoom_scale": float("nan")}, {"duration_frames": 31},
                                      {"duration_frames": "8"}, {"command": "bad"}])
def test_transition_rejects_unvalidated_parameters(plan, settings):
    with pytest.raises(ValidationError):
        apply_operations(plan, [{"op": "set_resource_transition", "resource_id": "editorgpt-transition:zoom",
                                 "from_segment_id": "a", "to_segment_id": "b", "settings": settings}])


def test_transition_adjacency_and_existing_ai_locks(plan):
    op = {"op": "set_resource_transition", "resource_id": "editorgpt-transition:crossfade",
          "from_segment_id": "a", "to_segment_id": "c"}
    with pytest.raises(OperationError, match="adjacent"):
        apply_operations(plan, [op])
    op["to_segment_id"] = "b"
    locked = apply_operations(plan, [op]).plan
    with pytest.raises(LockedError):
        apply_operations(locked, [op], OpContext(actor="ai", respect_locks=True))


def test_instances_are_derived_stable_and_frame_accurate(plan):
    from creative.resources.instances import edit_plan_instances
    op = {"op": "set_resource_transition", "resource_id": "editorgpt-transition:crossfade",
          "from_segment_id": "a", "to_segment_id": "b", "settings": {"duration_frames": 6}}
    changed = apply_operations(plan, [op]).plan
    instances = edit_plan_instances(changed)
    effect_instance = next(i for i in instances if i["type"] == "effect")
    assert effect_instance["id"] == "effect:b" and effect_instance["start"] == pytest.approx(0.8)
    assert effect_instance["resource_id"] == "editorgpt:steady__neutral"
    transition = next(i for i in instances if i["type"] == "transition")
    assert transition["start"] == pytest.approx(0.8) and transition["end"] == pytest.approx(1.0)
    changed["captions"][0]["text"] = "متن تازه"
    assert [i["id"] for i in edit_plan_instances(changed)] == [i["id"] for i in instances]


@pytest.fixture
def saved_job(monkeypatch, tmp_path, plan):
    from app import jobs
    if not shutil.which("ffmpeg"): pytest.skip("Native FFmpeg required for real source/probe/history test")
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=30:d=3",
                    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path / "video.mp4")],
                   check=True, timeout=20, capture_output=True)
    monkeypatch.setattr(jobs, "DB_AVAILABLE", False)
    monkeypatch.setattr(jobs, "JOBS_ROOT", tmp_path)
    monkeypatch.setattr(jobs, "LOCAL_REGISTRY", tmp_path / ".registry.json")
    monkeypatch.setattr(jobs, "_jobs", {})
    job = jobs.Job(id="resource-test", dir=tmp_path, user_id="alice")
    jobs._jobs[job.id] = job
    value, errors = jobs.save_plan(job, plan)
    assert value and errors == []
    return job


def test_real_persistence_audit_stale_baseline_and_undo(saved_job):
    from app import jobs, plan_versions
    initial = copy.deepcopy(jobs.load_plan(saved_job))
    version = plan_versions.latest_version(saved_job)["version"]
    preview = jobs.apply_plan_operations(saved_job, [effect()], dry_run=True, base_version=version, base_plan=initial)
    assert preview["diff"] and jobs.load_plan(saved_job) == initial
    result = jobs.apply_plan_operations(saved_job, [effect()], base_version=version, base_plan=initial)
    assert result["version"] > version
    assert plan_versions.latest_version(saved_job)["operations"][0]["resource_id"] == effect()["resource_id"]
    with pytest.raises(jobs.PlanVersionConflict):
        jobs.apply_plan_operations(saved_job, [effect()], base_version=version, base_plan=initial)
    with pytest.raises(jobs.PlanVersionConflict):
        jobs.apply_plan_operations(saved_job, [effect()], base_plan=initial)
    jobs.undo_plan(saved_job)
    assert jobs.load_plan(saved_job) == initial


def test_real_saved_plan_draft_render_has_no_paid_review(saved_job, monkeypatch):
    from app import jobs
    from creative import review
    if not (shutil.which("melt") or shutil.which("melt-7")):
        pytest.skip("Native MLT unavailable")
    data = jobs.load_plan(saved_job)
    data["canvas"] = {"width": 64, "height": 96, "fps": 30}
    data["captions"] = []
    data["generation_meta"] = {"creative_plan": {"schema_version": 2}}
    assert not jobs.save_plan(saved_job, data)[1]
    def forbidden(*args, **kwargs):
        pytest.fail("Draft previews must not call paid creative review")
    monkeypatch.setattr(review, "review_export", forbidden)
    jobs._run_job(saved_job, preview=True, loudnorm=False, raise_errors=True)
    assert saved_job.render.status == "done"
    assert saved_job.render.output.endswith("_preview.mp4")
    assert saved_job.render.technical_qc["creative_review"]["status"] == "not_run"
    from engine.probe import video_dimensions
    assert video_dimensions(saved_job.dir / "exports" / saved_job.render.output) == (32, 48)


def test_owned_api_context_and_actual_operation_roundtrip(saved_job):
    from app.routers.plans import router
    app = FastAPI()
    @app.middleware("http")
    async def identity(request: Request, call_next):
        request.state.user = SimpleNamespace(id=request.headers.get("X-Test-User", "alice"))
        return await call_next(request)
    app.include_router(router)
    client = TestClient(app)
    path = f"/jobs/{saved_job.id}"
    context = client.get(path + "/creative-resources")
    assert context.status_code == 200 and context.headers["cache-control"] == "no-store"
    body = context.json()
    assert len(body["effects"]) > 100
    assert {t["id"] for t in body["transitions"]} == {"editorgpt-transition:" + kind for kind in ("hard_cut", "crossfade", "directional", "zoom")}
    assert client.get(path + "/creative-resources", headers={"X-Test-User": "bob"}).status_code == 403
    payload = {"operations": [effect()], "base_version": body["version"], "base_plan": body["plan"]}
    assert client.post(path + "/operations", json=payload, headers={"X-Test-User": "bob"}).status_code == 403
    response = client.post(path + "/operations", json=payload)
    assert response.status_code == 200 and response.json()["ok"]
    assert client.post(path + "/operations", json=payload).status_code == 409
    refreshed = client.get(path + "/creative-resources").json()
    transition = {"op": "set_resource_transition", "resource_id": "editorgpt-transition:zoom",
                  "from_segment_id": "a", "to_segment_id": "b",
                  "settings": {"duration_frames": 8, "zoom_mode": "zoom_out", "zoom_scale": 1.2}}
    response = client.post(path + "/operations", json={"operations": [transition],
        "base_version": refreshed["version"], "base_plan": refreshed["plan"]})
    assert response.status_code == 200
    persisted = client.get(path + "/creative-resources").json()
    assert persisted["plan"]["transitions"][0]["zoom_scale"] == 1.2
    assert any(item["resource_id"] == "editorgpt-transition:zoom" for item in persisted["instances"])


def test_all_segments_and_boundaries_persist_as_one_batch_and_appear_on_timeline(saved_job):
    from app import jobs, project_document
    initial = copy.deepcopy(jobs.load_plan(saved_job))
    operations = [effect(segment=key) for key in ("a", "b", "c")]
    operations += [{"op": "set_resource_transition", "resource_id": "editorgpt-transition:crossfade",
                    "from_segment_id": a, "to_segment_id": b, "settings": {"duration_frames": 6}}
                   for a, b in (("a", "b"), ("b", "c"))]
    jobs.apply_plan_operations(saved_job, operations, base_plan=initial)
    persisted = jobs.load_plan(saved_job)
    assert {e["segment_id"] for e in persisted["visual_effects"]} == {"a", "b", "c"}
    assert len(persisted["transitions"]) == 2
    assert persisted["captions"] == initial["captions"]
    document = project_document.motion_document(saved_job)
    effects = next(t for t in document["tracks"] if t["id"] == "effects")["elements"]
    transitions = next(t for t in document["tracks"] if t["id"] == "graphics")["elements"]
    assert [e["id"] for e in effects] == ["effect:a", "effect:b", "effect:c"]
    assert [e["start"] for e in effects] == pytest.approx([0, .8, 1.6])
    assert all(e["type"] == "effect" and e["edit"]["via"] == ["plan"] for e in effects)
    assert len(transitions) == 2 and transitions[1]["start"] == pytest.approx(1.6)
    jobs.undo_plan(saved_job)
    assert jobs.load_plan(saved_job) == initial
