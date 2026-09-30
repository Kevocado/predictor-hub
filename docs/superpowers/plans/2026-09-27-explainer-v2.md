# Explainer v2 Implementation Plan

> **Plan only. No code moves with it.** The spec's status line gates a plan on
> the reviewer's approval and gates code on the plan's; #7 was merged with no
> comments, which I read as that approval. **If you meant something narrower,
> say so and I will stop before Task 1** — the first real commit in this work
> would be `contract.py`.

> **Amended by spec §13, which is the first commit of this PR and which changes
> two things in the draft plan you may have skimmed.** The draft put the trigger
> last and let the model choose its own confidence band. Both were wrong, and the
> reasoning is worth reading because the second one is a hole this redesign was
> built to close: **§13a** — `band` is now computed by the service from
> `pick.prob` with fixed thresholds in the spec, because §5a argued that a band
> should not be a *number* and missed that a *word* is worse, since nothing ties
> `"strong"` to anything and a model can call a 52% pick strong with nothing to
> check it. **§13d** — the trigger and the `f1`/`nba` refusal now ship **first**,
> because the scheduler is spending budget today on exactly what the redesign
> removes, and deferring that to the last phase means paying for a deferral.
> §13b and §13c add the PL market-row rule and the interaction. All four are in
> the spec; this plan implements them.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the explainer's prose-only output with a structured, visual panel that renders every figure from the facts bundle, for PL, NFL and CFB only, on demand only.

**Architecture:** The model stops supplying numbers. It returns a verdict, a named confidence band, and 2–4 factors that *reference* a market by key and carry a direction. The panel resolves those references against the facts and renders tiles, a split bar and factor rows from facts data. Because layout is data-driven and does not know whether a model was involved, the template path renders the same layout — which is the only way "the default is just as good" stays true.

**Tech Stack:** Python 3.13, FastAPI, pydantic v2, pytest; React 19, TypeScript, Tailwind 4, vitest.

**Spec:** `docs/superpowers/specs/2026-09-27-explainer-v2-design.md` — read it; this plan argues from it and the two travel together. §5 is the contract, §6 the panel, §7 the mocks, §2 the honesty rules.

## Global Constraints

- **The model never supplies a number that is rendered.** Every figure on screen comes from the facts bundle. This is the design; anything that reintroduces a model-supplied figure is a defect, not a variation.
- **Every figure must pass `validate()`.** Numbers in prose are checked against the facts pool as today.
- **`band` is COMPUTED from `pick.prob`, never supplied by the model** (spec §13a). The model returns `verdict` and `factors` only. A model that volunteers a band has it ignored, and that is tested rather than asserted. Thresholds live in one function, `band_for(prob, shape)`, called by the service *and* the template.
- **A derived ratio may be ENCODED as geometry and never STATED as a figure** (spec §5a-bis). `record` is `hits`/`settled`; write `41 / 68` and let the bar carry the proportion. Never "60.3%". Same in `aria-label`s.
- **No interaction may reveal a figure the facts do not carry** (spec §13c). Affordances may show a label, a highlight, or geometry the facts already supply. None may compute, round or interpolate. A hover tooltip reading "probably around 55-60%" is the named failure.
- **2–4 factors.** Zero is a validation failure.
- **An absent market renders nothing** — never a zero, never a dash. `predict_props` only adds a market `if market in models`, so absence is reachable. Likewise the PL market row: it renders only when `implied` covers **every** outcome the model's split has (spec §13b), and no draw probability is ever derived.
- **12px text floor**, enforced by a test in every repo that renders UI (see `Sports_Predictor/src/craft-floor.test.ts` and `predictor-hub/tests/craft-floor.test.mjs` for the shape).
- **`OPENROUTER_API_KEY` never in a repo, bundle, log, response or test.** It reaches the service only through the service's own env.
- **Tests never touch the network.** OpenRouter and ESPN stay mocked with `respx`.
- **A test double is built with the code that produces it.** Four bugs in this codebase were a double shaped like the consumer; where a schema class or route exists, use it.
- **Every guard gets one deliberately-broken input** before it is believed. Several guards this project shipped passed the exact thing they were written to catch.
- **Never rebase, force-push, or push to `main`.** Branch `claude/sports-predictors-frontend-plan-qpab3v`, one PR per repo, reviewer merges.

## File Structure

**Service (`predictor-hub/services/explainer/`)**
- `explainer/contract.py` — **NEW.** The one place that knows the v2 shape: `VERDICT_BANDS`, `band_for(prob, shape)`, `clean_verdict(body)`, `resolve_factors(verdict, facts)`. Exists so the validator, the template and the service cannot disagree about what a factor is — and so the band thresholds (§13a) exist once, called by both paths.
- `explainer/validate.py` — extends `validate()` with the factor rules.
- `explainer/template.py` — `explain_from_template()` returns a v2 verdict, built from the facts.
- `explainer/service.py` — `_clean()` and `_generate()` speak v2; refuses `f1`/`nba`.
- `explainer/config.py` — `SERVED_SPORTS = ("pl", "nfl", "cfb")` and the refusal in Task 1; `prompt_version` → `"v2"` in Task 2.
- `explainer/scheduler.py` — **DELETED** in Task 1, with its call in `app.py`.
- `explainer/app.py` — no scheduler task; `/explain` 404s for an unserved sport.
- `tests/test_contract.py`, `tests/test_validate_factors.py`, `tests/test_template_v2.py`, `tests/test_unserved_sport.py` — **NEW.**

**Shared UI (`predictor-hub/packages/predictor-ui/src/`)**
- `components/ExplainerVerdict.tsx` — **NEW.** Verdict line + band chip.
- `components/KeyNumberTile.tsx` — **NEW.** One market, model figure large, line beneath.
- `components/ProbabilitySplit.tsx` — **NEW.** `segments` bar, 2- or 3-way, optional second hairline row for the market's own split (rendered only when it covers every outcome, §13b). Each segment is focusable and shows its label on focus/tap (§13c).
- `components/FactorList.tsx` — **NEW.** Direction glyph + headline + sentence. Carries the §13c interaction: each row is a real `<button>` that highlights the tile and bar segment its `key` names.
- `components/RecordStrip.tsx` — **NEW.** `hits / settled` as a bar.
- `components/ExplainerPanel.tsx` — **MODIFIED.** Composes the above; keeps the footer, the rebuilt status and the collapse behaviour.
- `index.ts` — **MODIFIED.** Export the new components and the `Verdict` type.

**Sites**
- `Sports_Predictor/src/components/GameDetailModal.tsx` — **MODIFIED** (NFL + CFB).
- `PL_Predictor/frontend/src/components/FixtureSummaryPanel.tsx` — **MODIFIED** (PL).
- `F1_Predictor/frontend/src/components/SessionSummaryPanel.tsx` — **DELETED** in Task 4.
- `NBA_Predictor/frontend/src/components/GameSummaryPanel.tsx` — **DELETED** in Task 4.
- `F1_Predictor/src/f1_predictor/api/explain.py`, `NBA_Predictor/src/nba_predictor/api/explain.py` — **DELETED** in Task 4.
- Every site: `src/predictor-ui/` is vendored. Never hand-edit it; run `node scripts/sync-ui.mjs <site-src>` from `predictor-hub` and commit the result. `predictor-ui.sync.test.ts` must stay green in every site.

---

### Task 1: On demand only, and refuse the sports we do not serve

