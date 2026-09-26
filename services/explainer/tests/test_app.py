import httpx
import respx
from fastapi.testclient import TestClient

from conftest import facts
from explainer.app import create_app
from explainer.config import Settings


def client(tmp_path, key="sk-or-v1-supersecret"):
    s = Settings(openrouter_api_key=key, sport_api_nfl="http://nfl.test/api",
                 EXPLAINER_DB_PATH=str(tmp_path / "e.sqlite"), EXPLAINER_ENABLED=False)
    return TestClient(create_app(s))


def test_status_never_shows_the_key(tmp_path):
    with client(tmp_path) as c:
        res = c.get("/status")
    assert res.status_code == 200
    body = res.text
    assert "supersecret" not in body and "sk-or" not in body
    assert set(res.json()) == {"used_today", "cap", "enabled", "model"}


@respx.mock(assert_all_called=False)
def test_explain_maps_upstream_errors(tmp_path, respx_mock):
    respx_mock.get(url__startswith="https://site.api.espn.com").mock(return_value=httpx.Response(200, json={"articles": []}))
    respx_mock.get("http://nfl.test/api/facts/g1").mock(return_value=httpx.Response(200, json=facts()))
    respx_mock.get("http://nfl.test/api/facts/missing").mock(return_value=httpx.Response(404))
    respx_mock.get("http://nfl.test/api/facts/down").mock(side_effect=httpx.ConnectError("down"))
    with client(tmp_path) as c:
        ok = c.get("/explain/nfl/g1")
        assert ok.status_code == 200 and ok.json()["source"] == "template"
        assert c.get("/explain/nfl/missing").status_code == 404
        assert c.get("/explain/nfl/down").status_code == 502
        assert c.get("/explain/mlb/x").status_code == 404
