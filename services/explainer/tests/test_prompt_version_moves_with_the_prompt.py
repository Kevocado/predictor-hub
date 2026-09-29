"""The prompt text and `prompt_version` are one change, and this is what holds
them together.

`Cache.key` covers `prompt_version` (`cache.py`, called from `service.explain`)
and a hit is served **verbatim** -- the stored body, not a re-render of it. So a
change to the writer shipped under a version the deployed cache already holds
changes **nothing a reader sees**: the rows already written keep being served
under the old version's key, and the deploy is green the whole time. Nothing
crashes, nothing logs, and every suite passes.

That makes this an *absent* failure, and an absent failure cannot be caught by
anything that reads the configuration. A test that asserts
`prompt_version == "v3"` is a test of that literal: it is green on the prompt
change either way, which is the whole bug. What catches it is something recorded
**independently of the prompt** -- a fingerprint of the prompt text, held here,
next to the version that text was current for. Then editing the prompt without
moving the version is a change to one file that the other file's recorded
fingerprint no longer matches.

**Where the fingerprint lives, and why it is a hash and not the text.** It is a
literal in this test file, not a second copy of the prompt and not a value
derived from it, for three reasons:

* a second copy of the prompt is a second thing to update, and updating it is
  exactly the mistake being guarded against -- it would pass;
* a value derived at import time from `prompts.SYSTEM` matches by construction,
  which is the "compared against the live constant meant to pin it" defect, so
  the test would be a constant against itself;
* a hash records that the text is the text that was current, without putting 25
  lines of prompt in a file whose job is to be a rule. A whitespace-only edit
  moves it, which is the right answer.

The two files are therefore edited together, which is the point: the change
becomes a two-file diff, and a one-file diff cannot ship. The cost is stated
plainly in the failure message at the point of failure.

**What this does NOT cover, because it is the same commit's other half.** The
guard says "the prompt moved, so did the version". It does not say the version
is above what the *deployed cache* was measured to hold -- a version can be new
and still already be spent, if it was deployed and written under.
`tests/test_prompt_version.py` holds that measured floor. The two are separate
rules about separate things and neither substitutes for the other.
"""
from __future__ import annotations

import hashlib
import re

from pathlib import Path

from explainer.cache import Cache
from explainer.config import Settings
from explainer.prompts import SPORT_NOTES, SYSTEM

#: The prompt fingerprint current when each version was last edited, keyed by
#: that version. Read as a log, not as a preference.
#:
#: Append a row, never edit one, and only in the same commit as the prompt edit
#: that caused it. Editing a row to match a prompt you have just changed is the
#: guard switching itself off, and it is why the fingerprint is a hash: a row
#: that has to be a hash cannot be quietly replaced with a copy of the new text.
#:
#: `v3` and `v4` both have rows and **only `v4` has been written under**; the
#: measured deployed floor is `v2` (`tests/test_prompt_version.py`, measured on
#: the VPS 2026-09-27). `v3` was set on this branch, rule 2's second sentence was
#: reworded before `v3` ever reached a reader, and the version was bumped rather
#: than the `v3` row re-recorded -- see the note on `Settings.prompt_version` in
#: `config.py` for why the append-only rule is worth one unused number. A row
#: describing a prompt nobody was sent is a harmless oddity in a log; a row that
#: can be edited in the same commit as the prompt is a guard that can be turned
#: off. `v1` and `v2` shipped before this file existed, so there is nothing
#: honest to record for them -- and nothing needed: they are below the configured
#: version, so they cannot be the value under test.
RECORDED_PROMPT_DIGEST = {
    "v3": "6b4bb345ea4138429dbc1876a065f79502d4616a58862dd6d9d2b55376fb5268",
    "v4": "44057a9f0fafb366ce8f8a6b0de4e916ecc33e9971f199384572e068667a4f45",
    "v5": "440422fd643f307ce3e568c118b444881b8499e4affd3081f575a9221cb3d568",
}

_HEX64 = re.compile(r"[0-9a-f]{64}")


def _digest(system: str = SYSTEM, notes: dict | None = None) -> str:
    """A fingerprint of everything the writer sends: the frame and every sport's
    language note.

    Both, because both are the prompt: `messages()` puts the language note in the
    same system message, so a sport whose note changes is a writer change for
    that sport and the cache key has to move for it. Sorted so the digest does
    not depend on the dict's insertion order, which is a property of the source
    file and not of the text.
    """
    notes = SPORT_NOTES if notes is None else notes
    payload = system + "\n\n" + "\n".join(f"{k}: {notes[k]}" for k in sorted(notes))
    return hashlib.sha256(payload.encode()).hexdigest()


def test_the_prompt_text_is_the_one_the_shipped_version_was_edited_for():
    """The rule. Edit the prompt and forget the version, and this fails.

    The lookup is by the CONFIGURED version, so this is not "does v3 still
    match" -- that would be a test of a literal. It is "is the text being sent
    now the text that version was current for", which is the precondition, and
    which the two failure messages below separate: no row for this version at
    all is an unbumped edit, and a row that does not match is a prompt that
    moved under a version already spent.
    """
    version = Settings().prompt_version
    recorded = RECORDED_PROMPT_DIGEST.get(version)
    assert recorded is not None, (
        f"the prompt was edited and prompt_version is still {version!r}, which has "
        f"no fingerprint recorded here. Only {sorted(RECORDED_PROMPT_DIGEST)} are "
        f"recorded. The cache key covers prompt_version and a hit is served "
        f"verbatim, so a writer change under a version the cache already holds "
        f"ships nothing a reader sees. Bump config.Settings.prompt_version and add "
        f"a row for it in the same commit, with the digest of the new text."
    )
    assert recorded == _digest(), (
        f"the prompt text has moved and prompt_version is still {version!r}, so the "
        f"row recorded for it no longer matches ({recorded} recorded, {_digest()} now). "
        f"Either the writer changed without the version, or the row was edited to match "
        f"a prompt rather than to record one. Bump the version and add a row in the "
        f"same commit; the change is meant to be a two-file diff."
    )