**This is first because budget is being spent right now on exactly what it
removes** (§13d). The scheduler pre-generates 72 hours across five sports,
including the two the redesign does not serve; that continues until this lands.
The refusal is here rather than in Task 2 because it is the same kind of change —
a boundary decision in the service — and because an `f1` or `nba` request
arriving between now and Task 4 should be a 404 from the first hour rather than
from the day the frontends are edited.

Nothing in Tasks 2–4 can block this, and it blocks nothing.

**Files:**
- Delete: `services/explainer/explainer/scheduler.py`
- Modify: `services/explainer/explainer/app.py:31` (the `run_forever` task)
- Modify: `services/explainer/explainer/config.py` — add `SERVED_SPORTS`
- Modify: `services/explainer/explainer/service.py::explain` — the refusal
- Modify: `services/explainer/README.md` (the pre-generation section)
- Create: `services/explainer/tests/test_no_pregeneration.py`
- Create: `services/explainer/tests/test_unserved_sport.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.SERVED_SPORTS = ("pl", "nfl", "cfb")`, and a `404` for any
  other sport. No later task depends on either; Tasks 2–4 simply stop having to
  remember that `f1` and `nba` exist.

- [ ] **Step 1: Write the failing test**

```python
"""No background pre-generation: a summary is made when a reader asks for one."""
import inspect

import pytest

from explainer import app as app_mod


def test_the_scheduler_module_is_gone():
    # Pre-generating 72 hours across five sports was the main budget consumer.
    # On demand it should be a fraction of that, and the cap is revisited from
    # real numbers rather than a guess.
    with pytest.raises(ModuleNotFoundError):
        import explainer.scheduler  # noqa: F401


def test_the_app_starts_no_pregeneration_task():
    source = inspect.getsource(app_mod)
    assert "run_forever" not in source and "pregenerate" not in source, (
        "the scheduler is still wired into the lifespan"
    )
```

- [ ] **Step 1b: Write the failing refusal test**

This moves here from where the draft plan had it. The point is not to lose it but
to land it early:

```python
"""f1 and nba are out of scope, and the service must refuse rather than answer."""
import pytest
from fastapi.testclient import TestClient

from conftest import make
from explainer.app import create_app


@pytest.mark.parametrize("sport", ["f1", "nba"])
def test_an_unserved_sport_is_a_404_not_a_template(tmp_path, sport):
    s = make(tmp_path, **{f"sport_api_{sport}": "http://x.test/api"})
    with TestClient(create_app(s)) as c:
        res = c.get(f"/explain/{sport}/2026-12-race")
    assert res.status_code == 404, (
        "a refusal must not look like an answer; a template here would render a "
        "panel and spend nothing, which reads as success"
    )


@pytest.mark.parametrize("sport", ["pl", "nfl", "cfb"])
def test_a_served_sport_is_not_refused_by_the_sport_check(tmp_path, sport):
    # The refusal must be about the sport, not about reachability. Without this
    # the guard could be "404 whenever the fetch fails" and pass everything above
    # while being wrong for every served sport.
    s = make(tmp_path, **{f"sport_api_{sport}": "http://x.test/api"})
    with TestClient(create_app(s)) as c:
        res = c.get(f"/explain/{sport}/g1")
    assert res.status_code == 502, f"expected an upstream failure, got {res.status_code}"
```

- [ ] **Step 2: Run both to verify they fail** (all four assertions fail today).

- [ ] **Step 3: Delete the module and its call site.** Remove the `run_forever` import and the `asyncio.create_task(...)` in the lifespan, and the `PUBLIC_SNAPSHOT`-adjacent comment above it.

- [ ] **Step 3b: Add the refusal.** In `config.py`:

```python
SERVED_SPORTS = ("pl", "nfl", "cfb")
```

and in `service.py::explain`, as the **first** line of the method:

```python
    async def explain(self, sport: str, id: str) -> dict:
        if sport not in SERVED_SPORTS:
            # Before the facts fetch and before any budget is touched. A refusal,
            # not a template: a template here would render a panel and look like
            # success while spending nothing.
            raise NotFound(f"{sport} is not served")
        facts = await self._facts(sport, id)
```

- [ ] **Step 4: Keep the cache and the cap.** Both stay. A second open of the same fixture is still free, which is the property that makes on-demand acceptable; and the daily cap is unchanged until real numbers exist.

- [ ] **Step 5: Fix the README** — the pre-generation section becomes on-demand, and the rollout checklist drops the pre-generation step while keeping "watch the daily cap".

- [ ] **Step 6: Run the full suite**, then measure and report: before/after requests per fixture view, so the saving is a number rather than an adjective.

- [ ] **Step 7: Commit** and open the PR.

---

### Task 2: The contract, the computed band, and the service speaking v2

No UI. This is the part everything else depends on and it is independently testable.

**Files:**
- Create: `services/explainer/explainer/contract.py`
- Create: `services/explainer/tests/test_contract.py`
- Create: `services/explainer/tests/test_validate_factors.py`
- Create: `services/explainer/tests/test_template_v2.py`
- Modify: `services/explainer/explainer/validate.py`
- Modify: `services/explainer/explainer/service.py:30` (`SECTION_KEYS`), `:51` (`_clean`), `:140` (`_generate`)
- Modify: `services/explainer/explainer/template.py:27` (`explain_from_template`)
- Modify: `services/explainer/explainer/config.py:25` (`prompt_version`), `:5` (`SPORTS`)
- Test: `services/explainer/tests/test_service.py` (existing — must stay green)

**Interfaces:**
- Consumes: nothing from later tasks.
- Produces:
  - `contract.VERDICT_BANDS: tuple[str, ...] == ("leaning", "moderate", "strong")`
  - `contract.DIRECTIONS: tuple[str, ...] == ("up", "down")`
  - `contract.band_for(prob: float | None, shape: str) -> str` — **the** band rule (§13a). One implementation, called by the service *and* the template.
  - `contract.market_shape(facts: dict) -> str` — `"two_way"` or `"three_way"`, read from the facts rather than from the sport's name.
  - `contract.clean_verdict(body: dict) -> dict` — returns `{"verdict": str, "factors": [{"key","direction","headline","text"}, ...]}`, coercing missing fields and dropping factors with no `key`. **It has no `band` key at all** — the band is not model input, so it is not in the contract and cannot be read off a model body.
  - `contract.resolve_factors(verdict: dict, facts: dict) -> list[dict]` — keeps only factors whose `key` is a market in `facts["markets"]` or one of the pseudo-markets `("record", "context")`. **Unknown key → drop the factor, never raise.**
  - `contract.market_keys(facts: dict) -> set[str]`

- [ ] **Step 1: Write the failing contract test**

Create `services/explainer/tests/test_contract.py`:

