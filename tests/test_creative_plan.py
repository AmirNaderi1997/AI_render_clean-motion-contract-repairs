"""Creative Plan: versions, the approval gate, plan edits, brand memory and estimates."""
import asyncio
from types import SimpleNamespace

import pytest

from app import brand_profile, creative_plan, render_stats, studio_store
from app import studio_manual as manual


def run(coro): return asyncio.run(coro)


SENTENCES = [{"start": 0.0, "end": 3.0, "text": "وقتی چند میلیارد ضرر دادم فهمیدم"},
             {"start": 3.0, "end": 7.0, "text": "سرمایه اولیه اصولا نمی‌خواد"},
             {"start": 7.0, "end": 12.0, "text": "اول مهارت فروش رو یاد بگیر"}]


def status(**overrides):
    value = {
        "status": "ready", "style": "talking_1", "hook": "چند میلیارد ضرر دادم", "hook_highlight": ["چند میلیارد"],
        "name": "", "title": "", "cta": "", "music": "assets/music/piano.mp3", "storyboard": [],
        "render_settings": {"grade": dict(creative_plan.LOOKS["warm"]["grade"]), "title_color": "#F5B800",
                            "zoom": {"amount": 100}, "outro_logo": {"enabled": True, "motion": "pop"}},
        "creative_plan": {
            "brief": {"goal": "جذب مخاطب", "audience": "کارآفرینان", "core_message": "مهارت مهم‌تر از سرمایه است", "tone": "صادق"},
            "chosen": {"id": "c1", "name": "اعتراف", "angle": "از شکست شروع کن", "hook": "چند میلیارد ضرر",
                       "beats": [{"role": "hook", "intent": "شوک", "visual": "بستن روی صورت", "sentence": 0}]},
            "alternatives": [{"id": "c2", "name": "درس", "angle": "آموزشی", "hook": "سه درس", "style_hint": "talking_2"},
                             {"id": "c3", "name": "مینیمال", "angle": "ساده", "hook": "یک جمله", "style_hint": None}],
            "verdict": "قوی‌ترین هوک"}}
    value.update(overrides)
    return value


def content(**overrides):
    return creative_plan.build_talking(status(**overrides), sentences=SENTENCES, video_seconds=12.0, estimate=None,
                                       has_logo=False)


def test_plan_is_plain_language_and_grounded_in_the_analysis():
    plan = content()
    assert plan["style"]["id"] == "talking_1" and plan["style"]["label"]
    assert plan["hook"] == {"text": "چند میلیارد ضرر دادم", "highlight": ["چند میلیارد"]}
    assert plan["look"]["preset"] == "warm"
    assert plan["structure"][0]["text"] == SENTENCES[0]["text"] and plan["structure"][0]["at"] == "0:00"
    styles = {c["id"]: c["style"] for c in plan["concepts"]}
    assert styles == {"c1": "talking_1", "c2": "talking_2", "c3": "talking_1"}
    assert [c["selected"] for c in plan["concepts"]] == [True, False, False]
    assert plan["estimate"]["render"] is None  # no measurement yet: never an invented number
    assert plan["format"]["aspect"] == "9:16"


def test_versions_deduplicate_and_any_change_clears_approval():
    state, created = creative_plan.add_version({}, content(), source="agent")
    assert created and state["workflow"] == "awaiting_approval"
    first = creative_plan.current(state)
    refreshed = {**content(), "frames": {"x": "y"}, "estimate": {"render": {"low_s": 1, "high_s": 2}}}
    state, created = creative_plan.add_version(state, refreshed, source="agent")
    assert not created and len(state["plan"]["versions"]) == 1  # frames/estimates are not output changes
    state = creative_plan.approve(state, first["id"])
    assert creative_plan.is_approved(state)
    state, created = creative_plan.add_version(state, content(cta="فالو کنید"), source="user")
    assert created and not creative_plan.is_approved(state) and state["workflow"] == "awaiting_approval"
    assert creative_plan.current(state)["n"] == 2


def test_only_the_current_version_can_be_approved_once():
    state, _ = creative_plan.add_version({}, content(), source="agent")
    old = creative_plan.current(state)["id"]
    state, _ = creative_plan.add_version(state, content(cta="x"), source="user")
    with pytest.raises(creative_plan.PlanError):
        creative_plan.approve(state, old)
    approved = creative_plan.approve(state, creative_plan.current(state)["id"])
    with pytest.raises(creative_plan.PlanError):
        creative_plan.approve(approved, creative_plan.current(approved)["id"])  # not waiting any more


