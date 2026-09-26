# Phase 4: AI match explainer for PL, F1, NFL, CFB and NBA (implementation plan)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task.
> Also required:
> - superpowers:test-driven-development for every task;
> - superpowers:verification-before-completion before any "done";
> - superpowers:requesting-code-review after tasks 6, 11 and 14.
>
> For UI tasks, run `/impeccable` (clarify, harden and adapt; read `reference/craft-floor.md`), then `impeccable detect --json` and a 1440 and 390 screenshot round.
>
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** when someone opens a match or F1 session, a short "In plain English" panel explains what the model thinks and why, market by market. The panel is written by an OpenRouter LLM from our own numbers and free news headlines, with a template fallback.

**Architecture:**
- **One service:** a FastAPI service, `predictor-hub/services/explainer`, holds the OpenRouter key, a SQLite cache, a daily request ledger (cap 900 of the 1,000 a day), a validator, the ESPN news fetcher and a 3-hourly pre-generation loop.
- **Facts:** each sport API adds read-only `/facts/{id}` and `/facts/upcoming` endpoints. They return a fixed JSON contract and use snapshot data in public mode.
- **Display:** each site shows the result through a shared `predictor-ui` `ExplainerPanel`.

**Tech stack:**
- **Service:** Python 3.11, FastAPI, `httpx` (async), `pydantic` v2, SQLite (stdlib `sqlite3`), pytest with `respx` for HTTP mocks. Package manager `uv`.
- **Sites:** React 19, the vendored `predictor-ui`, Vitest.

**Spec:** [../specs/2026-09-25-phase3-4-datahub-explainer-design.md](../specs/2026-09-25-phase3-4-datahub-explainer-design.md), sub-project B. Read it first: sections 1 and 2 are approved; sections 3 and 4 need Kevin's OK before tasks 12–14.

**Repos:** `predictor-hub` (service and package), `NFL_Predictor`, `CFB_Predictor`, `PL_Predictor`, `NBA_Predictor`, `F1_Predictor` and `Sports_Predictor`. Work on the branch `claude/sports-predictors-frontend-plan-qpab3v` in every repo; it already exists, with open PRs.

## Global constraints

- **Key safety:** `OPENROUTER_API_KEY` is read only by the explainer service. It never appears in a site bundle, a GitHub secret, a log line or a response.
- **Budget:** daily cap `EXPLAINER_DAILY_CAP=900` requests per UTC day, counted before each call, retries included. At the cap, serve the template.
- **Models:** `EXPLAINER_MODEL` defaults to `deepseek/deepseek-chat-v3-0324:free` and `EXPLAINER_FALLBACK_MODEL` to `meta-llama/llama-3.3-70b-instruct:free`. Settings: temperature 0.3, `max_tokens` 700, timeout 25 s.
  - Before relying on these, check the free model IDs at https://openrouter.ai/models?q=free and update the defaults if either is gone.
- **Headers:** every OpenRouter call sends `Authorization: Bearer …`, `HTTP-Referer: https://40-160-91-131.sslip.io` and `X-Title: Predictor`.
- **Honesty:** a `pick_timing: "rebuilt"` bundle must produce text saying the pick was built after the start and isn't counted. `result.pick_won` is absent for rebuilt picks.
- **Banned words** (case-insensitive): `lock`, `bet`, `betting advice`, `hammer`, `guaranteed`, `sure thing`, `value play`.
- **Length and shape:** 120–220 words in total, 3–6 sections, headline of 18 words or fewer, each section's text 60 words or fewer.
- **Language:** PL and F1 in UK English; NFL, CFB and NBA in US English.
- **Tests:** tests never hit the network. Mock OpenRouter and ESPN with `respx`, and mock sport APIs with `httpx.MockTransport`.

## Review focus

1. **Numbers in the LLM text that aren't in the facts** (e.g. "a 70% chance" when facts say 62%): rejected. Retry once with the fallback model, then use the template. Test in Task 4.
2. **Quota:**
   - two concurrent requests for the same uncached id call OpenRouter once (per-key async lock);
   - the cap is never exceeded under concurrency.
   
   Tests in Tasks 3 and 6.
