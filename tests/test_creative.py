"""Creative Engine: contracts, degradation and selection, with the model mocked."""
import pytest

import creative
from creative import llm
from creative.director import _pick, compose_notes
from creative.schemas import Concept, ContentBrief, ConceptScore, Critique, CreativeUnavailable

SENTENCES = [{"start": 0.0, "end": 3.0, "text": "همه فکر می‌کنن ریلز یعنی ادیت سریع"},
             {"start": 3.0, "end": 7.0, "text": "ولی عدد واقعی ۸۷ درصد بیننده‌ها توی سه ثانیه اول می‌رن"},
             {"start": 7.0, "end": 12.0, "text": "پس هوک مهم‌تر از هر افکتیه"}]

BRIEF = {"kind": "talk", "topic": "ریلز و هوک", "core_message": "هوک مهم‌ترین بخش است", "audience": "تولیدکنندگان محتوا",
         "goal": "اعتبار", "tone": "قاطع", "emotional_arc": ["تعجب", "اثبات"],
         "key_moments": [{"i": 1, "why": "عدد", "emotion": "proof"}], "proof_points": ["۸۷ درصد"], "must_not": ["ادعای اضافه"]}


def concept(i, style="talking_1", hook="۸۷٪ قبل از ثانیه ۳ می‌رن"):
    return {"id": i, "name": f"ایده {i}", "angle": "زاویه", "hook": hook, "style_hint": style,
            "beats": [{"role": "hook", "intent": "توقف", "visual": "عدد بزرگ ۸۷٪", "motion": "metric-count-up", "sentence": 1}],
            "visual_language": "تایپوگرافی", "pacing": "تند", "why_it_works": "-", "risks": "-"}


CRIT = {"scores": [{"id": "A", "hook_strength": 6, "originality": 5, "fit_to_content": 6, "feasibility": 9, "faithfulness": 9},
                   {"id": "B", "hook_strength": 9, "originality": 8, "fit_to_content": 8, "feasibility": 8, "faithfulness": 9},
                   {"id": "C", "hook_strength": 5, "originality": 7, "fit_to_content": 5, "feasibility": 4, "faithfulness": 8}],
        "chosen_id": "B", "verdict": "B has the strongest hook", "improvements": ["Hold the number for 1.2 s"], "improved_hook": "۸۷٪ می‌رن. چرا؟"}


class Fake:
    """Routes a fake model response by which prompt is being used."""
    def __init__(self, critique=CRIT, fail_critic=False, bad_first=False):
        self.calls, self.critique, self.fail_critic, self.bad_first = [], critique, fail_critic, bad_first

    def __call__(self, system, user, route="editing_agent", max_tokens=16000):
        self.calls.append(route)
        from brain.llm import LLMUsage
        usage = LLMUsage(input_tokens=1, output_tokens=1, model="fake-model", elapsed_sec=0.01)
        if route == llm.CRITIC_ROUTE:
            if self.fail_critic:
                raise RuntimeError("LM API ReadTimeout")
            return self.critique, usage
        if "propose THREE concepts" in system:
            return {"concepts": [concept("A", "talking_2"), concept("B", "talking_3", "مشکل عدد است"), concept("C", "talking_4")]}, usage
        if "production-ready plan" in system:
            self.expanded = True
            return {"beats": [{"role": "hook", "intent": "توقف", "visual": "عدد ۸۷٪", "motion": "metric-count-up", "sentence": 1},
                              {"role": "payoff", "intent": "نتیجه", "visual": "هوک", "motion": "kinetic-hook-slam", "sentence": 2}],
                    "visual_language": "تایپوگرافی درشت", "pacing": "تند و بعد مکث"}, usage
        if self.bad_first and self.calls.count(llm.DIRECTOR_ROUTE) == 1:
            self.bad_first = False
            return {"nonsense": True}, usage  # missing topic/core_message → validation error → one repair attempt
        return BRIEF, usage


@pytest.fixture
def patch(monkeypatch):
    def apply(fake):
        monkeypatch.setattr("brain.llm.gateway_json", fake)
        monkeypatch.setattr(llm, "configured", lambda: True)
        return fake
    return apply


