"""Shared fixtures for the explain flow: a facts bundle and a model answer
that passes validation using only numbers from it."""
import copy

FACTS = {"sport": "nfl", "id": "g1", "title": "Chiefs at Ravens", "starts_at": "2026-10-05T00:20:00Z",
         "status": "upcoming", "pick_timing": "pre_kickoff", "pick": {"label": "BAL", "prob": 0.62},
         "markets": [{"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"}],
         "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 66}}

_PICK = ("The model makes Baltimore a 62% favorite at home. Its ratings put the Ravens ahead on both sides of the ball, "
         "and the gap has held steady through the week. Kansas City is good enough to win this, so read the number as "
         "a lean toward Baltimore rather than a call that simply cannot miss this weekend.")
_SPREAD = ("It rates Baltimore 3.4 points better than Kansas City, a little more than the -2.5 line the market is "
           "offering. That is a small disagreement: the model and the market mostly agree on who is better here.")
GOOD = {"headline": "Baltimore favored at 62%", "sections": [
    {"market": "result", "title": "Pick", "text": _PICK, "numbers_used": ["62%"]},
    {"market": "spread", "title": "Spread", "text": _SPREAD, "numbers_used": ["3.4", "-2.5"]},
    {"market": "trust", "title": "Trust", "text": "62% still loses about four times in ten games like this one, "
     "so treat it as a lean. Its picks made before kickoff are 41/66 this season."}]}


def facts(**over):
    return {**copy.deepcopy(FACTS), **over}


def good(**over):
    return {**copy.deepcopy(GOOD), **over}
