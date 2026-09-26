from types import SimpleNamespace

import httpx
import respx

from explainer.scheduler import RESERVE, pregenerate
from explainer.service import NotFound


class FakeLedger:
    def __init__(self, used, cap):
        self.used, self.cap = used, cap

    def used_today(self):
        return self.used


class FakeExplainer:
    def __init__(self, used=0, cap=900, fail=()):
        self.settings = SimpleNamespace(sport_api={"nfl": "http://nfl.test/api", "nba": "http://nba.test/api"},
                                        daily_cap=cap)
        self.ledger = FakeLedger(used, cap)
        self.calls, self.fail = [], set(fail)

    async def explain(self, sport, id):
        self.calls.append((sport, id))
        if id in self.fail:
            raise NotFound(id)
        self.ledger.used += 1
        return {}


@respx.mock
async def test_explains_every_upcoming_id_for_each_sport():
    nfl = respx.get("http://nfl.test/api/facts/upcoming").mock(return_value=httpx.Response(200, json={"ids": ["a", "b"]}))
    respx.get("http://nba.test/api/facts/upcoming").mock(return_value=httpx.Response(200, json={"ids": ["c"]}))
    ex = FakeExplainer()
    async with httpx.AsyncClient() as c:
        n = await pregenerate(ex, c, ["nfl", "nba"])
    assert ex.calls == [("nfl", "a"), ("nfl", "b"), ("nba", "c")] and n == 3
    assert nfl.calls[0].request.url.params["hours"] == "72"


@respx.mock
async def test_stops_at_the_on_demand_reserve():
    respx.get("http://nfl.test/api/facts/upcoming").mock(return_value=httpx.Response(200, json={"ids": list("abcdef")}))
    ex = FakeExplainer(used=900 - RESERVE - 2, cap=900)
    async with httpx.AsyncClient() as c:
        n = await pregenerate(ex, c, ["nfl"])
    assert n == 2 and ex.ledger.used == 900 - RESERVE


@respx.mock
async def test_a_failing_sport_or_id_is_skipped():
    respx.get("http://nfl.test/api/facts/upcoming").mock(side_effect=httpx.ConnectError("down"))
    respx.get("http://nba.test/api/facts/upcoming").mock(return_value=httpx.Response(200, json={"ids": ["x", "c"]}))
    ex = FakeExplainer(fail={"x"})
    async with httpx.AsyncClient() as c:
        n = await pregenerate(ex, c, ["nfl", "nba", "pl"])  # pl: not configured
    assert ex.calls == [("nba", "x"), ("nba", "c")] and n == 1
