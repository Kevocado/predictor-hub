"""`prompt_version` is a deploy precondition, and this is what holds it down.

Spec §13f: the cache key covers `prompt_version` and a hit is served verbatim,
so **a deploy that changes how a body is written, and does not move the
version, changes nothing a reader sees.** The cache is not empty — §4 keeps it
so a second open of a fixture is free — which means the fixtures a reader has
already opened are the ones still rendering the old text, and the deploy looks
identical from outside either way.

The failure this file exists for is therefore an *absent* one. Nothing crashes,
nothing logs an error, every suite is green, and the renderer change is inert.
The only way to catch it is a test that compares the configured version against
something recorded **independently** of the configuration — so the floor below
is a measurement, not a second copy of the default, and it lives here rather
than in `config.py` so the two cannot be edited as one file.

Measured on the VPS 2026-09-27, on the deployed explainer volume:

    $ sqlite3 /data/explainer.sqlite \\
        'SELECT prompt_version, count(*) FROM explanations GROUP BY 1'
    v2|41

`v2` is not hypothetical. Those rows are being served today and they were
written by a writer that predates the `neutral` direction default and the
band-withheld-on-`rebuilt` rule — the two fixes this bump is what makes live.
"""
import re

from pathlib import Path

import httpx

from conftest import facts, good, make, reply
from explainer.cache import Cache
from explainer.config import Settings
from explainer.facts import Facts, render
from explainer.llm import OPENROUTER_URL

FACTS_URL = "http://nfl.test/api/facts/g1"

#: Every prompt version the deployed cache was **measured** to hold, oldest
#: first. Read this as production state, not as a preference.
#:
#: Append, never edit. A deploy that leaves a version behind adds a row;
#: rewriting an existing one would turn this into a record of what somebody
#: remembered rather than of what was measured. Re-measure with the sqlite line
#: in the module docstring, and the guard below moves with it for free.
DEPLOYED_PROMPT_VERSIONS = ("v1", "v2")


def _order(version: str) -> int:
    """`v7` -> 7, and refuse anything else rather than ordering it by accident.

    A string comparison is the trap: `"v10" < "v9"`, so a comparator built on
    `<` inverts the rule the day this reaches v10 — while still passing on
    every version in between, which is the "looks guarded, is not" shape this
    file exists to avoid.
    """
    m = re.fullmatch(r"v(\d+)", version)
    if not m:
        raise AssertionError(f"{version!r} is not a plain vN prompt version, so nothing here can order it")
    return int(m.group(1))


def _v(n: int) -> str:
    return f"v{n}"


FLOOR = max(DEPLOYED_PROMPT_VERSIONS, key=_order)
README = Path(__file__).resolve().parents[1] / "README.md"


def test_the_ordering_is_numeric_rather_than_lexicographic():
    """Before it is trusted. A guard that inverts at v10 is worse than none:
    it passes on every version until the day it is needed."""
    assert _order(_v(10)) > _order(_v(9)), "v10 must sort above v9"
    assert _order(_v(2)) < _order(_v(3))
    assert sorted([_v(10), _v(9), _v(2)], key=_order) == [_v(2), _v(9), _v(10)]
    for bad in ("", "v", "2", "v2.1", "v2-no-pick", "vv2", "v 2", "V2"):
        try:
            _order(bad)
        except AssertionError:
            continue
        raise AssertionError(f"{bad!r} was ordered instead of refused")


def test_the_configured_version_is_above_what_production_has_cached():
    """The precondition itself. Reverts to the floor and this fails.

    Not `== "v3"`: a test asserting one literal is a test of that literal, and
    it would also be satisfied by a version nobody has deployed, which proves
    nothing about the cache. `>` is the rule §13f states, so `>` is the test.
    """
    s = Settings()
    assert _order(s.prompt_version) > _order(FLOOR), (
        f"prompt_version is {s.prompt_version!r} and the deployed cache holds "
        f"{FLOOR!r} rows (measured; see this module's docstring). The cache key "
        f"covers the version and a hit is served verbatim, so every cached body "
        f"keeps rendering the text it was written with and the writer change "
        f"ships inert. Move config.Settings.prompt_version off the floor, and "
        f"once it is what production holds, append it to "
        f"DEPLOYED_PROMPT_VERSIONS so the next writer change is caught too."
    )


