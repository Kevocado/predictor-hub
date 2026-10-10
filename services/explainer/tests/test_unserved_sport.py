"""The refusal guard: a sport the service does not answer for is a 404, not a
template.

The refusal has to be a *refusal*: a 404 that looks like a missing fixture. A
template here would render a panel, spend nothing, and read as success — so the
tests below assert the request was never even attempted, not merely that the
status code was right.

**Every configured sport is served as of the F1 reversal, so this file has no
sport to refuse — and that is the state in which a guard like this is easiest to
lose.** `UNSERVED` is derived from `config`, so it is now empty; the test
parametrised over it collected ZERO cases and pytest reported the file's last
remaining guard as `1 skipped` with an empty parameter set. That is the failure
this file exists to prevent, reached from the other direction: not a guard that
was written to pass, but a guard that stopped being collected while the file went
on looking covered.

So the refusal guard is asked its question by *removing* a sport from the served
tuple for the duration (`unserved_probe`), rather than by borrowing one. A test
that faked the sport instead — a sport id outside `SPORTS`, which has no
configurable API — would be worse than useless here: `_facts` raises
`NotFound("no sport API configured")` before it ever makes a request, so
"a refused sport must not touch its upstream" would hold whether the guard sat
before the fetch or after it. The probe is a sport with a real upstream on
purpose, so the "the refusal came first" claim stays an observation.

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

**F1 left this list last, and the reason it was on it was half right.** "A win
probability *is* the explanation" is true of the win probability and was never an
argument against the race story around it, which is what F1's `drivers` and
`podium` carry. F1 still has no line, so a model-vs-market tile has nothing
honest to show and the spread and total factors must not fire — that half of the
reason stands, and `tests/test_f1_served.py` holds it. A refusal is not a bug
report, though: it is a decision somebody has to reverse in the open.
"""
import asyncio
import contextlib
import io
import os
import pathlib
import re
import subprocess

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import facts
from explainer import service as explainer_service
from explainer.app import create_app
from explainer.cache import Cache
from explainer.config import SERVED_SPORTS, SPORTS, Settings
from explainer.ledger import Ledger
from explainer.service import Explainer, NotFound

#: Both lists are DERIVED from `config`, not written out here. The first version
#: of this file declared its own `SERVED = ("pl", "nfl", "cfb", "nba")` alongside
#: `assert len(SERVED_SPORTS) == 4`, which meant another sport had to be added in
#: two places and the tests that follow it were parametrised over the copy, not
#: the thing that ships. Now a new sport joins `SERVED_SPORTS` and is covered by
#: the 502 and refusal tests without anyone editing this file.
SERVED = tuple(SERVED_SPORTS)
UNSERVED = tuple(s for s in SPORTS if s not in SERVED_SPORTS)

#: The sport the refusal tests ask about when the derived list has nobody in it.
#:
#: F1, because it is the one that was last on the list, so every message and every
#: docstring below reads about the sport the decision is actually about. It has
#: to be in `SPORTS` -- that is what makes `sport_api_f1` settable, and a sport
#: with no API is a sport whose upstream cannot be reached at all, which would
#: leave "a refused sport must not touch its upstream" true whatever the guard
#: did with it.
UNSERVED_PROBE = "f1"

#: What the parametrised refusal test runs over: every sport `config` actually
#: refuses, or the probe while that list is empty.
#:
#: **The `or` is the whole point and is not a convenience.** With the list empty
#: and no fallback, `@pytest.mark.parametrize("sport", UNSERVED)` collects zero
#: cases; pytest reports that as `1 skipped` with the reason "got empty parameter
#: set", the file still holds a test, and the guard is gone with nothing failing.
#: Deriving the subject list from `config` is right -- it is what made a newly
#: added sport inherit these tests -- and on its own it is also how this file
#: would have emptied itself.
#:
#: **It is not guarded by asserting itself, and that is a correction.**
#: `assert REFUSAL_SUBJECTS` was the first attempt and it is the wrong question:
#: it asks whether one constant is truthy, so it catches today's edit and nothing
#: else. Re-parametrising the test over a *different* empty source -- `SPORTS`
#: minus something else derived, a literal nobody filled in -- leaves the
#: constant non-empty and the guard still collected zero cases. What holds is
#: `test_the_refusal_guard_is_actually_collected` below, which runs this test's
#: own collection and asks whether anything in it will RUN.
REFUSAL_SUBJECTS = UNSERVED or (UNSERVED_PROBE,)

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