def test_direct_talk_picks_critics_choice_and_builds_engine_guidance(patch):
    fake = patch(Fake())
    plan = creative.direct_talk(SENTENCES, "ریلز حرفه‌ای")
    assert plan.chosen.id == "B" and plan.style == "talking_3"
    assert fake.calls == [llm.DIRECTOR_ROUTE, llm.DIRECTOR_ROUTE, llm.CRITIC_ROUTE, llm.DIRECTOR_ROUTE]  # brief, proposal, critique, expansion
    assert [b.sentence for b in plan.chosen.beats] == [1, 2] and plan.chosen.visual_language == "تایپوگرافی درشت"
    assert "۸۷٪ می‌رن. چرا؟" in plan.director_notes          # critic's improved hook reaches the engines
    assert "Hold the number" in plan.director_notes and "Must not" in plan.director_notes
    assert plan.public()["alternatives"] and "models" not in plan.public()
    assert plan.models == ["fake-model"]


def test_critic_failure_degrades_instead_of_failing(patch):
    patch(Fake(fail_critic=True))
    plan = creative.direct_talk(SENTENCES)
    assert plan.chosen.id == "A" and "Not reviewed" in plan.critique.verdict


def test_invalid_json_is_repaired_once(patch):
    fake = patch(Fake(bad_first=True))
    plan = creative.direct_talk(SENTENCES)
    assert plan.brief.topic and fake.calls.count(llm.DIRECTOR_ROUTE) == 4  # bad brief, repaired brief, proposal, expansion


def test_gateway_failure_is_creative_unavailable(patch):
    def boom(*args, **kwargs):
        raise RuntimeError("LM API ReadTimeout")
    patch(boom)
    with pytest.raises(CreativeUnavailable):
        creative.direct_talk(SENTENCES)


def test_unconfigured_gateway_is_unavailable(monkeypatch):
    monkeypatch.setattr(llm, "configured", lambda: False)
    with pytest.raises(CreativeUnavailable):
        creative.direct_talk(SENTENCES)


def test_pick_overrules_a_choice_the_scores_contradict():
    concepts = [Concept(**concept("A")), Concept(**concept("B"))]
    critique = Critique(chosen_id="A", scores=[ConceptScore(id="A", hook_strength=3, originality=3, fit_to_content=3, feasibility=3, faithfulness=3),
                                              ConceptScore(id="B", hook_strength=9, originality=9, fit_to_content=9, feasibility=9, faithfulness=9)])
    assert _pick(critique, concepts).id == "B"
    close = Critique(chosen_id="A", scores=[ConceptScore(id="A", hook_strength=7, originality=7, fit_to_content=7, feasibility=7, faithfulness=7),
                                           ConceptScore(id="B", hook_strength=8, originality=7, fit_to_content=7, feasibility=7, faithfulness=7)])
    assert _pick(close, concepts).id == "A"   # small gaps respect the critic's explicit choice


def test_non_talk_kinds_never_pick_an_engine_style(patch):
    patch(Fake())
    plan = creative.direct_product({"product_name": "صندلی"}, "تیزر ۳۰ ثانیه", image_count=3)
    assert plan.kind == "product" and plan.style is None and all(c.style_hint is None for c in plan.concepts)


def test_feature_flag(monkeypatch):
    monkeypatch.setenv("CREATIVE_ENGINE", "0")
    assert creative.enabled() is False
    monkeypatch.setenv("CREATIVE_ENGINE", "1")
    assert creative.enabled() is True


def test_schemas_tolerate_messy_model_output():
    brief = ContentBrief(topic="  t  ", core_message="m", emotional_arc="one string", key_moments=["junk", {"i": 2, "why": "w"}], proof_points=None)
    assert brief.emotional_arc == ["one string"] and len(brief.key_moments) == 1 and brief.proof_points == []


def test_truncated_json_is_retried_with_a_larger_budget(monkeypatch):
    import json as _json
    budgets = []

    def flaky(system, user, route="editing_agent", max_tokens=16000):
        from brain.llm import LLMUsage
        budgets.append(max_tokens)
        if len(budgets) == 1:
            raise _json.JSONDecodeError("Unterminated string", "{", 1)
        return BRIEF, LLMUsage(input_tokens=1, output_tokens=1, model="m", elapsed_sec=0.0)

    monkeypatch.setattr("brain.llm.gateway_json", flaky)
    monkeypatch.setattr(llm, "configured", lambda: True)
    brief = llm.ask(ContentBrief, "s", "u", route=llm.DIRECTOR_ROUTE, tokens=4000)
    assert brief.topic and budgets[1] > budgets[0]


