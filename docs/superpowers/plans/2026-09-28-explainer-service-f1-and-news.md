# The Explainer Service: F1 Served, and Team News That Can Explain an Injury — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve F1 instead of refusing it, and make dated ESPN team news able to change an explanation — so a midweek injury is reflected rather than outlived.

**Architecture:** Two independent changes to one FastAPI service, in one repo. (1) `f1` joins `SERVED_SPORTS`; its facts already carry what it needs. (2) A resolver maps a fixture's team names onto the forms ESPN headlines actually use, and the newest matched headline's **date** joins the cache key, so news newer than the summary regenerates it exactly once.

**Tech Stack:** Python 3.12, FastAPI, httpx, pytest, SQLite cache. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-28-explainer-panel-flow-trigger-and-news-design.md` (§4 F1, §Team news). The plan argues from the spec; the spec travels with it.

## Global Constraints

- **Honesty rules, inherited from the branch merged as `c617ef7`.** A reader is never shown a figure withheld without being told; never told a "line" that is not the market's; never told a claim the numbers do not support. Any sentence this plan adds must be true for every bundle that reaches it.
- **No test may be a guard that can be silenced.** For every assertion written here, construct the mutation to the source it would survive, run it, and record the result. A surviving mutation is a finding, not a nuisance.
- **Never invent injuries.** The model may only report a headline it was given. This is why the prompt change is an instruction, not new data.
- **News is a bonus.** `news.py` already swallows every ESPN failure and returns `[]`. Nothing in this plan may make an explanation fail because news did.
- **Tests never touch the network.** ESPN is mocked with `respx`; the sibling-repo probe uses `git` plumbing, never a checkout.
- **No commit reaches `main` without review.** `superpowers:requesting-code-review` per task.
- **Never rebase, never force-push, never push to `main`.** Commit on the branch, push the branch.
- **Commit with `git commit -F <file>`.** Never let a message print to stdout instead of interpolating; that has shipped two empty commits in this project.
- **Do not use `git checkout --` to recover.** It has reverted unrelated work three times here. If you need to undo something, do it deliberately and re-verify.
- **Verify against `origin/main`, not a local branch.** Several sport repos' local `main` are 100+ commits stale.

---

## File Structure

| File | Responsibility |
|---|---|
| `explainer/config.py` | Which sports are answered. One line changes here. |
| `explainer/news.py` | **New.** Maps a fixture's team names to the forms ESPN uses. Pure, no I/O — so it is testable without a network and without `respx`. |
| `explainer/service.py` | Calls the resolver, and puts the news date in the cache key. |
| `explainer/prompts.py` | One instruction telling the model to lead with lineup news and date it. |
| `tests/test_news_names.py` | **New.** The resolver, and the anti-rot coverage tests. |
| `tests/test_news_freshness.py` | **New.** The key changes when the news date moves, and not otherwise. |
| `tests/test_f1_served.py` | **New.** F1 answers, and what it answers is honest. |
| `tests/test_unserved_sport.py` | **Modify.** The existing relationship guards; `f1` now joins the served set. |

`news.py` is the only new module. It is deliberately I/O-free so the resolver can
be tested as a pure function — the current `headlines()` does its matching
inline, which is why the matching could not be tested without a mocked HTTP layer.

---

## Task 1: Serve F1

**Files:**
- Modify: `explainer/config.py:39`
- Test: `tests/test_f1_served.py` (create)

**Interfaces:**
- Consumes: nothing. This task is first because it is the smallest and it unblocks a site PR.
- Produces: `SERVED_SPORTS` containing `"f1"`. Task 4's F1 site PR depends on it; nothing else in this plan does.

- [ ] **Step 1: Write the failing test**

Create `tests/test_f1_served.py`:

```python
"""F1 is served, and what it says about a session is true.

This reverses a recorded decision. `SERVED_SPORTS` omitted `f1` because "a win
probability IS the explanation" -- which remains true of the win probability, and
was never an argument against the race story around it. The reversal is recorded
in the spec and in the ledger; this file is its enforcement.

F1's facts carry `win`, `podium`, `points` and `dnf` and NO line, so the spread
and total factors must not fire. That is not a degradation: a `KeyNumberTile`
comparing the model to a book would have nothing honest to draw, which was the
original reason, and it still holds for THOSE elements.
"""
from explainer.config import SERVED_SPORTS
from explainer.template import explain_from_template


