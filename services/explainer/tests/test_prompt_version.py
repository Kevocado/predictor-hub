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
written by a writer that predates the `neutral` direction default -- the one
writer-side fix this bump is what makes live. **The band is not on that list**,
and that is the limit of the rule rather than an oversight: see the note below
and the one in `config.py`, which say the same thing.
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

#: What this module's docstring says the cached `v2` rows predate, stated as the
#: literal text of the sentence and pinned rather than asserted in prose. The
#: line break is part of it: the docstring is wrapped prose, so a pin that
#: re-wrapped the sentence would stop matching a sentence that had not changed,
#: and the alternative -- comparing whitespace-normalised text -- is a
#: transformation whose failure would be opaque.
#:
#: **The version this text used to claim was wrong, and a third copy of it made
#: the branch read as "the reviewer only checked one of two".** It said the cached
#: rows predate "the `neutral` direction default and the band-withheld-on-`rebuilt`
#: rule -- the two fixes this bump is what makes live". The band half is false, and
#: it is false in the code rather than in the reading:
#:
#: * `service._answer` re-derives `band` from the facts on **every** read, hit or
#:   miss -- `service.py` line 113, `"band": band_for(pick_prob(facts),
#:   market_shape(facts))` -- so a cached `v2` row already gets the right one, and
#:   no writer change can be the thing that makes the band correct.
#: * §13e withholds the band chip on a rebuilt pick in
#:   `packages/predictor-ui` `ExplainerPanel.tsx` line 232,
#:   `{v2 && !rebuilt && <BandChip band={data.band} />}`. That is a RENDERING
#:   decision about a value the response already carries, on the reader's side of
#:   the wire, and it does not read `prompt_version` at all.
#:
#: The `neutral` default is writer-side and IS cached, because it lives in the
#: stored `body`. So that one half was right and is what the sentence now says.
#: `config.py` and the README were already corrected on this branch, and this
#: module was the third copy left asserting the false claim.
#:
#: **What this test can and cannot do, stated because a pinned sentence is a
#: copy.** It fails if the sentence is reworded, deleted, or replaced with the
#: false claim alone. It survives an edit that keeps this sentence intact *and*
#: adds the false claim elsewhere in the docstring -- so it is a pin, not a
#: proof, and it is here because the honest alternative for prose is no guard at
#: all, which is what let the false claim ship in the first place. The facts it
#: rests on are re-derivable from the two files named above at any time.
CACHED_ROWS_PREDATE = (
    "written by a writer that predates the `neutral` direction default -- the one\n"
    "writer-side fix this bump is what makes live."
)

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


def test_the_cached_rows_claim_does_not_assert_the_band_is_writer_side():
    """The corrected sentence, pinned, because a docstring is a claim too.

    Reads this module's own docstring -- the third copy of the sentence, and the
    one `config.py` and the README were already corrected against. The fact
    behind it is not asserted here because it is not this repo's to assert: the
    band is re-derived in `service._answer` on every read, and the chip withheld
    on a rebuilt pick is a rendering decision in `packages/predictor-ui`. Both
    are named in the constant's docstring with the two lines to look at, so a
    reader who doubts this can check it in a minute rather than take it.

    The equality is on a SENTENCE inside the docstring rather than on the whole
    docstring, because the rest of it is about the sqlite line, the measured
    floor and why the floor lives in this file -- none of which this change
    touches, and all of which a rewrite would be free to adjust.
    """
    docstring = (__doc__ or "")
    assert docstring, "this module has no docstring, so the claim it pins is gone"
    assert CACHED_ROWS_PREDATE in docstring, (
        f"this module no longer states what the cached v2 rows predate:\n"
        f"{docstring}\n"
        f"It used to claim they predate the neutral default AND the "
        f"band-withheld-on-rebuilt rule, 'the two fixes this bump is what makes "
        f"live'. The band half was false: `service._answer` re-derives `band` on "
        f"every read, hit or miss, and the chip withheld on a rebuilt pick is a "
        f"reader-side rendering decision in `packages/predictor-ui` that this "
        f"field does not gate. `config.py` and the README were corrected on this "
        f"branch; this was the third copy, and leaving it made the branch read as "
        f"'the reviewer only checked one of two'."
    )


def test_the_measured_floor_and_the_configured_version_are_untouched():
    """The rest of the claim, asserted against the live values rather than prose.

    Item 5 was a docstring fix and was told not to change behaviour or the
    measured floor, so this is here to say so: the two values the module's rule
    compares are still `v2` and the configured version, still distinct, and
    `v2` is still the highest of what was measured to be deployed. A docstring
    edit that quietly moved a number here would be a change of behaviour wearing
    a change of wording.
    """
    assert FLOOR == "v2", f"the measured deployed floor is {FLOOR!r}, not 'v2'"
    assert DEPLOYED_PROMPT_VERSIONS == ("v1", "v2"), DEPLOYED_PROMPT_VERSIONS
    assert FLOOR != Settings().prompt_version, (
        "the floor and the configured version are the same value, so the "
        "precondition is a constant compared with itself"
    )
    assert _order(Settings().prompt_version) > _order(FLOOR), Settings().prompt_version


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


#: The first line of the README's deploy-precondition note. A heading, used as a
#: locator and nothing more: the assertion below is about how many *paragraphs*
#: open with it, so rewording the note is free and only a second copy is a
#: failure. Taken from the merged text, not invented for the test.
DEPLOY_NOTE_HEAD = "**`prompt_version` is part of the deploy, not of the code.**"


def test_the_deploy_precondition_is_stated_once():
    """Two branches each added this note in the same place, and the merge stacked
    them instead of conflicting. Git reported no conflict, the number in the
    sample was right, and the README carried the same paragraph twice with two
    different lists of what the bump makes live — which is a documentation file
    quietly holding two incompatible histories of the same decision.

    Nothing else in the file catches it, and nothing would have: `git` calls that
    a clean merge, and every assertion here is about one value being correct in
    one place.

    Counted over **paragraphs**, not occurrences of a substring, so a passing
    mention of the note in prose elsewhere in the README cannot be mistaken for a
    second copy — the duplicate that actually happened was a whole second
    paragraph, and that is the shape this counts. The length assertion is the
    anti-vacuity half, in the same shape as
    `test_prompt_instructions.py::test_the_figures_rule_offers_no_sentence_to_imitate`:
    "found one" has to be a statement about a note, not about a stub.
    """
    text = README.read_text()
    notes = [p for p in text.split("\n\n") if p.startswith(DEPLOY_NOTE_HEAD)]
    assert notes, (
        f"the README no longer states the deploy precondition: nothing begins "
        f"{DEPLOY_NOTE_HEAD!r}. A deploy that changes the writer and does not move "
        f"prompt_version ships nothing a reader sees, and this file is where a "
        f"deployer is meant to meet that before they deploy rather than after a "
        f"reader does."
    )
    assert len(notes) == 1, (
        f"the README states the deploy precondition {len(notes)} times. Two copies "
        f"of the same rule is not a second opinion, it is two histories of one "
        f"decision, and a reader cannot tell which fixes the current version is "
        f"carrying. Fold them into one note that lists every writer change this "
        f"version puts live."
    )
    assert len(notes[0]) > 200, (
        f"the deploy precondition is {len(notes[0])} characters, which is a "
        f"placeholder rather than the note: {notes[0]!r}"
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