3. **Stale explanations:** when odds or the snapshot change, the facts hash changes and the text regenerates. The old cache row is never served for new facts. Test in Task 2.
4. **ESPN news down, or a team with no news:** the explanation still generates with an empty `NEWS` block. Test in Task 5.
5. **Rebuilt picks and finals:** the rebuilt wording is present. A final shows the result, and says whether the pre-kickoff pick won only when `pick_timing` is `pre_kickoff`. Tests in Tasks 4 and 7.

---

### Task 1: service scaffold, config and the facts contract

**Files (create):**
- `predictor-hub/services/explainer/pyproject.toml`
- `predictor-hub/services/explainer/explainer/__init__.py`
- `predictor-hub/services/explainer/explainer/config.py`
- `predictor-hub/services/explainer/explainer/facts.py`
- `predictor-hub/services/explainer/tests/test_facts.py`

**Interfaces:**
- **`config.Settings`** (pydantic-settings) has:
  - `openrouter_api_key: str | None`
  - `model: str`
  - `fallback_model: str`
  - `daily_cap: int = 900`
  - `db_path: str = "/data/explainer.sqlite"`
  - `sport_api: dict[str, str]`, read from `SPORT_API_PL`, `SPORT_API_F1`, `SPORT_API_NFL`, `SPORT_API_CFB` and `SPORT_API_NBA`
  - `enabled: bool = True`
  - `prompt_version: str = "v1"`
- **`facts.Facts`** is a pydantic model that mirrors the spec's facts bundle exactly:

```python
class Market(BaseModel):
    market: str
    model_config = ConfigDict(extra="allow")   # sport-specific fields pass through

class Facts(BaseModel):
    sport: Literal["pl", "f1", "nfl", "cfb", "nba"]
    id: str
    title: str
    starts_at: str
    status: Literal["upcoming", "live", "final"]
    pick_timing: Literal["pre_kickoff", "rebuilt", "none"]
    pick: dict | None = None
    markets: list[Market] = []
    drivers: list[dict] = []
    context: dict = {}
    players: list[dict] = []
    record: dict | None = None
    result: dict | None = None

def render(f: Facts) -> str: ...   # stable, sorted-key JSON (json.dumps(model_dump(), sort_keys=True, ensure_ascii=False))
def numbers_in(text: str) -> set[str]: ...  # normalised numeric tokens (see Task 4)
```

- [ ] **Step 1: Write the failing tests**

```python
from explainer.facts import Facts, render

BASE = dict(sport="nfl", id="g1", title="Chiefs at Ravens", starts_at="2026-10-05T00:20:00Z",
            status="upcoming", pick_timing="pre_kickoff", pick={"label": "BAL", "prob": 0.62},
            markets=[{"market": "spread", "model_margin": 3.4, "line": "BAL -2.5"}])

def test_facts_accepts_sport_specific_market_fields():
    f = Facts(**BASE)
    assert f.markets[0].model_dump()["model_margin"] == 3.4

def test_render_is_stable_regardless_of_key_order():
    a = render(Facts(**BASE))
    b = render(Facts(**dict(reversed(list(BASE.items())))))
    assert a == b

def test_rebuilt_final_cannot_claim_the_pick_won():
    import pytest
    with pytest.raises(ValueError):
        Facts(**{**BASE, "status": "final", "pick_timing": "rebuilt", "result": {"score": "27-20", "pick_won": True}})
```

- [ ] **Step 2: Confirm they fail.** Run `cd services/explainer && uv run pytest -q`.
- [ ] **Step 3: Implement.**
  - Write `config.py` and `facts.py` as above.
  - Add a `model_validator(mode="after")` that raises when `pick_timing == "rebuilt"` and `result` has `pick_won`.
  - `pyproject.toml` dependencies: `fastapi`, `uvicorn`, `httpx`, `pydantic>=2`, `pydantic-settings`. Dev dependencies: `pytest`, `pytest-asyncio`, `respx`.
- [ ] **Step 4: Confirm they pass.** Run `uv run pytest -q`.
- [ ] **Step 5: Commit** with `git commit -m "feat(explainer): service scaffold and the facts contract"`.

### Task 2: the cache

**Files:**
- Create: `services/explainer/explainer/cache.py`
- Test: `services/explainer/tests/test_cache.py`

**Interfaces:**