def test_short_cooldowns_are_waited_out_once(monkeypatch):
    from brain.lm_gateway import GatewayError
    from brain.llm import LLMUsage
    waits, calls = [], []

    def limited(system, user, route="editing_agent", max_tokens=16000):
        calls.append(1)
        if len(calls) == 1:
            raise GatewayError("LM API HTTP 503: All models exhausted. Soonest reset ~38s.", 503, True)
        return BRIEF, LLMUsage(input_tokens=1, output_tokens=1, model="m", elapsed_sec=0.0)

    monkeypatch.setattr("brain.llm.gateway_json", limited)
    monkeypatch.setattr(llm, "configured", lambda: True)
    monkeypatch.setattr(llm, "_sleep", waits.append)
    assert llm.ask(ContentBrief, "s", "u", route=llm.DIRECTOR_ROUTE).topic
    assert waits == [40] and len(calls) == 2


def test_non_rate_limit_errors_do_not_sleep(monkeypatch):
    from brain.lm_gateway import GatewayError
    waits = []

    def broken(*args, **kwargs):
        raise GatewayError("LM API ReadTimeout", 504, True)

    monkeypatch.setattr("brain.llm.gateway_json", broken)
    monkeypatch.setattr(llm, "configured", lambda: True)
    monkeypatch.setattr(llm, "_sleep", waits.append)
    with pytest.raises(CreativeUnavailable):
        llm.ask(ContentBrief, "s", "u", route=llm.DIRECTOR_ROUTE)
    assert waits == []


def test_expansion_failure_keeps_the_outline(patch):
    class NoExpand(Fake):
        def __call__(self, system, user, route="editing_agent", max_tokens=16000):
            if "production-ready plan" in system:
                raise RuntimeError("LM API ReadTimeout")
            return super().__call__(system, user, route, max_tokens)
    patch(NoExpand())
    plan = creative.direct_talk(SENTENCES)
    assert plan.chosen.beats and plan.chosen.beats[0].intent       # from the outline sketch, not empty


# ── Flow F: revision ───────────────────────────────────────────────────────────
from creative import revise
from creative.revise import RevisionOp, apply_to_talking

STATE = {"style": "talking_2", "hook": "قدیمی", "render_settings": {"grade": {"saturation": 100, "contrast": 100}, "zoom": {"amount": 100, "enabled": True},
         "title_color": "#F5B800", "outro_logo": {"enabled": True}},
         "captions": [{"i": 0, "text": "الف"}], "storyboard": [{"i": 1, "title": "قدیمی", "visual_type": "concept"}, {"i": 3, "title": "دیگر", "visual_type": "stat"}]}


def test_revision_ops_map_only_onto_real_engine_fields():
    ops = [RevisionOp(op="rewrite_hook", text="۸۷٪ می‌رن. چرا؟", highlight=["۸۷٪", "نیست"]),
           RevisionOp(op="set_render", settings={"saturation": 400, "contrast": 130, "zoom_amount": 150, "title_color": "#00ff88", "outro_logo": False, "bogus": 1}),
           RevisionOp(op="replace_visual", sentence=1, text="سقف درآمد", visual_type="not-a-type", items=["خدمت"]),
           RevisionOp(op="drop_visual", sentence=3),
           RevisionOp(op="edit_caption", sentence=0, text="الف اصلاح"),
           RevisionOp(op="edit_caption", sentence=99, text="خارج از محدوده")]
    change = apply_to_talking(STATE, ops, sentence_count=4)
    c = change.changes
    assert c["hook2"] == "۸۷٪ می‌رن. چرا؟" and "hook" not in c                 # split styles keep their hook in hook2
    assert c["hook_highlight"] == ["۸۷٪"]                                        # highlight must be words of the hook
    assert c["render_settings"]["grade"]["saturation"] == 180                    # clamped to the engine's limit
    assert c["render_settings"]["grade"]["contrast"] == 130 and c["render_settings"]["zoom"]["amount"] == 150
    assert c["render_settings"]["title_color"] == "#00FF88" and c["render_settings"]["outro_logo"]["enabled"] is False
    assert c["storyboard"] == [{"i": 1, "title": "سقف درآمد", "visual_type": "concept", "items": ["خدمت"]}]  # bad type falls back; sentence 3 dropped
    assert c["captions"] == [{"i": 0, "text": "الف اصلاح"}]                      # out-of-range sentence ignored
    assert change.rerender and STATE["render_settings"]["grade"]["saturation"] == 100   # input state not mutated


