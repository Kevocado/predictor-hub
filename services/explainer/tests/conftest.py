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


