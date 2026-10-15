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


def test_abbreviated_titles_match_the_nickname_as_a_whole_word_not_a_substring():
    import asyncio
    from explainer import news

    arts = [
        {"headline": "Seahawks rule out LB Thomas for Thursday night", "published": "2026-10-14T20:00:00Z"},
        {"headline": "Early-season research on the incident at Bowden", "published": "2026-10-14T19:00:00Z"},
        {"headline": "Broncos QB Bo Nix limited in practice", "published": "2026-10-14T18:00:00Z"},
    ]

    async def fake(client, sport):
        return arts

    orig = news._articles
    news._articles = fake
    try:
        got = asyncio.run(news.headlines(None, "nfl", ["SEA", "DEN"]))
    finally:
        news._articles = orig
    assert [g["headline"][:8] for g in got] == ["Seahawks", "Broncos "]   # "season"/"research"/"Bowden" no longer match


def test_full_names_still_match_and_unknown_abbreviations_do_not_explode():
    from explainer import news

    assert news._patterns("nfl", ["Seattle Seahawks"])[0].search("Seattle Seahawks win")
    assert news._patterns("pl", ["Arsenal"])[0].search("Arsenal sign")
    assert news._patterns("nfl", ["XYZ"])