```python
class Cache:
    def __init__(self, path: str): ...            # creates table explanations(key TEXT PRIMARY KEY, sport, id, body_json, source, model, prompt_version, created_at)
    @staticmethod
    def key(sport: str, id: str, facts_json: str, news_json: str, prompt_version: str, model: str) -> str: ...  # sha256 hex
    def get(self, key: str) -> dict | None: ...
    def put(self, key: str, sport: str, id: str, body: dict, source: str, model: str, prompt_version: str) -> None: ...
    def latest_for(self, sport: str, id: str) -> dict | None: ...   # newest row for the id, used by /status only
```

- [ ] **Step 1: Write the failing tests**

```python
from explainer.cache import Cache

def test_roundtrip_and_new_facts_mean_new_key(tmp_path):
    c = Cache(str(tmp_path / "x.sqlite"))
    k1 = Cache.key("nfl", "g1", '{"p":0.62}', "[]", "v1", "m")
    k2 = Cache.key("nfl", "g1", '{"p":0.64}', "[]", "v1", "m")
    assert k1 != k2
    c.put(k1, "nfl", "g1", {"headline": "h", "sections": []}, "llm", "m", "v1")
    assert c.get(k1)["body"]["headline"] == "h"
    assert c.get(k2) is None
```

- [ ] **Step 2: Confirm it fails.**
- [ ] **Step 3: Implement** with stdlib `sqlite3`. Open one connection per call with `check_same_thread=False`. `get` returns `{"body", "source", "model", "prompt_version", "created_at"}`.
- [ ] **Step 4: Confirm it passes.**
- [ ] **Step 5: Commit** with `git commit -m "feat(explainer): SQLite cache keyed on facts, news, prompt and model"`.

### Task 3: the daily ledger

**Files:**
- Create: `services/explainer/explainer/ledger.py`
- Test: `services/explainer/tests/test_ledger.py`

**Interfaces:**

```python
class Ledger:
    def __init__(self, path: str, cap: int, now=lambda: datetime.now(timezone.utc)): ...
    def try_spend(self) -> bool: ...   # atomically: if today's count < cap, increment and return True; else False
    def used_today(self) -> int: ...
```

- [ ] **Step 1: Write the failing tests**

```python
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from explainer.ledger import Ledger

def test_cap_and_utc_rollover(tmp_path):
    t = [datetime(2026, 10, 1, 23, 59, tzinfo=timezone.utc)]
    led = Ledger(str(tmp_path / "l.sqlite"), cap=2, now=lambda: t[0])
    assert led.try_spend() and led.try_spend() and not led.try_spend()
    t[0] += timedelta(minutes=2)
    assert led.try_spend() and led.used_today() == 1

def test_never_exceeds_cap_under_concurrency(tmp_path):
    led = Ledger(str(tmp_path / "l.sqlite"), cap=50)
    with ThreadPoolExecutor(16) as pool:
        results = list(pool.map(lambda _: led.try_spend(), range(200)))
    assert sum(results) == 50
```

- [ ] **Step 2: Confirm they fail.**
- [ ] **Step 3: Implement.**
  - Table `spend(day TEXT PRIMARY KEY, n INTEGER)`.
  - `try_spend` runs one transaction under `BEGIN IMMEDIATE`: `INSERT OR IGNORE` today's row, then `UPDATE spend SET n = n + 1 WHERE day = ? AND n < ?`, and returns `cursor.rowcount == 1`.
  - Also guard with a `threading.Lock`.
- [ ] **Step 4: Confirm they pass.**
- [ ] **Step 5: Commit** with `git commit -m "feat(explainer): atomic daily request ledger"`.

### Task 4: the validator and the template fallback

**Files:**
- Create: `services/explainer/explainer/validate.py` and `services/explainer/explainer/template.py`
- Test: `services/explainer/tests/test_validate.py` and `services/explainer/tests/test_template.py`

**Interfaces:**

