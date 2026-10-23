import pytest

from creative import llm, script, speech
from creative.schemas import (Concept, ContentBrief, CreativeUnavailable, CriterionScore, ScriptDraft, ScriptLine, ScriptReview)

BRIEF = ContentBrief(kind="idea", topic="جایگزینی تدوینگرها با هوش مصنوعی", core_message="هوش مصنوعی اجرا را می‌گیرد، سلیقه را نه")
CONCEPT = Concept(id="A", name="سلیقه", angle="تدوینگر ابزار نیست، چشم است", hook="ابزار جای چشم را نمی‌گیرد", structure="contrarian_insight")


def line(i, narration, see="دست تدوینگر روی تایم‌لاین پر از کلیپ‌های پراکنده که یکی‌یکی کنار می‌رود", title="۱۰۰٪"):
    return ScriptLine(id=f"L{i}", role="claim", narration=narration, title=title, hear="تضاد", see=see, why_visual="نشان‌دادن تضاد",
                      emotion="کنجکاوی", focus="کلیپ انتخاب‌شده", link_prev="ادامهٔ همان تایم‌لاین")


def draft(*texts, structure="contrarian_insight"):
    return ScriptDraft(structure=structure, lines=[line(i + 1, t) for i, t in enumerate(texts)], ending="آخرین نما")


GOOD = draft("ابزار برش می‌زند؛ چشم انتخاب می‌کند.", "ماشین سریع‌تر است، اما سلیقه ندارد.", "تدوینگر خوب هنوز کارگردان لحظه‌هاست.")
TOO_LONG = draft(*["این یک جملهٔ بسیار بلند و پرتوضیح است که برای ویدیوی کوتاه اصلاً مناسب نیست و وقت را می‌خورد، چون کلی حرف دارد."] * 4)


def scores(value=8, evidence="ابزار برش می‌زند", verdict="ship", **extra):
    return ScriptReview(scores=[CriterionScore(criterion=c, score=value, reason="r", evidence="جمع نریشن 10.2 ثانیه" if c == "timing" else evidence)
                                for c in script.CRITERIA],
                        verdict=verdict, **extra)


class Fake:
    """Replaces llm.ask: answers by requested schema, in order, and counts calls."""
    def __init__(self, drafts, reviews):
        self.drafts, self.reviews, self.calls = list(drafts), list(reviews), {"write": 0, "review": 0}

    def __call__(self, schema, system, user, **kw):
        if schema is ScriptDraft:
            self.calls["write"] += 1
            return self.drafts.pop(0)
        if schema is ScriptReview:
            self.calls["review"] += 1
            return self.reviews.pop(0)
        raise AssertionError(schema)


def run(fake, monkeypatch, depth="fast", duration=15):
    monkeypatch.setattr(llm, "ask", fake)
    return script.run(BRIEF, CONCEPT, "caps", "src", duration_s=duration, depth=depth)


def test_measure_uses_real_speech_time_not_word_count():
    facts = script.measure(TOO_LONG, 15)
    assert facts["total_speech_s"] > facts["budget_s"] and any("ظرفیت" in p for p in facts["problems"])
    assert script.measure(GOOD, 15)["problems"] == []


def test_overlong_script_is_rewritten_even_if_the_critic_says_ship(monkeypatch):
    fake = Fake([TOO_LONG, GOOD], [scores(), scores()])
    result, report = run(fake, monkeypatch)
    assert result is GOOD and report.timing_ok and report.attempts == 2
    assert fake.calls == {"write": 2, "review": 2} and report.history[0]["verdict"] == "rewrite"
    assert any("ظرفیت" in item for item in report.history[0]["must_fix"])


def test_loop_is_bounded_by_depth(monkeypatch):
    bad = scores(4, verdict="rewrite", must_fix=["هوک ضعیف است"], change=["hook"])
    fake = Fake([GOOD] * 6, [bad] * 6)
    _, report = run(fake, monkeypatch, depth="fast")
    assert fake.calls["write"] <= 2 and report.attempts <= 2
    fake = Fake([GOOD, draft("یک راه دیگر برای شروع.", "ماشین اجرا می‌کند و آدم تصمیم می‌گیرد.", "این تمام ماجراست."), GOOD], [bad] * 6)
    _, report = run(fake, monkeypatch, depth="premium")
    assert fake.calls["write"] <= 3 and fake.calls["review"] <= 3


def test_evidence_must_be_in_the_script_or_the_score_is_capped(monkeypatch):
    liar = scores(9, evidence="جمله‌ای که در سناریو نیست اصلاً")
    review = script._verify(liar, GOOD, script.measure(GOOD, 15), False)
    hook = next(s for s in review.scores if s.criterion == "hook_strength")
    assert not hook.verified and hook.score <= 5 and review.verdict == "rewrite"
    honest = script._verify(scores(8), GOOD, script.measure(GOOD, 15), False)
    assert all(s.verified for s in honest.scores) and honest.verdict == "ship"