def test_edits_map_only_to_real_engine_fields():
    plan = content()
    result = creative_plan.talking_edits(plan, {"hook": "سه اشتباه بزرگ", "hook_highlight": ["اشتباه", "نیست"],
                                                "accent_color": "#a8cf80", "logo_enabled": False, "name": "رضا"}, status())
    assert result["engine"]["hook"] == "سه اشتباه بزرگ"
    assert result["engine"]["hook_highlight"] == ["اشتباه"]  # words not in the hook are dropped
    assert result["engine"]["render_settings"]["title_color"] == "#A8CF80"
    assert result["engine"]["render_settings"]["outro_logo"] == {"enabled": False, "motion": "none"}
    assert result["engine"]["name"] == "رضا"
    assert result["profile"] == {"accent_color": "#A8CF80", "name": "رضا"}
    assert result["reanalyze"] is None
    split = creative_plan.talking_edits(plan, {"hook": "هوک"}, status(style="talking_2"))
    assert "hook2" in split["engine"] and "hook" not in split["engine"]
    for bad in ({"accent_color": "yellow"}, {"look": "neon"}, {"caption_font": "Arial"}, {"hook": "  "},
                {"unknown": 1}, {"concept_id": "missing"}, {"style": "talking_9"}):
        with pytest.raises(creative_plan.PlanError):
            creative_plan.talking_edits(plan, bad, status())


def test_choosing_another_concept_or_style_requires_reanalysis():
    plan = content()
    assert creative_plan.talking_edits(plan, {"concept_id": "c1"}, status())["reanalyze"] is None
    assert creative_plan.talking_edits(plan, {"concept_id": "c2"}, status())["reanalyze"] == {"style": "talking_2", "concept_id": "c2"}
    assert creative_plan.talking_edits(plan, {"style": "talking_3"}, status())["reanalyze"] == {"style": "talking_3", "concept_id": None}
    assert creative_plan.talking_edits(plan, {"style": "talking_1"}, status())["reanalyze"] is None


def test_chat_approval_words():
    from app.studio_orchestrator import _is_approval
    assert all(_is_approval(t) for t in ("تأیید", "تایید!", " اوکی ", "OK", "رندر کن"))
    assert not any(_is_approval(t) for t in ("تأیید نمی‌کنم، هوک رو عوض کن", "رنگ رو زرد کن", ""))


@pytest.fixture
def jobs_root(tmp_path, monkeypatch):
    from app import jobs
    monkeypatch.setattr(jobs, "JOBS_ROOT", tmp_path)
    return tmp_path


def test_brand_profile_remembers_answers_including_explicit_none(jobs_root):
    assert brand_profile.load("u")["answered"] == []
    profile = brand_profile.update("u", {"name": "رضا", "tagline": "", "accent_color": "#ffcc00", "caption_font": "Comic"})
    assert profile["name"] == "رضا" and profile["accent_color"] == "#FFCC00"
    assert brand_profile.known(profile, "tagline") and not brand_profile.known(profile, "cta")
    assert profile["caption_font"] == ""  # unsupported font ignored
    assert brand_profile.load("other")["name"] == ""  # per user


def test_auto_mode_asks_only_unknown_brand_details(jobs_root, tmp_path, monkeypatch):
    monkeypatch.setattr(studio_store, "DB_AVAILABLE", False)
    monkeypatch.setattr(studio_store, "ROOT", tmp_path)
    monkeypatch.setattr(studio_store, "FALLBACK", tmp_path / "studio.json")
    from app.studio_orchestrator import _known_brand_keys
    store = studio_store.repo
    c = run(store.create_conversation("u"))
    first = manual.begin(c["id"], "u", "talking", "ادیت کن", [], essentials=True, skip=_known_brand_keys("u"))
    assert [s["key"] for s in first["steps"]] == ["name", "tagline", "logo", "logo_asset", "cta"]
    brand_profile.update("u", {"name": "رضا", "tagline": "", "cta": "فالو", "logo_motion": "fade"})
    second = manual.begin(c["id"], "u", "talking", "ادیت کن", [], essentials=True, skip=_known_brand_keys("u"))
    assert second["steps"] == [] and second["question_id"] is None