@pytest.fixture
def unserved_probe(monkeypatch):
    """Take `UNSERVED_PROBE` out of the served tuple for the test, and name it back.

    The guard is `if sport not in SERVED_SPORTS` on the first line of
    `Explainer.explain`, and it reads the name bound in `explainer.service`'s own
    namespace (`from .config import SERVED_SPORTS`). So this patches that name,
    which is the branch's INPUT rather than the branch.

    **Two things it deliberately does not do.** It does not touch `explain` or
    the `raise`, so a guard that stopped refusing -- or that was moved below the
    facts fetch -- still fails the tests below. And it does not use a sport id
    outside `SPORTS`: such a sport has no configurable API, so `_facts` raises
    `NotFound("no sport API configured")` before making any request, and
    "a refused sport must not touch its upstream" would then hold whether or not
    the guard is anywhere near the top of the method.

    Applied to every refusal test here, not only the ones whose subject is the
    probe: when `UNSERVED` is non-empty the subject is some other sport, and
    un-serving a sport that was already served changes nothing about it. One code
    path is easier to keep honest than two.
    """
    monkeypatch.setattr(
        explainer_service, "SERVED_SPORTS",
        tuple(s for s in SERVED_SPORTS if s != UNSERVED_PROBE),
    )
    return UNSERVED_PROBE


@pytest.mark.parametrize("sport", REFUSAL_SUBJECTS)
def test_an_unserved_sport_is_a_404_not_a_template(tmp_path, respx_mock, unserved_probe, sport):
    _no_news(respx_mock)
    # If the guard sat *after* the facts fetch, this route would be hit and the
    # response would be a 200 with a template body. Asserting the status code
    # alone would pass in exactly that case -- and with a subject that has no
    # configured API it would pass for a second reason as well, which is why the
    # subject has to be a real sport with a real upstream.
    upstream = respx_mock.get(url__startswith=f"http://{sport}.test/api").mock(
        return_value=httpx.Response(200, json=facts(sport=sport)))

    with pytest.raises(NotFound):
        asyncio.run(build(tmp_path, **{f"sport_api_{sport}": f"http://{sport}.test/api"}).explain(sport, "g1"))

    assert not upstream.called, "a refused sport must not touch its upstream"


