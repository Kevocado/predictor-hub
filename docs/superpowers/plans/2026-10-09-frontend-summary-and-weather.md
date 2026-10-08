# Frontend: the Edge / Risk / Price summary and the kickoff weather chip

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two frontend deliverables for the football sites (and the summary for all four): (A) the AI summary grouped into Edge, Risk and Price with a rank-duel visual for offence-versus-defence matchups; (B) a weather chip (sun, cloud, rain, snow, storm, fog, indoors) for football games, from the free Open-Meteo forecast.

**Architecture:** Both ship the same way as every shared UI change: components in `predictor-hub/packages/predictor-ui`, tested there, then re-synced into each site with `scripts/sync-ui.mjs` (never hand-edited in a site). Data arrives from each sport API: `conditions` (one small object per game) and, inside the explainer response, factors that now carry `slot` and may be keyed `matchup:<id>` (see the AI plan). The weather-code mapping lives in the API once; the component draws a `kind` it knows or draws nothing.

**Tech Stack:** React 19, TypeScript, Tailwind tokens (`pr-*`), vitest + testing-library; Python 3.11 for the API half of the weather chip; Open-Meteo `v1/forecast` (free, keyless).

**Spec:** `docs/superpowers/plans/2026-10-09-ai-summary-redesign.md` (data and contract), `PRODUCT.md` (users: fans on phones; honest record; show reasoning), `packages/predictor-ui/src/components/FactorList.tsx` (direction is never carried by colour alone).

**Verified vs drafted:** the weather API module (15 tests), `WeatherChip` and `RankDuel` (21 tests, `tsc --noEmit` clean) were built and run. `MatchupBrief` (4 tests) was also built and run. The `ExplainerPanel` switch and the site integrations are DRAFTED.

## Global Constraints

- Design rules from `PRODUCT.md`/`FactorList`: meaning is never carried by colour or a picture alone (words always present); icons are `aria-hidden`; mobile first (390px), no horizontal scroll, 16px gutters.
- Before writing any UI, run the `impeccable` skill: `impeccable context` once, read its `craft-floor.md`, then verify in bounded passes only: build fully, ONE batched desktop + 390px screenshot round, fix everything in one batch, at most one confirming round, stop. Screenshots go in the PR.
- A figure may only reach the page if the row's own words state it (the `SignalRows` rule). `RankDuel` draws ranks; the row headline must state the same two ranks (Task 3 asserts it).
- Missing or failed data means the element is absent, never zero, never a guess. A weather chip with no data renders nothing; an unknown `kind` renders nothing.
- Shared components are edited in the hub only, then re-synced per site with `scripts/sync-ui.mjs --from <full hub sha>`; never `--vendor-anyway`. Gate: `npm run build` plus the full vitest suite in each site and the hub.
- Weather is Open-Meteo only, called by the sport API (never from the browser), cached, and labelled with its source. Never `git add -A`; never push to main; use worktrees.

## File structure

Hub: create `packages/predictor-ui/src/components/{WeatherChip,RankDuel,MatchupBrief}.tsx` (+ tests), modify `src/index.ts`, `FactorList.tsx` (slot grouping prop), `ExplainerPanel.tsx` (pass slot data). NFL/CFB repos: create `data/forecast.py`, modify the games API to attach `conditions`, re-sync UI, mount the chip. NBA/PL: re-sync UI only (they get the summary redesign, no weather).

## PR plan

PR-1 (hub): Tasks 3-5 (components, inert until a site uses them). PR-2 (NFL API + site): Tasks 1-2, 6. PR-3 (CFB): Task 7. PR-4 (summary on all four sites): Task 8. Order: PR-1 first (the sites re-sync from its merge SHA).

---

# Part B first: the weather chip (smaller, independent)

## Task 1 (NFL API, verified): kickoff forecast to a small `conditions` object

**Why:** nflverse and the Open-Meteo archive already give weather for PAST games (`data/weather.py`). The chip is about UPCOMING games, which need the forecast endpoint (a different URL that serves only about 16 days ahead). I checked the live response shape on 2026-10-07: `hourly` carries `temperature_2m` (C), `precipitation_probability` (%), `weather_code` (WMO), `wind_speed_10m` (km/h).

**Files:**
- Create: `src/nfl_predictor/data/forecast.py`
- Test: `tests/test_forecast.py`

**Interfaces:**
- Consumes: `data.weather.STADIUM_COORDS`, `INDOOR_STADIUMS`.
- Produces: `kind_for(code) -> str | None`; `forecast_for(stadium, kickoff_utc_iso, now=None, get=requests.get) -> {kind, temp_f, wind_mph, precip_pct, source} | None`. `kind` is one of `clear, partly, cloudy, fog, rain, snow, storm, dome`.

- [ ] **Step 1: Write the failing tests.**