def _f1_facts(**over):
    base = {
        "sport": "f1", "id": "s1", "title": "2026 Bahrain Grand Prix",
        "starts_at": "2026-03-15T15:00:00Z", "status": "upcoming",
        "pick_timing": "pre_kickoff", "pick": {"label": "Lando Norris", "prob": 0.34},
        "markets": [
            {"market": "win", "model": {
                "Lando Norris": 0.34, "Max Verstappen": 0.29, "Oscar Piastri": 0.24}},
            {"market": "podium", "model": {"Lando Norris": 0.88}},
        ],
        "drivers": [{"name": "Lando Norris"}, {"name": "Max Verstappen"}],
        "context": {}, "players": [],
        "record": {"label": "Picks made before the session", "hits": 9, "settled": 20},
        "result": None,
    }
    base.update(over)
    return base


def test_f1_is_served():
    assert "f1" in SERVED_SPORTS, (
        f"f1 is not in SERVED_SPORTS={SERVED_SPORTS}. The refusal was reversed: "
        f"a win probability is the explanation, but the race story around it is "
        f"not, and F1's facts carry it."
    )


def test_f1_gets_a_pick_and_a_record_and_nothing_it_cannot_support():
    out = explain_from_template(_f1_facts())
    keys = [f["key"] for f in out["factors"]]
    assert keys, f"F1 produced no factors at all: {out}"
    assert "spread" not in keys, (
        f"F1 has no spread market and no line; a spread factor here would be "
        f"narrating a disagreement with a book that quoted nothing: {keys}"
    )
    assert "total" not in keys, f"F1's `points` market is not a `total`: {keys}"


def test_f1_names_the_session_not_a_kickoff():
    """A rebuilt session says the session, because `_START["f1"]` exists for
    exactly that and the default would say "kickoff"."""
    out = explain_from_template(_f1_facts(pick_timing="rebuilt"))
    text = " ".join(f["text"] for f in out["factors"])
    assert "after the session started" in text, text
    assert "kickoff" not in text, text
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd services/explainer
uv run --extra dev python -m pytest tests/test_f1_served.py -q -p no:cacheprovider
```

Expected: `test_f1_is_served` FAILS on the `assert "f1" in SERVED_SPORTS`. The
other two may pass — they are forward guards and the harness will prove they earn
their place.

- [ ] **Step 3: Make the minimal change**

In `explainer/config.py`, line 39:

```python
SERVED_SPORTS = ("pl", "nfl", "cfb", "nba")
```

becomes:

```python
#: F1 was refused here and is now served. The original reason -- "a win
#: probability IS the explanation" -- was true of the win probability and was
#: never an argument against the race story around it, which is what F1's
#: `drivers` and `podium` carry. F1 still gets a REDUCED panel: it has no line,
#: so the spread and total factors must not fire, and that half of the original
#: reason still stands. Reversed by
#: docs/superpowers/specs/2026-09-28-explainer-panel-flow-trigger-and-news-design.md
#: section 4; the ledger records the reversal alongside the ruling it replaces.
SERVED_SPORTS = ("pl", "nfl", "cfb", "nba", "f1")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd services/explainer
uv run --extra dev python -m pytest tests/test_f1_served.py -q -p no:cacheprovider
```

Expected: 3 passed.

- [ ] **Step 5: Run the whole suite, and expect the refusal guards to need updating**

```bash
cd services/explainer
uv run --extra dev python -m pytest -q -p no:cacheprovider
```

`tests/test_unserved_sport.py` derives `UNSERVED` from `SPORTS - SERVED_SPORTS`,
so `f1` leaves that tuple automatically. **If a test fails, read it before
changing it** — a failure here is a guard noticing the reversal, which is what it
is for. `test_nba_is_in_the_served_list_and_f1_is_not` asserts
`set(UNSERVED) == {"f1"}` and will now fail: rename it and assert
`set(UNSERVED) == set()`, keeping the relationship assertion and stating that an
empty refusal list is now the intended end state.

- [ ] **Step 6: Commit**

```bash
git add explainer/config.py tests/test_f1_served.py tests/test_unserved_sport.py
git commit -F /tmp/task1-f1.txt
```

Message: `feat(explainer): serve f1 — the refusal was about the win probability, not the race story`

- [ ] **Step 7: Review gate**

Dispatch `superpowers:requesting-code-review` for this commit. Do not proceed to
Task 2 on an unreviewed commit.

---

## Task 2: A resolver for the team names ESPN actually uses

**Files:**
- Create: `explainer/news.py` — **append** to the existing module, do not replace it
- Test: `tests/test_news_names.py` (create)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `news_names(sport: str, title: str) -> list[str]` — the names to match a headline against, longest-first, or `[]` when nothing resolves. Task 3 consumes it from `service.py`.

**Why a new function and not a change to `headlines()`:** `headlines()` does its
matching inline behind an `httpx` call, so the matching cannot be tested as a
pure function. Extracting it is what makes it testable at all, and the test is the
point: the current resolver is what stops this working.

**The two sports need different treatments, and conflating them is the bug:**

- **NFL** — the fixture title is abbreviations. `"MIA at BOS"` must resolve to
  `["miami", "chicago bears"]`. ESPN writes "Chicago Bears"; nothing in the
  bundle says "Bears".
- **PL** — the title already carries football-data.co.uk *canonical short* names
  (`pl_predictor/data/team_names.py`): "Man City", "Nott'm Forest", "Wolves".
  ESPN writes "Manchester City", "Nottingham Forest", "Wolves". So PL needs a
  different alias, not a bigger version of NFL's.

- [ ] **Step 1: Write the failing test**

Create `tests/test_news_names.py`:

```python
"""The names a headline is matched against, and why the current ones miss.

`service._news_terms` splits the fixture title on " at " / " v " / " vs " / " @ ",
so "MIA at BOS" yields ["MIA", "BOS"] -- and ESPN's headlines say "Chicago Bears".
For PL the title already carries canonical short names ("Man City",
"Nott'm Forest") while ESPN says "Manchester City", "Nottingham Forest". Neither
sport matches, and a miss is silent: the model is handed an empty NEWS block and
nothing says so.

The coverage tests at the bottom are the anti-rot half. An alias table is data
that goes stale, and the only way it goes stale quietly is a new team.
"""
from explainer.news import news_names