```python
"""The v2 shape, in one place, so the validator and the template cannot drift."""
import pytest

from explainer.contract import (DIRECTIONS, VERDICT_BANDS, band_for,
                                clean_verdict, market_keys, market_shape,
                                resolve_factors)

FACTS = {
    "sport": "nfl", "id": "g1", "title": "Chiefs at Ravens",
    "starts_at": "2026-10-05T00:20:00Z", "status": "upcoming",
    "pick_timing": "pre_kickoff", "pick": {"label": "BAL", "prob": 0.62},
    "markets": [{"market": "moneyline", "model": {"KC": 0.38, "BAL": 0.62}},
                {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"}],
    "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 68},
}


def test_the_bands_are_words_not_numbers():
    assert VERDICT_BANDS == ("leaning", "moderate", "strong")
    # A numeric band is a figure no fact supports, so the type is closed.
    assert all(b.isalpha() for b in VERDICT_BANDS)
    assert DIRECTIONS == ("up", "down")


def test_the_band_is_computed_from_the_probability_not_chosen():
    # 13a. A band is a function of pick.prob, so a 52% two-way pick cannot read
    # "strong" however confident the prose sounds. The thresholds are the ones
    # written in the spec, so this test fails if anyone retunes them silently.
    assert band_for(0.52, "two_way") == "moderate"
    assert band_for(0.61, "two_way") == "strong"
    assert band_for(0.51, "two_way") == "leaning"
    # A three-way market has no-edge at about 0.333, not 0.50, so the two-way
    # thresholds would call a 45% PL home win "leaning" and a 40% one "strong".
    assert band_for(0.52, "three_way") == "strong"
    assert band_for(0.45, "three_way") == "moderate"
    assert band_for(0.39, "three_way") == "leaning"


def test_no_probability_gives_the_weakest_band_not_the_middle_one():
    # There is no pick, so there is no confidence to claim. Defaulting to
    # "moderate" would be inventing one.
    assert band_for(None, "two_way") == "leaning"
    assert band_for(None, "three_way") == "leaning"


def test_the_shape_comes_from_the_facts_not_the_sports_name():
    assert market_shape(FACTS) == "two_way"          # NFL, a moneyline
    pl = dict(FACTS, sport="pl",
              markets=[{"market": "result", "model": {"H": 0.5, "D": 0.25, "A": 0.25}}])
    assert market_shape(pl) == "three_way"


def test_a_model_supplied_band_is_ignored_entirely():
    # The field is removed from the contract, but a model trained on the old
    # shape emits it anyway. Removing a field from a schema is not the same as
    # refusing to read it, and the second is what has to be tested.
    out = clean_verdict({"verdict": "v", "band": "strong", "factors": [
        {"key": "moneyline", "direction": "up", "headline": "h", "text": "t"}]})
    assert "band" not in out, "the model's band survived into the answer"


def test_clean_verdict_coerces_and_never_invents_a_key():
    out = clean_verdict({
        "verdict": "Baltimore is the pick.",
        "factors": [{"key": "spread", "direction": "up", "headline": "Line", "text": "Because."},
                    {"direction": "up", "headline": "No key", "text": "Dropped."}],
    })
    assert out["verdict"] == "Baltimore is the pick."
    assert [f["key"] for f in out["factors"]] == ["spread"], "a factor with no key survived"


def test_an_unknown_key_drops_the_factor_and_does_not_raise():
    out = clean_verdict({"verdict": "v", "factors": [
        {"key": "quarterback_weather", "direction": "up", "headline": "h", "text": "t"}]})
    assert out["factors"] == []


def test_resolve_keeps_only_keys_the_facts_actually_carry():
    verdict = clean_verdict({"verdict": "v", "factors": [
        {"key": "moneyline", "direction": "up", "headline": "h", "text": "t"},
        {"key": "record", "direction": "down", "headline": "h", "text": "t"},
        {"key": "total", "direction": "up", "headline": "h", "text": "t"}]})
    resolved = resolve_factors(verdict, FACTS)
    assert [f["key"] for f in resolved] == ["moneyline", "record"], (
        "total is not in these facts and must be dropped, not rendered as a dash")
    assert market_keys(FACTS) == {"moneyline", "spread"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd services/explainer && uv run --extra dev python -m pytest tests/test_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'explainer.contract'`

- [ ] **Step 3: Write `contract.py`**

```python
"""The v2 answer shape, defined once.

The model supplies words and ordering; it never supplies a number the panel
renders, and — per spec §13a — not the confidence band either. So a factor is a
*reference* to a market plus a direction, and the resolution of that reference
against the facts happens here: the one place that knows both vocabularies. An
unknown key drops the factor rather than raising, because a model inventing a
market name is a reason to show less, not to fail the reader's request.

The band is here for the same reason. §5a argued a band must not be a number;
it missed that a *word* is the same defect with less checking, since nothing ties
"strong" to anything and a model can call a 52% pick strong. So the band is
computed from `pick.prob` by `band_for`, and the model is not asked for one.
"""
from __future__ import annotations

VERDICT_BANDS = ("leaning", "moderate", "strong")
DIRECTIONS = ("up", "down")
#: Markets that are not in `facts["markets"]` but are still real things to
#: point a factor at.
PSEUDO_MARKETS = ("record", "context")

#: The band thresholds from §13a. Two-way and three-way differ because no-edge
#: is 0.50 when there are two outcomes and about 0.333 when there are three.
#: One table, one caller-pair; a second hand-written copy is how the model path
#: and the template path would drift, and drift there is what §8 forbids.
BAND_THRESHOLDS = {
    "two_way": {"strong": 0.60, "moderate": 0.52},
    "three_way": {"strong": 0.50, "moderate": 0.40},
}


def band_for(prob, shape: str) -> str:
    """The confidence word, derived. Never asked of the model.

    `prob` of `None` means there is no pick, so there is no confidence to
    claim: the weakest word, and the panel says there is no pick.
    """
    if prob is None:
        return "leaning"
    limits = BAND_THRESHOLDS[shape]
    if prob >= limits["strong"]:
        return "strong"
    if prob >= limits["moderate"]:
        return "moderate"
    return "leaning"


def market_keys(facts: dict) -> set[str]:
    return {str(m.get("market")) for m in (facts.get("markets") or []) if m.get("market")}


def market_shape(facts: dict) -> str:
    """Whether the pick's market has two outcomes or three.

    Read from the facts rather than keyed on the sport, so a sport added later
    is classified by its own market and cannot be given the wrong thresholds by
    forgetting to update a list.
    """
    return "two_way" if "moneyline" in market_keys(facts) else "three_way"


def _factors(body: dict) -> list[dict]:
    out = []
    for f in body.get("factors") or []:
        if not isinstance(f, dict):
            continue
        key = str(f.get("key") or "").strip()
        if not key:
            continue
        out.append({
            "key": key,
            "direction": f.get("direction") if f.get("direction") in DIRECTIONS else "up",
            "headline": str(f.get("headline") or ""),
            "text": str(f.get("text") or ""),
        })
    return out


def clean_verdict(body: dict) -> dict:
    """No `band` key, deliberately: the model does not supply one (§13a).

    A body that carries a `band` anyway is not rejected — rejecting would turn a
    cosmetic extra key into a failed reader's request — it is simply not read.
    `test_a_model_supplied_band_is_ignored_entirely` covers that.
    """
    return {
        "verdict": str(body.get("verdict") or "").strip(),
        "factors": _factors(body),
    }


def resolve_factors(verdict: dict, facts: dict) -> list[dict]:
    """Keep only the factors whose key names something the facts actually carry."""
    allowed = market_keys(facts) | set(PSEUDO_MARKETS)
    return [f for f in verdict.get("factors") or [] if f.get("key") in allowed]
```

- [ ] **Step 4: Run the contract test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_contract.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 5: Write the failing validator test for factors**

Create `services/explainer/tests/test_validate_factors.py`:

```python
"""validate() must police the v2 shape, not just prose numbers."""
import json

import pytest

from explainer.validate import validate

FACTS = {
    "sport": "nfl", "id": "g1", "title": "Chiefs at Ravens",
    "starts_at": "2026-10-05T00:20:00Z", "status": "final",
    "pick_timing": "pre_kickoff", "pick": {"label": "BAL", "prob": 0.62},
    "markets": [{"market": "moneyline", "model": {"KC": 0.38, "BAL": 0.62}}],
}
F = json.dumps(FACTS)


def _v(factors, verdict="Baltimore is the pick."):
    return {"verdict": verdict, "factors": factors}


def _f(key="moneyline", direction="up", headline="Model leans Baltimore", text="The gap has held."):
    return {"key": key, "direction": direction, "headline": headline, "text": text}


def test_a_clean_verdict_passes():
    assert validate(_v([_f(), _f("record", "down")]), F, "[]") == []


@pytest.mark.parametrize("n", [0, 1, 5, 6])
def test_the_factor_count_is_two_to_four(n):
    problems = validate(_v([_f() for _ in range(n)]), F, "[]")
    assert any("factors" in p for p in problems), f"{n} factors was accepted: {problems}"


def test_the_band_is_not_part_of_the_model_contract():
    # There is deliberately no band test here, because the model does not supply
    # one (§13a). `validate()` is not the place to police a field that is not in
    # the contract — `contract.band_for` computes it. A body carrying a band is
    # simply not read, and this asserts that it changes nothing.
    with_band = {"verdict": "v", "band": "strong",
                 "factors": [_f(), _f("record")]}
    assert validate(with_band, F, "[]") == validate(_v([_f(), _f("record")]), F, "[]"), (
        "a model-supplied band changed the verdict, so something is still reading it"
    )


def test_a_direction_must_be_up_or_down():
    body = _v([_f(direction="sideways"), _f("record")])
    assert validate(body, F, "[]"), "an unknown direction passed"


def test_a_factor_whose_key_is_not_in_the_facts_is_rejected():
    # The service drops these, so reaching here means the drop was bypassed.
    body = _v([_f(key="pitching_weather"), _f("record")])
    assert validate(body, F, "[]"), "a factor naming a market the facts lack passed"


def test_a_factor_text_may_not_carry_its_own_number():
    # The panel renders figures from the facts, so a figure in a factor is one
    # the layout has no slot for — and it is the route by which a model-supplied
    # number could reach a reader.
    body = _v([_f(text="The gap is 71%."), _f("record")])
    problems = validate(body, F, "[]")
    assert any("71" in p for p in problems), f"a number in a factor passed: {problems}"
```

- [ ] **Step 6: Run it to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_validate_factors.py -q`
Expected: FAIL — the current `validate()` requires `sections`, so it returns `["output must be {headline: str, sections: ...}"]` for every case, and the count/band/direction assertions cannot be reached.

- [ ] **Step 7: Extend `validate()` for v2**

In `explainer/validate.py`, add above `validate()`:

```python
from .contract import DIRECTIONS, PSEUDO_MARKETS, market_keys

MAX_FACTORS = 4
MIN_FACTORS = 2
```

and inside `validate()`, replace the shape check at the top with:

```python
    factors = output.get("factors") if isinstance(output, dict) else None
    verdict = output.get("verdict") if isinstance(output, dict) else None
    if not isinstance(verdict, str) or not isinstance(factors, list) \
            or not all(isinstance(f, dict) for f in factors):
        return ["output must be {verdict: str, factors: [{key, direction, headline, text}]}"]
```

and replace the per-section length loop with:

```python
    if not MIN_FACTORS <= len(factors) <= MAX_FACTORS:
        problems.append(f"needs {MIN_FACTORS}-{MAX_FACTORS} factors, got {len(factors)}")
    # No band check: the band is computed by contract.band_for, not supplied.
    # Validating a field nothing writes would be a test that cannot fail.
    allowed = market_keys(facts) | set(PSEUDO_MARKETS)
    for i, f in enumerate(factors):
        if f.get("direction") not in DIRECTIONS:
            problems.append(f"factor {i + 1} direction must be one of {DIRECTIONS}")
        if f.get("key") not in allowed:
            problems.append(f"factor {i + 1} names {f.get('key')!r}, which the facts do not carry")
        for part in ("headline", "text"):
            if len(str(f.get(part, "")).split()) > 20:
                problems.append(f"factor {i + 1} {part} is over 20 words")
```

`facts` is loaded later in the function than the shape check, so move the `facts = json.loads(facts_json)` line **above** the shape check and delete the later duplicate.

The number pool becomes:

```python
    texts = [verdict] + [str(f.get("headline", "")) for f in factors] \
        + [str(f.get("text", "")) for f in factors]
    body = " ".join(texts)
```

Keep the banned-word scan, the `_pool` number check, the rebuilt-disclosure check and the `_verdict_problems(facts, body)` call exactly as they are. **The word-count rules change** — there is no 120–220-word body any more, so delete the `total` range check and the 60-word section cap; a v2 body is short by construction.

- [ ] **Step 8: Run the validator tests**

Run: `uv run --extra dev python -m pytest tests/test_validate_factors.py tests/test_validate_verdict.py -q`
Expected: PASS. The verdict tests from the earlier Critical must still pass — if they now fail on the shape check, `_body()` in `test_validate_verdict.py` must be updated to build a v2 body, keeping the control-body assertion that isolates the verdict rule.

- [ ] **Step 9: Make the template emit v2**

In `explainer/template.py`, replace `explain_from_template`'s return with a v2 verdict built from the facts alone. The template is not prose-with-a-shape-change: it resolves the same market keys the panel renders, so both paths drive identical layout.

```python
def explain_from_template(facts: dict) -> dict:
    """The no-model path, in the SAME shape as the model's, built from the facts.

    Layout is data-driven, so this and the model path reach the same panel
    through one renderer. The only difference a reader can see is the footer.
    """
    from .contract import band_for, market_keys, market_shape

    keys = market_keys(facts)
    pick = facts.get("pick") or {}
    factors: list[dict] = []
    if "moneyline" in keys or "result" in keys:
        factors.append({"key": "moneyline" if "moneyline" in keys else "result",
                        "direction": "up",
                        "headline": "The model likes this one",
                        "text": "Its numbers favour the pick it made."})
    if "spread" in keys:
        factors.append({"key": "spread", "direction": "down",
                        "headline": "The line asks more than the model",
                        "text": "The market is asking for more than the model rates the gap."})
    if len(factors) < 2 and "record" in facts:
        factors.append({"key": "record", "direction": "up",
                        "headline": "Its record so far",
                        "text": "Counted from picks made before the start."})
    # The one band function, not a second hand-written threshold table. The
    # draft of this plan carried a private `>= 0.6 / < 0.45` ladder here, which
    # is precisely the drift §8 forbids: two paths, two rules, and no test that
    # could notice until a reader saw the wrong word on the wrong side.
    band = band_for(pick.get("prob"), market_shape(facts))
    verdict = (f"{pick['label']} is the pick." if pick
               else "There is no pick for this one yet.")
    return {"verdict": verdict, "band": band, "factors": factors[:4]}
```

- [ ] **Step 10: Write the failing template parity test**

Create `services/explainer/tests/test_template_v2.py`:

```python
"""The template and the model must reach the panel through one shape."""
from explainer.contract import band_for, market_shape, resolve_factors
from explainer.template import explain_from_template

FACTS = {
    "sport": "nfl", "id": "g1", "title": "Chiefs at Ravens",
    "starts_at": "2026-10-05T00:20:00Z", "status": "upcoming",
    "pick_timing": "pre_kickoff", "pick": {"label": "BAL", "prob": 0.62},
    "markets": [{"market": "moneyline", "model": {"KC": 0.38, "BAL": 0.62}},
                {"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"}],
    "record": {"label": "Picks made before kickoff", "hits": 41, "settled": 68},
}