```python
from datetime import datetime, timedelta, timezone

import pytest
from nfl_predictor.data.forecast import forecast_for, kind_for

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
KICK = "2026-10-11T17:00:00Z"


class _Resp:
    def __init__(self, body, ok=True):
        self._body, self._ok = body, ok

    def raise_for_status(self):
        if not self._ok:
            raise RuntimeError("503")

    def json(self):
        return self._body


def _body(code=61, temp_c=10.0, wind_kph=24.0, pop=70):
    return {"hourly": {"time": ["2026-10-11T16:00", "2026-10-11T17:00"], "temperature_2m": [9.0, temp_c],
                       "precipitation_probability": [10, pop], "weather_code": [3, code], "wind_speed_10m": [5.0, wind_kph]}}


@pytest.mark.parametrize("code,kind", [(0, "clear"), (2, "partly"), (3, "cloudy"), (45, "fog"), (63, "rain"), (81, "rain"),
                                       (73, "snow"), (95, "storm")])
def test_wmo_codes_map_to_pictures(code, kind):
    assert kind_for(code) == kind


def test_unknown_code_is_not_drawn_as_a_guess():
    assert kind_for(123) is None and kind_for(None) is None


def test_forecast_reads_the_kickoff_hour_and_converts_units():
    out = forecast_for("Lambeau Field", KICK, NOW, get=lambda *a, **k: _Resp(_body()))
    assert out == {"kind": "rain", "temp_f": 50, "wind_mph": 15, "precip_pct": 70, "source": "open-meteo"}


def test_roofed_stadium_is_a_dome_without_a_request():
    def boom(*a, **k):
        raise AssertionError("no request for a roof")
    assert forecast_for("U.S. Bank Stadium", KICK, NOW, get=boom)["kind"] == "dome"


def test_beyond_the_horizon_is_none():
    far = (NOW + timedelta(days=20)).strftime("%Y-%m-%dT17:00:00Z")
    assert forecast_for("Lambeau Field", far, NOW, get=lambda *a, **k: _Resp(_body())) is None


def test_http_failure_is_none_not_an_exception():
    assert forecast_for("Lambeau Field", KICK, NOW, get=lambda *a, **k: _Resp({}, ok=False)) is None


def test_missing_kickoff_hour_is_none():
    body = _body()
    body["hourly"]["time"] = ["2026-10-11T01:00", "2026-10-11T02:00"]
    assert forecast_for("Lambeau Field", KICK, NOW, get=lambda *a, **k: _Resp(body)) is None


def test_unknown_stadium_is_none():
    assert forecast_for("Nowhere Park", KICK, NOW, get=lambda *a, **k: _Resp(_body())) is None
```

- [ ] **Step 2: Run to verify failure.** Run: `uv run --python 3.11 --extra dev pytest -q -p no:cacheprovider tests/test_forecast.py` Expected: ImportError.

- [ ] **Step 3: Write the module.**

```python
"""Kickoff-hour forecast from Open-Meteo (free, keyless) as the small `conditions` object the sites draw as an icon.

Only games from now to 16 days out have a forecast. Anything else, and any failure, returns None: no chip beats a
wrong chip. Roofed stadiums return kind "dome" without a request.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import requests

from .weather import INDOOR_STADIUMS, STADIUM_COORDS

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HORIZON_DAYS = 16

#: WMO weather interpretation codes -> the handful of pictures the UI can draw.
_KINDS = {
    0: "clear", 1: "clear", 2: "partly", 3: "cloudy",
    45: "fog", 48: "fog",
    51: "rain", 53: "rain", 55: "rain", 56: "rain", 57: "rain", 61: "rain", 63: "rain", 65: "rain",
    66: "rain", 67: "rain", 80: "rain", 81: "rain", 82: "rain",
    71: "snow", 73: "snow", 75: "snow", 77: "snow", 85: "snow", 86: "snow",
    95: "storm", 96: "storm", 99: "storm",
}


def kind_for(code) -> str | None:
    """None for a code this table does not know: an unknown sky is not drawn as a guessed one."""
    try:
        return _KINDS.get(int(code))
    except (TypeError, ValueError):
        return None


def forecast_for(stadium: str, kickoff_utc_iso: str, now: datetime | None = None, get=requests.get) -> dict | None:
    if stadium in INDOOR_STADIUMS:
        return {"kind": "dome", "temp_f": None, "wind_mph": None, "precip_pct": None, "source": "roof"}
    coords = STADIUM_COORDS.get(stadium)
    if coords is None:
        return None
    now = now or datetime.now(timezone.utc)
    kickoff = datetime.fromisoformat(kickoff_utc_iso.replace("Z", "+00:00"))
    if not (now - timedelta(hours=6) <= kickoff <= now + timedelta(days=HORIZON_DAYS)):
        return None
    day = kickoff_utc_iso[:10]
    params = {
        "latitude": coords[0], "longitude": coords[1], "start_date": day, "end_date": day, "timezone": "UTC",
        "hourly": "temperature_2m,precipitation_probability,weather_code,wind_speed_10m",
    }
    try:
        response = get(FORECAST_URL, params=params, timeout=15)
        response.raise_for_status()
        hourly = response.json()["hourly"]
        i = next(i for i, t in enumerate(hourly["time"]) if t[:13] == kickoff_utc_iso[:13])
        kind = kind_for(hourly["weather_code"][i])
        if kind is None:
            return None
        return {
            "kind": kind,
            "temp_f": round(hourly["temperature_2m"][i] * 9 / 5 + 32),
            "wind_mph": round(hourly["wind_speed_10m"][i] / 1.609344),
            "precip_pct": hourly["precipitation_probability"][i],
            "source": "open-meteo",
        }
    except Exception:  # noqa: BLE001 - any failure means "no chip", never a guess
        return None
```