def test_cosmetic_rewrite_is_rejected_unless_structure_change_was_requested(monkeypatch):
    synonyms = draft("ابزار برش می‌زند؛ چشم انتخاب می‌کند!", "ماشین سریع‌تر است، ولی سلیقه ندارد.", "تدوینگر خوب هنوز کارگردان لحظه‌هاست.")
    bad = scores(5, verdict="rewrite", must_fix=["هوک باید قوی‌تر شود"], change=[])
    fake = Fake([GOOD, synonyms], [bad, bad])
    result, report = run(fake, monkeypatch)
    assert result is GOOD and report.history[0].get("rewrite_rejected")


def test_clichés_missing_visuals_and_repeated_title_are_found():
    weak = ScriptDraft(structure="x", lines=[line(1, "در دنیای امروز همه چیز عوض شده است."), line(2, "تدوین سریع", see="تصویر مرتبط", title="تدوین سریع"),
                                             line(3, "پایان خوبی بود.")])
    facts = script.measure(weak, 15)
    hard, soft = " ".join(facts["problems"]), " ".join(facts["notes"])
    assert "کلیشه" in hard and "تصویر مشخص" in hard and "ساختار" in hard
    assert "تکرار نریشن" in soft and "تکرار نریشن" not in hard        # a repeated title alone never costs a rewrite round


def test_critic_outage_does_not_hide_measured_problems(monkeypatch):
    def ask(schema, *a, **k):
        if schema is ScriptDraft:
            return TOO_LONG if not getattr(ask, "second", False) else GOOD
        raise CreativeUnavailable("critic down")
    monkeypatch.setattr(llm, "ask", ask)
    result, report = script.run(BRIEF, CONCEPT, "c", "s", duration_s=15, depth="fast")
    assert report.review is not None and report.deterministic and not report.timing_ok


def test_beats_carry_the_visual_first_contract():
    beats = script.to_beats(GOOD, 15)
    assert [b.line_id for b in beats] == ["L1", "L2", "L3"] and beats[0].why_visual and beats[0].focus and beats[1].link_prev
    longer = max(beats, key=lambda b: speech.speech_seconds(b.narration))
    shorter = min(beats, key=lambda b: speech.speech_seconds(b.narration))
    assert longer.duration_weight >= shorter.duration_weight


def test_dropped_connection_is_retried_not_fatal(monkeypatch):
    import httpx
    from brain import llm as brain_llm
    from creative import llm as creative_llm
    calls = []
    def flaky(system, user, route, budget):
        calls.append(route)
        if len(calls) == 1:
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")
        return {"structure": "x", "lines": []}, type("U", (), {"model": "m"})()
    monkeypatch.setattr(brain_llm, "gateway_json", flaky)
    monkeypatch.setattr(creative_llm, "configured", lambda: True)
    monkeypatch.setattr(creative_llm, "_sleep", lambda s: None)
    result = creative_llm._ask(ScriptDraft, "s", "u", route="creative_director", attempts=3)
    assert len(calls) == 2 and result.lines == []


def test_a_rewrite_that_only_fixes_a_measured_problem_is_accepted(monkeypatch):
    long_but_otherwise_same = draft(*["ابزار برش می‌زند؛ چشم انتخاب می‌کند. " * 3] * 3)
    fixed = draft("ابزار برش می‌زند؛ چشم انتخاب می‌کند.", "ماشین سریع‌تر است، اما سلیقه ندارد.", "تدوینگر خوب هنوز کارگردان لحظه‌هاست.")
    fake = Fake([long_but_otherwise_same, fixed], [scores(), scores()])
    result, report = run(fake, monkeypatch)
    assert result is fixed and report.timing_ok and "rewrite_rejected" not in report.history[0]


def test_unresolved_critic_objections_stay_in_the_report(monkeypatch):
    bad = scores(5, verdict="rewrite", must_fix=["پایان مبهم است"], change=["ending"])
    result, report = run(Fake([GOOD, GOOD], [bad, bad]), monkeypatch)
    assert report.review.verdict == "rewrite" and "پایان مبهم است" in report.review.must_fix and report.stopped == "cap"


def test_a_script_still_over_budget_after_the_critic_rounds_is_tightened_without_another_critic_call(monkeypatch):
    shorter = draft("ابزار برش می‌زند؛ چشم انتخاب می‌کند.", "ماشین سریع‌تر است، اما سلیقه ندارد.", "تدوینگر خوب هنوز کارگردان لحظه‌هاست.")
    ok = scores()
    fake = Fake([TOO_LONG, shorter], [ok])        # critic says ship, but the script is too long; no more critic rounds remain at depth 0
    monkeypatch.setattr(script, "DEPTH_REWRITES", {"fast": 0})
    result, report = run(fake, monkeypatch)
    assert result is shorter and report.timing_ok and fake.calls == {"write": 2, "review": 1}
    assert any(item.get("tighten") for item in report.history)


def test_beat_weights_stay_within_the_schema_for_long_videos():
    long_draft = draft(*["ابزار برش می‌زند؛ چشم انتخاب می‌کند و ماشین فقط سریع‌تر می‌شود، همین."] * 8)
    weights = [b.duration_weight for b in script.to_beats(long_draft, 120)]
    assert all(0.2 <= w <= 10 for w in weights) and abs(sum(weights) / len(weights) - 1) < 0.01
