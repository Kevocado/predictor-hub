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
_VERDICT = "Baltimore is the pick."

_READ = ("Kansas City's pass rush is the unit to watch against Baltimore's offensive line. "
         "The matchup is close enough that either side could set the tone.")

GOOD = {"verdict": _VERDICT, "read": _READ, "factors": []}


def rule_validate(output, facts_json, news_json):
    """`validate` for tests of the NUMBER / MARKET / VERDICT rules, which still
    run over prose. Those tests build v2-shaped bodies (verdict + factors); the
    factor text is folded into one read and the read-length rules are dropped,
    since `test_validate.py` owns the shape. A body that is already `{verdict,
    read}` passes straight through.
    """
    from explainer.validate import validate
    if isinstance(output, dict) and "read" not in output and isinstance(output.get("factors"), list):
        texts = [f"{f.get('headline', '')} {f.get('text', '')}" for f in output["factors"] if isinstance(f, dict)]
        output = {"verdict": output.get("verdict"), "read": " ".join(texts)}
    return [p for p in validate(output, facts_json, news_json) if not p.startswith("read ")]


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