def test_the_refusal_guard_is_actually_collected():
    """The guard above must collect at least one case that will actually RUN.

    **This is the defect this whole file is about, and it was reintroduced one
    line away.** The commit that un-refused F1 left `UNSERVED` empty, so
    `@pytest.mark.parametrize("sport", UNSERVED)` collected zero cases. pytest
    reports an empty parameter set as a SKIP, so the file kept its name, its
    docstring and its last remaining guard, and the suite read
    `398 passed, 1 skipped` with exit 0:

        $ python -m pytest -q
        SKIPPED [1] tests/test_unserved_sport.py: got empty parameter set for (sport)
        398 passed, 1 skipped

    The harness cannot see it either, and that is by construction rather than by
    luck: `mutcheck_template_line.run()` returns `count("failed"), count("passed"),
    0` and a skip is in neither bucket, and its baseline is recomputed on every
    run, so a suite that quietly lost a guard still produces a green baseline and
    a clean table.

    So the fallback in `REFUSAL_SUBJECTS` is load-bearing, and deleting it must
    fail HERE. Which is why this asserts the COLLECTION and not the constant:

    * `assert REFUSAL_SUBJECTS` asks whether one value is truthy. It catches the
      edit above and nothing else.
    * Asking what the test's collection contains catches every version of it --
      re-parametrising over a different empty source, a literal nobody filled
      in, a source that goes empty on a branch -- because they all produce the
      same thing: no case that runs.

    **It is a real collection, run by pytest, not a re-derivation of the
    argument.** `@pytest.mark.parametrize` is applied by pytest's own
    `pytest_generate_tests` hook while this module is collected, and the items
    that come out are what the suite will report. Reading `REFUSAL_SUBJECTS`
    again here would only re-ask the question the constant already answers.

    **Counting items is not enough, so it counts items that will RUN.** With the
    fallback gone pytest still collects exactly one item -- the test function
    itself, with `params == {'sport': NOTSET}` and a `skip` mark reading "got
    empty parameter set for (sport)". `--collect-only -q` on the mutated file
    prints `test_an_unserved_sport_is_a_404_not_a_template[NOTSET]` and
    `1 test collected`, which reads like coverage and is the absence of it. So
    the assertion is on items with no `skip` mark, and the reason the skipped
    ones carry is in the failure message.
    """
    collected = _collect(
        f"{pathlib.Path(__file__).resolve()}"
        f"::test_an_unserved_sport_is_a_404_not_a_template")

    skipped = [i for i in collected if i.get_closest_marker("skip") is not None]
    running = [i for i in collected if i.get_closest_marker("skip") is None]

    reasons = "; ".join(
        f"{i.name}: {i.get_closest_marker('skip').kwargs.get('reason')!r}"
        for i in skipped)
    assert running, (
        f"the refusal guard collects {len(collected)} case(s) and NONE of them "
        f"runs -- {reasons or 'no skip reason reported'}. The test still exists, "
        f"so this file still looks covered, and a skip is invisible both to the "
        f"summary line and to the mutation harness (which tallies only failed "
        f"and passed). The refusal guard is not testing anything. Check "
        f"`REFUSAL_SUBJECTS`: with every configured sport served, `UNSERVED` is "
        f"empty, and it is the `or (UNSERVED_PROBE,)` that keeps this "
        f"parametrisation non-empty."
    )
    # Not decorative, and it is not "assert the constant" again. An assertion of
    # "at least one runs" would be satisfied by a single case whose parameters
    # are still UNSET, so this asks that each case carries a real configured
    # sport. `SPORTS` rather than `REFUSAL_SUBJECTS`: the question is whether the
    # subject is a sport this service can be asked about, and comparing against
    # the very list under test would make the check agree with the thing it is
    # checking. It also catches a re-parametrisation over ids that are not
    # sports, which this file's own docstring rules out for a different reason
    # (`_facts` raises before it makes a request).
    for item in running:
        params = item.callspec.params if item.callspec is not None else {}
        assert params, f"{item.name} would run with no parameters at all"
        for name, value in params.items():
            assert value in SPORTS, (
                f"{item.name} would run with {name}={value!r}, which is not a "
                f"configured sport (SPORTS={SPORTS}). A refusal subject has to be "
                f"a sport with a real upstream: one with no configured API makes "
                f"`_facts` raise before it requests anything, so 'a refused sport "
                f"must not touch its upstream' would hold wherever the guard sat."
            )


def _collect(node_id: str) -> list:
    """Collect `node_id` with a real pytest session and return its items.

    In-process rather than a subprocess, so the collection is the same pytest
    and the same `conftest.py` the suite uses and a reader can follow it without
    a second interpreter. `--collect-only` means no test is executed: this asks
    what would be run, which is the question, and running the guard it is
    checking would be circular.

    The `pytest_collection_modifyitems` hook is pytest's own collection API and
    the items it hands over are the ordinary `Function` nodes the reporter
    counts, so `get_closest_marker` and `callspec` below are the same
    attributes pytest itself reads.
    """
    captured: list = []

    class _Collect:
        def pytest_collection_modifyitems(self, session, config, items):
            captured.extend(items)

    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        # `-p no:asyncio` unregisters `pytest-asyncio` in the NESTED session
        # only. It is here because this file drives its own event loop with
        # `asyncio.run` and defines no async test, so the plugin contributes
        # nothing to the collection being asked about -- and leaving it
        # registered makes it warn, on every outer run, that
        # `asyncio_default_fixture_loop_scope` is unset. The warning is raised
        # while the nested session configures, inside the outer session's
        # warning capture, so it lands against this test. `-W` does not help:
        # the plugin registers before the command line's warning filters are
        # applied. Pinning the ini value instead would freeze a setting the
        # project is free to choose later.
        code = pytest.main([node_id, "--collect-only", "-q",
                            "-p", "no:asyncio", "-p", "no:cacheprovider"],
                           plugins=[_Collect()])

    assert code == pytest.ExitCode.OK, (
        f"collecting {node_id} returned {code}, so this test cannot say whether "
        f"the refusal guard is collected:\n{out.getvalue()}"
    )
    return captured