def test_unsupported_requests_are_reported_not_faked():
    change = apply_to_talking({**STATE, "style": "talking_1"}, [RevisionOp(op="replace_visual", sentence=1, text="x"),
                                                               RevisionOp(op="unsupported", reason="تغییر صدا ممکن نیست")], 4)
    assert not change.rerender and len(change.unsupported) == 2


def test_change_style_requests_a_restyle():
    change = apply_to_talking(STATE, [RevisionOp(op="change_style", style="talking_3")], 4)
    assert change.restyle == "talking_3" and change.changes["style"] == "talking_3"
    assert not apply_to_talking(STATE, [RevisionOp(op="change_style", style="talking_2")], 4).rerender   # already that style
    assert not apply_to_talking(STATE, [RevisionOp(op="change_style", style="nonsense")], 4).rerender


def test_interpret_validates_and_bounds_the_model_output(monkeypatch):
    from brain.llm import LLMUsage
    seen = {}

    def fake(system, user, route="editing_agent", max_tokens=16000):
        seen["route"] = route
        return {"summary": "هوک عوض می‌شود", "ops": [{"op": "rewrite_hook", "text": "هوک تازه"}, "junk", {"op": "launch_rocket"}]}, LLMUsage(input_tokens=1, output_tokens=1, model="m", elapsed_sec=0.0)

    monkeypatch.setattr("brain.llm.gateway_json", fake)
    monkeypatch.setattr(llm, "configured", lambda: True)
    # an unknown op fails validation → one repair attempt, then the interpreter gives up cleanly
    with pytest.raises(CreativeUnavailable):
        revise.interpret("هوک رو عوض کن", {"style": "talking_1"})
    assert seen["route"] == llm.REVISION_ROUTE


# ── resilience of the engines' own decision call ─────────────────────────────
def test_decision_call_retries_transient_provider_failures(monkeypatch):
    from brain import llm as brain_llm
    from brain.lm_gateway import GatewayError
    calls, waits = [], []

    def flaky(system, user, route="editing_agent", max_tokens=16000):
        calls.append(route)
        if len(calls) < 3:
            raise GatewayError("LM API HTTP 502: upstream_error", 502, True)
        return {"ok": True}, None

    monkeypatch.setattr(brain_llm, "gateway_json", flaky)
    assert brain_llm.gateway_json_resilient("s", "u", "editing_agent", _sleep=waits.append) == ({"ok": True}, None)
    assert len(calls) == 3 and waits == [4, 8]            # bounded exponential waits


def test_decision_call_does_not_retry_permanent_errors(monkeypatch):
    from brain import llm as brain_llm
    from brain.lm_gateway import GatewayError
    waits = []

    def denied(*args, **kwargs):
        raise GatewayError("This AI route is disabled", 503, False)

    monkeypatch.setattr(brain_llm, "gateway_json", denied)
    with pytest.raises(GatewayError):
        brain_llm.gateway_json_resilient("s", "u", _sleep=waits.append)
    assert waits == []


def test_decision_call_honours_the_gateways_cooldown_hint(monkeypatch):
    from brain import llm as brain_llm
    from brain.lm_gateway import GatewayError
    waits, calls = [], []

    def limited(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise GatewayError("HTTP 503: exhausted. Soonest reset ~38s.", 503, True)
        return {"ok": 1}, None

    monkeypatch.setattr(brain_llm, "gateway_json", limited)
    brain_llm.gateway_json_resilient("s", "u", _sleep=waits.append)
    assert waits == [40]
