"""The hub's one read: what each sport picks next, how sure, and how it's done.

The hub was five same-size link cards. `PRODUCT.md` Principle 1 is "Pick first",
and every game surface already answers *who / how sure / has it been right*
before anything else — the hub was the one place that answered none of the three,
so a reader had to leave it to learn whether there was a reason to stay.

This endpoint is the data for that. It is deliberately **not** an explanation:
it is a pick, a computed band, and a record, per sport. Which is why it can cover
all five sports while `/explain` still serves only three — refusing to write
prose for a sport with no panel specified is a different decision from declining
to say which way the model leans.

Every test here is about the response being *honest*, because the endpoint's one
job is to be believed:

- the **band is computed**, never read from a payload (spec §13a). A facts bundle
  that asserts `"band": "strong"` at 0.44 must not be believed.
- **one sport failing does not fail the response.** A dead API costs one card,
  not the page — the whole point of the hub is that there are five things to see.
- **an absent record is absent, not zero.** `0/0` reads as "wrong every time",
  and NBA genuinely has no record yet.
- **no upstream body is echoed** into a reason, for the reason every other proxy
  in this family gives: an upstream error can carry an internal path.
"""
import asyncio
import json

import httpx
import pytest
import respx

from explainer import news
from explainer.app import create_app
from explainer.cache import Cache
from explainer.config import Settings
from explainer.ledger import Ledger
from explainer.service import Explainer

SPORTS = ("pl", "f1", "nfl", "cfb", "nba")


def bundle(sport, **over):
    """A facts bundle shaped like all five sports actually emit — verified by
    reading each repo's `_record()`: NFL and CFB say "before kickoff", PL says
    "before kick-off", NBA says "before tip-off", and every one returns the whole
    block as `None` when nothing is settled yet.
    """
    base = {
        "sport": sport, "id": f"{sport}-1",
        "title": f"{sport.upper()} fixture", "starts_at": "2026-10-05T00:20:00Z",
        "status": "upcoming", "pick_timing": "pre_kickoff",
        "pick": {"label": "BAL", "prob": 0.62},
        "markets": [{"market": "result", "model": {"Arsenal": 0.48, "Draw": 0.26, "Chelsea": 0.26}}],
        "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 66},
    }
    base.update(over)
    return base


def make(tmp_path, sports=SPORTS):
    s = Settings(openrouter_api_key="k", EXPLAINER_ENABLED=False, EXPLAINER_MODEL="m1")
    for sport in sports:
        setattr(s, f"sport_api_{sport}", f"http://{sport}.test/api")
    db = str(tmp_path / "e.sqlite")
    app = create_app(s)
    app.state.explainer = Explainer(s, Cache(db), Ledger(db, cap=10), httpx.AsyncClient())
    return app


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://hub")


def happy(mock, sport, **over):
    """A sport that answers /facts/upcoming then /facts/{id}."""
    mock.get(url__startswith=f"http://{sport}.test/api/facts/upcoming").mock(
        return_value=httpx.Response(200, json={"ids": [f"{sport}-1"]}))
    mock.get(url__startswith=f"http://{sport}.test/api/facts/{sport}-1").mock(
        return_value=httpx.Response(200, json=bundle(sport, **over)))


@pytest.fixture(autouse=True)
def _no_news():
    news._CACHE.clear()
    with respx.mock(assert_all_called=False) as mock:
        yield mock


async def summary(app):
    async with client(app) as c:
        r = await c.get("/hub/summary")
        assert r.status_code == 200, r.text
        return r.json()


def entry(body, sport):
    return next(e for e in body["sports"] if e["sport"] == sport)


# --- the three answers, in the order a reader needs them -----------------

@pytest.mark.anyio
async def test_answers_who_how_sure_and_how_it_has_been(tmp_path, _no_news):
    for s in SPORTS:
        happy(_no_news, s)
    body = await summary(make(tmp_path))
    nfl = entry(body, "nfl")
    assert nfl["pick"] == {"label": "BAL", "prob": 0.62}          # who
    assert nfl["band"] == "strong"                                # how sure
    assert nfl["record"] == {"label": "Picks made before kickoff", "hits": 41, "settled": 66}
    assert nfl["ok"] is True


@pytest.mark.anyio
async def test_keeps_the_sports_own_wording_for_its_record(tmp_path, _no_news):
    """"before kickoff" / "before kick-off" / "before tip-off" are the sports'
    own, and the hub is not the place to regularise them. A reader who sees
    "before tip-off" on the hub and "before kickoff" on the NBA site has learned
    two words for one rule; the hub repeating NBA's own label is the fix."""
    for s in SPORTS:
        label = {"nba": "Picks made before tip-off", "pl": "Picks made before kick-off"}.get(
            s, "Picks made before kickoff")
        happy(_no_news, s, record={"label": label, "hits": 41, "settled": 66})
    body = await summary(make(tmp_path))
    assert entry(body, "nba")["record"]["label"] == "Picks made before tip-off"
    assert entry(body, "pl")["record"]["label"] == "Picks made before kick-off"