```python
# validate.py
BANNED = ["lock", "bet", "betting advice", "hammer", "guaranteed", "sure thing", "value play"]
def numbers_in(text: str) -> set[float]: ...
# tokens like 62%, 0.62, −2.5, -2.5, +3, 47.8, 6/10; "62%" -> 0.62 and 62.0; U+2212 -> "-"
def validate(output: dict, facts_json: str, news_json: str) -> list[str]: ...
# returns problems; [] = valid. Checks: keys headline/sections; 3–6 sections; headline ≤ 18 words;
# section text ≤ 60 words; total 120–220 words; no banned word (whole-word, case-insensitive);
# every number in headline/texts is within 0.05 of some number in facts_json or news_json
# (percent tokens compared as fractions and as whole numbers); if facts pick_timing == "rebuilt",
# the text must contain "rebuilt" or "after kickoff"/"after the start"/"after the session".

# template.py
def explain_from_template(facts: dict) -> dict: ...  # returns the same {headline, sections} shape
```

- [ ] **Step 1: Write the failing tests**

```python
import json
from explainer.validate import validate

FACTS = json.dumps({"pick": {"label": "BAL", "prob": 0.62}, "pick_timing": "pre_kickoff",
                    "markets": [{"market": "spread", "line": "BAL -2.5", "model_margin": 3.4}]})

def good(extra=""):
    words = "The model makes Baltimore a 62% favourite and rates them 3.4 points better, ahead of the -2.5 line. " * 3
    return {"headline": "Baltimore favoured at 62%", "sections": [
        {"market": "result", "title": "Pick", "text": words[:300]},
        {"market": "spread", "title": "Spread", "text": "Model margin 3.4 against a -2.5 line. " + extra},
        {"market": "trust", "title": "Trust", "text": "62% still loses about four times in ten games like this one, so treat it as a lean."}]}

def test_accepts_numbers_from_facts():
    assert validate(good(), FACTS, "[]") == []

def test_rejects_invented_number():
    assert any("70" in p for p in validate(good("A 70% chance."), FACTS, "[]"))

def test_rejects_banned_word():
    assert validate(good("Lock it in."), FACTS, "[]")

def test_rebuilt_must_say_so():
    rebuilt = FACTS.replace("pre_kickoff", "rebuilt")
    assert any("rebuilt" in p for p in validate(good(), rebuilt, "[]"))
```

```python
from explainer.template import explain_from_template

def test_template_is_plain_and_honest_for_rebuilt():
    out = explain_from_template({"title": "Chiefs at Ravens", "pick": {"label": "BAL", "prob": 0.62},
                                 "pick_timing": "rebuilt", "markets": [], "players": [], "record": None})
    text = " ".join(s["text"] for s in out["sections"])
    assert "rebuilt after kickoff" in text.lower() and "62%" in out["headline"]
```

- [ ] **Step 2: Confirm they fail.**
- [ ] **Step 3: Implement.**
  - **`validate`:** as specified above. Keep word counts whitespace-split, and make the 120–220 word bound inclusive.
  - **`template`:** one sentence per available market:
    - `result`/`moneyline`/`win`: "The model makes {label} the pick at {prob%}."
    - `spread`/`handicap`: "It rates {label} {margin} points better; the line is {line}."
    - `total`/`total_goals`: "It projects {model_total} against a line of {line}."
    - Then the top 2 players, the record ("{hits}/{settled} picks made before kickoff correct"), and the rebuilt sentence when the pick is rebuilt.
    - The headline is "{title}: {label} at {prob%}".
- [ ] **Step 4: Confirm they pass.**
- [ ] **Step 5: Commit** with `git commit -m "feat(explainer): output validator (numbers must come from facts) and template fallback"`.

### Task 5: the news fetcher (ESPN, free)

**Files:**
- Create: `services/explainer/explainer/news.py`
- Test: `services/explainer/tests/test_news.py`

**Interfaces:**

```python
ESPN_NEWS = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news",
    "cfb": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/news",
    "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news",
    "pl":  "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/news",
    "f1":  "https://site.api.espn.com/apis/site/v2/sports/racing/f1/news",
}
async def headlines(client: httpx.AsyncClient, sport: str, teams: list[str], limit: int = 4) -> list[dict]: ...
# returns [{"headline", "published", "source": "ESPN"}], newest first, max `limit`, only items whose
# headline or description mentions one of `teams` (case-insensitive); on any error/timeout -> [].
# Cache per (sport) for 30 min in memory to avoid refetching per game.
```

- [ ] **Step 1: Write the failing tests** (mock ESPN with respx):
  - a matching headline is returned with its `published` date;
  - a non-matching one is dropped;
  - a 500 or timeout returns `[]` and never raises;
  - a second call within 30 min doesn't refetch (`respx` route `call_count == 1`).