- [ ] **Step 4: Run.** Expected: 15 passed.

- [ ] **Step 5: Commit.** `git add src/nfl_predictor/data/forecast.py tests/test_forecast.py && git commit -m "feat: kickoff forecast from Open-Meteo as a small conditions object"`

## Task 2 (NFL API, DRAFTED): attach `conditions` to games, cached

**Why:** the games endpoint should carry `conditions` per upcoming game so the site only has to draw it. A forecast changes, so cache it for a short time and never persist it into the public snapshot as if it were fact (it is a forecast, labelled `source`).

**Files:** Modify `src/nfl_predictor/api/routes.py` (the games list/detail builder; find with `grep -n "def .*games" src/nfl_predictor/api/routes.py`); Create `src/nfl_predictor/data/forecast_cache.py`; Test `tests/test_forecast_cache.py`, `tests/test_api_routes.py`.

- [ ] **Step 1: Failing tests.**

```python
from datetime import datetime, timedelta, timezone
from nfl_predictor.data.forecast_cache import ForecastCache

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def test_a_fresh_entry_is_reused_without_a_second_fetch():
    calls = []
    cache = ForecastCache(ttl=timedelta(hours=3), fetch=lambda s, k, now: calls.append(1) or {"kind": "rain"})
    assert cache.get("Lambeau Field", "2026-10-11T17:00:00Z", NOW) == {"kind": "rain"}
    assert cache.get("Lambeau Field", "2026-10-11T17:00:00Z", NOW + timedelta(hours=1)) == {"kind": "rain"}
    assert len(calls) == 1


def test_a_stale_entry_is_refetched():
    calls = []
    cache = ForecastCache(ttl=timedelta(hours=3), fetch=lambda s, k, now: calls.append(1) or {"kind": "rain"})
    cache.get("Lambeau Field", "2026-10-11T17:00:00Z", NOW)
    cache.get("Lambeau Field", "2026-10-11T17:00:00Z", NOW + timedelta(hours=4))
    assert len(calls) == 2


def test_a_failed_fetch_is_not_cached_as_none_forever():
    results = iter([None, {"kind": "clear"}])
    cache = ForecastCache(ttl=timedelta(hours=3), fetch=lambda s, k, now: next(results))
    assert cache.get("Lambeau Field", "2026-10-11T17:00:00Z", NOW) is None
    assert cache.get("Lambeau Field", "2026-10-11T17:00:00Z", NOW + timedelta(minutes=1)) == {"kind": "clear"}
```

- [ ] **Step 2: Run to verify failure.** Expected: ImportError.
- [ ] **Step 3: Implement.**

```python
"""In-process forecast cache: a few hours of staleness is fine for a weather icon; a failure is never remembered."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


class ForecastCache:
    def __init__(self, ttl: timedelta, fetch):
        self._ttl, self._fetch, self._store = ttl, fetch, {}

    def get(self, stadium: str, kickoff_iso: str, now: datetime | None = None):
        now = now or datetime.now(timezone.utc)
        key = (stadium, kickoff_iso)
        hit = self._store.get(key)
        if hit and now - hit[0] < self._ttl:
            return hit[1]
        value = self._fetch(stadium, kickoff_iso, now)
        if value is not None:
            self._store[key] = (now, value)
        return value
```

- [ ] **Step 4: Wire the route.** In `routes.py`, build one module-level `ForecastCache(timedelta(hours=3), forecast_for)`; for each UPCOMING game (not started, not final) set `game["conditions"] = cache.get(game["stadium"], _kickoff_utc(game))` using `weather_cache._kickoff_utc`; omit the key when the result is `None`. Never call it for started or final games. Add a route test with a fake cache (monkeypatch the module-level cache) asserting: upcoming game has `conditions`; a final game has none; a `None` result leaves no key. Public-snapshot mode: the snapshot is precomputed by a scheduled job, so the job must call the same function at build time AND the API must refresh `conditions` at request time for upcoming games (a forecast baked into a snapshot goes stale); state which path the code takes in the PR description.
- [ ] **Step 5: Full suite; commit by name.** `feat: attach cached kickoff conditions to upcoming games`.

