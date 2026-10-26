import pytest

from creative import llm, script, speech
from creative.schemas import (Concept, ContentBrief, CreativeUnavailable, CriterionScore, ScriptDraft, ScriptLine, ScriptReview)

BRIEF = ContentBrief(kind="idea", topic="جایگزینی تدوینگرها با هوش مصنوعی", core_message="هوش مصنوعی اجرا را می‌گیرد، سلیقه را نه",
                     must_name=["تدوینگر"])
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


def test_the_tightened_script_is_reviewed_itself_not_judged_by_the_verdict_on_its_longer_version(monkeypatch):
    longer = draft(*["متن کاملاً متفاوت و بسیار طولانی شمارهٔ دو است که برای این ویدیوی کوتاه باز هم زیادی توضیح می‌دهد و ظرفیت را پر می‌کند، " * 2] * 6)
    bad = scores(4, verdict="rewrite", must_fix=["هوک ضعیف است"], change=["hook"])
    monkeypatch.setattr(script, "DEPTH_REWRITES", {"fast": 1})
    fake = Fake([TOO_LONG, longer, GOOD], [bad, bad, scores()])
    result, report = run(fake, monkeypatch, depth="fast")
    assert result is GOOD and report.timing_ok
    assert fake.calls == {"write": 3, "review": 3}
    assert report.review.verdict == "ship" and report.history[-1].get("after_tightening") is True


def test_loop_is_bounded_by_depth_and_stops_when_it_stalls(monkeypatch):
    bad = scores(4, verdict="rewrite", must_fix=["هوک ضعیف است"], change=["hook"])
    fake = Fake([GOOD] * 8, [bad] * 8)
    _, report = run(fake, monkeypatch, depth="fast")
    assert fake.calls["write"] <= 1 + script.DEPTH_REWRITES["fast"] and report.stopped == "stalled"       # no better score for two rounds: stop
    steps = [draft(f"یک راه دیگر برای شروع شمارهٔ {k}.", f"ماشین اجرا می‌کند و آدم تصمیم می‌گیرد؛ نسخهٔ {k}.", "این تمام ماجراست.") for k in range(8)]
    better = [scores(4 + k * 0.5, verdict="rewrite", must_fix=[f"هوک {k}"], change=["hook"]) for k in range(8)]
    fake = Fake([GOOD] + steps, better)
    _, report = run(fake, monkeypatch, depth="premium")
    assert fake.calls["write"] <= 1 + script.DEPTH_REWRITES["premium"] and report.stopped in {"cap", "shipped"}   # improving rounds keep going up to the cap


def test_a_follow_up_review_gets_the_previous_demands_and_the_converging_rule(monkeypatch):
    seen = []
    bad = scores(5, verdict="rewrite", must_fix=["هوک باید قوی‌تر شود"], change=["hook"])
    reviews = [bad, scores()]
    drafts = [TOO_LONG, GOOD]

    def fake(schema, system, user, **kw):
        if schema is ScriptDraft:
            return drafts.pop(0)
        seen.append((system, user))
        return reviews.pop(0)
    monkeypatch.setattr(llm, "ask", fake)
    script.run(BRIEF, CONCEPT, "caps", "src", duration_s=15, depth="fast")
    assert "previous_must_fix" not in seen[0][1] and "FOLLOW-UP" not in seen[0][0]
    assert "هوک باید قوی‌تر شود" in seen[1][1] and "FOLLOW-UP" in seen[1][0]


def test_passes_accepts_clean_measured_facts_and_good_scores_even_when_the_critic_keeps_asking(monkeypatch):
    from creative.schemas import ScriptReport
    good = scores(7, verdict="rewrite", must_fix=["یک سلیقهٔ دیگر"])
    report = ScriptReport(review=good, timing_ok=True, hard_problems=[])
    assert script.passes(report)
    assert not script.passes(ScriptReport(review=good, timing_ok=False))
    assert not script.passes(ScriptReport(review=good, timing_ok=True, hard_problems=["موضوع ویدیو در گفتار نیامده"]))
    assert not script.passes(ScriptReport(review=scores(5, verdict="rewrite"), timing_ok=True))                 # a criterion below 6
    weak_hook = scores(7, verdict="rewrite")
    next(item for item in weak_hook.scores if item.criterion == "hook_strength").score = 6.5
    assert not script.passes(ScriptReport(review=weak_hook, timing_ok=True))                                   # hook and payoff must reach 7
    assert script.passes(ScriptReport(review=scores(), timing_ok=True)) and not script.passes(ScriptReport(timing_ok=True))


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
    monkeypatch.setattr(script, "DEPTH_REWRITES", {"fast": 1})
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