def test_the_template_emits_the_v2_shape():
    out = explain_from_template(FACTS)
    assert set(out) == {"verdict", "band", "factors"}
    assert out["band"] in ("leaning", "moderate", "strong")
    assert 2 <= len(out["factors"]) <= 4


def test_the_template_band_comes_from_the_one_function():
    # Across the whole range, not just this fixture: a template with its own
    # ladder passes any single-probability assertion and still drifts.
    for prob in (0.0, 0.39, 0.40, 0.45, 0.51, 0.52, 0.60, 0.61, 0.99, None):
        facts = dict(FACTS, pick={"label": "BAL", "prob": prob})
        assert explain_from_template(facts)["band"] == band_for(prob, "two_way"), (
            f"the template's band diverged from band_for at prob={prob}")


def test_a_three_way_facts_bundle_gets_the_three_way_thresholds():
    pl = dict(FACTS, sport="pl", pick={"label": "Home", "prob": 0.45},
              markets=[{"market": "result", "model": {"H": 0.45, "D": 0.27, "A": 0.28}}])
    assert explain_from_template(pl)["band"] == band_for(0.45, "three_way") == "moderate"


def test_every_template_factor_resolves_against_the_facts():
    # The point of the whole design: the template cannot produce a key the
    # panel would have to render as a dash, because it reads the same keys.
    out = explain_from_template(FACTS)
    assert len(resolve_factors(out, FACTS)) == len(out["factors"])


def test_the_template_states_no_derived_percentage():
    # record is hits/settled; the proportion is the bar's width, not a figure.
    blob = out_text(explain_from_template(FACTS))
    assert "60.3" not in blob and "60%" not in blob


def out_text(v):
    return " ".join([v["verdict"]] + [f["headline"] + " " + f["text"] for f in v["factors"]])
```

- [ ] **Step 11: Run it, then make the service and config speak v2**

Run the test first (expect FAIL until `explain_from_template` is replaced), then:

`explainer/config.py`:
```python
```
(SERVED_SPORTS and the refusal already landed in Task 1; nothing to add here.)

and change `prompt_version: str = "v1"` to `"v2"`. A new version means a new cache key, so v1 rows holding `headline`/`sections` are never read by a v2 renderer.

`explainer/service.py`:
```python
SECTION_KEYS = ("market", "title", "text")   # DELETE this line
```
```python
def _clean(body: dict) -> dict:
    """v2 has one shape, and the cache key covers the facts, so a v1 row can
    never reach this renderer. Assert it rather than trust the version bump:
    a reused version must fail loudly, not render an empty panel."""
    if not isinstance(body.get("verdict"), str) or not isinstance(body.get("factors"), list):
        raise ValueError(f"cached body is not a v2 verdict: {sorted(body)}")
    return clean_verdict(body)
```
and in `_generate`, replace `return _clean(out), "llm", model` with
`return _clean(out), "llm", model` unchanged, and change the final
`body = explain_from_template(facts.model_dump())` to stay as is.

`_answer` gains exactly one line, and it is the only place the response's band is
decided:

```python
# alongside the existing **row["body"] spread in _answer
"band": band_for((facts.get("pick") or {}).get("prob"), market_shape(facts)),
```

Unconditional, so it overwrites the template path's band with the same value
rather than trusting it. The template computes its own band for callers that use
it standalone; the response's band always comes from this one call. That is what
makes "the two paths cannot disagree about confidence" a property of the code
rather than a promise in a docstring — and the parity test in Step 10 proves it
for a range of probabilities, not one fixture.

**A test that the model's band is ignored end to end**, in
`tests/test_service.py`, beside the other honesty tests:

```python
async def test_a_confident_model_cannot_promote_a_52_percent_pick(...):
    # 13a. The model returns "strong"; the facts say 0.52 on a two-way market.
    # The response must say "moderate".
    out = await explainer.explain("nfl", "g1")     # with a mocked 0.52 pick
    assert out["band"] == "moderate", (
        "a model-supplied band reached the response; nothing should be reading it"
    )
```

This is the deliberately-broken input for the band rule, and it is the one that
matters: every other guard in this plan is proven by deleting the check, and
this one is proven by a model actively trying to inflate its own confidence.

- [ ] **Step 12: Run the whole service suite**

Run: `uv run --extra dev python -m pytest -q`
Expected: PASS. `test_service.py` will fail — it builds v1 bodies via `conftest.good()`. Update `conftest.good()` to return a v2 body and keep the same `headline` key working by renaming it to `verdict`; then fix the assertions that read `out["headline"]` to read `out["verdict"]`. Do not weaken those tests: they are the ones that prove the cache and the honesty plumbing still work.

- [ ] **Step 13: Prove the new validator and the band rule are load-bearing**

Run, and confirm each fails:
```bash
uv run --extra dev python -m pytest tests/test_validate_factors.py tests/test_contract.py -q
# then delete the factor-count check: the parametrised count test must fail
# then delete the key check: test_a_factor_whose_key_is_not_in_the_facts_is_rejected must fail
# then make band_for ignore its `shape` argument and always use two_way:
#   test_the_shape_comes_from_the_facts_not_the_sports_name and
#   test_a_three_way_facts_bundle_gets_the_three_way_thresholds must fail
# then make band_for return "moderate" for None: test_no_probability_gives_the_weakest_band must fail
# then read the model's band in _clean: test_a_model_supplied_band_is_ignored_entirely must fail
```

A guard that cannot fail is not a guard; four of this project's shipped guards
could. The last two matter more than the rest: they are the difference between a
band that is *derived* and one that merely *looks* derived.

- [ ] **Step 14: Commit**

```bash
cd predictor-hub
git add services/explainer
git commit -m "feat(explainer): the v2 contract, its rules, and the template that matches

The model stops supplying numbers. It returns a verdict, a named band, and
factors that REFERENCE a market by key; the panel resolves those against the
facts and renders the figures. A template and a model answer now reach the
panel through one shape, so the default is as good as the model by
construction rather than by effort.

prompt_version goes to v2 so no v1 row is ever read by this renderer, and
_clean() raises on a non-v2 body rather than rendering an empty panel if that
version is ever reused. f1 and nba are refused before the facts fetch and
before any budget is touched.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The shared components, template path first

**Files:**
- Create: `packages/predictor-ui/src/components/ExplainerVerdict.tsx`
- Create: `packages/predictor-ui/src/components/KeyNumberTile.tsx`
- Create: `packages/predictor-ui/src/components/ProbabilitySplit.tsx`
- Create: `packages/predictor-ui/src/components/FactorList.tsx`
- Create: `packages/predictor-ui/src/components/RecordStrip.tsx`
- Create: `packages/predictor-ui/src/components/explainerV2.test.tsx`
- Modify: `packages/predictor-ui/src/components/ExplainerPanel.tsx`
- Modify: `packages/predictor-ui/src/index.ts`

