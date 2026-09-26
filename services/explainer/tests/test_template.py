from explainer.template import explain_from_template
from explainer.validate import validate
import json

FACTS = {"title": "Chiefs at Ravens", "pick": {"label": "BAL", "prob": 0.62}, "pick_timing": "pre_kickoff",
         "markets": [{"market": "moneyline", "model": {"BAL": 0.62, "KC": 0.38}},
                     {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"},
                     {"market": "total", "model_total": 47.8, "line": 45.5}],
         "players": [{"name": "Lamar Jackson", "team": "BAL", "projection": "248 pass yds, 52 rush yds"},
                     {"name": "Derrick Henry", "team": "BAL", "projection": "92 rush yds"},
                     {"name": "Third Guy", "team": "KC", "projection": "10 rec yds"}],
         "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 66}}


def test_template_is_plain_and_honest_for_rebuilt():
    out = explain_from_template({"title": "Chiefs at Ravens", "pick": {"label": "BAL", "prob": 0.62},
                                 "pick_timing": "rebuilt", "markets": [], "players": [], "record": None})
    text = " ".join(s["text"] for s in out["sections"])
    assert "rebuilt after kickoff" in text.lower() and "62%" in out["headline"]


def test_template_covers_markets_players_and_record():
    out = explain_from_template(FACTS)
    text = " ".join(s["text"] for s in out["sections"])
    assert "BAL the pick at 62%" in text
    assert "3.4 points better; the line is BAL -2.5" in text
    assert "47.8 against a line of 45.5" in text
    assert "Lamar Jackson" in text and "Derrick Henry" in text and "Third Guy" not in text
    assert "41/66" in text
    assert out["headline"] == "Chiefs at Ravens: BAL at 62%"


def test_template_numbers_always_pass_the_validator_number_check():
    out = explain_from_template(FACTS)
    problems = validate(out, json.dumps(FACTS), "[]")
    assert not [p for p in problems if "number" in p]


def test_template_without_a_pick_says_so():
    out = explain_from_template({"title": "Arsenal v Spurs", "pick": None, "pick_timing": "none", "markets": []})
    assert "no pick" in " ".join(s["text"] for s in out["sections"]).lower()