- [ ] **Step 2: Confirm they fail.**
- [ ] **Step 3: Implement.** Use the ESPN response keys `articles[].headline`, `articles[].description` and `articles[].published`, and a timeout of 6 s.
- [ ] **Step 4: Confirm they pass.**
- [ ] **Step 5: Commit** with `git commit -m "feat(explainer): free ESPN headlines per team, fail-safe"`.

### Task 6: the OpenRouter client, prompts, the explain flow and the HTTP API

**Files:**
- Create: `services/explainer/explainer/prompts.py`, `services/explainer/explainer/llm.py`, `services/explainer/explainer/service.py` and `services/explainer/explainer/app.py`
- Test: `services/explainer/tests/test_service.py` and `services/explainer/tests/test_app.py`

**Interfaces:**

```python
# prompts.py
SYSTEM = """You explain one sports prediction to a fan in plain English. ... (the six rules from spec §2, verbatim) ...
Return JSON only: {"headline": str, "sections": [{"market": str, "title": str, "text": str, "numbers_used": [str]}]}"""
SPORT_NOTES = {"pl": "...UK English; result is home/draw/away; 'handicap'; gameweek...",
               "f1": "...UK English; tell the race story: tie grid position to the headline chance, name who can move up and why, cite the given contributors...",
               "nfl": "...US English; spread and total; key numbers 3 and 7; rest and weather...",
               "cfb": "...US English; spread and total; conference context...",
               "nba": "...US English; spread and total; back-to-backs, pace, net rating..."}
def messages(sport: str, facts_json: str, news_json: str) -> list[dict]: ...

# llm.py
async def complete(client: httpx.AsyncClient, settings, model: str, msgs: list[dict]) -> dict: ...
# POST https://openrouter.ai/api/v1/chat/completions with response_format={"type":"json_object"},
# temperature 0.3, max_tokens 700, timeout 25s, headers per Global Constraints; parses choices[0].message.content as JSON;
# raises LLMError on HTTP error / non-JSON.

# service.py
class Explainer:
    def __init__(self, settings, cache: Cache, ledger: Ledger, client: httpx.AsyncClient): ...
    async def explain(self, sport: str, id: str) -> dict: ...
# flow: GET {sport_api[sport]}/facts/{id} -> Facts; teams from facts.title/players;
# news = await headlines(...); key = Cache.key(...); cached -> return;
# per-key asyncio.Lock (dict of locks) so concurrent callers share one generation;
# if settings.enabled and key set: for model in (model, fallback_model): if not ledger.try_spend(): break;
#   try complete(); problems = validate(); if not problems: store source="llm"; return
# else/failed: body = explain_from_template(facts); store source="template"; return
# returns {"sport","id","headline","sections","source","model","generated_at","prompt_version"}

# app.py
GET /explain/{sport}/{id}      -> Explainer.explain   (404 if sport API 404s; 502 if the sport API is down)
GET /status                    -> {"used_today", "cap", "enabled", "model"}   (no key material)
```

- [ ] **Step 1: Write the failing tests** (`respx` mocks for the sport API and OpenRouter):
  - **happy path:** stored as `source == "llm"`, and a second call is a cache hit (the OpenRouter route is called once);
  - **invalid first answer:** one call to each model, then valid;
  - **both invalid:** `source == "template"`;
  - **ledger at cap:** the template, with zero OpenRouter calls;
  - **no key:** the template;
  - **two concurrent `explain` calls for the same uncached id:** OpenRouter is called exactly once (`asyncio.gather`);
  - **`/status`:** never includes the key string.
- [ ] **Step 2: Confirm they fail.**
- [ ] **Step 3: Implement as specified.**
- [ ] **Step 4: Confirm they pass.** Run `uv run pytest -q`.
- [ ] **Step 5: Commit** with `git commit -m "feat(explainer): OpenRouter flow with validation, retry, template, per-key lock and HTTP API"`.
- [ ] **Step 6: Review.** Request a code review (superpowers:requesting-code-review) of Tasks 1–6 before continuing.

### Task 7: the pre-generation scheduler, Dockerfile and README

