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

# 40 words: under the 60-word per-section cap with a claim in front of it, no
# digits, and no spelled-out numbers. Both matter and both bit the first
# version of this file:
#   * the validator scans section TITLES for numbers too (validate.py puts
#     them in the same `texts` list as the prose), so titles reading
#     "Read 0 / 1 / 2" failed as invented figures;
#   * at 48 words, prefixing a claim pushed sections over 60 and the test
#     passed for the wrong reason.
# The control-body test below is what catches both, and it is the reason it
# exists: every other test here asserts something is rejected, and a body
# rejected for a different reason would make them all vacuous.
NEUTRAL = (
    "Baltimore are the slight favourites and the rating gap has held all week. "
    "Rest and weather point the same way, and Kansas City are good enough to "
    "win this, so read the number as a lean rather than a call."
)
TITLES = ("Read one", "Read two", "Read three")


def _body(*claims: str, headline: str = "Baltimore favoured at 62%") -> dict:
    """3 sections, 60 words or fewer each, 120-220 in total, no stray numbers.

    `headline` is a parameter because the no-pick case cannot use the default:
    it removes the pick from the facts, and a headline still quoting 62% would
    then be an invented figure and be rejected as one, which is the wrong reason.
    """
    sections = [{"market": f"m{i}", "title": TITLES[i], "text": NEUTRAL} for i in range(3)]
    for i, claim in enumerate(claims):
        sections[i]["text"] = f"{claim} {NEUTRAL}"
    return {"headline": headline, "sections": sections}


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
        headline="No pick for this one",
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


# ---------------------------------------------------------------------------
# The other direction.
#
# A verdict check that is too blunt is its own honesty failure: it rejects
# honest prose, the service falls back to the template, and the panel quietly
# loses the explanations it was built for. These pin the cases a naive keyword
# match would swallow, and they are the reason CLAIM_WON below is a subject +
# verb pattern rather than a word list.
# ---------------------------------------------------------------------------

REBUILT = {**FACTS, "pick_timing": "rebuilt", "result": {"score": "BAL 27-20"}}
LOST = {**FACTS, "pick_timing": "pre_kickoff", "result": {"score": "BAL 27-20", "pick_won": False}}
WON = {**FACTS, "pick_timing": "pre_kickoff", "result": {"score": "BAL 27-20", "pick_won": True}}


def test_a_rebuilt_pick_may_still_be_described_without_a_verdict():
    """The everyday case, and the one a keyword match breaks.

    "won" and "right" both occur in ordinary football prose that has nothing to
    do with whether the pick landed. Every one of these is honest.
    """
    problems = _validate(REBUILT, _body(
        "This pick was rebuilt after kickoff, so it is not counted.",
        "Baltimore won the toss and took the opening kickoff.",
    ))
    assert problems == [], f"honest prose was rejected: {problems}"


def test_a_lost_pick_may_be_described_in_words_other_than_right_and_wrong():
    problems = _validate(LOST, _body("The pick was wrong: BAL 27-20."))
    assert problems == [], f"an honest loss was rejected: {problems}"


def test_the_word_right_about_the_reading_is_not_a_verdict_claim():
    """"Right" is also an ordinary adjective. Only a claim about the PICK counts."""
    problems = _validate(WON, _body(
        "The pick was right: BAL 27-20.",
        "It is worth asking whether the model had the right read on the weather.",
    ))
    assert problems == [], f"a won pick described with 'right read' was rejected: {problems}"