def test_rejected_script_never_reaches_executable_beats(monkeypatch):
    from creative import director
    from creative.schemas import ScriptReport, Critique
    report = ScriptReport(stopped='cap', review=ScriptReview(verdict='rewrite', must_fix=['هوک ضعیف است']))
    monkeypatch.setattr(director.scriptwriter, 'run', lambda *a, **k: (GOOD, report))
    monkeypatch.setattr(director.scriptwriter, 'to_beats', lambda *a: pytest.fail('rejected draft must not become a storyboard'))
    with pytest.raises(CreativeUnavailable, match='کیفیت'):
        director._write_script(CONCEPT, BRIEF, Critique(chosen_id='A'), '', '', [], 0, 240, '', duration_s=30, reference=None, depth='fast')


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
    monkeypatch.setattr(script, "DEPTH_REWRITES", {"fast": 1})
    result, report = run(Fake([GOOD, GOOD], [bad, bad]), monkeypatch)
    assert report.review.verdict == "rewrite" and "پایان مبهم است" in report.review.must_fix and report.stopped == "cap"


def test_a_script_still_over_budget_after_the_critic_rounds_is_tightened_and_then_reviewed_once(monkeypatch):
    shorter = draft("ابزار برش می‌زند؛ چشم انتخاب می‌کند.", "ماشین سریع‌تر است، اما سلیقه ندارد.", "تدوینگر خوب هنوز کارگردان لحظه‌هاست.")
    ok = scores()
    fake = Fake([TOO_LONG, shorter], [ok, ok])    # critic says ship, but the script is too long; no rewrite rounds remain at depth 0: tighten, then one final review
    monkeypatch.setattr(script, "DEPTH_REWRITES", {"fast": 0})
    result, report = run(fake, monkeypatch)
    assert result is shorter and report.timing_ok and fake.calls == {"write": 2, "review": 2} and report.history[-1].get("after_tightening") is True
    assert any(item.get("tighten") for item in report.history)


def test_beat_weights_stay_within_the_schema_for_long_videos():
    long_draft = draft(*["ابزار برش می‌زند؛ چشم انتخاب می‌کند و ماشین فقط سریع‌تر می‌شود، همین."] * 8)
    weights = [b.duration_weight for b in script.to_beats(long_draft, 120)]
    assert all(0.2 <= w <= 10 for w in weights) and abs(sum(weights) / len(weights) - 1) < 0.01


def test_the_topic_must_be_spoken():
    off_topic = draft("برش رو می‌شه سپرد به ابزار.", "ولی تصمیمِ برش رو نه.", "ابزار می‌بره؛ تو تصمیم می‌گیری.")
    facts = script.measure(off_topic, 15, must_name=["تدوینگر", "هوش مصنوعی"])
    assert any("موضوع ویدیو در گفتار نیامده" in p and "هوش مصنوعی" in p for p in facts["problems"])
    named = draft("هوش مصنوعی جای تدوینگر را می‌گیرد؟", "ابزار می‌بُرد؛ تصمیم با توست.", "این هنوز کار آدم است.")
    ok = script.measure(named, 15, must_name=["تدوینگر", "هوش مصنوعی"])
    assert not any("موضوع ویدیو" in p for p in ok["problems"]) and not ok["notes"]
    late = draft("ابزار می‌بُرد؛ تصمیم با توست.", "این کار آدم است.", "هوش مصنوعی تدوینگر را کنار نمی‌گذارد.")
    assert any("دو جملهٔ اول" in n for n in script.measure(late, 15, must_name=["تدوینگر"])["notes"])


def test_evidence_matching_tolerates_punctuation_joined_quotes_and_arabic_letters():
    for evidence in ("«ابزار برش می‌زند» … «تدوینگر خوب هنوز کارگردان لحظه‌هاست»", "ماشین سریع‌تر است اما سلیقه ندارد", "L2: «ماشین سريع‌تر است، اما سلیقه ندارد.» | «چشم انتخاب می‌کند»"):
        review = script._verify(scores(8, evidence=evidence), GOOD, script.measure(GOOD, 15), False)
        assert all(s.verified for s in review.scores), evidence