def test_the_floor_is_a_measurement_rather_than_a_second_copy_of_the_default():
    """The two values have to be able to disagree, or the comparison above is a
    constant compared with itself. This is the property that makes it a test."""
    assert FLOOR != Settings().prompt_version, (
        "the floor and the default are the same value, so the guard is a "
        "constant compared against itself and cannot fail"
    )


def test_the_response_sample_reports_the_version_that_ships():
    """The documentation half of the same precondition, with no second copy of
    the number anywhere: the code holds it, the README's sample reports it, and
    a bump that forgets the README leaves the next person reading a version that
    is not deployed. Cheap, and it is the half that rots first.

    Read out of the sample rather than searched for as a bare substring — the
    README also names the *floor*, so `v2` appears in it for a completely
    different reason, and a substring match would have passed on the revert this
    is here to catch.
    """
    sample = re.search(r'"prompt_version":\s*"([^"]+)"', README.read_text())
    assert sample is not None, "the README's response sample no longer names a prompt_version"
    assert sample.group(1) == Settings().prompt_version, (
        f"the README's sample response says prompt_version {sample.group(1)!r} "
        f"and this build ships {Settings().prompt_version!r}"
    )


async def test_a_row_written_under_the_deployed_version_is_not_served(tmp_path, no_news):
    """The mechanism, end to end: seed the cache exactly as production holds it
    and show the read misses.

    The floor is `v2` and the deployed cache is full of `v2` rows, so this is
    not a synthetic setup — it is the deployed cache. The seeded body cannot be
    served under any honest writer (a single factor, `up` on a bundle whose
    facts carry the pick, prose the facts do not support), so a regression that
    served it would show up in the returned verdict rather than only in a call
    count.

    Fails on two independent mutations, which is the reason it is here and not
    only the constant: revert the default to the floor, or drop
    `prompt_version` from the cache key.
    """
    no_news.get(FACTS_URL).mock(return_value=httpx.Response(200, json=facts()))
    llm = no_news.post(OPENROUTER_URL).mock(return_value=reply(good()))

    ex = make(tmp_path)
    s = ex.settings
    stale = {"verdict": "A stale row that must never be served.",
             "factors": [{"key": "spread", "direction": "up",
                          "headline": "Stale", "text": "Written before the current writer."}]}
    key = Cache.key("nfl", "g1", render(Facts(**facts())), "",
                    FLOOR, f"{s.model}|{s.fallback_model}")
    ex.cache.put(key, "nfl", "g1", stale, "llm", s.model, FLOOR)
    assert ex.cache.get(key) is not None, "the seeded row is missing, so this proves nothing"

    out = await ex.explain("nfl", "g1")

    assert llm.call_count == 1, (
        f"the {FLOOR!r} row was served verbatim and the writer never ran: the "
        f"version is not in the cache key, or it did not move"
    )
    assert out["prompt_version"] == s.prompt_version != FLOOR
    assert out["verdict"] != stale["verdict"], "the cached body was returned as the answer"
    assert "Stale" not in [f["headline"] for f in out["factors"]]


def test_the_configured_version_reaches_the_key_the_service_builds(tmp_path):
    """The wiring, stated once. `service.explain` passes `s.prompt_version` into
    `Cache.key`; the test above only means anything while that holds, and a
    refactor that inlined a default would otherwise look harmless."""
    ex = make(tmp_path)
    s = ex.settings
    key = Cache.key("nfl", "g1", "{}", "", s.prompt_version, "m")
    assert key == Cache.key("nfl", "g1", "{}", "", Settings().prompt_version, "m")
    assert key != Cache.key("nfl", "g1", "{}", "", FLOOR, "m")


def test_a_bump_leaves_the_older_rows_readable(tmp_path):
    """What a bump costs, and what it must not do. `latest_for` reads across
    versions for `/status`, so nothing is deleted and the old rows stay
    addressable — but a new writer must not be handed one, which is the
    previous test. Both halves, because a fix for either one alone is a
    plausible next commit."""
    ex = make(tmp_path)
    ex.cache.put("k1", "nfl", "g1", {"verdict": "old"}, "llm", "m", FLOOR)
    ex.cache.put("k2", "nfl", "g1", {"verdict": "new"}, "llm", "m", ex.settings.prompt_version)
    assert [ex.cache.get(k)["prompt_version"] for k in ("k1", "k2")] == [FLOOR, ex.settings.prompt_version]
    assert ex.cache.latest_for("nfl", "g1")["prompt_version"] == ex.settings.prompt_version