---

## Task 3 (hub, verified): `WeatherChip`

The chip is a picture then the words, always both. Wind is named only at 15 mph or more; a rain chance only when 30% or more and the sky is wet; a dome says "Indoors" and nothing else. An unknown `kind` or no conditions renders nothing.

**Files:** Create `packages/predictor-ui/src/components/WeatherChip.tsx`, `WeatherChip.test.tsx`; Modify `packages/predictor-ui/src/index.ts`.

- [ ] **Step 1: Write the tests.**

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { WeatherChip, weatherSentence, type Conditions, type WeatherKind } from "./WeatherChip";

describe("WeatherChip", () => {
  it("says the sky and the temperature in words", () => {
    render(<WeatherChip conditions={{ kind: "rain", temp_f: 50, wind_mph: 8, precip_pct: 70 }} />);
    expect(screen.getByTestId("weather-chip")).toHaveTextContent("Rain · 50°F · 70% chance");
  });

  it("names wind only when it matters", () => {
    expect(weatherSentence({ kind: "clear", temp_f: 61, wind_mph: 9 })).toBe("Clear · 61°F");
    expect(weatherSentence({ kind: "clear", temp_f: 61, wind_mph: 22 })).toBe("Clear · 61°F · 22 mph wind");
  });

  it("a dome says indoors and no temperature", () => {
    render(<WeatherChip conditions={{ kind: "dome", temp_f: 72, wind_mph: 30 }} />);
    expect(screen.getByTestId("weather-chip")).toHaveTextContent(/^Indoors$/);
  });

  it("renders nothing without conditions or with an unknown kind", () => {
    const { container, rerender } = render(<WeatherChip conditions={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<WeatherChip conditions={{ kind: "tornado" } as unknown as Conditions} />);
    expect(container).toBeEmptyDOMElement();
  });

  it.each(["clear", "partly", "cloudy", "fog", "rain", "snow", "storm", "dome"] as WeatherKind[])("%s draws an icon that is hidden from assistive tech", (kind) => {
    render(<WeatherChip conditions={{ kind }} />);
    const svg = screen.getByTestId("weather-chip").querySelector("svg")!;
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg.childElementCount).toBeGreaterThan(0);
  });

  it("a rain chance under 30% is not announced", () => {
    expect(weatherSentence({ kind: "rain", temp_f: 50, precip_pct: 20 })).toBe("Rain · 50°F");
  });
});
```

- [ ] **Step 2: Run to verify failure.** Run: `cd packages/predictor-ui && npx vitest run src/components/WeatherChip.test.tsx` Expected: cannot resolve `./WeatherChip`.

- [ ] **Step 3: Write the component.**

```tsx
/**
 * Kickoff-hour conditions as one small chip: a picture, then the words. The words are always there, so the picture
 * never has to carry the meaning alone, and a screen reader gets the same sentence as everyone else.
 *
 * `conditions` is the object the sport API serves (`kind`, `temp_f`, `wind_mph`, `precip_pct`). The WMO-code-to-kind
 * mapping lives in the API, once; this component only draws a `kind` it knows and renders NOTHING for one it does not,
 * because an unknown sky drawn as a guessed one is a false statement. No conditions, no chip.
 */
export type WeatherKind = "clear" | "partly" | "cloudy" | "fog" | "rain" | "snow" | "storm" | "dome";

export type Conditions = {
  kind: WeatherKind;
  temp_f?: number | null;
  wind_mph?: number | null;
  precip_pct?: number | null;
};

const WORDS: Record<WeatherKind, string> = {
  clear: "Clear", partly: "Partly cloudy", cloudy: "Cloudy", fog: "Fog", rain: "Rain", snow: "Snow", storm: "Storms", dome: "Indoors",
};

/** Wind worth naming on a football field. Below this it is noise. */
export const WINDY_MPH = 15;

const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" } as const;

function Icon({ kind }: { kind: WeatherKind }) {
  const cloud = <path d="M7 18h9.5a3.5 3.5 0 0 0 .4-6.98A5 5 0 0 0 7.3 9.6 4.2 4.2 0 0 0 7 18Z" />;
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false" {...stroke}>
      {kind === "clear" && (<><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>)}
      {kind === "partly" && (<><circle cx="8" cy="8" r="3" /><path d="M8 2v1.5M2 8h1.5M3.8 3.8l1 1M12.2 3.8l-1 1" /><g transform="translate(2 2)">{cloud}</g></>)}
      {kind === "cloudy" && cloud}
      {kind === "fog" && (<><path d="M5 9h14M3 13h18M6 17h12" /></>)}
      {kind === "rain" && (<>{cloud}<path d="M9 20l-1 2M13 20l-1 2M17 20l-1 2" /></>)}
      {kind === "snow" && (<>{cloud}<path d="M9 20.5h.01M13 21.5h.01M17 20.5h.01" strokeWidth={2.6} /></>)}
      {kind === "storm" && (<>{cloud}<path d="M12.5 15l-2.5 4h3l-2 3" /></>)}
      {kind === "dome" && (<><path d="M3 18a9 9 0 0 1 18 0" /><path d="M2 18h20M12 9V6" /></>)}
    </svg>
  );
}

