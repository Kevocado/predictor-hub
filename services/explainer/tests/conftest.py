"""Shared fixtures for the explain flow: a facts bundle and a model answer
that passes validation using only numbers from it."""
import copy
import json

import httpx
import pytest
import respx

from explainer import news
from explainer.cache import Cache
from explainer.config import Settings
from explainer.ledger import Ledger
from explainer.service import Explainer

FACTS = {"sport": "nfl", "id": "g1", "title": "Chiefs at Ravens", "starts_at": "2026-10-05T00:20:00Z",
         "status": "upcoming", "pick_timing": "pre_kickoff", "pick": {"label": "BAL", "prob": 0.62},
         "markets": [{"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"}],
         "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 66}}

# A v2 answer: a verdict and three factors, each naming a market the facts
# carry, and every figure in the prose taken from FACTS. `validate()` checks all
# of that, so this fixture is also the suite's proof that a well-formed v2 body
# passes — if it drifts out of shape, everything that uses it fails for a reason
# that has nothing to do with the test asking.
#
# The numbers are 62%, 3.4 and -2.5 from `pick.prob`, `markets[0].model_margin`
# and `markets[0].line`, and 41/66 from the record. Nothing here is invented,
# which is the property `test_validate.py` leans on.
_VERDICT = "Baltimore is the pick at 62%, though the line asks more than the model does."

_SPREAD = ("It rates Baltimore 3.4 points better than Kansas City, a little more than the -2.5 line "
           "the market is offering. That is a small disagreement.")
_RECORD = ("Its picks made before kickoff are 41/66 this season, so read the number as a lean rather "
           "than a call that cannot miss.")
_CONTEXT = ("Kansas City is good enough to win this one, so the gap is a judgement rather than a "
            "certainty.")

GOOD = {"verdict": _VERDICT, "factors": [
    {"key": "spread", "direction": "up", "headline": "The model likes Baltimore", "text": _SPREAD},
    {"key": "record", "direction": "up", "headline": "Its record so far", "text": _RECORD},
    {"key": "context", "direction": "down", "headline": "And the other way", "text": _CONTEXT},
]}


def facts(**over):
    return {**copy.deepcopy(FACTS), **over}


def good(**over):
    return {**copy.deepcopy(GOOD), **over}


def reply(body, status=200):
    content = body if isinstance(body, str) else json.dumps(body)
    return httpx.Response(status, json={"choices": [{"message": {"content": content}}]})


@pytest.fixture
def no_news():
    news._CACHE.clear()
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__startswith="https://site.api.espn.com").mock(return_value=httpx.Response(200, json={"articles": []}))
        yield mock


def make(tmp_path, key="k", cap=10, enabled=True):
    s = Settings(openrouter_api_key=key, sport_api_nfl="http://nfl.test/api", EXPLAINER_DAILY_CAP=cap,
                 EXPLAINER_ENABLED=enabled, EXPLAINER_MODEL="m1", EXPLAINER_FALLBACK_MODEL="m2")
    db = str(tmp_path / "e.sqlite")
    return Explainer(s, Cache(db), Ledger(db, cap=cap), httpx.AsyncClient())