@pytest.mark.anyio
async def test_orders_the_sports_the_way_the_hub_lists_them(tmp_path, _no_news):
    for s in SPORTS:
        happy(_no_news, s)
    body = await summary(make(tmp_path))
    assert [e["sport"] for e in body["sports"]] == list(SPORTS)


# --- the band is computed, and that is the whole point of §13a -----------

@pytest.mark.anyio
async def test_the_band_is_computed_and_a_payload_cannot_override_it(tmp_path, _no_news):
    """A facts bundle that *claims* a band does not get to set one.

    0.44 is a lean on a two-way market. If the payload could say "strong", the hub
    would print a confidence word no threshold supports — and the payload is
    exactly the part of the system a future change might let a model fill in.
    """
    for s in SPORTS:
        happy(_no_news, s, pick={"label": "KC", "prob": 0.44}, band="strong")
    body = await summary(make(tmp_path))
    assert entry(body, "nfl")["band"] == "moderate"


@pytest.mark.anyio
async def test_a_three_way_market_is_banded_more_generously_than_a_two_way_one(tmp_path, _no_news):
    """The asymmetry, in the direction it actually runs.

    §13a: three-way thresholds are **lower** — strong ≥0.50, moderate ≥0.40
    against two-way's ≥0.60 and ≥0.52. So the same 0.44 reads "moderate" on a
    three-outcome market and "leaning" on a two-outcome one.

    My first version of this test asserted the opposite ("closer to no-edge on
    three") and failed against a correct implementation. Worth recording
    because the inflation is the whole reason the thresholds differ, and reading
    them the wrong way round is easy: a *lower* bar sounds like a *lesser* claim.
    """
    for s in SPORTS:
        happy(_no_news, s, pick={"label": "X", "prob": 0.44},
              markets=[{"market": "result", "model": {"Arsenal": 0.44, "Draw": 0.30, "Chelsea": 0.26}}])
    three_way = entry(await summary(make(tmp_path)), "pl")["band"]
    assert three_way == "moderate"

    for s in SPORTS:
        happy(_no_news, s, pick={"label": "X", "prob": 0.44},
              markets=[{"market": "moneyline", "model": {"A": 0.44, "B": 0.56}}])
    two_way = entry(await summary(make(tmp_path)), "nfl")["band"]
    assert two_way == "leaning"


@pytest.mark.anyio
async def test_a_top_level_result_does_not_make_a_two_way_sport_look_three_way(tmp_path, _no_news):
    """The trap `market_shape` exists for, re-pinned at the hub.

    NFL's facts carry a top-level `result` (the score) as well as PL having a
    `result` MARKET. Keying on the string alone would band every finished NFL
    game on three-way thresholds — which are the more generous ones — so a 0.52
    NFL pick would read "strong".
    """
    for s in SPORTS:
        happy(_no_news, s, pick={"label": "KC", "prob": 0.52},
              markets=[{"market": "moneyline", "model": {"BAL": 0.52, "KC": 0.48}}],
              result={"score": "BAL 24-17", "pick_won": True})
    assert entry(await summary(make(tmp_path)), "nfl")["band"] == "moderate"


@pytest.mark.anyio
async def test_no_pick_means_no_band(tmp_path, _no_news):
    """`pick_timing: "none"` with no pick is a VALID state, not a failure.

    A sport with no forecast at all reports exactly that, and the hub should show
    it as a sport that is not calling one — not as a broken card. NFL pins the
    state in `test_pick_timing_is_none_only_when_there_is_no_forecast_at_all`.
    """
    for s in SPORTS:
        happy(_no_news, s, pick=None, pick_timing="none")
    body = await summary(make(tmp_path))
    e = entry(body, "nfl")
    assert e["ok"] is True
    assert e["pick"] is None
    assert e.get("band") is None
    assert e["pick_timing"] == "none"


@pytest.mark.anyio
async def test_a_pick_timing_that_promises_a_pick_but_gives_none_is_a_contract_failure(tmp_path, _no_news):
    """The other half of the distinction, which my first version collapsed.

    "pre_kickoff" means a number was stored before kickoff. If the bundle claims
    that and carries no pick, one of the two is wrong, and the hub cannot tell
    which — so it says the facts did not match rather than showing a sport that
    is "not calling" anything when it says it called something.
    """
    for s in SPORTS:
        happy(_no_news, s, pick=None, pick_timing="pre_kickoff")
    body = await summary(make(tmp_path))
    e = entry(body, "nfl")
    assert e["ok"] is False
    assert e["reason_kind"] == "bad_contract"
    assert e["pick"] is None


