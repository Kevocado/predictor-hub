"""GET /explain/{sport}/{id}/context: facts.context's tactical lists, and nothing that costs anything."""
import httpx
import respx
from fastapi.testclient import TestClient

from conftest import facts
from explainer.app import create_app
from explainer.config import Settings

URL = "http://nfl.test/api/facts/g1"
CTX = {"matchups": [{"id": "a"}], "player_context": [{"name": "N"}], "home_rest_days": 7}


def client(tmp_path):
    s = Settings(openrouter_api_key="k", sport_api_nfl="http://nfl.test/api",
                 EXPLAINER_DB_PATH=str(tmp_path / "e.sqlite"), EXPLAINER_ENABLED=True)
    return TestClient(create_app(s))


def test_returns_only_the_three_lists_and_touches_no_model_news_or_ledger(tmp_path):
    with respx.mock(assert_all_called=False) as m:
        m.get(URL).mock(return_value=httpx.Response(200, json=facts(context=CTX)))
        llm = m.post(url__startswith="https://openrouter.ai").mock(return_value=httpx.Response(500))
        espn = m.get(url__startswith="https://site.api.espn.com").mock(return_value=httpx.Response(500))
        with client(tmp_path) as c:
            res = c.get("/explain/nfl/g1/context")
            assert res.status_code == 200
            assert res.json() == {"matchups": [{"id": "a"}], "player_context": [{"name": "N"}]}
            assert c.get("/status").json()["used_today"] == 0
        assert not llm.called and not espn.called


def test_no_context_is_an_empty_object(tmp_path):
    with respx.mock() as m:
        m.get(URL).mock(return_value=httpx.Response(200, json=facts()))
        with client(tmp_path) as c:
            assert c.get("/explain/nfl/g1/context").json() == {}


def test_is_cached_briefly(tmp_path):
    with respx.mock() as m:
        route = m.get(URL).mock(return_value=httpx.Response(200, json=facts(context=CTX)))
        with client(tmp_path) as c:
            c.get("/explain/nfl/g1/context"); c.get("/explain/nfl/g1/context")
        assert route.call_count == 1


def test_unknown_sport_and_id_are_404(tmp_path):
    with respx.mock() as m:
        m.get("http://nfl.test/api/facts/nope").mock(return_value=httpx.Response(404))
        with client(tmp_path) as c:
            assert c.get("/explain/zzz/g1/context").status_code == 404
            assert c.get("/explain/nfl/nope/context").status_code == 404


def test_upstream_failure_is_a_sanitised_502(tmp_path):
    with respx.mock() as m:
        m.get(URL).mock(return_value=httpx.Response(500, text="SECRET traceback host=10.0.0.5"))
        with client(tmp_path) as c:
            res = c.get("/explain/nfl/g1/context")
        assert res.status_code == 502
        assert "SECRET" not in res.text and "10.0.0.5" not in res.text


def test_the_explain_route_still_works_beside_it(tmp_path):
    with respx.mock(assert_all_called=False) as m:
        m.get(URL).mock(return_value=httpx.Response(200, json=facts()))
        m.get(url__startswith="https://site.api.espn.com").mock(return_value=httpx.Response(200, json={"articles": []}))
        with client(tmp_path) as c:
            assert c.get("/explain/nfl/g1").json()["source"] == "template"
