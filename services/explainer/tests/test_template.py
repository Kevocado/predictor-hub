import json

from explainer.template import explain_from_template
from explainer.validate import validate

FACTS = {"title": "Chiefs at Ravens", "pick": {"label": "BAL", "prob": 0.62}, "pick_timing": "pre_kickoff",
         "markets": [{"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
                     {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"},
                     {"market": "total", "model_total": 47.8, "line": 45.5}],
         "players": [{"name": "Lamar Jackson", "team": "BAL", "projection": "248 pass yds, 52 rush yds"},
                     {"name": "Derrick Henry", "team": "BAL", "projection": "92 rush yds"},
                     {"name": "Third Guy", "team": "KC", "projection": "10 rec yds"}],
         "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 66}}


def _text(out) -> str:
    return " ".join([out["verdict"]] + [f["headline"] + " " + f["text"] for f in out["factors"]])


def test_template_is_plain_and_honest_for_rebuilt():
    out = explain_from_template({"title": "Chiefs at Ravens", "pick": {"label": "BAL", "prob": 0.62},
                                 "pick_timing": "rebuilt", "markets": [], "players": [], "record": None})
    text = _text(out).lower()
    assert "rebuilt after kickoff" in text, f"a rebuilt pick is not disclosed: {text}"
    assert "62%" in text, f"the probability vanished: {text}"
    # A rebuilt pick is shown, never judged.
    assert "right" not in text and "wrong" not in text, f"a rebuilt pick was graded: {text}"


def test_template_covers_markets_and_the_record():
    out = explain_from_template(FACTS)
    text = _text(out)
    assert "BAL the pick at 62%" in text
    assert "3.4 points better" in text and "BAL -2.5" in text
    assert "47.8" in text and "45.5" in text
    assert "41 of 66" in text
    assert [f["key"] for f in out["factors"]] == ["moneyline", "spread", "total", "record"], (
        f"four slots, and the order decides who survives: {[f['key'] for f in out['factors']]}"
    )


def test_template_does_not_spend_a_factor_slot_on_the_player_list():
    """Players are a panel extra (spec §6), not a factor.

    The panel renders them from the facts directly. A factor slot spent on them
    would displace a market, and with four slots and three markets available that
    is a real cost for a list the reader already has.
    """
    out = explain_from_template(FACTS)
    text = _text(out)
    assert "Lamar Jackson" not in text, "the player list is being re-sent as prose"
    assert all(f["key"] != "context" for f in out["factors"]), (
        "a context factor was spent on padding when three markets were available"
    )


def test_template_numbers_always_pass_the_validator_number_check():
    """The template is held to the same number rule as the model.

    It is not validated in production, so nothing else would catch a figure it
    invented — and a template that fails its own validator is a template that
    quietly teaches the model the wrong thing.
    """
    out = explain_from_template(FACTS)
    problems = validate(out, json.dumps(FACTS), "[]")
    assert not [p for p in problems if "number" in p], f"the template invented a figure: {problems}"


def test_template_never_states_a_derived_percentage():
    """`record` is hits/settled and the facts contain no percentage (spec §5a-bis)."""
    text = _text(explain_from_template(FACTS))
    assert "60.3" not in text and "62%" in text  # 62% is the pick's own prob, in the facts


def test_template_without_a_pick_says_so():
    out = explain_from_template({"title": "Arsenal v Spurs", "pick": None, "pick_timing": "none", "markets": []})
    assert "no pick" in _text(out).lower()
    assert out["band"] == "leaning", "no pick must not read as a confidence"