**Files:**
- Create: `services/explainer/explainer/scheduler.py`, `services/explainer/Dockerfile` and `services/explainer/README.md`
- Test: `services/explainer/tests/test_scheduler.py`

**Interfaces:**
- `async def pregenerate(explainer, client, sports: list[str], hours: int = 72) -> int` fetches `GET {sport_api}/facts/upcoming?hours=72` (which returns `{"ids": [...]}`) for each sport, calls `explainer.explain` for each id sequentially, and returns the number generated.
- It stops early when `ledger.used_today() >= cap - 50`, keeping 50 for on-demand use.
- `app.py` starts `asyncio.create_task(loop())` on startup, running `pregenerate` every 3 h when `settings.enabled`.

- [ ] **Step 1: Write the failing tests.**
  - It calls explain for every upcoming id.
  - It stops at the reserve.
  - A failing sport API is skipped and the others still run.
- [ ] **Step 2: Confirm they fail.**
- [ ] **Step 3: Implement.** The Dockerfile uses `python:3.11-slim` and `uv`, and runs `uvicorn explainer.app:app --host 0.0.0.0 --port 8090` with a `/data` volume. The README lists every env var and the Caddy snippet `handle_path /api/explain/* { reverse_proxy predictor-explainer:8090 }` (the explainer's routes are `/explain/...`; see Task 13).
- [ ] **Step 4: Confirm they pass.**
- [ ] **Step 5: Commit** with `git commit -m "feat(explainer): 3-hourly pre-generation with an on-demand reserve; container and docs"`.

### Task 8: NFL `/facts/{game_id}` and `/facts/upcoming`

**Files:**
- Create: `NFL_Predictor/src/nfl_predictor/api/facts.py` (a router, included in `main.py` beside `routes.router`)
- Test: `NFL_Predictor/tests/test_facts.py`

**Interfaces:**
- `GET /facts/{game_id}` returns the spec's facts bundle with `sport="nfl"`. It is assembled only from existing functions, or from snapshot data in PUBLIC_MODE:
  - the game row (`schedules.fetch_week_games`, or the snapshot `weeks[week]["games"]`);
  - the prediction (`get_game_prediction`);
  - the week row (`store.get_predictions_for_week`), for `pick_timing` (`"rebuilt"` if `row["rebuilt"]`, `"pre_kickoff"` if the status is resolved or snapshotted, `"none"` when there is no row);
  - props (the top 3 for the two teams by projected yards);
  - the track record (`store.get_track_record()["games"]`, for hits and settled).
- **Markets:**
  - moneyline from `home_win_prob`;
  - spread with `model_margin` = `predicted_margin` and `line` = `spread(home, -spread_line)` in the site's wording (nflverse `spread_line > 0` means home favoured);
  - total with `model_total` = `predicted_total` and `line` = `total_line`.
- **Drivers:** rating gap, rest, home field and divisional, from `feature_build.build_features_for_game`. Skip this in PUBLIC_MODE if the snapshot lacks it, and never compute live there.
- **Context:** weather (`temp` and `wind`), roof, rest, and injuries from `data/injuries.fetch_injuries([season])` for the two teams, status Out or Doubtful, up to 6 names.
- `GET /facts/upcoming?hours=72` returns `{"ids": [game_id, …]}` for games starting in that window.

- [ ] **Step 1: Write the failing tests.**
  - With PUBLIC_MODE on and a fake snapshot, the bundle validates against the contract. Copy `Facts` into the test as a local pydantic model, or assert the keys and types.
  - `pick_timing` is `rebuilt`, `pre_kickoff` or `none` in the three cases.
  - A final includes `result.score`, and has `pick_won` only when the timing is `pre_kickoff`.
  - No live model call happens in public mode (monkeypatch `_get_game_prediction_live` to raise).
  - `/facts/upcoming` returns only games within the window.
- [ ] **Step 2: Confirm they fail.** Run `uv run pytest -q tests/test_facts.py`.
- [ ] **Step 3: Implement** `facts.py`, and include the router in `main.py`.
- [ ] **Step 4: Confirm they pass.** Run `uv run pytest -q`.
- [ ] **Step 5: Commit and push** with `git commit -m "feat: /facts endpoints for the match explainer"`.

### Task 9: CFB `/facts`

**Files:**
- Create: `CFB_Predictor/src/cfb_predictor/api/facts.py`
- Test: `CFB_Predictor/tests/test_facts.py`

**Interfaces:** the same as Task 8, with these differences:
- `sport="cfb"`;
- no injuries source, so leave `context.injuries` out;
- `context.conferences` is `"{away_conf} at {home_conf}"`;
- markets are spread and total only where the lines exist.

**Tests:** as in Task 8, for the CFB snapshot shape. Add a case with no market lines, where only the pick market is present.

**Commit:** `feat: CFB /facts endpoints for the match explainer`.

### Task 10: NBA `/facts`

**Files:**
- Create: `NBA_Predictor/src/nba_predictor/api/facts.py`
- Test: `NBA_Predictor/tests/test_facts.py`

**Interfaces:**
- `sport="nba"`; the id is the NBA `game_id`.
- `pick_timing` uses the existing `tracking/timing.py`:
  - `rebuilt` if the game's `rebuilt` flag is set;
  - `pre_kickoff` if a prediction exists and `made_before_tip`;
  - otherwise `none`.
- **Markets:**
  - moneyline from `home_win_probability`;
  - spread from `predicted_margin`, written with `marginLine` semantics (a team name, and "Toss-up" under 0.5);
  - total from `predicted_total`;
  - market lines from `store.get_market_predictions_for_game`, pre-tip rows only.
- **Players:** the top 3 player projections from `/games/{id}/players` that aren't rebuilt.
- **Record:** from `compute_track_record`, the `game_outcome` row.
- **Context:** rest days and back-to-back flag, if the schedule has them. If not, omit them; don't compute new features.

**Tests:** the three `pick_timing` cases, rebuilt player props excluded, and a final's result.

**Commit:** `feat: NBA /facts endpoints for the match explainer`.

### Task 11: PL and F1 `/facts`

**PL** (`PL_Predictor/src/pl_predictor/api/facts.py`, test `tests/test_facts.py`):
- `sport="pl"`; the id is the fixture `event_id`.
- `pick` uses the frontend `matchPick` rule (argmax of home/draw/away, with the same tie order). Port it to Python beside the facts module.
- **Markets:**
  - `result`: home, draw and away probabilities;
  - `total_goals` and `btts`, if the fixture detail has them;
  - live odds and edge from the existing value-bet data when `has_live_odds`.
- `drivers` come from the fixture detail's feature contributions, if the detail endpoint returns them.
- `players` are the top 3 scorer probabilities.
- `pick_timing` is `rebuilt` when the fixture is `backfilled`.
- `record` comes from `get_track_record` (pre-kickoff counts).

**F1** (`F1_Predictor/src/f1_predictor/api/facts.py`, test `tests/test_facts.py`):
- The id is `{season}-{round}-{session}`, where the session is `race`, `qualifying` or `sprint`.
- `pick` is the top driver by win (or pole).
- `pick_timing`:
  - `pre_kickoff` when the source is `tracked` or `live` before the session;
  - `rebuilt` when the source is `rebuilt` or `backtest`.
- `drivers`: the top 8 with `grid` (when known), `win`, `podium`, `points` and `dnf`. For the top 3 plus the biggest mover (the largest |grid − predicted rank|), add `contributors`: up to 5 of the existing `/explain` strength contributors, as `{feature label from glossary, value, direction: "raises" | "lowers"}`.
- `context`: circuit, sprint weekend (true/false), tier and forecast weather, when the features have them.
- `/facts/upcoming` lists sessions that start within the window.

**Tests for both:**
- the contract keys;
- the rebuilt cases (PL backfilled; F1 rebuilt or backtest);
- F1 contributors present for the pole-sitter and the biggest mover;
- public mode reads the snapshot only.

**Commits:** `feat: PL /facts endpoints for the match explainer` and `feat: F1 /facts (race story inputs) for the match explainer`. Then request a code review of Tasks 8–11.

### Task 12: `ExplainerPanel` in `predictor-ui`

(Confirm spec section 3 with Kevin first.)

**Files:**
- Create: `predictor-hub/packages/predictor-ui/src/components/ExplainerPanel.tsx`
- Test: `predictor-hub/packages/predictor-ui/src/components/explainer.test.tsx`
- Export it from `index.ts`.

**Interfaces:**

```ts
export type Explanation = { headline: string; sections: { market: string; title: string; text: string }[];
  source: "llm" | "template"; model: string; generated_at: string };
export function ExplainerPanel(props: { data: Explanation | null; loading: boolean; error: boolean;
  onRetry: () => void; collapsed?: boolean }): JSX.Element
```

- [ ] **Step 1: Write the failing tests.**
  - **Loading:** a Skeleton reading "Writing the summary…".
  - **Error:** an ErrorState with Try again that calls `onRetry`.
  - **`source="llm"`:** the footer reads "AI summary of the model's numbers · {model} · {n} min ago".
  - **`source="template"`:** the footer reads "Summary written from the model's numbers" and contains no "AI".
  - **`collapsed`:** shows only the headline, plus a button "Read the race story" with `aria-expanded`.
  - The heading "In plain English" is present.
- [ ] **Step 2: Confirm they fail.**
- [ ] **Step 3: Implement** with family tokens and 12 px minimum text. Each section renders as a `<h4>` title with a `<p>`.
- [ ] **Step 4: Confirm they pass.** Run `npx vitest run && npx tsc --noEmit -p .`.
- [ ] **Step 5: Commit.** Then resync into Sports, PL, NBA and F1 (`node scripts/sync-ui.mjs <site>/src`), run each site's tests, and commit `chore: resync predictor-ui (ExplainerPanel)` in each.

### Task 13: wire the panel into each site, plus the proxies

For each site, add `api.explain(...)` to the client (15 s timeout, same-origin):
- **Sports** (`/api/explain/nfl|cfb/{game_id}`):
  - render `ExplainerPanel` at the top of `GameDetailModal`;
  - `Caddyfile`: `handle_path /api/explain/* { rewrite * /explain{uri}; reverse_proxy {$EXPLAINER_UPSTREAM:predictor-explainer:8090} }`.
- **PL** (`/api/explain/pl/{event_id}`): render at the top of `FixtureModal`. PL's FastAPI serves the site, so add a small proxy route `GET /api/explain/{sport}/{id}` in `api/routes.py` that forwards to `EXPLAINER_URL` with httpx (a 20 s timeout, and a 502 on failure).
- **NBA** (`/api/explain/nba/{game_id}`): render at the top of `GameDetailModal`. Add the same FastAPI proxy route.
- **F1** (`/api/explain/f1/{season}-{round}-{session}`): render in `SessionTimelinePanel` above the `TimingTower`, with `collapsed` set. Add the same FastAPI proxy route.

**Tests:** each site's modal test mocks `api.explain` and checks the headline renders, that Try again refetches, and that the rest of the modal renders while the explanation is still loading.

**Verify** each site with vitest, tsc and `impeccable detect`, then screenshots of one open game per site at 1440 and 390.

**Commits:** `feat: In plain English panel on the game detail`, one per site.

### Task 14: end-to-end check and rollout docs

- [ ] Run the service locally with no key, point `SPORT_API_NFL` at the local NFL API, and open a game on the Sports site. The template summary renders with the non-AI footer.
- [ ] With a key (Kevin's VPS only), check `/status` after one pre-generation cycle (`used_today` should increase), and read three explanations for number accuracy against the facts.
- [ ] Update `predictor-hub/docs/superpowers/plans/2026-09-25-predictor-frontend-action-plan.md` with a Phase 4 status note, and add the VPS steps to the explainer README:
  - the container;
  - the env vars;
  - the Caddy or FastAPI proxy per site;
  - `EXPLAINER_ENABLED=false` as the kill switch.
- [ ] Request a final whole-branch code review, then fix every Critical and Important finding.

## Self-review

- **Spec coverage:**
  - architecture: Tasks 1–7;
  - facts contract: Task 1 plus Tasks 8–11;
  - prompts and guardrails: Tasks 4 and 6;
  - news: Task 5;
  - budget: Tasks 3, 6 and 7;
  - UI: Tasks 12–13;
  - rollout: Task 14;
  - F1 race story: Tasks 6 (prompt) and 11 (contributors).
- **Review focus:** each line maps to the named task's tests.
- **Types:**
  - `Explanation` (Task 12) matches the service's response in Task 6: headline, sections, source, model and generated_at.
  - The facts keys match the spec's bundle.