@pytest.mark.anyio
async def test_a_probability_with_no_side_is_a_contract_failure(tmp_path, _no_news):
    """A figure next to nothing. A band computed from it would be a confidence
    word about a side the reader cannot name."""
    for s in SPORTS:
        happy(_no_news, s, pick={"prob": 0.62})
    e = entry(await summary(make(tmp_path)), "nfl")
    assert e["ok"] is False
    assert e["reason_kind"] == "no_pick_label"


# --- absent is not zero --------------------------------------------------

@pytest.mark.anyio
async def test_an_absent_record_is_absent_rather_than_zero(tmp_path, _no_news):
    """NBA has no settled record yet, and its bundle says so with `record: None`.

    Rendering that as `{hits: 0, settled: 0}` would read as "wrong every time",
    which is a claim about a record that does not exist. A derived percentage is
    not invented either: 0/0 has no answer.
    """
    for s in SPORTS:
        happy(_no_news, s, record=None if s == "nba" else
              {"label": "Picks made before kickoff", "hits": 41, "settled": 66})
    body = await summary(make(tmp_path))
    nba = entry(body, "nba")
    assert nba["record"] is None
    assert "pct" not in nba
    assert nba["pick"] is not None, "a missing record must not cost the pick"


@pytest.mark.anyio
async def test_a_known_rate_with_no_count_is_not_zero_hits(tmp_path, _no_news):
    """NFL emits `hits: None` when it knows the rate but not the count. Zero
    would be a claim; the count is simply not available."""
    for s in SPORTS:
        happy(_no_news, s, record={"label": "Picks made before kickoff", "hits": None, "settled": 66})
    body = await summary(make(tmp_path))
    rec = entry(body, "nfl")["record"]
    assert rec["hits"] is None
    assert rec["settled"] == 66


# --- one broken sport costs one card, not the page -----------------------

@pytest.mark.anyio
async def test_one_failing_sport_does_not_fail_the_response(tmp_path, _no_news):
    for s in SPORTS:
        if s == "cfb":
            _no_news.get(url__startswith="http://cfb.test/api/facts/upcoming").mock(
                return_value=httpx.Response(500, text="Internal Server Error: /srv/app/secrets/db.url"))
        else:
            happy(_no_news, s)
    body = await summary(make(tmp_path))
    assert len(body["sports"]) == 5
    cfb = entry(body, "cfb")
    assert cfb["ok"] is False
    assert cfb["pick"] is None
    for s in ("pl", "nfl", "nba"):
        assert entry(body, s)["ok"] is True


@pytest.mark.anyio
async def test_a_reason_never_echoes_the_upstream_body(tmp_path, _no_news):
    """Every other proxy in this family refuses to pass an upstream body on, and
    gives the same reason: an upstream error can carry an internal path. The
    deploy script's smoke output is not a place a secret leaks either."""
    _no_news.get(url__startswith="http://nfl.test/api/facts/upcoming").mock(
        return_value=httpx.Response(503, text="postgres://user:hunter2@db:5432/prod is down"))
    for s in SPORTS:
        if s != "nfl":
            happy(_no_news, s)
    body = await summary(make(tmp_path))
    blob = json.dumps(entry(body, "nfl"))
    assert "hunter2" not in blob
    assert "/srv/app" not in blob
    assert "postgres://" not in blob


@pytest.mark.anyio
async def test_a_sport_with_no_upcoming_fixture_says_so_rather_than_failing(tmp_path, _no_news):
    for s in SPORTS:
        if s == "f1":
            _no_news.get(url__startswith="http://f1.test/api/facts/upcoming").mock(
                return_value=httpx.Response(200, json={"ids": []}))
        else:
            happy(_no_news, s)
    body = await summary(make(tmp_path))
    f1 = entry(body, "f1")
    assert f1["ok"] is False
    assert f1["pick"] is None
    assert "fixture" in (f1.get("reason") or "").lower()


@pytest.mark.anyio
async def test_a_bundle_that_breaks_the_contract_fails_only_its_own_card(tmp_path, _no_news):
    for s in SPORTS:
        if s == "pl":
            _no_news.get(url__startswith="http://pl.test/api/facts/upcoming").mock(
                return_value=httpx.Response(200, json={"ids": ["pl-1"]}))
            _no_news.get(url__startswith="http://pl.test/api/facts/pl-1").mock(
                return_value=httpx.Response(200, json={"sport": "pl"}))  # no title, no status
        else:
            happy(_no_news, s)
    body = await summary(make(tmp_path))
    assert entry(body, "pl")["ok"] is False
    assert entry(body, "nfl")["ok"] is True