def test_the_shipped_version_is_the_newest_one_recorded():
    """The other direction, because a half-done fix is the likely next mistake.

    Recording a new fingerprint and forgetting to move the configured version
    leaves a row that no test reads -- the first test still passes, because the
    configured version's own row is untouched. So the newest row has to be the
    one in force.
    """
    newest = max(RECORDED_PROMPT_DIGEST, key=lambda v: int(v[1:]))
    assert Settings().prompt_version == newest, (
        f"prompt_version is {Settings().prompt_version!r} but the newest recorded "
        f"prompt fingerprint is {newest!r}. A fingerprint was recorded for a prompt "
        f"that is not the one shipping, so the first test is checking an older row."
    )


def test_the_record_is_a_fingerprint_rather_than_a_copy_of_the_prompt():
    """What makes the record independent, asserted rather than assumed.

    A row that could hold the prompt text would be a second copy somebody could
    update in the same breath as the prompt, and the guard would be off. Requiring
    a hash makes that impossible to do by accident, and requiring a hash that
    *matches* is the first test -- so a row cannot be a decoy value either.
    """
    for version, digest in RECORDED_PROMPT_DIGEST.items():
        assert _HEX64.fullmatch(digest), (
            f"the row for {version!r} is {digest!r}, which is not a sha256 digest. "
            f"Recompute it rather than pasting the prompt text in."
        )
    assert RECORDED_PROMPT_DIGEST, "there is nothing recorded, so nothing is guarded"


def test_two_versions_cannot_share_one_fingerprint():
    """Rows are distinct, so a version cannot be added by copying another.

    Cheap, and it closes the sloppy half of the append-only rule: a new row
    pasted from its neighbour passes every other test here -- the configured
    version's own row still matches the live prompt -- while recording a prompt
    change that never happened.
    """
    digests = list(RECORDED_PROMPT_DIGEST.values())
    assert len(set(digests)) == len(digests), (
        f"two versions record the same prompt: {RECORDED_PROMPT_DIGEST}"
    )


def test_the_fingerprint_cannot_be_derived_from_the_prompt_at_runtime():
    """The independence of the record, checked by construction rather than by
    inspection of it.

    The defect this file exists for is a guard comparing a value against a
    derived copy of itself. Two shapes of it, both closed here: the record
    computed from the live prompt at import time (which matches by construction
    and can never fail), and the record stored in `config.py` beside the
    constant (which is edited in the same breath as the thing it is supposed to
    pin). Neither is a matter of taste about where a literal lives, so both are
    asserted: the table is a literal in this file, and `config.py` carries no
    fingerprint of its own to be edited alongside.
    """
    source = (Path(__file__).resolve().parents[1] / "explainer" / "config.py").read_text()
    for version, digest in RECORDED_PROMPT_DIGEST.items():
        assert digest not in source, (
            f"the fingerprint for {version!r} is also written into config.py, so the "
            f"two can be edited as one file and the guard compares a value with itself"
        )
    assert "sha256" not in source and "hashlib" not in source, (
        "config.py computes a fingerprint of the prompt, so the record and the thing "
        "it records cannot be edited independently"
    )


def test_every_recorded_version_is_one_this_service_can_order():
    """The record is a log of `vN`, and `max()` in the test above says so.

    A row called `"v3-fixed"` or `"3"` sorts and compares as a string, so the
    ordering test would pass or fail for reasons that have nothing to do with the
    version -- the same reason `_order` exists in `test_prompt_version.py`.
    """
    for version in RECORDED_PROMPT_DIGEST:
        assert re.fullmatch(r"v\d+", version), (
            f"{version!r} is not a plain vN version, so nothing here can order it"
        )


def test_the_fingerprint_moves_when_the_frame_moves():
    """The guard's own sensitivity, tested before it is trusted.

    A fingerprint that is insensitive is a constant, and a constant recorded in
    a test file passes forever while the prompt changes underneath it. One
    character is the smallest possible edit and the one a real change makes.
    """
    assert _digest(SYSTEM) == _digest()  # the defaults are the live prompt
    assert _digest(SYSTEM + " ") != _digest(), (
        "the fingerprint does not cover the frame, so editing SYSTEM would not "
        "be caught"
    )


def test_the_fingerprint_moves_when_a_language_note_moves():
    """And the notes, which are the other half of what `messages()` sends.

    A sport's note is in the same system message as the frame, so a change to it
    is a writer change for that sport and the cache key has to move with it.
    Checking all five rather than one: the notes differ per sport, and a digest
    that happened to cover only the first would pass on the other four.
    """
    baseline = _digest()
    for sport in SPORT_NOTES:
        moved = _digest(notes={**SPORT_NOTES, sport: SPORT_NOTES[sport] + " "})
        assert moved != baseline, f"the fingerprint does not cover the {sport} language note"


def test_the_version_it_records_is_in_the_cache_key():
    """What the whole rule rests on: the key covers the version, and the key is
    what makes a stale row unreachable.

    One line, and it is here because this commit must stand on its own --
    `tests/test_prompt_version.py` asserts the same sensitivity, but that file
    arrives with the `origin/main` merge and not with this change.
    """
    key = Cache.key("nfl", "g1", "{}", "", Settings().prompt_version, "m")
    assert key != Cache.key("nfl", "g1", "{}", "", "v0", "m")
    assert key == Cache.key("nfl", "g1", "{}", "", Settings().prompt_version, "m")
