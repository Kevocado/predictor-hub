import json

from explainer.validate import numbers_in, validate

FACTS = json.dumps({"starts_at": "2026-10-05T00:20:00Z", "pick": {"label": "BAL", "prob": 0.62},
                    "pick_timing": "pre_kickoff",
                    "markets": [{"market": "spread", "line": "BAL -2.5", "model_margin": 3.4}],
                    "record": {"hits": 41, "settled": 66}})

PICK = ("The model makes Baltimore a 62% favorite at home. Its ratings put the Ravens ahead on both sides of the ball, "
        "and the gap has held steady through the week. Kansas City is good enough to win this, "
        "so read the number as a lean toward Baltimore rather than a call that simply cannot miss this weekend.")
SPREAD = ("It rates Baltimore 3.4 points better than Kansas City, a little more than the -2.5 line the market is "
          "offering. That is a small disagreement: the model and the market mostly agree on who is better here.")


def good(extra=""):
    return {"headline": "Baltimore favored at 62%", "sections": [
        {"market": "result", "title": "Pick", "text": PICK},
        {"market": "spread", "title": "Spread", "text": SPREAD + (" " + extra if extra else "")},
        {"market": "trust", "title": "Trust", "text": "62% still loses about four times in ten games like this one, "
         "so treat it as a lean. Its picks made before kickoff are 41/66 this season."}]}


def test_fixture_is_in_the_length_band():
    words = sum(len(s["text"].split()) for s in good()["sections"])
    assert 120 <= words <= 220


def test_accepts_numbers_from_facts():
    assert validate(good(), FACTS, "[]") == []


def test_rejects_invented_number():
    assert any("70" in p for p in validate(good("A 70% chance."), FACTS, "[]"))


def test_true_minus_and_rounding_are_tolerated():
    out = good("Or −2.50 if you like decimals.")
    assert validate(out, FACTS, "[]") == []


def test_numbers_from_news_are_allowed():
    news = json.dumps([{"headline": "Ravens sign 7 practice-squad players", "date": "2026-10-02"}])
    assert validate(good("The team added 7 players."), FACTS, news) == []


def test_kickoff_time_digits_are_not_a_free_pass():
    assert any("20" in p for p in validate(good("A 20% chance of rain."), FACTS, "[]"))


def test_rejects_banned_word():
    assert validate(good("Lock it in."), FACTS, "[]")
    assert validate(good("Not betting advice."), FACTS, "[]")
    assert validate(good("A better team."), FACTS, "[]") == []


def test_rebuilt_must_say_so():
    rebuilt = FACTS.replace("pre_kickoff", "rebuilt")
    assert any("rebuilt" in p for p in validate(good(), rebuilt, "[]"))
    ok = good("This pick was rebuilt after kickoff and is not counted.")
    assert validate(ok, rebuilt, "[]") == []


def test_shape_and_length_rules():
    assert any("sections" in p for p in validate({"headline": "x", "sections": good()["sections"][:2]}, FACTS, "[]"))
    long_head = good(); long_head["headline"] = "word " * 19
    assert any("headline" in p for p in validate(long_head, FACTS, "[]"))
    assert any("words" in p for p in validate({"headline": "h", "sections": [{"text": "short"}] * 3}, FACTS, "[]"))
    assert validate({"nope": 1}, FACTS, "[]")


def test_numbers_in_reads_percents_both_ways():
    assert {0.62, 62.0, -2.5, 6.0, 10.0} <= numbers_in("62% vs −2.5, 6/10")