def test_nfl_resolves_abbreviations_to_the_forms_espn_writes():
    assert news_names("nfl", "MIA at BOS") == ["miami", "chicago bears"]


def test_pl_resolves_canonical_short_names():
    assert news_names("pl", "Man City v Arsenal") == ["man city", "arsenal"]


def test_pl_expands_the_names_that_differ():
    names = news_names("pl", "Nott'm Forest v Wolves")
    assert "nottingham forest" in names, names
    assert "wolves" in names, names


def test_a_name_it_cannot_resolve_is_left_alone_rather_than_guessed():
    """An unresolved name falls through as itself. A miss yields no news, which is
    the safe direction -- a wrong alias yields news about the WRONG TEAM, which
    would put another franchise's injury in this game's panel."""
    assert news_names("nfl", "XYZ at BOS") == ["xyz", "chicago bears"]


def test_nothing_resolvable_is_an_empty_list_not_a_guess():
    assert news_names("nfl", "") == []


def test_every_nfl_abbreviation_in_the_committed_snapshot_has_an_alias():
    """Anti-rot. A new abbreviation fails here until it is added, rather than
    quietly matching nothing forever."""
    import json
    import subprocess

    from explainer.news import NFL_ALIASES

    raw = subprocess.run(
        ["git", "-C", NFL_REPO, "show", "origin/main:data/public_snapshot.json"],
        capture_output=True, text=True, check=True).stdout.replace("\r\n", "\n")
    games = [g for w in json.loads(raw)["weeks"].values() for g in (w.get("games") or [])]
    abbrs = {t for g in games for t in (g.get("home_team"), g.get("away_team")) if t}
    missing = sorted(a for a in abbrs if a.lower() not in NFL_ALIASES)
    assert not missing, (
        f"these NFL abbreviations have no alias, so a headline about them would "
        f"never match: {missing}. Add each to NFL_ALIASES in news.py."
    )


