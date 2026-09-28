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
    {"market": "spread",    "model_margin": m, "line": <MODEL's own wording>,
                            "market_line": <MARKET's line, only when quoted>}
    {"market": "total",     "model_total": t,
                            "market_line": <MARKET's total, only when quoted>}

**The `line` key is the trap, and this listing used to hide it.** It showed NBA's
spread as `line: <team> <n>`, which is what NFL emits, so the file justifying
serving NBA depicted NBA as identical to the two football sports -- the original
assumption, still in the file. NBA puts the MODEL's projected margin in `line`
and the market's in `market_line`, and emits `market_line` only when a pre-tip
market row exists. See `explainer/template.py` `MARKET_LINE_KEY`.

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
import re
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import facts
from explainer.app import create_app
from explainer.cache import Cache
from explainer.config import SERVED_SPORTS, SPORTS, Settings
from explainer.ledger import Ledger
from explainer.service import Explainer, NotFound

#: Both lists are DERIVED from `config`, not written out here. The first version
#: of this file declared its own `SERVED = ("pl", "nfl", "cfb", "nba")` alongside
#: `assert len(SERVED_SPORTS) == 4`, which meant a fifth sport had to be added in
#: two places and the tests that follow it were parametrised over the copy, not
#: the thing that ships. Now a new sport joins `SERVED_SPORTS` and is covered by
#: the 502 and refusal tests without anyone editing this file.
SERVED = tuple(SERVED_SPORTS)
UNSERVED = tuple(s for s in SPORTS if s not in SERVED_SPORTS)

#: The markets an NBA facts bundle must carry for the v2 panel to have something
#: to draw. If NBA's `/facts` ever loses one of these, this is where the question
#: gets asked again — and it should be asked, because the panel's tiles, split bar
#: and market row all read from `markets`.
NBA_REQUIRED_MARKETS = {"moneyline", "spread", "total"}

#: What each market must CARRY, not merely be called. A decoy returning
#: `[{"market": "moneyline"}, {"market": "spread"}, {"market": "total"}]` with no
#: figures at all satisfied the name-only version of this check -- and so did NBA
#: dropping `market_line` everywhere, which is the key the whole second commit
#: turns on, so the panel would revert to the model-vs-model sentence with this
#: test still green.
NBA_REQUIRED_FIGURES = {
    "moneyline": ("model",),
    "spread": ("model_margin",),
    "total": ("model_total",),
}


def build_app(tmp_path, **sport_apis):
    """The FastAPI app, for the status-code assertions."""
    return create_app(_settings(tmp_path, **sport_apis))


def build(tmp_path, **sport_apis):
    """The Explainer, for the ledger and upstream assertions.

An Explainer wired the way the app's lifespan wires it.

    `TestClient(app)` does NOT run the lifespan, so `app.state.explainer` is never
    built and every route raises `AttributeError: 'State' object has no attribute
    'explainer'`. The pre-existing test in this file got away with that because it
    only asserted a 404, which the refusal produces *before* anything reaches
    app.state -- so it was never testing a served sport at all.

    So this builds the service directly, as tests/test_service.py does, and calls
    `explain()` on it. That is the layer where the refusal actually lives, and it
    is the layer `tests/test_service.py` already uses.
    """
    s = _settings(tmp_path, **sport_apis)
    return Explainer(s, Cache(s.db_path), Ledger(s.db_path, cap=10), httpx.AsyncClient())


def _settings(tmp_path, **sport_apis):
    return Settings(openrouter_api_key="sk-or-v1-supersecret",
                    EXPLAINER_DB_PATH=str(tmp_path / "e.sqlite"),
                    EXPLAINER_ENABLED=False, **sport_apis)


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

@pytest.mark.parametrize("sport", SERVED)
def test_a_served_sport_with_a_dead_backend_is_a_502_not_a_404(tmp_path, respx_mock, sport):
    """Why the 404 assertions above are trustworthy at all.

    Without this, the guard could be "404 whenever the fetch fails" and every
    refusal test would still pass. This was in the original file and was removed
    during the rewrite on the strength of a claim that `TestClient` does not run
    the lifespan -- which is false. It runs the lifespan when used as a context
    manager, which `test_app.py` already relies on.

    Parametrised over every served sport rather than just one, because a new sport
    joining the list should inherit the check without anyone remembering.
    """
    _no_news(respx_mock)
    respx_mock.get(url__startswith=f"http://{sport}.test/api").mock(
        side_effect=httpx.ConnectError("backend down"))

    with TestClient(build_app(tmp_path, **{f"sport_api_{sport}": f"http://{sport}.test/api"})) as app:
        res = app.get(f"/explain/{sport}/g1")

    assert res.status_code == 502, res.text
    # The first disjunct of the original -- `"not reachable" in detail` -- can
    # never be true: the service's message is f"{sport} API unreachable: ...".
    # A disjunct that cannot be satisfied is a test of nothing.
    assert "unreachable" in res.json()["detail"].lower(), res.text


def test_nba_is_served(tmp_path, respx_mock):
    """The regression this change exists to close: NBA was refused alongside F1 on
    an assumption that was never checked against NBA's own facts.

    **Two things were wrong with the first version, and both made it unable to
    fail.**

    *It asserted `answer.get("verdict")`.* `service._generate` catches every
    exception and falls back to `minimal()`, whose verdict is the truthy string
    "No explanation is available for this one yet." So mutating the template to
    `raise RuntimeError` for every NBA render left THIS TEST PASSING -- verified.
    The suite as a whole caught it elsewhere, but the guard whose stated job is
    "NBA answers" was green while every NBA reader saw the not-ready stub. A
    guard must assert something the failure cannot satisfy, so this one requires a
    factor whose key is a market the bundle actually carries.

    *It used `facts(sport="nba")`, which is an NFL bundle with the `sport` string
    relabelled* -- "Chiefs at Ravens", a "before kickoff" record, one spread
    market, and no `market_line` anywhere. So it exercised no NBA shape at all:
    not the two-key problem, not the quoted line, not "tip-off". The bundle is
    built here instead, and it is the shape NBA's own `_markets` returns.

    (The old `test_no_explain_proxy.py` had the same relabelling habit, and the
    project rule is that a double is built with the code that produces it.)
    """
    _no_news(respx_mock)
    respx_mock.get(url__startswith="http://nba.test/api/facts/g1").mock(
        return_value=httpx.Response(200, json=_nba_facts()))

    answer = asyncio.run(build(tmp_path, sport_api_nba="http://nba.test/api").explain("nba", "g1"))

    keys = {f["key"] for f in answer.get("factors", [])}
    assert keys, f"NBA produced no factors at all: {answer}"
    # Subset, not intersection. An intersection tolerates the spread factor being
    # ABSENT -- which is precisely the state commit f1d14b9 was written about, so an
    # intersection here would pass with the very bug this test exists to protect
    # against reintroduced. The bundle carries a quoted `market_line`, so the
    # spread is free to assert and names the thing at stake.
    for required in ("moneyline", "spread", "total"):
        assert required in keys, (
            f"NBA's answer has no {required} factor: {sorted(keys)}. Its own facts "
            f"supply all three, and this bundle supplies a quoted `market_line`, so "
            f"the spread is the one that must not be dropped. A `minimal()` "
            f"fallback would pass an `answer.get('verdict')` assertion with "
            f"{answer.get('verdict')!r}, which is why this asserts factors."
        )


def _nba_facts() -> dict:
    """An NBA facts bundle, built the shape NBA's own `_markets` produces.

    Deliberately includes a quoted spread line, so the bundle exercises the
    `market_line` path -- and a `record.label` that says "tip-off", because the
    template's `_START` and the panel's record label have to agree for a sport
    that does not use the word "kickoff".
    """
    return {
        "sport": "nba", "id": "g1", "title": "MIA at BOS",
        "starts_at": "2026-10-20T00:20:00Z", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": "BOS", "prob": 0.62},
        "markets": [
            {"market": "moneyline", "model": {"BOS": 0.62, "MIA": 0.38}},
            {"market": "spread", "model_margin": 4.2,
             "line": "BOS by 4.2", "market_line": "BOS -3.5"},
            {"market": "total", "model_total": 226.5, "market_line": "224.5"},
        ],
        "drivers": [], "context": {}, "players": [],
        "record": {"label": "Picks made before tip-off", "hits": 30, "settled": 50},
        "result": None,
    }


def test_nba_is_in_the_served_list_and_f1_is_not():
    """The list itself, so a future edit that re-adds F1 or drops NBA fails here
    rather than in production.

    Asserted as a RELATIONSHIP, not as a count. `len(SERVED_SPORTS) == 4` was the
    previous form and it was wrong in a way that reads as strictness: it fails
    when a sport is correctly added, and it passes when the same number of wrong
    sports is in the list. What actually has to hold is that every configured
    sport has been deliberately classified, that the two halves do not overlap,
    and that F1 is the only refusal.
    """
    assert set(SERVED) & set(UNSERVED) == set(), "a sport is both served and refused"
    assert set(SERVED) | set(UNSERVED) == set(SPORTS), (
        f"a sport was added to config without deciding to serve or refuse it: "
        f"served={sorted(SERVED)} unserved={sorted(UNSERVED)} configured={sorted(SPORTS)}"
    )
    assert "nba" in SERVED_SPORTS
    assert "f1" not in SERVED_SPORTS
    assert set(UNSERVED) == {"f1"}, f"F1 is the only refusal; got {sorted(UNSERVED)}"


def test_nbas_facts_carry_the_markets_the_panel_draws():
    """The reason NBA can serve, asserted rather than assumed.

    This is the check that was missing when NBA was refused. F1's `win` market is
    a probability map with no line, no spread and no total; NBA has the same three
    markets as the two football sports. If NBA's facts builder ever drops one, the
    panel's tiles and split bar lose a figure, and that should be a failing test
    rather than a blank space on a game page.

    **It inspects the SHAPE, not the names.** The first version of this test
    regex-matched `"market": "x"` out of NBA's source and a review built a fake
    `facts.py` whose `_markets()` returns `[]` and mentions all three names only
    in a comment -- six passed. Names in a string prove nothing about what a
    function returns. So this *runs* the builder.

    Read from NBA's own git rather than a checkout, so it tests what ships. If the
    sibling is absent the test FAILS rather than skips: a skipped test here would
    make the whole justification for serving NBA unverifiable, which is the one
    thing this file exists to prevent.
    """
    source = _nba_facts_source()
    if "def _markets" not in source:
        pytest.fail("could not find _markets() in NBA's facts.py, so the market "
                    "check would pass vacuously")

    # Run the builder rather than scan for names. The whole module cannot be
    # exec'd -- it imports pandas and the storage layer -- so the function and the
    # two small helpers it calls are cut out and run together. That is the
    # difference between a test that asks what NBA returns and one that greps for
    # the word.
    markets = _run_nba_markets(source)

    missing = NBA_REQUIRED_MARKETS - set(markets)
    assert not missing, (
        f"NBA's /facts does not return {sorted(missing)}; the v2 panel draws its "
        f"tiles, split bar and market row from `markets`, and the site serves NBA "
        f"now. It returns {sorted(set(markets))}."
    )

    # The names are necessary and not sufficient. Each market must also carry the
    # model figure the panel reads, because a bundle of three empty market dicts
    # satisfies the name check while the panel has nothing to draw -- and the
    # spread must carry the QUOTED key, because `template.MARKET_LINE_KEY` reads
    # `market_line` for NBA and falls back to nothing at all.
    for name, keys in NBA_REQUIRED_FIGURES.items():
        market = markets.get(name)
        assert market is not None, f"{name} missing entirely"
        for key in keys:
            assert market.get(key) is not None, (
                f"NBA's {name} market has no {key!r}: {market}. A market with a name "
                f"and no figure is a label, not a market."
            )
    for name, expected in NBA_EXPECTED_LINES.items():
        assert markets[name].get("market_line") == expected, (
            f"NBA's {name} `market_line` is "
            f"{markets[name].get('market_line')!r}, expected {expected!r}. The "
            f"template reads this key for NBA and has NO fallback -- `line` is the "
            f"MODEL's own wording there -- so a wrong or model-derived value here "
            f"renders the model compared with itself, silently, which is the exact "
            f"failure this branch exists to prevent."
        )


def _run_nba_markets(source: str) -> dict[str, dict]:
    """Exec NBA's real quoted-line chain and ask what it puts in `market_line`.

    **The stub moved, and that is the whole point.** The earlier version stubbed
    `_market_line` -- the one function that decides what lands in `market_line` --
    so it could prove the KEY was present and say nothing about the VALUE. A
    decoy built from NBA's real helpers with only `_market_line` changed to
    return the model's own wording passed the whole suite, and the template then
    rendered *"against a line of Toss-up"* from the real code path.

    So the stub is now the **storage read** (`_market_rows`) and the tip-off
    filter (`made_before_tip`), and the real `_market_line` and `_line_from_market`
    run. `_line_from_market` is the function that knows a spread is signed and
    team-attributed (`'BOS -3.5'`) while a total is neither (`'Over 224.5'`) --
    and the ledger records that a totals line once rendered as `Over +224.5`. None
    of that is re-implemented here, so the probe cannot drift from it.
    """
    def cut(name: str) -> str:
        m = re.search(rf"^def {name}\(.*?(?=^def |^@router|\Z)", source, re.S | re.M)
        assert m, f"NBA's facts.py has no {name}(); the probe would pass vacuously"
        return m.group(0)

    body = "".join(cut(n) for n in (
        "_num", "_favourite", "_margin_line", "_line_from_market", "_market_line", "_markets",
    ))
    env: dict = {}
    exec(compile("from __future__ import annotations\nfrom typing import Any\n" + body,
                 "<nba markets>", "exec"), env)

    #: One pre-tip row per market, in the shape `_market_line` reads.
    rows = [
        {"market": "spread", "point": -3.5, "created_at": "2026-10-19T12:00:00Z",
         "selection": "BOS"},
        {"market": "totals", "point": 224.5, "created_at": "2026-10-19T12:00:00Z",
         "selection": "Over"},
    ]
    env["_market_rows"] = lambda game_id: rows
    env["made_before_tip"] = lambda created_at, game: True

    game = {"game_id": "401585", "home_team": "BOS", "away_team": "MIA"}
    prediction = {"home_win_prob": 0.62, "predicted_margin": 4.2, "predicted_total": 226.5}
    out = env["_markets"](game, prediction)
    return {str(m.get("market")): m for m in out if isinstance(m, dict)}


#: The exact strings NBA's real `_line_from_market` produces from the rows above.
#: A spread is signed and team-attributed; a total is neither. Pinned as literals
#: because a spread reading `'Over 224.5'` or `'BOS -3.5'` where the other belongs
#: is precisely the class of defect the ledger already records NBA shipping once.
NBA_EXPECTED_LINES = {
    "spread": "BOS -3.5",
    "total": "Over 224.5",
}


def _nba_facts_source() -> str:
    import os
    import subprocess
    from pathlib import Path

    here = Path(__file__).resolve()
    candidates = [Path(os.environ["NBA_REPO"])] if os.environ.get("NBA_REPO") else []
    candidates += [p / "NBA_Predictor" for p in here.parents]
    root = next((c for c in candidates if (c / ".git").exists()), None)
    assert root is not None, (
        "NBA_Predictor not found beside this repo, so the claim that NBA carries "
        f"the panel's markets is UNVERIFIED rather than true. Set NBA_REPO. "
        f"Looked in {[str(c) for c in candidates[:4]]}"
    )
    try:
        src = subprocess.run(
            ["git", "-C", str(root), "show", "origin/main:src/nba_predictor/api/facts.py"],
            capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        # Not a bare re-raise. `origin/main` is absent in a fork, on a branch that
        # has not pushed it, and when git is not installed at all, and the default
        # `CalledProcessError` says none of that -- it prints a command line and an
        # exit status. This test exists to keep a CLAIM honest, so when it cannot
        # check the claim it has to say the claim is unchecked.
        pytest.fail(
            f"could not read NBA's facts.py from {root} "
            f"(origin/main:src/nba_predictor/api/facts.py), so the claim that NBA "
            f"carries the panel's markets is UNVERIFIED rather than true. "
            f"Underlying error: {exc}"
        )
    assert src.strip(), "NBA's facts.py came back empty; the check would pass vacuously"
    return src
