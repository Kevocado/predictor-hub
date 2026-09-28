"""validate() must police the v2 shape, not just prose numbers.

The number pool, the banned words, the rebuilt-pick disclosure and the
outcome-verdict check are all unchanged and all still load-bearing — this file
adds the rules that only exist because the shape changed. In particular the
factor rules, because a v1 body would otherwise pass a v1-shaped check and be
rendered by a v2 panel as nothing.
"""
import json

import pytest

from explainer.validate import validate

# Shaped like the real bundle (spec §5c), including a `record`, because the
# pseudo-markets only resolve if the facts actually carry them.
FACTS = {
    "sport": "nfl", "id": "g1", "title": "Chiefs at Ravens",
    "starts_at": "2026-10-05T00:20:00Z", "status": "upcoming",
    "pick_timing": "pre_kickoff", "pick": {"label": "BAL", "prob": 0.62},
    "markets": [{"market": "moneyline", "model": {"KC": 0.38, "BAL": 0.62}},
                {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"}],
    "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 68},
}
F = json.dumps(FACTS)


def _f(key="moneyline", direction="up", headline="Model leans Baltimore",
       text="The rating gap has held all week."):
    return {"key": key, "direction": direction, "headline": headline, "text": text}


def _v(factors, verdict="Baltimore is the pick."):
    return {"verdict": verdict, "factors": factors}


def _clean_body():
    return _v([_f(), _f("record", "down")])


# --- the shape -------------------------------------------------------------

def test_a_clean_verdict_passes():
    assert validate(_clean_body(), F, "[]") == []


def test_a_v1_body_is_rejected_outright():
    """The regression this whole phase is for.

    `prompt_version` is bumped, so a v1 row should never be read by this
    renderer. But a reused version must fail *loudly* rather than render an empty
    panel, and the only place that can notice is here.
    """
    v1 = {"headline": "Baltimore favored at 62%", "sections": [
        {"market": "result", "title": "Pick", "text": "It likes Baltimore."}]}
    problems = validate(v1, F, "[]")
    assert problems, "a v1 body passed the v2 shape check"
    assert "verdict" in problems[0]


@pytest.mark.parametrize("body", [
    {"factors": [_f(), _f("record")]},                                  # no verdict
    {"verdict": "v"},                                                    # no factors
    {"verdict": "v", "factors": {}},                                     # not a list
    {"verdict": "v", "factors": ["a string"]},                           # not dicts
    {"verdict": 7, "factors": [_f(), _f("record")]},                     # verdict not str
])
def test_malformed_bodies_are_rejected(body):
    assert validate(body, F, "[]"), f"accepted: {body}"


# --- the factor rules ------------------------------------------------------

@pytest.mark.parametrize("n", [0, 1, 5, 6])
def test_the_factor_count_is_two_to_four(n):
    problems = validate(_v([_f() for _ in range(n)]), F, "[]")
    assert any("factors" in p for p in problems), f"{n} factors was accepted: {problems}"


@pytest.mark.parametrize("n", [2, 3, 4])
def test_two_to_four_factors_pass(n):
    assert validate(_v([_f() for _ in range(n)]), F, "[]") == [], f"{n} factors was rejected"


def test_a_direction_must_be_one_of_the_three():
    """The contract, restated as the validator enforces it.

    `neutral` joined `up` and `down`: a factor that is not about the pick — the
    total, both teams to score, the record — has to be sayable, and with only two
    values the model had to pick one of them and was wrong half the time. Widening
    the vocabulary is not widening what is accepted, though: anything outside the
    three is still refused, which is the whole content of this test.
    """
    assert validate(_v([_f(direction="neutral"), _f("record")]), F, "[]") == [], (
        "a neutral factor is now in the contract and must be accepted"
    )
    for good in ("up", "down", "neutral"):
        assert validate(_v([_f(direction=good), _f("record")]), F, "[]") == [], good

    problems = validate(_v([_f(direction="sideways"), _f("record")]), F, "[]")
    assert any("direction" in p for p in problems), f"accepted: {problems}"


@pytest.mark.parametrize("bad", ["sideways", "UP", "Up", "", None, 1, True, "up ", "up/down"])
def test_nothing_outside_the_three_is_accepted(bad):
    """A third value must not become "anything goes".

    Every one of these is a different way of writing a direction, and only three
    of them are directions. The check is membership in `DIRECTIONS`, not a length
    or a prefix test, so a body carrying `1` or `True` (which compare equal to
    nothing here) or `"up "` is refused rather than coerced into meaning.
    """
    problems = validate(_v([_f(direction=bad), _f("record")]), F, "[]")
    assert any("direction" in p for p in problems), f"accepted {bad!r}: {problems}"


def test_a_factor_whose_key_is_not_in_the_facts_is_rejected():
    # The service drops these in `resolve_factors`, so reaching `validate()` with
    # one means the drop was bypassed — which is exactly when it should be an
    # error rather than a silently missing row.
    problems = validate(_v([_f(key="pitching_weather"), _f("record")]), F, "[]")
    assert any("pitching_weather" in p for p in problems), f"accepted: {problems}"


def test_the_pseudo_markets_are_allowed():
    assert validate(_v([_f(key="record"), _f(key="context")]), F, "[]") == []


# --- length ----------------------------------------------------------------

def test_the_verdict_may_not_run_on():
    problems = validate(_clean_body() | {"verdict": " ".join(["word"] * 19)}, F, "[]")
    assert any("verdict" in p for p in problems), f"accepted: {problems}"


def test_a_factor_headline_may_not_run_on():
    long_headline = " ".join(["word"] * 11)
    problems = validate(_v([_f(headline=long_headline), _f("record")]), F, "[]")
    assert any("headline" in p for p in problems), f"accepted: {problems}"


def test_a_factor_text_may_not_run_on():
    long_text = " ".join(["word"] * 36)
    problems = validate(_v([_f(text=long_text), _f("record")]), F, "[]")
    assert any("text" in p for p in problems), f"accepted: {problems}"


def test_a_short_body_is_fine_and_no_minimum_length_survives_from_v1():
    """v1 demanded 120-220 words. There is no minimum in v2.

    A v2 body is short by construction — a verdict line and 2-4 factors, with the
    figures drawn by the panel rather than written in prose. A word floor kept
    from v1 would reject the honest short answer and push the model back toward
    padding, which is the opposite of what the redesign is for.
    """
    assert validate(_clean_body(), F, "[]") == [], "a short v2 body was rejected"


# --- what must NOT have changed -------------------------------------------

def test_the_band_is_not_part_of_the_model_contract():
    # There is deliberately no band rule here, because the model does not supply
    # one (§13a): `contract.band_for` computes it. `validate()` policing a field
    # nothing writes would be a test that cannot fail.
    with_band = _clean_body() | {"band": "strong"}
    assert validate(with_band, F, "[]") == validate(_clean_body(), F, "[]"), (
        "a model-supplied band changed the verdict, so something is still reading it"
    )


def test_a_number_the_facts_do_not_carry_is_still_rejected():
    body = _v([_f(text="The gap is 71%."), _f("record")])
    problems = validate(body, F, "[]")
    assert any("71" in p for p in problems), f"a number in a factor passed: {problems}"


def test_a_number_the_facts_do_carry_is_still_accepted():
    body = _v([_f(text="It rates Baltimore better by 3.4 points."), _f("record")])
    assert validate(body, F, "[]") == [], "a real figure from the facts was rejected"


def test_banned_words_are_still_banned():
    body = _v([_f(text="This is a guaranteed winner at 3.4 points."), _f("record")])
    problems = validate(body, F, "[]")
    assert any("banned" in p for p in problems), f"accepted: {problems}"


def test_the_rebuilt_disclosure_is_still_required():
    facts = {**FACTS, "pick_timing": "rebuilt"}
    body = _v([_f(text="It rates Baltimore better by 3.4 points."), _f("record")])
    problems = validate(body, json.dumps(facts), "[]")
    assert any("rebuilt" in p for p in problems), f"accepted: {problems}"


def test_the_outcome_verdict_check_still_runs_on_factors():
    """The Critical from the earlier review, carried into v2.

    It used to scan `headline` + section texts. In v2 the text lives in factor
    headlines and texts, so the check has to follow it there — and a validator
    that quietly stopped scanning would be an honesty regression nobody would
    notice until a reader was told their pick won.
    """
    facts = {**FACTS, "status": "final", "result": {"score": "24-17", "pick_won": False}}
    body = _v([_f(text="The pick was right and it landed easily."), _f("record")])
    problems = validate(body, json.dumps(facts), "[]")
    assert any("contradict" in p for p in problems), (
        f"the outcome check did not see a claim in a factor: {problems}"
    )