def test_every_pl_canonical_name_has_an_alias():
    """Anti-rot, from PL's own canonical list rather than a hand-kept copy."""
    import re
    import subprocess

    from explainer.news import PL_ALIASES

    src = subprocess.run(
        ["git", "-C", PL_REPO, "show", "origin/main:src/pl_predictor/data/team_names.py"],
        capture_output=True, text=True, check=True).stdout
    canonical = set(re.findall(r'^\s{4}"([^"]+)":\s*"', src, re.M))
    assert canonical, "could not read PL's canonical team names; the test would pass vacuously"
    missing = sorted(c for c in canonical if c.lower() not in PL_ALIASES)
    assert not missing, (
        f"these PL canonical names have no alias: {missing}. A name absent here "
        f"matches only its own short form, which ESPN does not use for "
        f"Man City or Nott'm Forest."
    )
```

The two sibling repos are resolved with the **same scheme the existing probe in
`tests/test_unserved_sport.py` uses** — env var first, then every parent directory,
first hit with a `.git` wins. Do not use a fixed `parents[N]` index: the depth
depends on where the worktree sits, and in this tree `parents[3]` is the worktree
while `parents[4]` is the directory the siblings actually live in.

```python
import os
from pathlib import Path

_HERE = Path(__file__).resolve()


def _sibling(name: str, env: str) -> Path:
    candidates = [Path(os.environ[env])] if os.environ.get(env) else []
    candidates += [p / name for p in _HERE.parents]
    root = next((c for c in candidates if (c / ".git").exists()), None)
    assert root is not None, (
        f"{name} not found beside this repo, so the anti-rot check is UNVERIFIED "
        f"rather than true. Set {env}. Looked in {[str(c) for c in candidates[:4]]}"
    )
    return root


NFL_REPO = _sibling("NFL_Predictor", "NFL_REPO")
PL_REPO = _sibling("PL_Predictor", "PL_REPO")
```

**If a sibling repo is absent these resolve by failing the module, not skipping.**
A skip would make the anti-rot guarantee unverifiable behind a green suite, which
is the failure this project keeps hitting. Both prerequisites are documented in
`services/explainer/README.md`'s Tests section alongside the existing `NBA_REPO` note.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd services/explainer
uv run --extra dev python -m pytest tests/test_news_names.py -q -p no:cacheprovider
```

Expected: collection error — `explainer.news` has no `news_names`. That is a
legitimate red; the import error is the "function not defined" of this plan.

- [ ] **Step 3: Implement the resolver**

Append to `explainer/news.py`:

```python
# --------------------------------------------------------------------------
# Team names, in the forms ESPN headlines actually use.
#
# Split out of `headlines()` so it can be tested as a pure function. While the
# matching lived inline behind an httpx call, the only way to test it was to mock
# a news feed -- and a mocked feed contains whatever names the test put in it, so
# the test could not notice that the real names did not match. That is how a
# silent miss survived: the service was fed an empty NEWS block for every fixture
# and nothing said so.
#
# Two sports, two different problems, and conflating them is the bug:
#
#   NFL  the title is ABBREVIATIONS. "MIA at BOS" -> Miami, Chicago Bears.
#   PL   the title is already football-data.co.uk CANONICAL SHORT names --
#        "Man City", "Nott'm Forest" -- while ESPN writes "Manchester City",
#        "Nottingham Forest". A bigger NFL table does not fix this.
#
# A name with no entry falls through as itself rather than being guessed. An
# unresolved name yields no news, which is safe; a WRONG alias yields news about
# another franchise, which would put their injury in this game's panel.
# --------------------------------------------------------------------------

NFL_ALIASES: dict[str, str] = {
    "ARI": "arizona cardinals", "ATL": "atlanta falcons", "BAL": "baltimore ravens",
    "BUF": "buffalo bills", "CAR": "carolina panthers", "CHI": "chicago bears",
    "CIN": "cincinnati bengals", "CLE": "cleveland browns", "DAL": "dallas cowboys",
    "DEN": "denver broncos", "DET": "detroit lions", "GB": "green bay packers",
    "HOU": "houston texans", "IND": "indianapolis colts", "JAC": "jacksonville jaguars",
    "KC": "kansas city chiefs", "LV": "las vegas raiders", "LAC": "los angeles chargers",
    "LAR": "los angeles rams", "MIA": "miami dolphins", "MIN": "minnesota vikings",
    "NE": "new england patriots", "NO": "new orleans saints", "NYG": "new york giants",
    "NYJ": "new york jets", "PHI": "philadelphia eagles", "PIT": "pittsburgh steelers",
    "SEA": "seattle seahawks", "SF": "san francisco 49ers", "TB": "tampa bay buccaneers",
    "TEN": "tennessee titans", "WAS": "washington commanders",
}

PL_ALIASES: dict[str, str] = {
    "man city": "manchester city",
    "nott'm forest": "nottingham forest",
    "nottm forest": "nottingham forest",
    "wolves": "wolves",
    "spurs": "tottenham hotspur",
    "newcastle": "newcastle united",
    "brighton": "brighton and hove albion",
    "west ham": "west ham united",
    "west brom": "west bromwich albion",
    "leeds": "leeds united",
    "sheffield united": "sheffield united",
    "ipswich": "ipswich town",
    "leicester": "leicester city",
    "forest": "nottingham forest",
}

_SPLIT = re.compile(r"\s+(?:at|v|vs\.?|@)\s+", re.IGNORECASE)


def news_names(sport: str, title: str) -> list[str]:
    """The names to match a headline against, longest first, or `[]`.

    Longest first so a longer alias cannot be shadowed by a shorter one that
    happens to be a prefix -- "manchester city" must be tested before "man city"
    if both are present.

    Drivers rather than team names for F1, which has no teams.
    """
    if not title or not isinstance(title, str):
        return []
    parts = [p.strip() for p in _SPLIT.split(title) if p.strip()]
    if not parts:
        return []
    table = NFL_ALIASES if sport == "nfl" else PL_ALIASES
    out: list[str] = []
    for part in parts:
        key = part.lower()
        out.append(table.get(key, key))
    return sorted(set(out), key=len, reverse=True)
```