export function weatherSentence(c: Conditions): string {
  const parts = [WORDS[c.kind]];
  if (c.kind !== "dome") {
    if (typeof c.temp_f === "number") parts.push(`${Math.round(c.temp_f)}°F`);
    if (typeof c.wind_mph === "number" && c.wind_mph >= WINDY_MPH) parts.push(`${Math.round(c.wind_mph)} mph wind`);
    if (typeof c.precip_pct === "number" && c.precip_pct >= 30 && (c.kind === "rain" || c.kind === "snow" || c.kind === "storm")) {
      parts.push(`${Math.round(c.precip_pct)}% chance`);
    }
  }
  return parts.join(" · ");
}

export function WeatherChip({ conditions }: { conditions?: Conditions | null }) {
  if (!conditions || !(conditions.kind in WORDS)) return null;
  const sentence = weatherSentence(conditions);
  return (
    <span
      data-testid="weather-chip"
      data-kind={conditions.kind}
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-pr border border-pr-rule px-1.5 py-0.5 font-pr-body text-xs text-pr-text-dim"
    >
      <Icon kind={conditions.kind} />
      <span>{sentence}</span>
    </span>
  );
}
```

- [ ] **Step 4: Export and run.** Add to `src/index.ts`: `export { WeatherChip, weatherSentence, WINDY_MPH, type Conditions, type WeatherKind } from "./components/WeatherChip";` Run: `cd packages/predictor-ui && npx vitest run` and `npx tsc --noEmit`. Expected: pass, clean.

- [ ] **Step 5: Commit.** `git add packages/predictor-ui/src/components/WeatherChip.tsx packages/predictor-ui/src/components/WeatherChip.test.tsx packages/predictor-ui/src/index.ts && git commit -m "feat(ui): WeatherChip, the kickoff conditions as a picture and words"`

## Task 4 (hub, verified): `RankDuel`

Two bars, one per unit, full for first in the league and a stub for last, with the rank printed beside each. An impossible rank throws instead of drawing.

**Files:** Create `packages/predictor-ui/src/components/RankDuel.tsx`, `RankDuel.test.tsx`; Modify `index.ts`.

- [ ] **Step 1: Write the tests.**

```tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RankDuel, RankOutOfRangeError, rankFill } from "./RankDuel";

const base = { attacker: "Bills", attackerStat: "passing offence", attackerRank: 3, defender: "Jets", defenderStat: "pass defence", defenderRank: 28, nTeams: 32 };

describe("rankFill", () => {
  it("first is full, last is a stub, never empty", () => {
    expect(rankFill(1, 32)).toBe(1);
    expect(rankFill(32, 32)).toBe(1 / 32);
  });
  it.each([[0, 32], [33, 32], [1.5, 32], [3, 1]])("refuses rank %s of %s", (r, n) => {
    expect(() => rankFill(r, n)).toThrow(RankOutOfRangeError);
  });
});

describe("RankDuel", () => {
  it("prints both ranks and league size beside the bars", () => {
    render(<RankDuel {...base} />);
    const duel = screen.getByTestId("rank-duel");
    expect(duel).toHaveTextContent("Bills · passing offence");
    expect(duel).toHaveTextContent("#3 of 32");
    expect(duel).toHaveTextContent("#28 of 32");
  });
  it("draws the strong unit long and the weak one short", () => {
    render(<RankDuel {...base} />);
    const [a, d] = screen.getAllByTestId("rank-fill");
    expect(a).toHaveStyle({ width: "93.8%" });
    expect(d).toHaveStyle({ width: "15.6%" });
  });
  it("refuses an impossible rank instead of drawing it", () => {
    expect(() => render(<RankDuel {...base} defenderRank={40} />)).toThrow(RankOutOfRangeError);
  });
});
```

- [ ] **Step 2: Run to verify failure.** Expected: cannot resolve `./RankDuel`.

- [ ] **Step 3: Write the component.**

```tsx
/**
 * One offence-versus-defence duel as two bars. A bar is how good the unit ranks: full is first of the league, a stub is
 * last. The rank is always printed beside its bar, so the bar is a picture of the words and never the only carrier.
 *
 * Every number drawn here (the two ranks and the league size) is the same number the row's headline states; the
 * caller passes the headline separately and `SignalRows`-style figure checks apply to it (see MatchupBrief).
 */
