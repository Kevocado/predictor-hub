"""F1 is out of scope, and the service must refuse rather than answer.

The refusal has to be a *refusal*: a 404 that looks like a missing fixture. A
template here would render a panel, spend nothing, and read as success — so the
tests below assert the request was never even attempted, not merely that the
status code was right.

**And NBA is in this file's history, because it was here by mistake.** This module
once read `UNSERVED = ("f1", "nba")`, on the stated reasoning that "the v2 panel
is specified for the three sports whose facts carry the markets it draws". That
reasoning was checked for F1 and assumed for NBA, and NBA's `/facts` carries
`moneyline`, `spread` and `total` — the same three keys, in the same shape, as
NFL and CFB:

    {"market": "moneyline", "model": {home: p, away: 1 - p}}
    {"market": "spread",    "model_margin": m, "line": <team> <n>}
    {"market": "total",     "model_total": t}

Every component the v2 panel draws is fed by that. NBA was refused on a reason
that was true of F1 and false of NBA, and it now serves.

F1 stays out, and the reason is a product decision rather than a data gap: a
win probability *is* the explanation. A model that says "Norris 71%" has said the
whole thing, and prose over a field of twenty drivers is the model restating its
own input in longer words — the failure this product exists to avoid. There is no
line for F1 either, so a model-vs-market tile has nothing honest to show.
"""
import asyncio
import os
import subprocess

import httpx
import pytest

from conftest import facts
from explainer.cache import Cache
from explainer.config import Settings
from explainer.ledger import Ledger
from explainer.service import Explainer, NotFound

UNSERVED = ("f1",)
SERVED = ("pl", "nfl", "cfb", "nba")

#: The markets an NBA facts bundle must carry for the v2 panel to have something
#: to draw. If NBA's `/facts` ever loses one of these, this is where the question
#: gets asked again — and it should be asked, because the panel's tiles, split bar
#: and market row all read from `markets`.
NBA_REQUIRED_MARKETS = {"moneyline", "spread", "total"}


def build(tmp_path, **sport_apis):
    """An Explainer wired the way the app's lifespan wires it.

    `TestClient(app)` does NOT run the lifespan, so `app.state.explainer` is never
    built and every route raises `AttributeError: 'State' object has no attribute
    'explainer'`. The pre-existing test in this file got away with that because it
    only asserted a 404, which the refusal produces *before* anything reaches
    app.state -- so it was never testing a served sport at all.

    So this builds the service directly, as tests/test_service.py does, and calls
    `explain()` on it. That is the layer where the refusal actually lives, and it
    is the layer `tests/test_service.py` already uses.
    """
    s = Settings(openrouter_api_key="sk-or-v1-supersecret",
                 EXPLAINER_DB_PATH=str(tmp_path / "e.sqlite"),
                 EXPLAINER_ENABLED=False, **sport_apis)
    return Explainer(s, Cache(s.db_path), Ledger(s.db_path, cap=10),
                     httpx.AsyncClient())


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

    with pytest.raises(NotFound):
        asyncio.run(build(tmp_path, **{f"sport_api_{sport}": f"http://{sport}.test/api"}).explain(sport, "g1"))

    assert not upstream.called, "a refused sport must not touch its upstream"


def test_a_refusal_spends_nothing(tmp_path, respx_mock):
    """The refusal is the first line of the route, before the facts fetch and
    before `try_spend()`. A refused request that cost budget would drain the cap
    for a sport the service will never answer for."""
    _no_news(respx_mock)
    svc = build(tmp_path, sport_api_f1="http://f1.test/api")
    with pytest.raises(NotFound):
        asyncio.run(svc.explain("f1", "g1"))
    assert svc.ledger.used_today() == 0


def test_a_refusal_does_not_look_like_a_missing_fixture(tmp_path, respx_mock):
    """404 is right and 200-with-a-template is wrong, but the *message* matters
    too: a reader (or a caller retrying) must be able to tell "this sport has no
    panel" from "that game does not exist"."""
    _no_news(respx_mock)
    with pytest.raises(NotFound) as excinfo:
        asyncio.run(build(tmp_path, sport_api_f1="http://f1.test/api").explain("f1", "g1"))

    message = str(excinfo.value)
    assert "f1" in message, message
    # And it must not read as "no such game", which is the OTHER refusal on this
    # route: a reader (or a caller retrying) has to be able to tell "this sport has
    # no panel" from "that game does not exist".
    assert "no such game" not in message.lower(), message


# --- NBA now serves ------------------------------------------------------

def test_nba_is_served(tmp_path, respx_mock):
    """The regression this change exists to close: NBA was refused alongside F1 on
    an assumption that was never checked against NBA's own facts."""
    _no_news(respx_mock)
    respx_mock.get(url__startswith="http://nba.test/api/facts/g1").mock(
        return_value=httpx.Response(200, json=facts(sport="nba")))

    answer = asyncio.run(build(tmp_path, sport_api_nba="http://nba.test/api").explain("nba", "g1"))

    assert answer.get("verdict"), answer


def test_nba_is_in_the_served_list_and_f1_is_not():
    """The list itself, so a future edit that re-adds F1 or drops NBA fails here
    rather than in production."""
    from explainer.config import SERVED_SPORTS

    assert "nba" in SERVED_SPORTS
    assert "f1" not in SERVED_SPORTS
    assert len(SERVED_SPORTS) == 4


def test_nbas_facts_carry_the_markets_the_panel_draws():
    """The reason NBA can serve, asserted rather than assumed.

    This is the check that was missing when NBA was refused. F1's `win` market is a
    probability map with no line, no spread and no total; NBA has the same three
    markets as the two football sports. If NBA's facts builder ever drops one, the
    panel's tiles and split bar lose a figure, and that should be a failing test
    rather than a blank space on a game page.
    """
    import os
    import re
    from pathlib import Path

    # Read the file from git rather than from a checkout on disk: the sibling
    # repo is not always present, and a test that silently skips is a test that
    # silently stops guarding. `origin/main`'s copy is what ships, and `git show`
    # needs only this repo's remote.
    # The sibling repo, found by walking up from this file rather than by a fixed
    # relative path: this suite runs from a worktree, a plain checkout, and CI,
    # and `parents[N]/NBA_Predictor` is wrong in two of those.
    here = Path(__file__).resolve()
    candidates = [Path(os.environ["NBA_REPO"])] if os.environ.get("NBA_REPO") else []
    candidates += [p / "NBA_Predictor" for p in here.parents]
    root = next((c for c in candidates if (c / ".git").exists()), None)
    assert root is not None, (
        "NBA_Predictor not found beside this repo; set NBA_REPO to its path. "
        f"Looked in {[str(c) for c in candidates[:4]]}"
    )
    try:
        src = subprocess.run(
            ["git", "-C", str(root), "show",
             "origin/main:src/nba_predictor/api/facts.py"],
            capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        pytest.fail(
            "could not read NBA's facts.py from its own repository, so the claim "
            "that NBA carries the panel's markets is UNVERIFIED rather than "
            f"true: {exc}. Set NBA_REPO to a checkout if the layout differs."
        )
    if not src.strip():
        pytest.fail("NBA's facts.py came back empty; the market check would pass vacuously")
    markets = set(re.findall(r'"market":\s*"(\w+)"', src))
    missing = NBA_REQUIRED_MARKETS - markets
    assert not missing, (
        f"NBA's /facts no longer emits {sorted(missing)}; the v2 panel draws its "
        f"tiles, split bar and market row from `markets`, and the site serves NBA "
        f"now. It emits {sorted(markets)}."
    )