And change `import re` at the top of `news.py` if it is not already there.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd services/explainer
uv run --extra dev python -m pytest tests/test_news_names.py -q -p no:cacheprovider
```

Expected: 7 passed. If the two coverage tests fail, the failure message names
exactly which abbreviations or names lack an alias — add those to the table and
re-run. That is the test doing its job, not a test to relax.

- [ ] **Step 5: Commit**

```bash
git add explainer/news.py tests/test_news_names.py
git commit -F /tmp/task2-names.txt
```

Message: `fix(explainer): match team news by the names ESPN writes, not the ones the title carries`

- [ ] **Step 6: Review gate**

`superpowers:requesting-code-review`.

---

## Task 3: Make newer news regenerate a summary, once

**Files:**
- Modify: `explainer/service.py:46-47` (`_news_terms`) and `:152-157` (the key)
- Test: `tests/test_news_freshness.py` (create)

**Interfaces:**
- Consumes: `news.news_names(sport, title) -> list[str]` from Task 2.
- Produces: `news_fingerprint(news: list[dict]) -> str` — the newest matched headline's `YYYY-MM-DD`, or `""` when there is no news. Task 4 does not use it; the panel's `news_date` arrives with the summary body in a later plan.

- [ ] **Step 1: Write the failing test**

Create `tests/test_news_freshness.py`:

```python
"""A summary must not outlive the news it was written from.

`service.py` says, in a comment, that news "isn't in the key: a fresh headline
alone must not cost another generation". That is a real budget concern and it is
the wrong trade for injury news: a summary written on Tuesday saying a
quarterback is starting is served on Wednesday, after a midweek injury, and the
reader is told something that is no longer true.

The rule this pins: the newest MATCHED headline's DATE is in the key, and nothing
else about the news is. So a genuinely newer headline regenerates once, and a
summary already citing today's news is reused at no cost. A fixture with no
matched news puts "" in the key and is therefore unaffected.
"""
from explainer.cache import Cache
from explainer.service import news_fingerprint


def _key(news):
    return Cache.key("nfl", "g1", "{}", news_fingerprint(news), "v3", "m")


def test_no_news_puts_nothing_in_the_key():
    assert news_fingerprint([]) == ""


def test_a_summary_written_before_todays_news_gets_a_different_key():
    """The midweek case, exactly as it happens."""
    before = [{"headline": "Bears quarterback listed questionable", "published": "2026-10-13T14:00:00Z"}]
    after = [{"headline": "Bears quarterback ruled out", "published": "2026-10-14T11:00:00Z"},
             {"headline": "Bears quarterback listed questionable", "published": "2026-10-13T14:00:00Z"}]
    assert _key(before) != _key(after), (
        "a newer headline did not change the key, so Tuesday's summary survives "
        "Wednesday's injury"
    )