def test_estimate_comes_only_from_measured_renders(jobs_root):
    assert render_stats.estimate("talking:talking_1", 60) is None
    for wall in (60, 90, 120, 150):
        render_stats.record("talking:talking_1", 30, wall)
    estimate = render_stats.estimate("talking:talking_1", 60)
    assert estimate["samples"] == 4 and 120 <= estimate["low_s"] <= estimate["high_s"] <= 300


# -- gate integration ------------------------------------------------------------------------------

@pytest.fixture
def studio(tmp_path, monkeypatch, jobs_root):
    from app import studio_orchestrator as o, talking_reel
    monkeypatch.setattr(studio_store, "DB_AVAILABLE", False)
    monkeypatch.setattr(studio_store, "ROOT", tmp_path)
    monkeypatch.setattr(studio_store, "FALLBACK", tmp_path / "studio.json")
    engine = status()
    calls = {"start": 0, "analyze": []}

    def update(_dir, changes):
        for key, value in changes.items():
            engine[key] = value
    monkeypatch.setattr(o.jobstore, "get", lambda ref: SimpleNamespace(dir=tmp_path, raw_name="v.mp4"))
    async def nothing(*args): pass
    monkeypatch.setattr(o, "_sync_motion_messages", nothing)
    monkeypatch.setattr(talking_reel, "load", lambda _: engine)
    monkeypatch.setattr(talking_reel, "public", lambda s: s)
    monkeypatch.setattr(talking_reel, "update", update)
    monkeypatch.setattr(talking_reel, "custom_logo", lambda _: None)
    monkeypatch.setattr(talking_reel, "start", lambda *a, **k: calls.__setitem__("start", calls["start"] + 1))
    monkeypatch.setattr(talking_reel, "analyze", lambda *a, **k: calls["analyze"].append(k))
    monkeypatch.setattr(o, "_talking_context", lambda job: (tmp_path / "v.mp4", engine, SENTENCES))
    monkeypatch.setattr(o, "_plan_frames", lambda *a: {})
    monkeypatch.setattr(o, "execute", lambda name, payload: {"duration": 12.0})
    store = studio_store.repo
    c = run(store.create_conversation("u"))
    p = run(store.create_project(c["id"], "u", "talking", "t", {"workflow": "analyzing"}, "job"))
    return SimpleNamespace(o=o, store=store, c=c, p=p, engine=engine, calls=calls)


def project(s): return run(s.store.get_project(s.p["id"], "u"))


def test_ready_analysis_waits_for_approval_then_renders_once(studio):
    s = studio
    run(s.o.sync_conversation(s.c["id"], "u"))
    run(s.o.sync_conversation(s.c["id"], "u"))
    p = project(s)
    assert p["status"] == "awaiting_confirmation" and s.calls["start"] == 0
    assert len(p["state"]["plan"]["versions"]) == 1  # repeated syncs do not create versions
    messages = run(s.store.get_conversation(s.c["id"], "u"))["messages"]
    assert sum("برنامهٔ تدوین آماده است" in m["content"] for m in messages) == 1
    version = creative_plan.current(p["state"])["id"]
    run(s.o.approve_plan(s.p["id"], "u", version))
    with pytest.raises(creative_plan.PlanError):
        run(s.o.approve_plan(s.p["id"], "u", version))
    p = project(s)
    assert s.calls["start"] == 1 and p["state"]["workflow"] == "production" and p["status"] == "running"


def test_plan_edit_creates_a_version_and_requires_fresh_approval(studio):
    s = studio
    run(s.o.sync_conversation(s.c["id"], "u"))
    v1 = creative_plan.current(project(s)["state"])["id"]
    run(s.o.edit_plan(s.p["id"], "u", v1, {"accent_color": "#FFFFFF", "cta": "پیج رو فالو کن"}))
    p = project(s)
    v2 = creative_plan.current(p["state"])
    assert v2["n"] == 2 and v2["content"]["look"]["accent_color"] == "#FFFFFF"
    assert v2["content"]["brand"]["cta"] == "پیج رو فالو کن"
    assert brand_profile.load("u")["cta"] == "پیج رو فالو کن"  # remembered for the next project
    with pytest.raises(creative_plan.PlanError):
        run(s.o.edit_plan(s.p["id"], "u", v1, {"cta": "stale"}))
    with pytest.raises(creative_plan.PlanError):
        run(s.o.approve_plan(s.p["id"], "u", v1))
    assert s.calls["start"] == 0


