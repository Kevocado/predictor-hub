"""AIS-3: a sentence that restates the fixture header is dropped, the rest kept.

The panel already draws the pick, its probability, the price and the score. A
read that writes one of them back is the complaint this feature exists to fix,
and rejecting the whole body for one bad sentence throws away the matchup
paragraph beside it. So the service drops the sentence and serves the rest.

The old rules are unchanged: a read that still contains a restatement when it
reaches `validate()` is refused, exactly as before.
"""
import json

from conftest import facts, good, make, reply
from explainer.validate import drop_restatements, restating_sentences, validate

import httpx

FACTS_URL = "http://nfl.test/api/facts/g1"

FACTS = {
    "sport": "nfl", "id": "g1", "title": "Bills at Jets",
    "starts_at": "2026-10-11T17:00:00Z", "status": "upcoming",
    "pick_timing": "pre_kickoff", "pick": {"label": "Bills", "prob": 0.64},
    "markets": [{"market": "moneyline", "model": {"Bills": 0.64, "Jets": 0.36}},
                {"market": "spread", "model_margin": 6.5, "line": "BUF -3.5"}],
    "context": {
        "home_rest_days": 10, "away_rest_days": 7,
        "matchups": [{"id": "pass_off_vs_pass_def:home", "attacker": "Bills", "defender": "Jets",
                      "stat": "passing offence", "foil": "pass defence", "attacker_rank": 3,
                      "defender_rank": 28, "n_teams": 32, "toward_pick": None}],
        "player_context": [{"team": "BUF", "name": "Josh Allen", "role": "top_passer",
                            "stat": "passing yards", "value": 265}],
    },
}
F = json.dumps(FACTS)

MATCHUP = ("Buffalo's passing offence ranks #3 of 32 and meets a Jets pass defence "
           "ranked #28. Josh Allen is the passer to watch in that matchup.")


def test_a_probability_sentence_is_dropped_and_the_matchup_kept():
    read = "The Bills win 64% of the time. " + MATCHUP
    assert restating_sentences(FACTS, read) == ["The Bills win 64% of the time."]
    assert drop_restatements(FACTS, read) == MATCHUP


def test_a_sentence_that_names_the_pick_as_the_pick_is_dropped():
    read = "Bills are the pick. " + MATCHUP
    assert restating_sentences(FACTS, read) == ["Bills are the pick."]
    assert drop_restatements(FACTS, read) == MATCHUP


def test_the_pick_label_with_a_verdict_word_is_dropped():
    read = "The Bills have the edge. " + MATCHUP
    assert restating_sentences(FACTS, read) == ["The Bills have the edge."]


def test_a_label_and_edge_with_a_tactical_number_is_the_matchup_story():
    read = "The edge comes from Buffalo's #3 passing offence against the Jets' #28 pass defence. " \
           "Josh Allen is the passer to watch in that matchup."
    assert restating_sentences(FACTS, read) == []
    assert drop_restatements(FACTS, read) == read


def test_the_score_is_dropped_when_the_facts_record_one():
    final = {**FACTS, "status": "final", "pick_timing": "rebuilt",
             "result": {"score": "27-20", "pick_won": True}}
    read = ("Baltimore won 27-20. " + MATCHUP +
            " This pick was rebuilt after kickoff.")
    assert restating_sentences(final, read) == ["Baltimore won 27-20."]
    assert "27-20" not in drop_restatements(final, read)


def test_a_clean_read_is_returned_unchanged():
    assert drop_restatements(FACTS, MATCHUP) == MATCHUP


def test_a_read_that_is_all_restatement_drops_to_nothing():
    assert drop_restatements(FACTS, "Bills are the pick. The pick is Bills.") == ""


def test_the_filtered_read_passes_the_old_validators():
    read = "Bills are the pick at 64%. " + MATCHUP
    clean = drop_restatements(FACTS, read)
    assert validate({"verdict": "Bills are the pick.", "read": clean}, F, "[]") == []


def test_validate_still_refuses_a_restating_read():
    problems = validate({"verdict": "Bills are the pick.",
                         "read": "Bills are the pick at 64%. " + MATCHUP}, F, "[]")
    assert any("restates" in p for p in problems), problems


async def test_the_service_serves_the_matchup_sentence_and_drops_the_restatement(tmp_path, no_news):
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    read = ("Baltimore is the pick. Kansas City's pass rush is the unit to watch "
            "against Baltimore's offensive line. The matchup is close enough that "
            "either side could set the tone.")
    no_news.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=reply(good(read=read)))

    out = await make(tmp_path).explain("nfl", "g1")

    assert out["source"] == "llm", out
    assert "is the pick" not in out["read"], out["read"]
    assert out["read"].startswith("Kansas City's pass rush"), out["read"]
    assert out["verdict"] == "Baltimore is the pick."