export type RankDuelProps = {
  attacker: string;
  attackerStat: string;
  attackerRank: number;
  defender: string;
  defenderStat: string;
  defenderRank: number;
  nTeams: number;
};

export class RankOutOfRangeError extends Error {
  constructor(rank: number, n: number) {
    super(`rank ${rank} is not within 1..${n}`);
    this.name = "RankOutOfRangeError";
  }
}

/** Share of the track to fill: 1st of n is 100%, last of n is 1/n. Throws rather than drawing an impossible bar. */
export function rankFill(rank: number, n: number): number {
  if (!Number.isInteger(rank) || !Number.isInteger(n) || n < 2 || rank < 1 || rank > n) throw new RankOutOfRangeError(rank, n);
  return (n - rank + 1) / n;
}

function Bar({ team, stat, rank, n, tone }: { team: string; stat: string; rank: number; n: number; tone: string }) {
  const pct = Math.round(rankFill(rank, n) * 1000) / 10;
  return (
    <div className="min-w-0 flex-1">
      <div className="flex items-baseline justify-between gap-2 font-pr-body text-xs text-pr-text-dim">
        <span className="truncate">{team} · {stat}</span>
        <span className="font-pr-display text-sm font-semibold text-pr-text">#{rank}<span className="text-pr-text-faint"> of {n}</span></span>
      </div>
      <div className="mt-1 h-1.5 rounded-pr bg-pr-panel-2" role="presentation">
        <div data-testid="rank-fill" className={`h-1.5 rounded-pr ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export function RankDuel(p: RankDuelProps) {
  return (
    <div data-testid="rank-duel" className="flex flex-col gap-2 sm:flex-row sm:gap-4">
      <Bar team={p.attacker} stat={p.attackerStat} rank={p.attackerRank} n={p.nTeams} tone="bg-pr-accent" />
      <Bar team={p.defender} stat={p.defenderStat} rank={p.defenderRank} n={p.nTeams} tone="bg-pr-fill-mute" />
    </div>
  );
}
```

- [ ] **Step 4: Export and run.** Add `export { RankDuel, rankFill, RankOutOfRangeError, type RankDuelProps } from "./components/RankDuel";` to `index.ts`. Run: `cd packages/predictor-ui && npx vitest run` and `npx tsc --noEmit`. Expected: pass.

- [ ] **Step 5: Commit** by name: `feat(ui): RankDuel, one offence-versus-defence matchup as two bars`.

## Task 5 (hub, component verified; panel switch drafted): `MatchupBrief`, the Edge / Risk / Price grouping

**Why:** `FactorList` already marks each row "for the pick" / "against it" / "context" and refuses colour-only meaning. This adds the grouping a reader scans: three labelled groups, matchup rows carrying a `RankDuel`, Price shown only when present.

**Files:** Create `packages/predictor-ui/src/components/MatchupBrief.tsx`, `MatchupBrief.test.tsx`; Modify `ExplainerPanel.tsx` (use `MatchupBrief` when any factor carries `slot`, else `FactorList` exactly as before), `index.ts`.

**Interfaces:**
- Consumes: `Factor` (now with optional `slot?: "edge" | "risk" | "price" | "context"`), `RankDuel`, and `matchups?: MatchupRow[]` from the response context (`id, attacker, defender, stat, foil, attacker_rank, defender_rank, n_teams, toward_pick`).
- Produces: `MatchupBrief({ factors, matchups })`; `groupBySlot(factors) -> { edge, risk, price, context }`.

- [ ] **Step 1: Write the failing tests.**

```tsx
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MatchupBrief, groupBySlot } from "./MatchupBrief";

const duel = { id: "pass_off_vs_pass_def:home", attacker: "Bills", defender: "Jets", stat: "passing offence", foil: "pass defence", attacker_rank: 3, defender_rank: 28, n_teams: 32, toward_pick: true };
const factors = [
  { key: "matchup:pass_off_vs_pass_def:home", direction: "up" as const, slot: "edge" as const, headline: "Bills' #3 passing offence meets Jets' #28 pass defence", text: "t" },
  { key: "spread", direction: "neutral" as const, slot: "price" as const, headline: "Model -4.0 against a quoted -6.5", text: "t" },
];

describe("groupBySlot", () => {
  it("keeps order within a slot and drops nothing", () => {
    const g = groupBySlot([...factors, { ...factors[0], key: "matchup:b" }]);
    expect(g.edge.map((f) => f.key)).toEqual(["matchup:pass_off_vs_pass_def:home", "matchup:b"]);
    expect(g.price).toHaveLength(1);
  });
});

describe("MatchupBrief", () => {
  it("labels the groups and draws the duel for a matchup row", () => {
    render(<MatchupBrief factors={factors} matchups={[duel]} />);
    expect(screen.getByRole("heading", { name: "Edge" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Price" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Risk" })).toBeNull();   // an empty slot is omitted, not padded
    expect(within(screen.getByTestId("rank-duel")).getByText("#28", { exact: false })).toBeInTheDocument();
  });

  it("refuses a duel whose ranks the headline does not state", () => {
    const bad = [{ ...factors[0], headline: "Bills have the edge in the air" }];
    expect(() => render(<MatchupBrief factors={bad} matchups={[duel]} />)).toThrow(/headline/i);
  });

  it("a matchup factor with no matching row in matchups is not drawn as a duel", () => {
    render(<MatchupBrief factors={factors} matchups={[]} />);
    expect(screen.queryByTestId("rank-duel")).toBeNull();
    expect(screen.getByText(/#3 passing offence/)).toBeInTheDocument();   // the words still render
  });
});
```

- [ ] **Step 2: Run to verify failure.** Expected: cannot resolve `./MatchupBrief`.
- [ ] **Step 3: Implement.**

```tsx
import { FactorList, type Factor } from "./FactorList";
import { RankDuel } from "./RankDuel";

export type Slot = "edge" | "risk" | "price" | "context";
export type SlottedFactor = Factor & { slot?: Slot };
export type MatchupRow = {
  id: string; attacker: string; defender: string; stat: string; foil: string;
  attacker_rank: number; defender_rank: number; n_teams: number; toward_pick: boolean | null;
};

const TITLES: Record<Exclude<Slot, "context">, string> = { edge: "Edge", risk: "Risk", price: "Price" };

export function groupBySlot(factors: SlottedFactor[]): Record<Slot, SlottedFactor[]> {
  const out: Record<Slot, SlottedFactor[]> = { edge: [], risk: [], price: [], context: [] };
  for (const f of factors) out[f.slot ?? "context"].push(f);
  return out;
}

export class DuelHeadlineMismatchError extends Error {
  constructor(key: string) {
    super(`headline of ${key} does not state both ranks its duel draws`);
    this.name = "DuelHeadlineMismatchError";
  }
}

/** Same rule as SignalRows: the numbers drawn must be the numbers written. */
function assertStates(f: SlottedFactor, m: MatchupRow) {
  const nums = (f.headline.match(/\d+/g) ?? []).map(Number);
  if (!nums.includes(m.attacker_rank) || !nums.includes(m.defender_rank)) throw new DuelHeadlineMismatchError(f.key);
}

function Row({ factor, matchup }: { factor: SlottedFactor; matchup?: MatchupRow }) {
  if (matchup) assertStates(factor, matchup);
  return (
    <li className="py-2">
      <p className="font-pr-body text-sm text-pr-text">{factor.headline}</p>
      {matchup && (
        <div className="mt-2">
          <RankDuel attacker={matchup.attacker} attackerStat={matchup.stat} attackerRank={matchup.attacker_rank}
                    defender={matchup.defender} defenderStat={matchup.foil} defenderRank={matchup.defender_rank} nTeams={matchup.n_teams} />
        </div>
      )}
      {factor.text && <p className="mt-1 font-pr-body text-xs text-pr-text-dim">{factor.text}</p>}
    </li>
  );
}

export function MatchupBrief({ factors, matchups = [] }: { factors: SlottedFactor[]; matchups?: MatchupRow[] }) {
  const groups = groupBySlot(factors);
  const byKey = new Map(matchups.map((m) => [`matchup:${m.id}`, m]));
  return (
    <div className="flex flex-col gap-4">
      {(Object.keys(TITLES) as (keyof typeof TITLES)[]).map((slot) =>
        groups[slot].length === 0 ? null : (
          <section key={slot} aria-labelledby={`brief-${slot}`}>
            <h3 id={`brief-${slot}`} className="font-pr-display text-xs font-semibold uppercase tracking-wide text-pr-text-faint">{TITLES[slot]}</h3>
            <ul className="divide-y divide-pr-rule">
              {groups[slot].map((f) => <Row key={f.key} factor={f} matchup={byKey.get(f.key)} />)}
            </ul>
          </section>
        ),
      )}
      {groups.context.length > 0 && <FactorList factors={groups.context} />}
    </div>
  );
}
```

`FactorList` takes `factors` plus optional `onSelect`, `highlighted`, `expanded`, `onToggle`, `expandable`; `MatchupBrief` passes only `factors` for the context group (run verified: 4 tests, `tsc --noEmit` clean). Wiring `highlighted`/`onSelect` through the brief (so a row lights its figure, spec 13c) is part of the panel switch below.
- [ ] **Step 4: Export and run the hub suite.** Add `export { MatchupBrief, groupBySlot, DuelHeadlineMismatchError, type MatchupRow, type SlottedFactor, type Slot } from "./components/MatchupBrief";` to `index.ts`. Run `cd packages/predictor-ui && npx vitest run` and `npx tsc --noEmit`. Expected: pass. In `ExplainerPanel.tsx`, switch to `MatchupBrief` only when `data.factors.some(f => f.slot)`; add a test that a response without `slot` renders exactly the old `FactorList` (existing tests must pass unchanged).
- [ ] **Step 5: Design pass (impeccable).** Add `MatchupBrief` states to the hub harness (`packages/predictor-ui/harness`): full (2 Edge, 1 Risk, 1 Price), Edge only, no matchups, long team names. ONE batched round of screenshots at desktop and 390px; fix everything in one batch; one confirming round. Attach to the PR.
- [ ] **Step 6: Commit** by name: `feat(ui): MatchupBrief groups the summary into Edge, Risk and Price`.

---

## Task 6 (NFL site, DRAFTED): mount the weather chip

**Depends on:** hub PR-1 merged; NFL API Task 2 merged.

- [ ] **Step 1:** In the hub worktree, run `scripts/sync-ui.mjs --from <full hub sha> --to ../NFL_Predictor/frontend/src/vendor/predictor-ui` (use the exact invocation from the repo's `scripts/` header; never `--vendor-anyway`). Commit the vendored copy in an NFL branch.
- [ ] **Step 2:** Find where a game's kickoff time is rendered (`grep -rn "kickoff\|MatchCard" frontend/src`). Mount `<WeatherChip conditions={game.conditions} />` directly after the kickoff time on the game card and at the top of the game detail. No extra wrapper row when `conditions` is absent.
- [ ] **Step 3: Failing test first.** Render the card with a game carrying `conditions: { kind: "rain", temp_f: 50, wind_mph: 18, precip_pct: 70 }` and assert the chip text `Rain · 50°F · 18 mph wind · 70% chance`; render without `conditions` and assert no `weather-chip`.
- [ ] **Step 4:** `npm run build` plus the full vitest suite. Screenshots (desktop + 390px) of: dome game, rain, clear, windy, no conditions. One batched round, one fix pass.
- [ ] **Step 5:** PR; wait for CI and CodeRabbit to finish before merging (full-SHA gate).

## Task 7 (CFB, DRAFTED): the same for college

- [ ] **Step 1:** CFB has no `STADIUM_COORDS` table. Task 0 of this task: build one from CFBD venue data already fetched by the app (venue latitude/longitude) if present, else from a one-time `/venues` call (1 call). Venue `dome`/`grass` flags give the indoor set. Commit as `data/venue_coords.json` with a test that every FBS home venue in the current schedule resolves (list the misses; do not guess coordinates for them, those games simply get no chip).
- [ ] **Step 2:** Port `forecast.py` and its tests, keyed by venue id. Reuse the exact `_KINDS` table; keep the two copies identical (header comment) because the repos share no package.
- [ ] **Step 3:** Attach `conditions` as in Task 2; sync UI; mount the chip as in Task 6; build, tests, screenshots, PR.

---

# Part A: the summary

## Task 8 (all four sites, DRAFTED): render the new summary

**Depends on:** AI plan Tasks 3-6 (API `context.matchups`, explainer `slot`) deployed for that sport.

- [ ] **Step 1:** After hub PR-1 merges, re-sync `predictor-ui` into NFL, CFB, PL and NBA (one PR per site, vendored copy only, with the sync script's output in the description).
- [ ] **Step 2:** Pass `matchups` from the response `context.matchups` into `ExplainerPanel` (props added in Task 5). Where a site builds its own panel props, add `matchups` there; the old `Explanation` shape stays valid because `slot` and `matchups` are optional.
- [ ] **Step 3: Failing test per site.** With a recorded explainer response carrying one Edge duel, one Risk duel and a Price factor, assert the three headings, two `rank-duel` elements and the stated ranks. With a legacy response (no `slot`), assert the old layout is unchanged. NBA: assert no Price heading ever appears.
- [ ] **Step 4:** Per site: `npm run build` + full vitest; desktop + 390px screenshots of the summary in each of: full, Edge only, no matchups (LLM off, template path), finished game (no Edge/Risk rows). One batched round, one fix pass.
- [ ] **Step 5:** PR per site; full-SHA gate after CI and CodeRabbit finish. Deploy per site with `scripts/deploy-site.sh`, then check the live page.

## Self-review

Coverage: weather icon from Open-Meteo (Tasks 1-3, 6-7: forecast, icon kinds sun/cloud/rain/snow/storm/fog/indoors, dome handling, failure means no chip, source labelled); AI summary UI (Tasks 4, 5, 8: Edge/Risk/Price, offence-versus-defence rank duel, empty slots omitted, legacy responses unchanged, NBA has no Price). Placeholders: Tasks 2, 5-8 are drafted code with the unverified parts named (`FactorList` props, the games-route insertion point, CFB venue data). Names used consistently across tasks: `Conditions`/`WeatherKind`, `forecast_for`, `kind_for`, `RankDuel`, `rankFill`, `MatchupRow`, `SlottedFactor`, `groupBySlot`, `MatchupBrief`.
