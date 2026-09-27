"""f1 and nba are out of scope, and the service must refuse rather than answer.

The refusal has to be a *refusal*: a 404 that looks like a missing fixture. A
template here would render a panel, spend nothing, and read as success — so the
tests below assert the request was never even attempted, not merely that the
status code was right.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import facts
from explainer.app import create_app
from explainer.config import Settings

UNSERVED = ("f1", "nba")
SERVED = ("pl", "nfl", "cfb")


def client(tmp_path, **sport_apis):
    s = Settings(openrouter_api_key="sk-or-v1-supersecret",
                 EXPLAINER_DB_PATH=str(tmp_path / "e.sqlite"),
                 EXPLAINER_ENABLED=False, **sport_apis)
    return TestClient(create_app(s))


def _no_news(mock):
    mock.get(url__startswith="https://site.api.espn.com").mock(
        return_value=httpx.Response(200, json={"articles": []}))


@pytest.mark.parametrize("sport", UNSERVED)
def test_an_unserved_sport_is_a_404_not_a_template(tmp_path, respx_mock, sport):
    _no_news(respx_mock)
    # If the guard sat *after* the facts fetch, this route would be hit and the
    # response would be a 200 with a template body. Asserting the status code
    # alone would pass in exactly that case.
    upstream = respx_mock.get(url__startswith=f"http://{sport}.test/api").mock(
        return_value=httpx.Response(200, json=facts(sport=sport)))

    with client(tmp_path, **{f"sport_api_{sport}": f"http://{sport}.test/api"}) as c:
        res = c.get(f"/explain/{sport}/2026-12-race")

    assert res.status_code == 404, (
        f"{sport} is not served but the request was answered with {res.status_code}; "
        "a refusal must not look like an answer"
    )
    assert not upstream.called, (
        "the refusal happened AFTER the facts fetch, so the budget and the "
        "upstream were touched for a sport we do not serve"
    )


@pytest.mark.parametrize("sport", SERVED)
def test_a_served_sport_with_a_dead_backend_is_a_502_not_a_404(tmp_path, respx_mock, sport):
    """The other half, and the reason the first half is trustworthy.

    Without this, the guard could be "404 whenever the fetch fails" and pass
    every unserved-sport test while being wrong for every served one.
    """
    _no_news(respx_mock)
    respx_mock.get(url__startswith=f"http://{sport}.test/api").mock(
        side_effect=httpx.ConnectError("down"))

    with client(tmp_path, **{f"sport_api_{sport}": f"http://{sport}.test/api"}) as c:
        res = c.get(f"/explain/{sport}/g1")

    assert res.status_code == 502, (
        f"{sport} is served, so an unreachable backend is an upstream failure "
        f"({res.status_code}) and never a 404"
    )


def test_a_refusal_spends_nothing_from_the_daily_cap(tmp_path, respx_mock):
    """A refused request must not consume budget.

    The cap is the thing being protected, so this is the assertion that ties the
    refusal to the reason it exists. It reads the ledger's own counter through
    /status rather than trusting a status code.

    The upstream route is registered even though it should never be reached: if
    the guard were moved after the facts fetch, respx would reject the unmocked
    request and this would fail with "not mocked" — a true result for the wrong
    reason, which is how a test stops saying what it claims to say. With the
    route present, the only thing that can fail this is the spend.
    """
    _no_news(respx_mock)
    respx_mock.get(url__startswith="http://f1.test/api").mock(
        return_value=httpx.Response(200, json=facts(sport="f1")))

    with client(tmp_path, sport_api_f1="http://f1.test/api") as c:
        for _ in range(5):
            assert c.get("/explain/f1/2026-12-race").status_code == 404
        used = c.get("/status").json()["used_today"]
    assert used == 0, f"five refused requests spent {used} of the daily cap"