def test_more_headlines_on_the_same_day_cost_nothing():
    """The cost bound. Two headlines published the same day are one regeneration,
    not two -- and a day with no new news is free."""
    a = [{"headline": "one", "published": "2026-10-14T09:00:00Z"}]
    b = [{"headline": "two", "published": "2026-10-14T18:00:00Z"},
         {"headline": "one", "published": "2026-10-14T09:00:00Z"}]
    assert _key(a) == _key(b), "a same-day second headline cost a regeneration"


def test_unmatched_news_is_absent_entirely():
    """`headlines()` already returns only matched items, so an empty list is the
    signal. This asserts the fingerprint does not invent a date from nothing."""
    assert news_fingerprint([{"headline": "x", "published": ""}]) == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd services/explainer
uv run --extra dev python -m pytest tests/test_news_freshness.py -q -p no:cacheprovider
```

Expected: collection error — no `news_fingerprint`.

- [ ] **Step 3: Implement**

In `explainer/service.py`, replace `_news_terms` (which is only used for news
matching) with a call into the new resolver, and add the fingerprint:

```python
from .news import headlines, news_fingerprint
```

Delete `_news_terms` and its `re` import if nothing else uses them, and change the
call site:

```python
        facts = await self._facts(sport, id)
        news = await headlines(self.client, sport, news_names(sport, facts.title))
```

Then replace the key construction:

```python
        # The newest MATCHED headline's DATE is in the key, and nothing else about
        # the news is. `Cache.key` has always taken a news argument; passing ""
        # is what made a midweek injury unable to change a written summary.
        #
        # Why the date and not the news: two headlines on one day are one
        # regeneration, not two, and a day with no new news is free. That bounds
        # the cost at one extra write per fixture per day, and only when there is
        # genuinely newer news for these two teams. Passing the whole news JSON
        # instead would regenerate on any editorial rewrite.
        key = Cache.key(sport, id, facts_json, news_fingerprint(news),
                        s.prompt_version, f"{s.model}|{s.fallback_model}")
```

And add, at module level in `service.py`:

```python
def news_fingerprint(news: list[dict]) -> str:
    """The newest matched headline's date, or `""` when there is no news.

    A DATE and not the headline text: the question this answers is "is the news I
    was written from still the newest news?", and a headline rewritten for
    clarity on the same day has not changed the answer.
    """
    for item in news:
        published = str(item.get("published") or "")[:10]
        if published:
            return published
    return ""
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd services/explainer
uv run --extra dev python -m pytest tests/test_news_freshness.py -q -p no:cacheprovider
```

Expected: 4 passed.

- [ ] **Step 5: Run the whole suite**

```bash
cd services/explainer
uv run --extra dev python -m pytest -q -p no:cacheprovider
```

Expected: green. A failure is a guard noticing the key changed — read it before
touching it.

- [ ] **Step 6: Mutation-check the new guard**

The freshness rule is a cache key, which no test can catch by running the suite
twice. Mutate `news_fingerprint` and confirm the failure:

```bash
cd services/explainer
cp explainer/service.py /tmp/service.keep
python3 - <<'PY'
import pathlib
p = pathlib.Path("explainer/service.py"); t = p.read_text()
a = 'return published'
assert t.count(a) == 1
p.write_text(t.replace(a, "return published[:0] or published", 1))
PY
uv run --extra dev python -m pytest tests/test_news_freshness.py -q -p no:cacheprovider
cp /tmp/service.keep explainer/service.py
```

Expected: at least one failure. If not, the test asserts something the
implementation does not depend on.

- [ ] **Step 7: Commit**

```bash
git add explainer/service.py tests/test_news_freshness.py
git commit -F /tmp/task3-freshness.txt
```

Message: `fix(explainer): a summary must not outlive the news it was written from`

- [ ] **Step 8: Review gate**

`superpowers:requesting-code-review`.

---

## Task 4: Tell the model to lead with lineup news, and date it

**Files:**
- Modify: `explainer/prompts.py` — the `SYSTEM` rules
- Test: `tests/test_news_in_prompt.py` (create)

**Interfaces:**
- Consumes: nothing. Independent of Tasks 2 and 3 — this is the prompt half, and it is safe to land before them.
- Produces: nothing other tasks consume. It changes behaviour only when a summary is generated with news present.

- [ ] **Step 1: Write the failing test**

Create `tests/test_news_in_prompt.py`:

```python
"""The frame has to ASK for news to be explained.

`prompts.SYSTEM` already says "using FACTS (our model's numbers) and NEWS (dated
headlines)" and already forbids inventing injuries. Neither of those asks for
news to be used: a headline can sit in the input and go unused, and the model is
then silent about a quarterback who will not play. This pins the instruction
that makes the headline the first thing a reader hears when it matters.
"""
from explainer.prompts import SYSTEM


