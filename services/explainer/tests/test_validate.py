import json

from explainer.validate import MAX_FACTOR_WORDS, numbers_in, validate

FACTS = json.dumps({"starts_at": "2026-10-05T00:20:00Z", "pick": {"label": "BAL", "prob": 0.62},
                    "pick_timing": "pre_kickoff",
                    "markets": [{"market": "spread", "line": "BAL -2.5", "model_margin": 3.4}],
                    "record": {"hits": 41, "settled": 66}})

# Converted from the v1 sections. Every assertion below is the one it was; only
# the shape changed, and the texts are shorter because a v2 factor text is capped
# at 35 words where a v1 section was allowed 60. `extra` is appended to the first
# factor's text, which is the v2 equivalent of appending to a section.
VERDICT = "Baltimore is the pick at 62%, though the line asks more than the model does."
SPREAD = "It rates Baltimore 3.4 points better, a little more than the -2.5 line the market offers."
RECORD = "Its picks made before kickoff are 41/66, so read this as a lean rather than a certainty."
CONTEXT = "Kansas City can win this one, and the ratings behind it have held all week."


def good(extra=""):
    body = {"verdict": VERDICT, "factors": [
        {"key": "spread", "direction": "up", "headline": "The model likes Baltimore", "text": SPREAD},
        {"key": "record", "direction": "up", "headline": "Its record so far", "text": RECORD},
        {"key": "context", "direction": "down", "headline": "And the other way", "text": CONTEXT},
    ]}
    if extra:
        body["factors"][0]["text"] += " " + extra
    return body


def test_fixture_is_within_the_v2_caps():
    """v1 asserted a 120-220 word band. v2 has caps and **no floor**.

    Kept as a test because the absence of a floor is a decision: a minimum
    carried over from v1 would reject the honest short answer and push the model
    into padding, which is the opposite of what the redesign is for.
    """
    for f in good()["factors"]:
        assert len(f["text"].split()) <= MAX_FACTOR_WORDS
    assert len(good()["verdict"].split()) <= 18
    assert len(" ".join(f["text"] for f in good()["factors"]).split()) < 120, (
        "if this fixture has grown past 120 words it no longer proves that a short "
        "body is acceptable"
    )


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
    body = good()
    one = {"verdict": body["verdict"], "factors": body["factors"][:1]}
    assert any("factors" in p for p in validate(one, FACTS, "[]"))

    long_verdict = good() | {"verdict": "word " * 19}
    assert any("verdict" in p for p in validate(long_verdict, FACTS, "[]"))

    long_text = good()
    long_text["factors"][0]["text"] = "word " * (MAX_FACTOR_WORDS + 1)
    assert any("text" in p for p in validate(long_text, FACTS, "[]"))

    long_headline = good()
    long_headline["factors"][0]["headline"] = "word " * 11
    assert any("headline" in p for p in validate(long_headline, FACTS, "[]"))

    assert validate({"nope": 1}, FACTS, "[]")


def test_numbers_in_reads_percents_both_ways():
    assert {0.62, 62.0, -2.5, 6.0, 10.0} <= numbers_in("62% vs −2.5, 6/10")


def test_tolerance_is_rounding_of_the_written_figure_not_five_points():
    facts = json.loads(FACTS)
    facts["pick"]["prob"] = 0.64
    assert any("62%" in p for p in validate(good(), json.dumps(facts), "[]"))  # 62% vs 64%: a misstatement
    facts["pick"]["prob"] = 0.6234
    assert validate(good(), json.dumps(facts), "[]") == []  # 62% is 0.6234 rounded


def test_whole_number_may_round_a_decimal():
    facts = json.loads(FACTS)
    facts["markets"].append({"market": "total", "model_total": 47.8, "line": 45.5})
    assert validate(good("It projects 48 points against 45.5."), json.dumps(facts), "[]") == []
    assert validate(good("It projects 49 points."), json.dumps(facts), "[]")
