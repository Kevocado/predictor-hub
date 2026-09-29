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
    # The whole key set, deliberately: this is the only endpoint that reports on
    # the service's own state, so an addition here is a decision to make rather
    # than a diff to accept. `failures` earns its place -- a dead default model
    # is otherwise invisible, because every call degrades to a template and the
    # reader still gets a panel.
    assert set(res.json()) == {"used_today", "cap", "enabled", "model", "failures"}


def test_status_reports_failure_kinds_with_zeros_rather_than_omitting_them(tmp_path):
    """So "no failures" and "nobody has looked" cannot be confused.

    An absent key and a zero mean different things to a dashboard, and the
    absent-key version is how a dead model stays invisible.
    """
    with client(tmp_path) as c:
        failures = c.get("/status").json()["failures"]
    assert failures["rate_limited"] == 0 and failures["not_found"] == 0
    for kind in ("unauthorized", "bad_response", "cut_off", "transport", "provider_error"):
        assert kind in failures, f"{kind} is missing from /status: {failures}"
    # Model names are fine to expose; the key never is.
    assert "supersecret" not in str(failures)


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