def test_the_frame_asks_for_lineup_news_to_be_explained():
    assert "lineup" in SYSTEM.lower() or "injury" in SYSTEM.lower(), (
        "the frame never mentions injury or lineup news, so the model is given "
        "headlines and no reason to use them"
    )


def test_the_frame_asks_for_the_news_to_be_dated():
    assert "date" in SYSTEM.lower(), (
        "a reader cannot judge a summary that does not say how old its news was"
    )


def test_the_frame_still_forbids_inventing_an_injury():
    """The prohibition is what makes the new instruction safe. Do not let a
    future edit satisfy the two tests above by dropping this."""
    assert "Never invent" in SYSTEM, (
        "the prohibition on inventing injuries was removed; the instruction to "
        "lead with news is only safe because the model may report a headline it "
        "was given and nothing else"
    )
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd services/explainer
uv run --extra dev python -m pytest tests/test_news_in_prompt.py -q -p no:cacheprovider
```

Expected: the first two FAIL, the third passes.

- [ ] **Step 3: Add the instruction**

In `explainer/prompts.py`, inside `SYSTEM`, after rule 1 (which ends with the
`("a little more than the line", not a new figure)` clause), add:

```
2. Team news. When NEWS carries an injury, lineup or availability headline for
   either team, open with it: say who is out or in doubt, say when the news was
   published, and say what it changes for the prediction. When NEWS carries
   nothing about either team's lineup, say nothing about team news at all --
   a paragraph about a quarterback who is playing is a worse answer than none.
```

Then **renumber the existing rules 2-5 to 3-6** and fix every cross-reference to
them. Search the file for the rule numbers before you edit, and check
`tests/test_review_fixes.py` and `tests/test_contract.py`, which assert on
`SYSTEM` text.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd services/explainer
uv run --extra dev python -m pytest -q -p no:cacheprovider
```

Expected: green. `tests/test_prompt_version_moves_with_the_prompt.py` will
**fail**, and correctly: the prompt moved. Record the new fingerprint the way
that test's failure message instructs, and **bump `prompt_version` in the same
commit** — the deployed cache holds `v3` rows, and a changed frame under an
unchanged version ships nothing. Record `v4`.

- [ ] **Step 5: Commit**

```bash
git add explainer/prompts.py explainer/config.py tests/test_news_in_prompt.py
git commit -F /tmp/task4-prompt.txt
```

Message: `feat(explainer): lead with lineup news when there is any, and date it`

- [ ] **Step 6: Review gate**

`superpowers:requesting-code-review`.

---

## After Task 4

```bash
cd services/explainer
uv run --extra dev python -m pytest -q -p no:cacheprovider
uv run --extra dev python tools/mutcheck_template_line.py
```

Then dispatch one review across all four commits, and merge only on a clean
verdict. **The deploy is a separate step and is not part of this plan** — a
`prompt_version` bump changes what a deployed instance writes, and that is the
`golive` decision, not a code change.

## Not in this plan

- **The panel.** `FixtureExplainer`, `FixtureFlow`, `SummaryButton` and the shared
  `panelFacts` are a second plan against the same spec, in `predictor-ui`. This
  plan is the service half so that it can ship and be reviewed on its own.
- **The site rollouts** are a third plan: NBA (gated on NBA_Predictor#9), PL,
  Sports, F1. All four re-vendor, so all four wait on the component plan.
- **Sports_Predictor#6** (the Caddy no-echo) is reviewed and merged separately,
  as a prerequisite recorded in the spec.