@pytest.mark.anyio
async def test_an_unreachable_sport_is_reported_rather_than_raised(tmp_path, _no_news):
    import httpx as _h
    for s in SPORTS:
        if s == "nba":
            _no_news.get(url__startswith="http://nba.test/api/facts/upcoming").mock(
                side_effect=_h.ConnectError("nope"))
        else:
            happy(_no_news, s)
    body = await summary(make(tmp_path))
    assert entry(body, "nba")["ok"] is False
    assert entry(body, "pl")["ok"] is True


@pytest.mark.anyio
async def test_a_bug_in_shaping_one_sport_does_not_take_the_page(tmp_path, _no_news, monkeypatch):
    """`return_exceptions=True` earns its place here, and this is the test for it.

    Every other failure test goes through a `try` block inside `_one`, so the
    gather never sees an exception and `return_exceptions` is untested. Removing
    it passes all of them — checked, and it is exactly the case that would 500 the
    whole page: a bug in `_shape` (or in `band_for` on a bundle nobody imagined)
    raising for one sport.

    So the fault is injected *below* the try blocks, in the shaping itself.
    """
    from explainer import hub as hub_mod

    for s in SPORTS:
        happy(_no_news, s)

    real = hub_mod._shape

    def boom(sport, facts):
        if sport == "cfb":
            raise ValueError("a shape bug nobody imagined")
        return real(sport, facts)

    monkeypatch.setattr(hub_mod, "_shape", boom)

    # The fault is injected BELOW the per-fetch try blocks, so the gather is the
    # only thing standing between one sport's bug and a 500 for the page.
    body = await summary(make(tmp_path))
    assert len(body["sports"]) == 5
    cfb = entry(body, "cfb")
    assert cfb["ok"] is False
    # `internal`, not `bad_contract`. The first version caught the injected fault
    # in the same try that guards the JSON parse, so a bug in this module was
    # reported as the sport's facts not matching the contract -- which sends an
    # operator to the wrong repository to look for bad data that is perfectly
    # good. The message is a claim about who is at fault, so it has to be true.
    assert cfb["reason_kind"] == "internal", "an internal fault must not be blamed on the sport's data"
    assert "a shape bug" not in json.dumps(cfb), "the exception text is not a reader-facing reason"

    # Proven to be OUR fault, not theirs: with `return_exceptions=True` gone the
    # fault escapes `_one`, escapes `summary`, and 500s the whole hub for five
    # sports over one sport's bug. The card is the cheap fix; the page going down
    # is what it prevents.
    import explainer.hub as hub_mod2
    # The real gather, captured first: `hub_mod2.asyncio` IS the asyncio module,
    # so a replacement that calls `asyncio.gather` calls itself. That recursion is
    # how the first attempt at this assertion failed, with a RecursionError
    # instead of the ValueError it was looking for.
    real_gather = asyncio.gather

    async def rethrowing(*aws, **kwargs):
        kwargs.pop("return_exceptions", None)
        return await real_gather(*aws, **kwargs)  # return_exceptions=False

    hub_mod2.asyncio.gather = rethrowing
    try:
        with pytest.raises(ValueError):
            await summary(make(tmp_path))
    finally:
        hub_mod2.asyncio.gather = real_gather
    for s in ("pl", "nfl", "nba"):
        assert entry(body, s)["ok"] is True


# --- the endpoint's own shape --------------------------------------------

@pytest.mark.anyio
async def test_spends_nothing_and_asks_no_model(tmp_path, _no_news):
    """The hub must not consume the daily cap or call a provider. It is a read of
    numbers the sports already computed, and the cap exists for explanations."""
    for s in SPORTS:
        happy(_no_news, s)
    app = make(tmp_path)
    body = await summary(app)
    assert body["sports"]
    assert app.state.explainer.ledger.used_today() == 0
    called = [str(c.request.url) for c in _no_news.calls]
    assert not any("openrouter" in u for u in called), called
    assert all("/facts/" in u for u in called), called


@pytest.mark.anyio
async def test_carries_no_key_material_and_no_upstream_body(tmp_path, _no_news):
    for s in SPORTS:
        happy(_no_news, s)
    body = await summary(make(tmp_path))
    blob = json.dumps(body)
    assert "k" == "" or "openrouter" not in blob.lower()
    for leaked in ("SPORT_API", "OPENROUTER", "sqlite", "/data/"):
        assert leaked not in blob