def test_a_refusal_spends_nothing(tmp_path, respx_mock, unserved_probe):
    """The refusal is the first line of the route, before the facts fetch and
    before `try_spend()`. A refused request that cost budget would drain the cap
    for a sport the service will never answer for."""
    _no_news(respx_mock)
    svc = build(tmp_path, **{f"sport_api_{unserved_probe}": f"http://{unserved_probe}.test/api"})
    with pytest.raises(NotFound):
        asyncio.run(svc.explain(unserved_probe, "g1"))
    assert svc.ledger.used_today() == 0


def test_a_refusal_does_not_look_like_a_missing_fixture(tmp_path, respx_mock, unserved_probe):
    """404 is right and 200-with-a-template is wrong, but the *message* matters
    too: a reader (or a caller retrying) must be able to tell "this sport has no
    panel" from "that game does not exist"."""
    _no_news(respx_mock)
    with pytest.raises(NotFound) as excinfo:
        asyncio.run(build(tmp_path, **{f"sport_api_{unserved_probe}": f"http://{unserved_probe}.test/api"})
                     .explain(unserved_probe, "g1"))

    message = str(excinfo.value)
    assert unserved_probe in message, message
    # And it must not read as "no such game", which is the OTHER refusal on this
    # route: a reader (or a caller retrying) has to be able to tell "this sport has
    # no panel" from "that game does not exist".
    #
    # **On the real wording.** This read `"no such game" not in message.lower()`,
    # and that string appears nowhere in the codebase -- so the assertion could
    # not fail, while having the shape of a check that distinguishes the two
    # refusals. The missing-fixture refusal is `service.py:92`,
    # `f"{sport} has no facts for {id!r}"`, and that is the wording to exclude.
    # `service.py:86`'s `no sport API configured for ...` is a third refusal and
    # is not what this is about: it is a misconfiguration, not a missing
    # fixture, and a caller should be able to tell that apart too.
    assert "has no facts" not in message.lower(), (
        f"the refusal reads like a missing fixture rather than an un-served "
        f"sport, so a caller retrying cannot tell the two apart: {message!r}. The "
        f"missing-fixture refusal is `f\"{{sport}} has no facts for {{id!r}}\"` at "
        f"service.py:92, and this branch must not produce it."
    )
    # Positive, so the negative above is not satisfied by a message that says
    # nothing at all -- which is the other way this pair of assertions could pass
    # while being useless.
    assert "not served" in message.lower(), (
        f"the refusal does not say the sport is not served, so it names neither "
        f"state to the caller: {message!r}"
    )


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

    # The v9 panel is a verdict and a read. `service._generate` swallows every
    # exception into `minimal()`, whose verdict is also truthy, so assert the one
    # thing only the real template says: it names the pick.
    assert answer.get("verdict") == "BOS is the pick.", f"NBA did not get the template's own answer: {answer}"
    assert answer["factors"] == [] and "read" in answer and answer["band"] in ("leaning", "moderate", "strong")


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