**Interfaces:**
- Consumes: the v2 answer from Task 2, over the wire as `verdict`, `factors`, and `band` alongside `source`, `model`, `generated_at`, `sport`, `pick_timing`. **The panel treats `band` as computed** — it renders the word it is given and never recomputes one, because the thresholds are the service's (§13a) and a second copy in TypeScript is a second thing to keep right.
- Produces:
  - `export type Verdict = { verdict: string; band: "leaning"|"moderate"|"strong"; factors: {key: string; direction: "up"|"down"; headline: string; text: string}[] }`
  - `export type MarketTile = { market: string; label: string; value: string; line?: string }`
  - `export type Segment = { label: string; share: number; market?: string }` — `market` is the `key` a factor may reference, which is what makes the §13c highlight a lookup rather than a second naming scheme.
  - `KeyNumberTile({ tile, highlighted }: { tile: MarketTile; highlighted?: boolean })`
  - `ProbabilitySplit({ segments, caption, compare, minSegmentPx, highlightedKey, onSegmentFocus }: {...})` — the last two drive the §13c highlight and the focus/tap label.
  - `FactorList({ factors, expanded, onToggle, highlightedKey }: {...})` — each row is a real `<button>` (§13c), not a `div` with `onClick`.
  - `RecordStrip({ label, hits, settled }: { label: string; hits: number | null; settled: number })`
  - `ExplainerPanel({ data, loading, error, onRetry, collapsed, moment, tiles, segments, compare, record })` — the first six are today's props; the last four are new and optional so a caller with nothing to show still renders. The panel owns the highlight state, because the linkage is a property of the panel, not of either end.

**The one state this task adds** is `highlightedKey: string | null`, held by `ExplainerPanel` and passed down. It is derived from a factor's `key`, so it can only ever name a market the facts already carry.

- [ ] **Step 1: Write the failing component tests**

Create `packages/predictor-ui/src/components/explainerV2.test.tsx`. Cover, at minimum:

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExplainerPanel, KeyNumberTile, ProbabilitySplit, RecordStrip, FactorList } from "./index";
import type { Explanation, MarketTile, Segment } from "./index";

// Built with the values the facts carry — the same `market` keys the /facts
// bundles use, so a rename on either side fails here rather than in a browser.
const NFL: Explanation = {
  verdict: "Baltimore is the pick, but the line is thinner than the number.",
  band: "moderate",
  factors: [
    { key: "moneyline", direction: "up", headline: "Model leans Baltimore",
      text: "The rating gap has held all week and the model has not moved off it." },
    { key: "spread", direction: "down", headline: "The line asks more than the margin",
      text: "The market is asking for more than the model thinks the gap is worth." },
  ],
  source: "llm", model: "nemotron-3.5-lightning", generated_at: new Date().toISOString(),
  sport: "nfl", pick_timing: "pre_kickoff",
};

const TILES: MarketTile[] = [
  { market: "moneyline", label: "Moneyline", value: "62%", line: "market 55%" },
  { market: "spread", label: "Spread", value: "BAL \u22122.5", line: "model \u22123.4" },
];

const SEGMENTS: Segment[] = [
  { label: "KC", share: 0.38, market: "moneyline" },
  { label: "BAL", share: 0.62, market: "spread" },
];

