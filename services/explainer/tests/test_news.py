import httpx
import pytest
import respx

from explainer import news

URL = news.ESPN_NEWS["nfl"]
BODY = {"articles": [
    {"headline": "Ravens' Lamar Jackson limited in practice", "description": "Knee", "published": "2026-10-02T15:00:00Z"},
    {"headline": "Bills sign kicker", "description": "Depth move", "published": "2026-10-03T15:00:00Z"},
    {"headline": "Injury report", "description": "Chiefs WR out for Sunday", "published": "2026-10-04T15:00:00Z"},
]}


@pytest.fixture(autouse=True)
def fresh_cache():
    news._CACHE.clear()


@respx.mock
async def test_returns_matching_headlines_newest_first_and_drops_others():
    respx.get(URL).mock(return_value=httpx.Response(200, json=BODY))
    async with httpx.AsyncClient() as c:
        out = await news.headlines(c, "nfl", ["Ravens", "chiefs"])
    assert [o["published"] for o in out] == ["2026-10-04T15:00:00Z", "2026-10-02T15:00:00Z"]
    assert out[1] == {"headline": "Ravens' Lamar Jackson limited in practice", "published": "2026-10-02T15:00:00Z",
                      "source": "ESPN"}
    assert all("Bills" not in o["headline"] for o in out)


@respx.mock
async def test_limit_is_respected():
    respx.get(URL).mock(return_value=httpx.Response(200, json=BODY))
    async with httpx.AsyncClient() as c:
        assert len(await news.headlines(c, "nfl", ["Ravens", "Chiefs", "Bills"], limit=2)) == 2


@respx.mock
@pytest.mark.parametrize("effect", [httpx.Response(500), httpx.ReadTimeout("slow"), httpx.Response(200, text="not json")])
async def test_errors_return_empty_and_never_raise(effect):
    route = respx.get(URL)
    route.side_effect = effect if isinstance(effect, Exception) else None
    if not isinstance(effect, Exception):
        route.mock(return_value=effect)
    async with httpx.AsyncClient() as c:
        assert await news.headlines(c, "nfl", ["Ravens"]) == []


@respx.mock
async def test_second_call_within_30_minutes_does_not_refetch():
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=BODY))
    async with httpx.AsyncClient() as c:
        await news.headlines(c, "nfl", ["Ravens"])
        await news.headlines(c, "nfl", ["Chiefs"])
    assert route.call_count == 1


async def test_unknown_sport_or_no_teams_is_empty():
    async with httpx.AsyncClient() as c:
        assert await news.headlines(c, "mlb", ["Cubs"]) == []
        assert await news.headlines(c, "nfl", []) == []