def test_picking_another_concept_reanalyzes_with_that_concept(studio):
    s = studio
    run(s.o.sync_conversation(s.c["id"], "u"))
    v1 = creative_plan.current(project(s)["state"])["id"]
    run(s.o.edit_plan(s.p["id"], "u", v1, {"concept_id": "c2"}))
    p = project(s)
    assert s.calls["analyze"][0]["style"] == "talking_2" and s.calls["analyze"][0]["concept"]["id"] == "c2"
    assert p["state"]["workflow"] == "analyzing" and p["state"]["plan_pending"]
    with pytest.raises(creative_plan.PlanError):
        run(s.o.approve_plan(s.p["id"], "u", v1))  # nothing is approvable while re-analysing
    s.engine.update(style="talking_2", hook2="سه درس از ضرر")
    run(s.o.sync_conversation(s.c["id"], "u"))
    p = project(s)
    assert p["state"]["workflow"] == "awaiting_approval"
    assert creative_plan.current(p["state"])["content"]["style"]["id"] == "talking_2"


def test_brand_profile_fills_empty_fields_before_the_first_plan(studio):
    s = studio
    brand_profile.update("u", {"name": "رضا رفیعی", "accent_color": "#A8CF80"})
    run(s.o.sync_conversation(s.c["id"], "u"))
    content_ = creative_plan.current(project(s)["state"])["content"]
    assert content_["brand"]["name"] == "رضا رفیعی" and content_["look"]["accent_color"] == "#A8CF80"


def test_localize_ready_waits_for_approval_in_auto_mode(studio, monkeypatch):
    s = studio
    from app import localize
    p = run(s.store.create_project(s.c["id"], "u", "localize", "l", {"auto_render": True}, "loc"))
    monkeypatch.setattr(localize, "load", lambda ref: {"status": "ready"})
    monkeypatch.setattr(localize, "public", lambda st: {"status": "ready", "title": "t", "lines": []})
    monkeypatch.setattr(localize, "start_render", lambda ref: pytest.fail("unapproved dubbing"))
    run(s.o.sync_conversation(s.c["id"], "u"))
    p = run(s.store.get_project(p["id"], "u"))
    assert p["status"] == "awaiting_confirmation" and p["state"]["manual_checkpoint"]


def test_style_mockup_renders_on_a_real_frame(tmp_path):
    import subprocess
    from engine.render_ass import ass_burner_ffmpeg
    from engine.style_frames import render_mockup
    ffmpeg = ass_burner_ffmpeg()
    if not ffmpeg:
        pytest.skip("no ffmpeg with libass")
    video = tmp_path / "v.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i", "testsrc=s=720x1280:d=2", str(video)], check=True)
    for style in ("talking_1", "talking_2", "talking_3", "talking_4"):
        out = render_mockup(video, tmp_path / f"{style}.jpg", style_id=style, at=1, hook="سه درس از ضرر",
                            highlight=["ضرر"], caption="سرمایه اولیه اصولا نمی‌خواد", name="رضا")
        assert out.stat().st_size > 1000


def test_chat_brand_changes_update_the_profile_only_when_they_change(jobs_root):
    from app.studio_orchestrator import _remember_brand_changes
    previous = {"title_color": "#F5B800", "zoom": {"amount": 100}}
    _remember_brand_changes("u", {"render_settings": {**previous, "zoom": {"amount": 150}}}, previous=previous)
    assert brand_profile.load("u")["answered"] == []  # a zoom tweak is not a brand decision
    _remember_brand_changes("u", {"cta": "فالو کن", "title": "مدیرعامل",
                                  "render_settings": {**previous, "title_color": "#FFFFFF"}}, previous=previous)
    profile = brand_profile.load("u")
    assert (profile["cta"], profile["tagline"], profile["accent_color"]) == ("فالو کن", "مدیرعامل", "#FFFFFF")


def test_talking_1_persian_name_keeps_joined_letters():
    from engine.talking_styles import talking_1 as t1
    plan = t1.ReelPlan(shots=[], captions=[], duration=3)
    def name_event(name):
        ass = t1.build_ass(plan, "هوک", [], name, "", None, moments=False)
        return next(line for line in ass.splitlines() if line.startswith("Dialogue") and ",name," in line)
    assert "\\fsp0" in name_event("رضا رفیعی")       # letter spacing would break Persian joining
    assert "\\fsp0" not in name_event("Reza Rafiei")  # Latin names keep the style's spacing