describe("KeyNumberTile", () => {
  it("shows the model's figure large and the market's line beneath", () => {
    render(<KeyNumberTile tile={{ market: "spread", label: "Spread", value: "BAL −2.5", line: "model −3.4" }} />);
    expect(screen.getByText("BAL −2.5")).toBeInTheDocument();
    expect(screen.getByText("model −3.4")).toBeInTheDocument();
  });
  it("renders nothing for an absent value rather than a dash or a zero", () => {
    const { container } = render(<KeyNumberTile tile={{ market: "x", label: "X", value: "" }} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("ProbabilitySplit", () => {
  it("carries the same numbers in words for a screen reader", () => {
    render(<ProbabilitySplit caption="model" segments={[{ label: "KC", share: 0.38 }, { label: "BAL", share: 0.62 }]} />);
    expect(screen.getByRole("img", { name: /KC 38%|BAL 62%/ })).toBeInTheDocument();
  });
  it("renders a 3% segment as a sliver rather than vanishing", () => {
    const { container } = render(<ProbabilitySplit caption="model" minSegmentPx={2}
      segments={[{ label: "A", share: 0.97 }, { label: "B", share: 0.03 }]} />);
    const widths = [...container.querySelectorAll("[data-segment]")].map((e) => e.getAttribute("style"));
    expect(widths.some((s) => s?.includes("2px") || s?.includes("width: 2"))).toBe(true);
  });
  it("honours prefers-reduced-motion", () => {
    // assert no transition/animation is applied — the bar must not animate for
    // a reader who asked for less motion
  });
});

describe("RecordStrip", () => {
  it("states n / n and never a percentage the facts do not contain", () => {
    render(<RecordStrip label="Picks made before kickoff" hits={41} settled={68} />);
    expect(screen.getByText("41 / 68")).toBeInTheDocument();
    expect(screen.queryByText(/60\.3|60%/)).toBeNull();
  });
  it("shows an em dash when hits is unknown", () => {
    render(<RecordStrip label="r" hits={null} settled={0} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});

describe("FactorList", () => {
  it("never carries the direction by colour alone", () => {
    const { container } = render(<FactorList factors={NFL.factors} />);
    expect(container.querySelectorAll("[data-direction]")).toHaveLength(2);
    expect(screen.getByText(/for the pick/i)).toBeInTheDocument();
  });

  // 13c, and the second half of each of the three affordances: reachable and
  // operable by keyboard alone. That is the assertion which catches a div with
  // an onClick, and it is the one that has to be written or the affordance will
  // ship mouse-only while the test suite is green.
  it("is a real button, so it is reachable and operable by keyboard", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<FactorList factors={NFL.factors} onToggle={onToggle} />);
    const first = screen.getByRole("button", { name: /model leans baltimore/i });
    expect(first.tagName).toBe("BUTTON");
    first.focus();
    await user.keyboard("{Enter}");
    expect(onToggle).toHaveBeenCalledWith(0);
  });
});

describe("the factor-to-figure linkage (13c)", () => {
  it("highlights the tile and the segment whose market the factor names", async () => {
    const user = userEvent.setup();
    render(<ExplainerPanel data={NFL} tiles={TILES} segments={SEGMENTS} />);
    await user.click(screen.getByRole("button", { name: /the line asks more/i }));
    expect(screen.getByTestId("tile-spread")).toHaveAttribute("data-highlighted", "true");
    expect(screen.getByTestId("segment-BAL")).toHaveAttribute("data-highlighted", "true");
  });

  it("reveals no figure the facts do not carry", async () => {
    // The named failure for this feature: a hover tooltip reading
    // "probably around 55-60%". Nothing may compute, round or interpolate.
    const user = userEvent.setup();
    render(<ExplainerPanel data={NFL} tiles={TILES} segments={SEGMENTS} />);
    await user.click(screen.getByRole("button", { name: /the line asks more/i }));
    expect(document.body.textContent).not.toMatch(/\b\d+\s*[-\u2013]\s*\d+\s*%/);
  });

  it("shows a narrow segment its label on focus, never by shrinking it", async () => {
    const user = userEvent.setup();
    render(<ProbabilitySplit caption="model" segments={[{ label: "A", share: 0.97, market: "moneyline" },
                                                       { label: "B", share: 0.03, market: "total" }]} />);
    const seg = screen.getByTestId("segment-B");
    await user.tab();
    expect(seg).toHaveFocus();
    expect(seg).toHaveTextContent(/3%/);          // the fact's own figure, in words
    expect(seg).toHaveAttribute("data-min-width", "2px");   // and still a sliver
  });

  it("does not animate anything under prefers-reduced-motion", () => {
    // Render with the media query matched and assert no transition is applied.
    // A highlight that slides is a problem for a reader who asked for less
    // motion, and it is invisible to every other test in this file.
  });
});
```

- [ ] **Step 2: Run them to verify they fail**

Run: `cd packages/predictor-ui && npx vitest run src/components/explainerV2.test.tsx`
Expected: FAIL — the components do not exist and `Explanation` has no `verdict`.

- [ ] **Step 3: Implement the four components**

Each is small and single-purpose. Rules that are not negotiable, from spec §6a–§6c:

- `KeyNumberTile` returns `null` when `value` is empty. No dash, no zero.
- `ProbabilitySplit` is `role="img"` with an `aria-label` built from the segments ("KC 38%, BAL 62%"). Widths are percentages of the container, with a `minSegmentPx` floor applied via `min-width` so a 3% slice still renders. The bar animates its widths once, 240ms ease-out, from a visible default — and **only** under `@media (prefers-reduced-motion: no-preference)`.
- `FactorList` renders the direction as a glyph **and** the words "for the pick" / "against it", so the meaning survives with no colour and no glyph. The glyph is `aria-hidden`.
- `RecordStrip` renders `hits` and `settled` as text and the proportion as bar geometry. It never computes or prints a percentage.
- **The `compare` row (§13b) renders only when it covers every outcome `segments` has.** `ProbabilitySplit` compares its two lists by label and, if any label in `segments` is missing from `compare`, it omits the second row entirely. It does not render the row with a gap, and it does not derive the missing share by subtraction. The caller does not get to opt out of this: a partial comparison is a comparison the reader cannot make, and the component is the only place that can know.
- **Every affordance is a real interactive element** (§13c): a factor row is a `<button>` with the direction and headline as its accessible name; a bar segment is a focusable `<button>` whose accessible name is the same figures the bar's own `aria-label` carries. No `div` with `onClick`, no `onMouseEnter` as the only route to anything.
- **No affordance may reveal a figure the facts do not carry** (§13c). Each shows a label, a highlight, or geometry the facts already supply. Nothing computes, rounds, interpolates or estimates — and the test asserting it is a negative assertion on the rendered text, because that is the only shape a "probably around 55-60%" failure takes.
- Highlights cross-fade over 120ms, and every transition is inside
  `@media (prefers-reduced-motion: no-preference)`. Under `reduce`, the highlight
  appears instantly and the expansion is not animated.
- Every one uses the existing family tokens only: `--font-pr-display`, `--font-pr-body`, `--pr-accent`, `--pr-text-dim`, `--pr-text-faint`, `--pr-rule`, `--pr-panel`. **No new colours and no new typefaces.**
- 12px floor on all text. §6a's reason still holds: a 3% segment has no room for an in-place label, so the label goes in a legend or on focus — never shrunk below the floor.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/components/explainerV2.test.tsx`
Expected: PASS.

- [ ] **Step 5: Verify the components are not using the detector's banned defaults**

Run: `impeccable detect --json src` and expect `[]`. The floor refuses gradient text, glass-as-decoration, a coloured border above 1px on a card, and monospace as a costume; the tiles and bars must not reintroduce any of them.

- [ ] **Step 6: Rewrite `ExplainerPanel` to compose them**

Replace the `sections` loop with the composed layout from spec §6: verdict line, tiles, split bar, factor rows, record strip, footer. Keep all of today's behaviour that is still required:

- the **footer fails closed** — model-written text only when `source === "llm"` and a model and a readable `generated_at`; `ago()` unchanged;
- the **rebuilt status** outside the collapsible region, with `StatusBadge` and the existing `STARTED[when]` sentence;
- the **collapse toggle** for F1's callers with `aria-expanded` (F1's own pages still use this panel until Task 4 removes them, so it must not break in between);
- `useId()` for the heading, so two panels on a page do not collide.

The `data` prop keeps its name and gains the v2 fields; `Explanation` becomes today's type plus `verdict`, `band`, `factors`. The four new props (`tiles`, `segments`, `compare`, `record`) are optional.

**The panel owns `highlightedKey`** (§13c), because the linkage is a property of
the panel and not of either end — a factor and a tile cannot highlight each
other without something holding the state between them:

```tsx
const [highlightedKey, setHighlightedKey] = useState<string | null>(null);
// FactorList onToggle -> setHighlightedKey(factors[i].key), and the expanded set
// cleared on the same toggle so one press does not both expand and highlight.
```

Three properties this state must have, each with a test:

- it can only hold a `key` a factor already named, so it cannot highlight a
  figure the facts lack;
- clearing it restores the resting state — a highlight that cannot be dismissed
  is a stuck state, and Escape does that;
- **hover and focus set it, click toggles it**, so a pointer user and a keyboard
  user reach the same result by different means. Hover is a convenience, never
  the only route.

`band` is rendered as given and never recomputed here. The thresholds are the
service's (§13a), and a second copy in TypeScript is a second thing to keep
right for no benefit.

- [ ] **Step 7: Run the whole package suite and typecheck**

Run: `npx vitest run && npx tsc --noEmit -p .`
Expected: PASS. `explainer.test.tsx` will fail — it builds v1 bodies. Update its fixtures to v2, and **keep its existing assertions**, especially "the template footer claims nothing" and the `MOMENT_OF` mapping test. Those are the honesty assertions; do not relax them to make the suite green.

- [ ] **Step 8: Prove the honesty footer still fails closed**

Temporarily set `source: "llm"` with `model: ""` on a fixture and confirm the rendered text contains no `\bAI\b`; then set `generated_at: "not-a-date"` and confirm the same. Both must fall back to the template sentence. Restore the fixtures.

- [ ] **Step 9: Commit**

```bash
cd predictor-hub
git add packages/predictor-ui
git commit -m "feat(predictor-ui): the v2 panel — tiles, a split bar, factor rows

Every figure on screen is rendered from the facts the caller passes in; the
components take no number from the verdict. RecordStrip states n / n and lets
the bar carry the proportion, because record is hits/settled and a percentage
would be a figure no fact contains.

Template parity is structural: the layout is driven by the data the caller
passes, not by whether a model was involved, so there is one renderer.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Wire it in, and take it out of F1 and NBA

One PR per repo. NFL and CFB are served by the **Sports_Predictor** frontend, so that is a single PR covering both sports.

**Files:**
- Modify: `Sports_Predictor/src/components/GameDetailModal.tsx`
- Modify: `PL_Predictor/frontend/src/components/FixtureSummaryPanel.tsx`
- Delete: `F1_Predictor/frontend/src/components/SessionSummaryPanel.tsx` and its usages
- Delete: `NBA_Predictor/frontend/src/components/GameSummaryPanel.tsx` and its usages
- Delete: `F1_Predictor/src/f1_predictor/api/explain.py`, `NBA_Predictor/src/nba_predictor/api/explain.py`
- Each site: re-vendor `src/predictor-ui/` with `node scripts/sync-ui.mjs <site-src>` and keep `predictor-ui.sync.test.ts` green

**Interfaces:**
- Consumes: `ExplainerPanel` and the four new components from Task 2.
- Produces: nothing new; this task only connects and removes.

- [ ] **Step 1: Map the tiles and segments per sport, in a test first**

In `Sports_Predictor`, write the mapping test before the mapping code. The facts shapes are fixed and were verified against the real bundles:

```tsx
// NFL: markets[].market is moneyline | spread | total
//   moneyline -> { model: {KC: 0.38, BAL: 0.62} }   two segments
//   spread    -> { model_margin: 3.4, line: "BAL -2.5", model_cover_prob?: 0.58 }
//   total     -> { model_total: 45.2, line: 44.5 }
// PL: markets[].market is result | total_goals | btts
//   result      -> { model: {home_win, draw, away_win}, implied?, edge? }  THREE segments
//   total_goals -> { model_total, over_2_5?, under_2_5? }
//   btts        -> { yes_prob }
```

Assert: a two-way split for NFL, a **three-way** split for PL with the draw as its own segment, a second hairline row when `implied` is present, and **no tile at all** for a market the facts lack.

And assert the three cases §13b is about, because the draft plan's "when
`implied` is present" reads as satisfiable and is not — PL's `implied` covers
only the two sides, so the row would sit under a three-way split with the draw
segment above nothing:

```tsx
it("omits the market row for a three-way split with no implied.draw", () => {
  // Real PL shape: implied has home and away, no draw.
  const out = mapPL({ result: { model: { home_win: 0.45, draw: 0.27, away_win: 0.28 },
                                 implied: { home_win: 0.42, away_win: 0.44 } } });
  expect(out.compare).toBeUndefined();
});

it("renders the market row once implied covers all three outcomes", () => {
  const out = mapPL({ result: { model: { home_win: 0.45, draw: 0.27, away_win: 0.28 },
                                 implied: { home_win: 0.42, draw: 0.25, away_win: 0.44 } } });
  expect(out.compare).toHaveLength(3);
});

it("never derives a draw probability to fill the gap", () => {
  // 0.42 + 0.44 = 0.86, so subtraction "works". It is still wrong: it assumes
  // the overround is spread across all three outcomes, and different books
  // spread it differently. The honest answer is to show nothing.
  const out = mapPL({ result: { model: { home_win: 0.45, draw: 0.27, away_win: 0.28 },
                                 implied: { home_win: 0.42, away_win: 0.44 } } });
  expect(out.compare?.find((s) => s.label === /draw/i)).toBeUndefined();
});
```

The tile's market line follows the same rule: `implied` is stated **for a side
that is present**, and omitted when the side it would name has no `implied`. A
draw pick with no `implied.draw` gets no market line at all.

- [ ] **Step 2: Run it to verify it fails**, then implement the mapping.

- [ ] **Step 3: Wire `GameDetailModal`** (NFL and CFB) and `FixtureSummaryPanel` (PL) to the v2 panel, passing the tiles/segments/record built from the facts the site already fetches.

- [ ] **Step 4: Prove the panel never gates the detail**

Each site's existing "hanging request" test must still pass: a promise that never resolves, and the fixture heading still arrives. If a site's suite lacks that test, **add it** — it is the regression this feature is most likely to cause.

- [ ] **Step 5: Remove the panel from F1 and NBA, and delete both proxies**

Delete the panel components, every usage, and `api/explain.py` in both. A dead proxy is worse than none: it is an endpoint that looks supported and 404s from the wrong layer.

- [ ] **Step 6: Run each repo's full suite and typecheck**

```bash
# Sports_Predictor
npx vitest run && npx tsc -b && impeccable detect --json src        # expect []
# PL_Predictor
cd frontend && npx vitest run && npx tsc --noEmit -p tsconfig.app.json
# F1_Predictor
cd frontend && npx vitest run && npx tsc --noEmit -p tsconfig.app.json
# NBA_Predictor — its typecheck is `tsc -b`; it has no tsconfig.app.json
cd frontend && npx vitest run && npx tsc -b
```

Plus each repo's pytest, using the venv interpreter: `PYTHONPATH=src uv run --extra dev python -m pytest -q`. NFL and CFB need Python 3.11 (they pin pandas 1.5.3, which has no cp312+ wheel). F1: `--ignore=tests/test_openf1.py` (needs network).

- [ ] **Step 7: Open one PR per repo**, describing the sport's tile/segment mapping and the two removals.

---

## Self-Review

**Spec coverage, with §13 included.** §2 honesty rules 1–4 → Task 2 (the stored
record and the pre-kickoff rule are already enforced by `/facts` and are
inherited, not re-implemented; the new work is rule 4, which is the design).
Rule 5 and §2a's outcome-verdict check → already shipped in `validate.py`,
extended in Task 2 Step 7. §3 scope and the `f1`/`nba` refusal → **Task 1**
Steps 1b and 3b, removals in Task 4. §4 trigger → **Task 1** (§13d moved it
first). §5 contract → Task 2. §5a-bis (encode, never state) → Task 3's
`RecordStrip`. §6 panel → Task 3. §6a–§6c → Task 3's component rules, with §6c's
"there are none in v2 beyond a retry" replaced by §13c. §7 mocks → Task 3,
verified against the rendered result. §8 template parity → Task 2 Steps 9 and 10.
§9 testing → every task, plus the four cross-cutting rules in Global Constraints.
§10's four phases → these four tasks, reordered by §13d. **§13a** the computed
band → Task 2 Steps 1, 3, 9, 11 and 13. **§13b** the PL market row → Task 3
Step 3 (`ProbabilitySplit` omits a `compare` that does not cover every outcome)
and Task 4 Step 1 (the mapping test). **§13c** interaction → Task 3 Steps 1, 3
and 6. **§13d** the order → Task 1.

**What §13a changed about the design, stated plainly.** The draft plan had the
model supply a `band` and had the template hand-write its own threshold ladder.
Both are now gone. The band is one function, `band_for(prob, shape)`, called
from exactly two places — `_answer` for the model path and
`explain_from_template` — and `clean_verdict` has no `band` key at all, so a
model-supplied band has nowhere to be read from. The threshold ladder in the
template draft would have passed every single-probability assertion in Step 10
while still drifting from the service's, which is the reason Step 10 now sweeps a
range of ten probabilities instead.

**Gaps I am naming rather than filling.** §10's "revisit the cap after a week of
real numbers" is a Task 1 measurement, not a code change. §11's open items
(deleting the `/facts` endpoints, whether the record strip and player list belong
in the panel at all) are decisions for after this lands, and the panel's
`record` and player props are optional props so either can be dropped without
touching the rest. §13b notes that a real market comparison for the PL draw
requires a `/facts` change, and defers it. The §13c interaction has been designed
and specified but **not seen in a browser** — see below.

**Placeholder scan.** No TBD, no "similar to Task N", no "add appropriate error
handling". Every code step carries the code. Every test step names the file and
the expected failure.

**Type consistency.** `Verdict`, `MarketTile`, `Segment` are defined once in
Task 3's Interfaces and used by name in Tasks 3 and 4. `clean_verdict`,
`resolve_factors`, `market_keys`, `band_for` and `market_shape` are defined in
Task 2 Step 3 and consumed by `validate()` in Step 7, `template.py` in Step 9 and
`_answer` in Step 11. `SERVED_SPORTS` is defined and used in Task 1.
`Explanation` gains `verdict`/`band`/`factors` in Task 3 Step 6, which is what
Task 2's `conftest.good()` already produces in Task 2 Step 12 — the two tasks are
ordered so that is true, and if Task 2's suite is run before Task 3 the package
tests are simply not in scope for that commit. `band` is on the **response** but
not in the **model contract**; `Explanation` (a response) has it,
`clean_verdict`'s return (a model body) does not, and the plan says so in both
places it could be confused.

**The honest limit on all of it.** No v2 component has been rendered. The §7
mocks are ASCII, so the two-way NFL split, the three-way PL split with the draw
as its own segment, the 3% sliver, the 120ms cross-fade and the `aria-label`
wording are **designed, not seen**. Task 3's tests assert structure, keyboard
operability and the numeric content of accessible names; they cannot tell you a
proportion reads wrong or that a factor list buries the reason. `impeccable
detect` is static pattern matching and will report `[]` on a panel that looks
confusing. That judgement needs eyes, and I would rather say so now than ship a
panel I have only typechecked.
