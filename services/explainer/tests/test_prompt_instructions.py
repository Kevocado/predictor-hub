"""The v9 prompt: the model is asked for a verdict and a tactical read, and for nothing the service cannot check.

Every assertion reads `prompts.SYSTEM` (the value the model is sent), not the
source file, so a comment beside the code cannot satisfy it.

What this guards, in the order a regression would hurt:

* the model is told the read is built from matchups / player_context / form_rows,
  and that market numbers are background it must not repeat (the validator
  enforces the second half; the prompt must not invite what the validator discards);
* the output shape is `{verdict, read}`: no factors, no band, no `matchup:` keys;
* no sentence is offered to imitate (a comparison of the model's margin with the
  line is a claim nothing here can check);
* the honesty rules survive: no betting advice, rebuilt disclosure, quoted-line
  rule, never invent;
* every served sport is sent the whole frame.
"""
from __future__ import annotations

import pytest

from explainer.config import SERVED_SPORTS
from explainer.prompts import SPORT_NOTES, SYSTEM, messages


def test_the_input_is_the_three_context_lists():
    for key in ("context.matchups", "context.player_context", "context.form_rows"):
        assert key in SYSTEM, key


def test_market_numbers_are_background_and_must_not_be_repeated():
    low = SYSTEM.lower()
    assert "background" in low
    assert "never write the pick's probability, the spread, the total, the moneyline price, or rest days" in low
    assert "discarded" in low  # the consequence, so the model can calibrate


def test_the_output_is_verdict_and_read_only():
    assert '{"verdict": str, "read": str}' in SYSTEM
    assert "two or three sentences" in SYSTEM and "at most 90 words" in SYSTEM
    assert "at most 18 words" in SYSTEM
    for old in ('"factors"', "matchup:", "Edge", "Risk", "Price", '"direction"', "2 to 5 factors"):
        assert old not in SYSTEM.replace("a list of factors", ""), old


def test_duels_are_neutral_unless_the_code_directed_them():
    assert "toward_pick" in SYSTEM
    assert "advantage" in SYSTEM  # named only to be forbidden
    assert "unless toward_pick is true or false" in SYSTEM


def test_it_offers_no_sentence_to_imitate():
    """The earlier frame handed over a quoted example comparing the model's margin with the line."""
    assert "the line asks for more" not in SYSTEM


def test_the_honesty_rules_survive():
    assert "never write \"lock\", \"bet\", \"value play\", \"hammer\"" in SYSTEM
    assert 'pick_timing is "rebuilt"' in SYSTEM
    assert "WITH A QUOTED LINE" in SYSTEM
    assert "Never invent" in SYSTEM and "never compute" in SYSTEM
    assert "Never claim the pick won or lost" in SYSTEM


@pytest.mark.parametrize("sport", sorted(SERVED_SPORTS))
def test_every_served_sport_is_sent_the_whole_frame(sport):
    system = messages(sport, "{}", "[]")[0]["content"]
    assert system.startswith(SYSTEM)
    assert SPORT_NOTES[sport] in system
