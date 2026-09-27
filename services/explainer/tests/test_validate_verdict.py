"""The validator must not let prose contradict the facts about a pick's OUTCOME.

The bundle carries the ground truth — `status`, `result.pick_won` — and the
facts contract deliberately omits `pick_won` for a rebuilt pick. The only
outcome check in the validator was the rebuilt-disclosure word list, so prose
could assert a verdict the facts contradict, and a model that inferred one from
`result.score` would pass.

Measured against the validator as it stood (rebuilt final, no `pick_won`):

    "This pick was rebuilt after kickoff, so it is not counted. The pick was
     right anyway."                                               -> PASSED
    "This was rebuilt after kickoff and it picked the winner."    -> PASSED
    "There is no pick. The pick was right all the same."          -> PASSED
    pre_kickoff, pick_won FALSE, "The pick was right: BAL 27-20." -> PASSED
    pre_kickoff, pick_won FALSE, "The pick was wrong: BAL 27-20." -> PASSED

Every body below is built to satisfy ALL the other rules — 3-6 sections, 60
words per section, 120-220 total, no banned word, every number present in the
facts — so the only thing that can reject one is the verdict rule. A body that
tripped the length or number rule would pass these tests for the wrong reason,
and the two honest cases (`...may be called wrong/right`) would be meaningless.
"""
import json

from explainer.validate import validate

FACTS = {
    "sport": "nfl", "id": "g1", "title": "Chiefs at Ravens",
    "starts_at": "2026-10-05T00:20:00Z", "status": "final",
    "pick": {"label": "BAL", "prob": 0.62},
    "markets": [{"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"}],
}

# 48 words: comfortably under the 60-word per-section cap, no digits, and the
# only number-like token ("62%") is in the facts.
NEUTRAL = (
    "Baltimore are the slight favourites and the rating gap has held all week. "
    "The market is a little generous by the model's own reading, and rest and "
    "weather point the same way for both sides. Kansas City are good enough to "
    "win this, so read the number as a lean rather than a call that cannot miss."
)


def _body(*claims: str) -> dict:
    """3 sections, 60 words or fewer each, 120-220 in total, no stray numbers."""
    sections = [{"market": f"m{i}", "title": f"Read {i}", "text": NEUTRAL} for i in range(3)]
    for i, claim in enumerate(claims):
        sections[i]["text"] = f"{claim} {NEUTRAL}"
    return {"headline": "Baltimore favoured at 62%", "sections": sections}


def _validate(facts: dict, body: dict) -> list[str]:
    return validate(body, json.dumps(facts), "[]")


def test_the_control_bodies_are_valid_so_the_verdict_rule_is_what_judges():
    """If these control bodies were rejected for any other reason, every
    assertion below would be vacuous. Pin that first."""
    facts = {**FACTS, "pick_timing": "rebuilt", "result": {"score": "BAL 27-20"}}
    control = _body(
        "This pick was rebuilt after kickoff, so it is not counted.",
        "The scoreline model expected a close game throughout.",
    )
    problems = _validate(facts, control)
    assert problems == [], f"the control body is not clean, so these tests prove nothing: {problems}"


def test_a_rebuilt_pick_cannot_be_called_right():
    facts = {**FACTS, "pick_timing": "rebuilt", "result": {"score": "BAL 27-20"}}
    problems = _validate(facts, _body(
        "This pick was rebuilt after kickoff, so it is not counted.",
        "The pick was right anyway.",
    ))
    assert any("verdict" in p for p in problems), \
        f"a rebuilt pick was allowed to claim it won: {problems}"


def test_a_rebuilt_pick_cannot_say_it_picked_the_winner():
    facts = {**FACTS, "pick_timing": "rebuilt", "result": {"score": "BAL 27-20"}}
    problems = _validate(facts, _body(
        "This was rebuilt after kickoff and it picked the winner here.",
        "The scoreline model expected a close game throughout.",
    ))
    assert any("verdict" in p for p in problems), \
        f"a rebuilt pick was allowed to say it picked the winner: {problems}"


def test_no_pick_cannot_be_called_right():
    facts = {**FACTS, "pick_timing": "none", "pick": None, "result": None}
    problems = _validate(facts, _body(
        "There is no pick for this one yet, and the pick was right all the same.",
    ))
    assert any("verdict" in p for p in problems), \
        f"a bundle with no pick was allowed to claim one was right: {problems}"


def test_a_lost_pick_cannot_be_called_right():
    facts = {**FACTS, "pick_timing": "pre_kickoff", "result": {"score": "BAL 27-20", "pick_won": False}}
    problems = _validate(facts, _body("The pick was right: BAL 27-20."))
    assert any("verdict" in p for p in problems), \
        f"a pick the facts say lost was allowed to be called right: {problems}"


def test_a_won_pick_cannot_be_called_wrong():
    facts = {**FACTS, "pick_timing": "pre_kickoff", "result": {"score": "BAL 27-20", "pick_won": True}}
    problems = _validate(facts, _body("The pick was wrong: BAL 27-20."))
    assert any("verdict" in p for p in problems), \
        f"a pick the facts say won was allowed to be called wrong: {problems}"


def test_a_lost_pick_may_be_called_wrong():
    """The negative case: the fix must not reject an honest loss."""
    facts = {**FACTS, "pick_timing": "pre_kickoff", "result": {"score": "BAL 27-20", "pick_won": False}}
    assert _validate(facts, _body("The pick was wrong: BAL 27-20.")) == []


def test_a_won_pick_may_be_called_right():
    facts = {**FACTS, "pick_timing": "pre_kickoff", "result": {"score": "BAL 27-20", "pick_won": True}}
    assert _validate(facts, _body("The pick was right: BAL 27-20.")) == []