def test_every_configured_sport_is_served_and_nothing_is_refused():
    """The list itself, so a future edit that drops a sport fails here rather
    than in production.

    Asserted as a RELATIONSHIP, not as a count. `len(SERVED_SPORTS) == 4` was the
    previous form and it was wrong in a way that reads as strictness: it fails
    when a sport is correctly added, and it passes when the same number of wrong
    sports is in the list. What actually has to hold is that every configured
    sport has been deliberately classified and that the two halves do not
    overlap.

    **The refusal list is now empty, and that is the intended end state rather
    than a gap in the file.** It was `{"f1"}` and it was NBA before that, and
    each of those was a product decision somebody reversed in the open. So the
    assertion is not "F1 is absent" restated -- it is that nothing is refused at
    all, which is a claim about every sport in `SPORTS` at once and would notice
    one being dropped. That is why this test is stronger than the one it replaces
    and not a weaker paraphrase of it: `"f1" not in SERVED_SPORTS` and
    `"nba" in SERVED_SPORTS` are both entailed by the empty set below, and only
    the empty set would notice a sixth sport being un-served.
    """
    assert set(SERVED) & set(UNSERVED) == set(), "a sport is both served and refused"
    assert set(SERVED) | set(UNSERVED) == set(SPORTS), (
        f"a sport was added to config without deciding to serve or refuse it: "
        f"served={sorted(SERVED)} unserved={sorted(UNSERVED)} configured={sorted(SPORTS)}"
    )
    assert set(UNSERVED) == set(), (
        f"a configured sport is refused again: {sorted(UNSERVED)}. Every sport in "
        f"`SPORTS` serves as of the F1 reversal, so a non-empty refusal list means "
        f"a sport was taken out of `SERVED_SPORTS` deliberately -- which is a "
        f"product decision to be made in the open, in a commit that says why, and "
        f"not something this test should be edited to accept."
    )


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


# --- the half of NBA's rule this repo adopts, checked from HERE ----------------
#
# **Why a second file, and what it does and does not buy.** The claim that
# `MIN_SPREAD_MARGIN` is NBA's floor and not a number this repo picked is asserted
# in `test_template_spread_claim.py`, derived by running NBA's real `_margin_line`.
# Those two assertions lived in one file, and one file cannot defend itself: delete
# both and the suite is green and the claim has no witness anywhere -- not the
# harness, not `config.py`, not the README. A reviewer is right that no assertion
# can defend itself against its own deletion; what they are also right about is the
# specific residual, and the cheap fix for a residual is a second witness in a file
# the first file's deletion does not touch.
#
# So this is one derived assertion, in a file that already reads NBA's git through
# `_nba_facts_source` and already owns the "run NBA's builder rather than grep it"
# method. **It is a DERIVATION and not a grep**, which is the part that matters: a
# regex over NBA's source would be satisfied by NBA's docstring, which quotes
# `Toss-up` and the whole rule in prose, and by any comment above the line. This
# cuts the function out and RUNS it, so a comment cannot answer it.
#
# **It is not a replacement.** `test_template_spread_claim.py` still holds the
# literal, the boundary sweep at and just under the floor, the anti-vacuity checks
# on the probe, and the decoy that moves NBA's floor and asserts the probe notices.
# This one asserts the single thing whose loss would leave the claim unwitnessed.
#
# **It is in this file because this file is on `origin/main`**, so adding a witness
# is an addition to something a reader already has rather than a fourth file whose
# only content is a copy of another file's assertion.

#: How finely the witness sweeps, and why a thousandth is the right step. Every
#: floor a sports builder plausibly writes -- 0.25, 0.3, 0.5, 0.6 -- lands exactly
#: on a step, so the derived value is the floor rather than an approximation of it,
#: which is what lets the comparison below be exact equality. And the sweep is
#: BEHAVIOURAL, so a floor NBA writes as `0.5` on one line and `1.0 / 2` on another
#: is the same number to this witness.
_FLOOR_STEP = 0.001
_FLOOR_MAX = 2.0

#: The word NBA emits for a margin that is not a gap. Read out of the function's
#: own output rather than written here, because a literal is the kind of copy this
#: derivation exists to remove -- if NBA renames it, a witness holding `"Toss-up"`
#: would compare against a string NBA no longer emits and report a floor of "the
#: first margin that is not that string", which happens to still be right. So it is
#: derived: a margin of 0 is a non-gap, and that string is what the function calls
#: one.
def _nba_floor_from_its_own_function() -> float:
    """The smallest margin NBA's own `_margin_line` words as a gap, found by
    running it. Raised from, not re-implemented from."""
    source = _nba_facts_source()
    cut = re.search(r"^def _margin_line\(.*?(?=^def |\Z)", source, re.S | re.M)
    assert cut, (
        "NBA's facts.py has no `_margin_line` on origin/main, so the claim that this "
        "template's floor is NBA's is UNVERIFIED rather than true. The function is "
        "the authority: it decides whether a projected margin is worded as a gap or "
        "as a toss-up, and a bundle it called a toss-up arrives here already "
        "described as one."
    )
    env: dict = {}
    exec(compile("from __future__ import annotations\n" + cut.group(0),
                 "<nba _margin_line>", "exec"), env)
    margin_line = env["_margin_line"]

    # The side gate is made a non-question, so what the sweep measures is the
    # MAGNITUDE half of NBA's rule and nothing else: `home_prob = 0.62` puts the
    # pick at home, a non-negative margin puts the projection at home too, so "is
    # this margin pointed at the pick's team" holds at every magnitude. The other
    # half is not adoptable here at all -- the bundle carries no home/away
    # designation -- and that limit is `test_template_spread_claim.py`'s to state in
    # full. All this witness claims is the number.
    not_a_gap = margin_line("BOS", "MIA", 0.62, 0.0)
    assert not not_a_gap.startswith("BOS by"), (
        f"NBA words a zero margin as a gap ({not_a_gap!r}), so there is no boundary "
        f"to find and any floor this file reports would be an artefact"
    )
    assert margin_line("BOS", "MIA", 0.62, _FLOOR_MAX).startswith("BOS by"), (
        f"NBA does not word a {_FLOOR_MAX}-point margin as a gap naming a team, so "
        f"the word this sweep is looking for is not the word NBA uses"
    )
    for i in range(int(round(_FLOOR_MAX / _FLOOR_STEP)) + 1):
        value = round(i * _FLOOR_STEP, 6)
        if margin_line("BOS", "MIA", 0.62, value) != not_a_gap:
            return value
    raise AssertionError(
        f"NBA's `_margin_line` called every margin up to {_FLOOR_MAX} a toss-up, so "
        f"it sets no magnitude floor and whatever this repo used would be a second "
        f"disagreement with the bundle's producer."
    )


def test_this_services_margin_floor_is_the_one_nbas_own_function_sets():
    """The one derived assertion, here so it is not only in the other file.

    `explainer.template.MIN_SPREAD_MARGIN` is the threshold below which this
    template stops narrating a projected margin at all, on the stated ground that
    NBA's own builder words a smaller one as the literal `Toss-up` and a bundle
    carrying it has therefore already been told there is no gap. If that ground is
    wrong the template contradicts the producer of its own data, in the direction
    that prints a gap the sport said there was not.

    **Derived by running NBA's function, over a thousand margins.** Not a literal --
    a literal is a copy of the number, and against a decoy NBA whose floor is `0.6`
    the copy passes with the template disagreeing with its data by a tenth of a
    point. Not a regex over NBA's source -- NBA's docstring quotes `Toss-up` and
    the whole rule in prose, and `count=1`-style first-match readers are satisfied
    by a comment. RUNNING it is the only read that cannot be answered by prose, and
    it is why this is here rather than a second copy of the other file's assertion.
    """
    from explainer.template import MIN_SPREAD_MARGIN

    derived = _nba_floor_from_its_own_function()
    assert derived == MIN_SPREAD_MARGIN, (
        f"NBA's own `_margin_line` words a margin as a gap from {derived} and this "
        f"template's floor is {MIN_SPREAD_MARGIN}. One of the two is a copy of the "
        f"other and the copy is wrong: a bundle whose margin NBA called a toss-up "
        f"arrives here already described as one, and a template with a different "
        f"floor contradicts the producer of its own data. NBA's docstring says the "
        f"function ports `marginLine`; the floor is not a number this repo gets to "
        f"choose."
    )

