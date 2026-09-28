#!/usr/bin/env python3
"""Mutation-check the explainer's quoted-line handling and the NBA serving guards.

Run from `services/explainer`:
    uv run --extra dev python tools/mutcheck_template_line.py

Why this is a file and not a shell loop: three harnesses in these projects
reported "all passed" for the wrong reason, in three different ways, and two of
those shipped inside a commit.

* **It separates failed, passed and errored**, and it does NOT treat all three as
  a bite. An earlier version read the PASSED count out of a line reading `1
  failed, 9 passed`, so four mutations looked like partial passes; another read a
  collection error -- a mutation that produced a syntax error -- as zero failures,
  i.e. silent. Both are wrong, and the fix for the first is a tally taken from
  the summary line; the second turned out to need a bucket of its own, because
  `errored` is a THIRD state that is neither a bite nor a pass.
* **It purges `__pycache__` and sets `PYTHONDONTWRITEBYTECODE`** before every run.
  Python treats a `.pyc` as current on the source's mtime *and size*, and the
  stored mtime has one-second resolution, so a mutation that keeps the file the
  same length inside the same second is silently ignored and pytest imports the
  unmutated bytecode. **This script reported one guard as SILENT on four runs of
  five and BITES on the fifth, purely on where the second boundary fell.** Adding
  a debug `read_text()` "fixed" it, because a few more milliseconds was enough.
  A check that fails intermittently and for no visible reason is worse than one
  that fails consistently, because it is believed the times it says yes.
* **It runs the WHOLE suite, not one file.** Scoped to
  `test_template_quoted_line.py` it cannot see a guard in
  `test_unserved_sport.py` -- and two did survive a review that way.
* **It carries a canary** that must stay silent, so a harness which never applies
  its mutations is distinguishable from a set of guards that never fail.
* **It restores under `try/finally`, and keeps a `.bak` beside each file it
  touches**, because an interrupted run must not leave a mutated source. The
  docstring used to claim the `.bak` and nothing wrote one; and the `config.py`
  restore was `write_text(read_text())`, a no-op that would have left the file
  mutated if anything raised mid-table. Both are now real. The `.bak` exists
  because on the sibling harness a bug in its own unpacking raised mid-table, and
  the `git checkout` used to recover **reverted three unrelated fixes along with
  the mutation** -- so "restore what you mutated" has to name which file. The
  `.bak` is removed once the restore is CONFIRMED, and on no earlier exit, so a
  run that merely found a silent mutation does not leave litter behind; a crash
  still leaves them, which is the case they are for.
* **It reads its own tally out of the pytest summary and not out of the first
  number it finds**, because the first number it finds is frequently in a
  traceback. See `_last_count`.
* **It checks a row's expected-silent MARK against what the run did**, and does
  not let the mark stand in for the observation. See `classify`.
* **A row whose mutation does not parse gets its own bucket**, and a run holding
  one exits non-zero. See `BROKEN`. A collection error used to be filed as
  `BITES (collection error)`, i.e. as the good outcome -- so an anchor or
  replacement that did not parse was recorded as *having bitten*, which is the
  one thing a mutation table must never say about a row that never ran.
* **It refuses a table whose anchors cannot be applied safely, before the baseline
  run and before anything is written.** Two checks, and the second exists because
  the first was testing a spelling rather than the property it names. See
  `unescaped_dots` for the `.` scan and `newline_crossings` for the measurement
  that catches `[\\s\\S]*`, `(?:.|\\n)*` and `\\W*` -- the three spellings a reader
  writes *after* being told not to use a bare dot, each of which destroys more of
  a source file than `.*` does and none of which the scan can see. A third check,
  `invalid_patterns`, refuses a pattern the engine will not compile, which
  otherwise escapes as a traceback out of the tool meant to report problems
  readably.
"""
import os
import pathlib
import re
import shutil
import subprocess
import sys

TARGET = pathlib.Path("explainer/template.py")
CONFIG = pathlib.Path("explainer/config.py")
PROMPTS = pathlib.Path("explainer/prompts.py")
SUITE = "tests/"  # the whole suite, on purpose -- see the docstring
#: Every file a row may mutate, with its original text captured at import.
#:
#: A dict rather than three module-level names, because three names meant three
#: places to add a file and three places to forget one: `prompts.py` joined
#: because the prompt is a writer too, and a row that reinstates the figures rule
#: the template no longer supports has to be applied to the file that holds it.
#:
#: The originals are read ONCE, at import, and the `config.py` entry used to be
#: ``write_text(read_text())`` -- writing back what it had just read, so an
#: exception between the write and the restore left the file mutated. Capturing
#: the text is the only version of this that is not a no-op.
ORIGINALS: dict[pathlib.Path, str] = {
    path: path.read_text() for path in (TARGET, CONFIG, PROMPTS)
}

#: Expected to be silent, with the reason recorded. Surviving because a property
#: is order-independent is a pass; surviving because nothing covers an input is a
#: failure, and the two must not share a verdict.
EXPECTED_SILENT_MARK = "expected silent"
CANARY = "CANARY: nothing covers this"
#: The FIVE buckets a row can land in. Named so `classify` reads as a rule rather
#: than as branching, and so a test can assert on the names.
EXPECTED = "expected-silent"
MISLABELLED = "mislabelled"
BROKEN = "broken"
SILENT = "silent"
BITES = "bites"

#: The one line every spread-sentence row anchors on, named once because four
#: rows share it and a copy pasted four times is four things to keep in step.
#:
#: `^...$` with `count=1`, so the match is the whole line and the FIRST such line
#: in the file. Do not quote that line's text verbatim in a comment above it in
#: `template.py`: the comment would take the match, the mutation would land
#: there and change nothing, and the row would report itself covered. That is
#: not hypothetical -- the `>=`-becomes-`>` row read SILENT for exactly this
#: reason. `template.py` carries the same warning at the row it applies to.
_SPREAD_SENTENCE = r'^                             f"It projects a margin of \{abs\(margin\):g\} \{unit\}, against a line of \{line\}\."\)\)$'

MUTATIONS = [
    # --- _quoted_line: the two-key read ---
    # A canary has to mutate something NOTHING covers, or it stops being the
    # control. This one used to be `MAX_FACTORS`, and it BITES -- correctly, since
    # a review asked for the factor budget to be pinned and it now is. A canary
    # that starts failing is a canary that has been promoted into a real test,
    # which is fine for the suite and useless here.
    (CANARY, r'unit = "goals" if sport == "pl" else "points"',
     'unit = "points" if sport == "pl" else "points"'),
    ("precedence flipped: line before market_line",
     r"^    for key in keys:$", "    for key in reversed(keys):"),
    ("neither key is read",
     r"^    for key in keys:$", "    for key in ():"),
    ("the strip is dropped, so blank lines slip through",
     r"^        if isinstance\(value, str\):$", "        if False:"),
    ("the truthiness test is dropped, so 0 and '' become lines",
     r"^        if value:$", "        if True:"),
    ("the bool guard is dropped, so True renders as a line",
     r"^        if isinstance\(value, bool\):$", "        if False:"),
    ("the non-dict guard is dropped",
     r"^    if not isinstance\(market, dict\):$", "    if False:"),
    # --- the default key list, and the prompt ---
    # A default argument nothing uses is a statement no observation can check.
    # This row puts one back and the suite has to notice the code changed shape
    # even though no rendered output does: `test_the_helper_takes_no_default_
    # key_list` reads the signature. Without it the row would be SILENT, which
    # is the whole reason the default was removed -- a reader could change it and
    # no run of anything would say so.
    ("the dead default key list comes back on the helper",
     r"^def _quoted_line\(market: dict \| None, keys: tuple\[str, \.\.\.\]\) -> str \| None:$",
     'def _quoted_line(market: dict | None, keys: tuple[str, ...] = ("line",)) -> str | None:'),
    # The one statement of the default is now reachable, so a change to it
    # changes what a sport absent from the table renders. This bites on the
    # ORDER and on the LENGTH, which is what the dead default could not do.
    ("the default key list loses the market_line key",
     r'^DEFAULT_MARKET_LINE_KEY: tuple\[str, \.\.\.\] = \("market_line", "line"\)$',
     'DEFAULT_MARKET_LINE_KEY: tuple[str, ...] = ("line",)'),
    ("the default key list is reversed, so a model's wording is preferred",
     r'^DEFAULT_MARKET_LINE_KEY: tuple\[str, \.\.\.\] = \("market_line", "line"\)$',
     'DEFAULT_MARKET_LINE_KEY: tuple[str, ...] = ("line", "market_line")'),
    # `prompts.SYSTEM`'s figures rule, which used to hand the model a sentence
    # asserting a model-vs-market comparison the service cannot check.
    # `test_prompt_instructions.py` holds the wording; these two rows are what
    # stops it coming back as wording the test would have to be edited to accept.
    # `[^\n]*` rather than `.*`: these anchors are matched with `re.S`, and `.*`
    # under DOTALL runs to the end of the FILE -- so the first version of these
    # two rows replaced everything from the figures rule to the closing quote of
    # SYSTEM, and both reported BITES as a COLLECTION ERROR. A mutation that
    # breaks the file into not parsing is a bite, so the table was right and the
    # row was testing nothing it claimed to. The same DOTALL trap applies to any
    # future anchor that is not whole-line, which is why `_SPREAD_SENTENCE` above
    # is written without a `.` at all.
    ("the prompt quotes the model-vs-market comparison back",
     r"^Write NO figures in the panel\.[^\n]*$",
     'Write NO figures in the panel. The panel draws every number from FACTS itself, '
     'so a figure in your text would either duplicate it or contradict it. Say "the '
     'line asks for more than the model rates the gap" and let the panel show the gap.'),
    ("the prompt's rule on which number is bigger is dropped",
     r"^Write NO figures in the panel\.[^\n]*$",
     "Write NO figures in the panel. The panel draws every number from FACTS itself, "
     "so a figure in your text would either duplicate it or contradict it. Say which "
     "market the row is about and let the panel show the gap."),
    # The comparative that survived the fix that removed its twin. `origin/main`
    # told the model to SAY the comparison; this branch tells it not to; and the
    # example sentence sat in rule 2 the whole time, byte-identical, in the rule
    # whose subject is what the prose may not write. A model handed an example
    # produces something close to it, so this is an instruction rather than an
    # illustration.
    #
    # Anchored on rule 2 with `^...$` and `[^\n]*`, which is the DOTALL-safe
    # spelling documented above, and the first match in the file: no comment
    # quotes this line, and the `.` in `2\.` is escaped so the new static check
    # accepts the row rather than refusing the table.
    #
    # The tests beside it are exact-equality and a structural quote inventory, so
    # both of them also fail here. What this row is for is the case they cannot
    # reach: a reworded example, or a test edited in the same commit as the
    # prompt. `test_prompt_instructions.py` states that limit itself.
    ("the comparative comes back to rule 2",
     r"^2\. No betting advice:[^\n]*$",
     '2. No betting advice: never write "lock", "bet", "value play", "hammer", '
     '"guaranteed" or "sure thing". Disagreement with the market is information '
     '("the model rates BAL a little better than the line does"), not a '
     'recommendation.'),

    # --- the two call sites: these are the actual fix ---
    # The spread gate grew a `big_enough` term for the margin floor, so this
    # anchor matches the WHOLE condition and `big_enough` gets its own rows
    # below. An anchor that matched a prefix would have kept applying here and
    # silently stopped testing the whole gate -- which is the NOT APPLIED
    # failure mode, arrived at by making the code correct.
    ("the spread factor never fires",
     r"^    if margin_market is not None and margin is not None and label and quoted and big_enough:$",
     "    if False:"),
    # --- the margin floor: `model_margin: 0` narrated a disagreement of nothing ---
    ("the margin floor is dropped, so a zero gap is narrated again",
     r"^    big_enough = margin is not None and abs\(margin\) >= MIN_SPREAD_MARGIN$",
     "    big_enough = margin is not None"),
    # Anchored to the CODE line, with `^...$`, and not to the bare expression:
    # the `count=1` takes the first match in the file, and a comment quoting the
    # expression verbatim sits above this line and absorbs the mutation. That is
    # not hypothetical -- this row read SILENT for that reason while the
    # boundary test below it went unrun. See the NOTE in `template.py`.
    ("the floor becomes exclusive, so a real half-point gap is dropped",
     r"^    big_enough = margin is not None and abs\(margin\) >= MIN_SPREAD_MARGIN$",
     "    big_enough = margin is not None and abs(margin) > MIN_SPREAD_MARGIN"),
    ("the floor is lowered to 0, admitting every margin again",
     r"^MIN_SPREAD_MARGIN = 0\.5$", "MIN_SPREAD_MARGIN = 0.0"),
    ("the floor loses its abs(), so a negated small margin narrates again",
     r"^    big_enough = margin is not None and abs\(margin\) >= MIN_SPREAD_MARGIN$",
     "    big_enough = margin is not None and margin >= MIN_SPREAD_MARGIN"),
    ("the total gate reverts to the NBA-blind `line` check",
     r"^    if total_market is not None and total is not None and total_line is not None:$",
     '    if total_market is not None and total is not None and total_market.get("line") is not None:'),
    ("NBA's market-line key becomes the default two-key read",
     r'    "nba": \("market_line",\),', '    "nba": ("market_line", "line"),'),
    ("NBA is dropped from the market-line table",
     r'    "nba": \("market_line",\),\n', ""),
    ("NFL's line is added to the table, re-enabling the model-vs-model sentence",
     r'    "nba": \("market_line",\),', '    "nfl": ("market_line",),\n    "nba": ("market_line",),'),
    ("_START: f1 and pl entries swapped",
     r'_START = \{"f1": "the session started", "pl": "kickoff", "nba": "tip-off"\}',
     '_START = {"f1": "kickoff", "pl": "the session started", "nba": "tip-off"}'),
    ("_START: the f1 phrase mangled",
     r'"f1": "the session started"', '"f1": "the race started"'),
    ("NBA's tip-off wording removed again",
     r'_START = \{"f1": "the session started", "pl": "kickoff", "nba": "tip-off"\}',
     '_START = {"f1": "the session started", "pl": "kickoff"}'),

    # --- _outcome_key: the market the pick row names ---
    # A row for each because a fix whose only witness is a pytest file is a fix
    # whose test can be deleted in the same commit, which is the objection this
    # table exists to raise; this row cannot be satisfied by editing a test.
    #
    # `in` becomes `not in`, which drops the case for every bundle rather than
    # renaming it: F1's `win` falls through to the `context` pseudo-market and
    # lands on the rebuilt-disclosure row's key, so the panel renders two
    # `data-testid="factor-context"` elements and lights both when either is
    # selected. Inverting the test catches the mistake a reader makes when
    # adding a market name -- reaching for `not in` because they are testing
    # membership of something else -- as well as the deletion, and a rename to a
    # market F1's facts do not carry is caught by
    # `test_f1_served.py::test_f1_gets_a_pick_and_a_record_...` and by
    # `tests/test_factor_keys.py`.
    ("_outcome_key's win case is inverted, so F1's pick falls back to context",
     r'^    if "win" in by_key:$', '    if "win" not in by_key:'),

    # --- the spread factor's claims: about the market, about a side ---
    # A row for text that was DELETED is what stops it coming back. The three
    # below restore exactly what shipped, and the fourth invents a comparison
    # the fix declined to compute. A test that only checks the honest numbers are
    # PRESENT cannot catch any of them: the false sentence only ever added words
    # or a team, so every "3.4 points better" / "BAL -2.5" assertion stayed green
    # while the claim shipped. Exact equality is what closes that, and these rows
    # are the other half -- they are what would stop a *different* false sentence
    # passing a *different* substring test.
    ("the deleted clause comes back",
     _SPREAD_SENTENCE,
     '                             f"It projects a margin of {abs(margin):g} {unit}, against a line of {line}. "\n'
     '                             f"That is the market asking for more than the model thinks the gap is worth."))'),
    # The second claim the sentence used to make, and the one with no test that
    # could see it until the sentence stopped making it: `model_margin` is
    # home-minus-away, NFL and CFB word the line from the home team, and the
    # bundle carries no home/away designation -- so naming the pick attributes a
    # margin to a side it may not belong to. The test that has to break is
    # `test_the_spread_sentence_is_the_same_whichever_side_the_pick_is_on`.
    ("the pick is named again, so a margin is attributed to a side",
     _SPREAD_SENTENCE,
     '                             f"It rates {label} {abs(margin):g} {unit} better, against a line of {line}."))'),
    ("a comparison is invented, so the sentence depends on the line",
     _SPREAD_SENTENCE,
     '                             f"It projects a margin of {abs(margin):g} {unit}, against a line of {line}. "\n'
     '                             f"The market asks for {\'more\' if float(quoted.rsplit(\'-\', 1)[-1]) > abs(margin) else \'less\'}."))'),
    ("the abs() goes, so a negative margin is written as a signed gap",
     _SPREAD_SENTENCE,
     '                             f"It projects a margin of {margin:g} {unit}, against a line of {line}."))'),
    ("the spread factor's mark goes back to a constant 'down'",
     r'^        factors\.append\(_fact\(str\(margin_market\["market"\]\), NEUTRAL, "The line",$',
     '        factors.append(_fact(str(margin_market["market"]), "down", "The line",'),

    # --- the padding rows and the verdict ------------------------------------
    # Reachable more than they look: measured, the "Not much to go on" row renders
    # on NFL 271/272 bundles, CFB 555/888 and NBA 373/1760, and the "Where this
    # stands" row on CFB 331, NFL 47, NBA 231, PL 50. So for a thin bundle these
    # are most of the panel, not padding in the disposable sense -- and four edits
    # to them were silent before `test_template_padding.py` existed.
    #
    # Every anchor here is whole-line with `[^\n]*` or an escaped literal dot, so
    # the new static check accepts the table and the DOTALL trap cannot reach it.
    # None of the four sentences is quoted verbatim in a comment above its line,
    # which is the decoy this repo has been bitten by; the comments above the
    # padding loop paraphrase rather than repeat.
    #
    # The removed sentence, byte for byte. An earlier draft padded with a `record`
    # factor saying no settled record yet and it was withdrawn because that is
    # false for exactly the bundles that reach this row -- so this row is a
    # sentence that has already been removed once, on a ground a comment was the
    # only guard for.
    ("the padding row claims a settled record is missing again",
     r'^PADDING_NO_QUOTE = "[^\n]*$',
     'PADDING_NO_QUOTE = "The model has no settled record on this one yet."'),
    # A comparison nothing computes, in the one row whose whole job is to say what
    # the bundle is short of. The class this branch exists to remove.
    ("the padding row compares the model with the market again",
     r'^PADDING_BOTH = "[^\n]*$',
     'PADDING_BOTH = "So the model strongly disagrees with the market here."'),
    # A revert to the pre-branch wording, which is a claim about figures not having
    # arrived and is wrong for every NBA bundle that reaches the row.
    ("the padding row reverts to 'still filling in'",
     r'^PADDING_NO_PROJECTION = "[^\n]*$',
     'PADDING_NO_PROJECTION = "The facts for this one are still filling in."'),
    # The state CHOICE rather than a wording: with the projection test forced on,
    # a bundle carrying no model figure at all is told it has one.
    #
    # The anchor is the WHOLE current line, `count=1`, and the line has three
    # terms. It used to have two, and this row's anchor was left pointing at the
    # old text when the third was added -- which is `NOT APPLIED`, the one
    # outcome that is neither a bite nor a pass and that the loop files as a
    # silent mutation. It is the same failure as the spread gate's `big_enough`
    # (an anchor that matched a prefix kept applying and silently stopped
    # testing the whole gate), and it is why the anchor is the whole line.
    ("the padding row assumes a model projection is always there",
     r'^        projected = margin is not None or total is not None or prob is not None$',
     "        projected = True"),
    # **The critical's own mutation, and the row that did not exist while it
    # shipped.** Dropping the `prob` term is the edit that turns the row back into
    # "So there is no model number for this one yet" over a bundle whose moneyline
    # the panel is drawing -- 555 of 888 CFB bundles and 208 of 272 NFL ones,
    # measured. The row above it does not catch this: forcing `projected = True`
    # and dropping a term are different failures, and only one of them was
    # guarded. A fix whose regression test lives only in the pytest file is a fix
    # whose test can be deleted with the same commit; this row cannot be satisfied
    # by editing a test.
    ("the padding row stops asking about the moneyline",
     r'^        projected = margin is not None or total is not None or prob is not None$',
     "        projected = margin is not None or total is not None"),
    # The other end of the same gate: forcing it off denies a number to every
    # bundle, which is the same false sentence by the other route. Kept because
    # the two rows above are the two ways to get this wrong and only one of them
    # is "too permissive".
    ("the padding row assumes the model never has a number",
     r'^        projected = margin is not None or total is not None or prob is not None$',
     "        projected = False"),
    ("the padding row ignores a quoted price",
     r'^        quoted_any = quoted is not None or total_line is not None or implied is not None$',
     "        quoted_any = False"),
    # The finding's own mutation: the gate stops being able to see PL's book
    # price, so a bundle carrying `implied` is told there is no quoted price to
    # read its number against. Latent today (0 of 380 real PL bundles carry
    # `implied`) and that is exactly why it needs a row: a defect nothing
    # currently reaches is a defect nothing currently catches, and the harness is
    # the only guard here that cannot be satisfied by editing a test.
    ("the padding row stops asking about the book's price",
     r'^        quoted_any = quoted is not None or total_line is not None or implied is not None$',
     "        quoted_any = quoted is not None or total_line is not None"),
    # And the other half of the same helper, which is the mutation a reader is
    # most likely to write: "does the market have an `implied` key" rather than
    # "does that map hold a price". PL's `_implied` writes `None` for a side with
    # no price, so a key-presence check denies nothing for a bundle that has
    # none -- and the paired test is the one that catches it.
    ("the padding row counts an empty implied map as a price",
     r'^        implied = _implied_price\(by_key\.get\("result"\)\)$',
     '        implied = 1.0 if "result" in by_key else None'),
    # **A survivor, and it carries the expected-silent mark because it is one.**
    # Rewriting `projected` to read the moneyline market's `model` MAP rather than
    # the pick's probability is a different key for the same decision. Verified out
    # of process rather than assumed: with this row applied, all 1,432 real NFL and
    # CFB bundles plus 380 real PL ones render 0 false rows, exactly as the shipped
    # code does -- because `pick.prob` and a moneyline/result `model` map are
    # present together in every one of them. No builder in the family ever
    # separates them, so no test over a bundle can either.
    #
    # Marked rather than deleted, and the mark is the mechanism working as designed:
    # a row silent because a property holds is a pass, a row silent because nothing
    # covers an input is a failure, and this is the first kind. `classify` checks
    # the label against the run, so a future change to any `_markets` that made the
    # two disagree would make this row BITES and fail the run loudly -- which is
    # the correct outcome, because the property would no longer be true. Deleting
    # the row would have left the survivor undocumented and the run green, which is
    # the state this row was added to end.
    (f"the padding row asks the moneyline market instead of the pick "
     f"[{EXPECTED_SILENT_MARK}: the two keys are never separated by any builder]",
     r'^        projected = margin is not None or total is not None or prob is not None$',
     "        projected = margin is not None or total is not None or any("
     "isinstance(m.get('model'), dict) and m['model'] for m in by_key.values())"),
    # And `has_pick` instead of `prob`, which the hunt found IS caught -- by the
    # record test, whose bundle carries a probability with no usable label. Kept
    # because the two are close enough to look interchangeable on a football
    # bundle, and because the row that catches it is not obviously about this.
    ("the padding row asks has_pick instead of the probability",
     r'^        projected = margin is not None or total is not None or prob is not None$',
     "        projected = margin is not None or total is not None or has_pick"),
    # The mark. `down` means "against the pick", nothing computes it, and the row
    # fires beside a 99% pick. A keyword absence would not catch this; the emitted
    # value is what `test_template_padding.py` compares.
    ("the padding row's mark goes back to a pick-relative 'down'",
     r'^                factors\.append\(_fact\("context", NEUTRAL, "Not much to go on",$',
     '                factors.append(_fact("context", _toward("down", has_pick), "Not much to go on",'),
    # And the second row's text, which used the same loop and so the same absence
    # of a guard. The replacement is a comparison, so the row is the same class as
    # the one above and a different row of the panel.
    ("the second padding row compares the model with the market",
     r'^                                     f"So there is little to weigh up here: \{title\}\."\)\)$',
     '                                     f"So the model strongly disagrees with the market here: {title}."))'),
    # The verdict, and the most prominent sentence in the panel. `prompts.py`
    # forbids the model from exactly this, and the panel draws the band chip from
    # the facts beside it -- so a 0.41 two-way pick would read "strong pick" next
    # to a `leaning` chip, at the same time.
    ("the verdict calls the pick a strong one",
     r'^    verdict = f"\{label\} is the pick\." if label and prob is not None else "There is no pick for this one yet\."$',
     '    verdict = f"{label} is a strong pick." if label and prob is not None else "There is no pick for this one yet."'),
    ("the verdict stops naming the pick's team",
     r'^    verdict = f"\{label\} is the pick\." if label and prob is not None else "There is no pick for this one yet\."$',
     '    verdict = "That is the one to have." if label and prob is not None else "There is no pick for this one yet."'),

    # --- config.SERVED_SPORTS, via the module that reads it ---
    ("SERVED_SPORTS loses nba",
     r'SERVED_SPORTS = \("pl", "nfl", "cfb", "nba", "f1"\)', 'SERVED_SPORTS = ("pl", "nfl", "cfb")'),
    # The row this replaces was "SERVED_SPORTS regains f1", anchored on the
    # pre-reversal tuple. It could not simply be re-anchored, and the reason is
    # the one below -- **and the first version of this comment gave a different,
    # impossible one, which is worth keeping in mind when reading it.**
    #
    # It said re-anchoring "would have reported a BITE for a mutation that
    # changed nothing". Read `main` against it and that cannot happen: the loop
    # is `n == 1` -> write -> `run()` -> `failed > 0`, and a replacement equal
    # to its own source writes a byte-identical file, so pytest is green,
    # `failed == 0`, and the row is filed `SILENT`. Checked with this file's own
    # `classify` rather than by reading: a re-anchored row classifies `silent`,
    # not `bites`.
    #
    # The real harm is quieter and it is permanent. A permanently silent row is
    # an unmarked row, so it lands in the "did not bite" list and the run exits
    # 1 on every run, forever -- and the two ways a reader responds are both
    # losses: delete the row and lose the `SERVED_SPORTS` coverage it appeared
    # to hold, or mark it `expected silent` and put a false claim into the
    # table. Dead weight, not a false bite.
    #
    # So the row is the mirror of the decision rather than a copy of it: F1
    # un-served, which is the reversal being undone by accident, and which
    # `tests/test_f1_served.py` bites.
    #
    # (A row whose anchor matches NOTHING is a different failure with a correct
    # mechanism, and it is why the three rows below had to be re-anchored rather
    # than moved: `n == 0` falls to the `else`, prints `NOT APPLIED`, appends to
    # `silent` and exits 1. That is the loud outcome, not a silent one.)
    ("SERVED_SPORTS loses f1 -- the reversal undone",
     r'SERVED_SPORTS = \("pl", "nfl", "cfb", "nba", "f1"\)', 'SERVED_SPORTS = ("pl", "nfl", "cfb", "nba")'),
    # **Two survivors, marked rather than deleted, and the mark claims something
    # NARROWER than the first version of this comment said.**
    #
    # Both ask the spread and total rows to read a market F1's own facts do not
    # have -- its `win` probability map and its `podium` map. What the mark
    # claims: **F1's `win` and `podium` carry no `model_margin` and no
    # `model_total` today, so the market NAME is inert today.**
    #
    # Two claims that used to be made here and are not true:
    #
    # * *"no market NAME can make the spread or the total row fire; a figure has
    #   to be there."* Wrong as written. A name **plus a figure** makes it fire,
    #   and the gate in `template.py` also requires a quoted line -- F1 has
    #   neither `line` nor `market_line`, so two things are missing rather than
    #   one. Verified rather than assumed: with the spread row reading
    #   `... or by_key.get("win")` and `win` given `model_margin: 3.4` and
    #   `line: "Norris by 3.4"`, F1 renders
    #   *"It projects a margin of 3.4 points, against a line of Norris by 3.4"* --
    #   the model compared with itself, which `_quoted_line`'s docstring names as
    #   the failure that helper exists to prevent. The name alone is inert; the
    #   name plus a figure plus a line is not.
    # * *"a facts builder that gave `win` a `model_margin` ... would make one of
    #   these BITES and fail the run loudly ... a false alarm, and it is the safe
    #   direction."* Wrong in a way that is DELETED rather than softened,
    #   because **this run never contains a sibling repo.** It mutates
    #   `explainer/template.py`, `explainer/config.py` and
    #   `explainer/prompts.py`, then runs `pytest tests/`. F1's facts are built
    #   in a repo this service does not import and this harness does not touch,
    #   so no change there can reach this row at any point, in either direction.
    #   It would not fail loudly; it would go UNNOTICED, and unnoticed is the
    #   unsafe direction rather than the safe one. "A false alarm, in the safe
    #   direction" described a loud failure that cannot happen instead of a quiet
    #   one that can.
    #
    # **So this row is a canary over THIS repo's own F1 bundles**, and the
    # sibling's shape is not being claimed at all. The `win`/`podium` shapes the
    # harness can see are the ones in `tests/test_f1_served.py`: give `win` a
    # `model_margin` and a `line` there and the row BITES, because the row would
    # then be rendering.
    #
    # The witness that F1's real facts carry no figure is
    # `test_f1_gets_a_pick_and_a_record_and_nothing_it_cannot_support`, and it
    # asserts on the rendered HEADLINES. Asserting on factor KEYS read like the
    # same check and was not: both rows are keyed `str(market["market"])`, so
    # under the mutation above the key list carries no "spread" and no "total"
    # (it is `["context", "win", "record"]` before the ruling and
    # `["win", "win", "record"]` after), so both key-based assertions were True
    # while "The line" was on screen. Where the sibling's shape is genuinely
    # unknown, the honest guard is on what this repo renders.
    (f"the spread row reads f1's `win` market "
     f"[{EXPECTED_SILENT_MARK}: `win` carries no model_margin and no quoted line today, so the name is inert]",
     r'^    margin_market = by_key\.get\("spread"\) or by_key\.get\("handicap"\)$',
     '    margin_market = by_key.get("spread") or by_key.get("handicap") or by_key.get("win")'),
    (f"the total row reads f1's `podium` market "
     f"[{EXPECTED_SILENT_MARK}: `podium` carries no model_total and no quoted line today, so the name is inert]",
     r'^    total_market = by_key\.get\("total"\) or by_key\.get\("total_goals"\)$',
     '    total_market = by_key.get("total") or by_key.get("total_goals") or by_key.get("podium")'),
    # The one row that carries the expected-silent mark, and the reason it is
    # still here rather than deleted.
    #
    # **The mechanism is kept because the reason is a property of the design and
    # belongs in the table, not in a reader's memory.** `SERVED_SPORTS` is read
    # for membership (`sport not in SERVED_SPORTS`, service.py) and as a set
    # (`set(expected) == set(SERVED_SPORTS)`, test_template_quoted_line.py), so
    # nothing consumes its order. "Nothing depends on this" is the one kind of
    # silence that is a RESULT rather than a gap, and a table that cannot say so
    # cannot distinguish it from a missing test -- which is the confusion the
    # whole tool exists to remove.
    #
    # The check is now `not bite` rather than "the label says so", so the row is
    # only filed as documented-silent when the run agrees. If a test is ever added
    # that makes the order matter, this row BITES and the run fails loudly,
    # which is the correct outcome: the property is no longer true.
    #
    # Its own limit, stated: the label is checked against the observation, so a
    # row marked expected-silent can no longer hide a bite. It cannot tell you
    # WHY nothing depends on the order, only that nothing does.
    (f"SERVED_SPORTS reordered [{EXPECTED_SILENT_MARK}: order-independence is the design]",
     r'SERVED_SPORTS = \("pl", "nfl", "cfb", "nba", "f1"\)', 'SERVED_SPORTS = ("nba", "pl", "nfl", "cfb", "f1")'),
]


#: The flags every anchor is applied with, named once. `re.S` is the whole reason
#: a pattern can reach past the end of its line, and it is applied in `main` and
#: in the static checks below -- so a check that used different flags would be
#: measuring a different regex from the one that runs. A named constant rather than
#: a literal repeated in five places because the two sets drifting apart is the
#: same defect this whole file exists to catch.
FLAGS = re.M | re.S


def unescaped_dots(pattern: str) -> list[str]:
    r"""Every `.` in `pattern` that the regex engine would read as "any character".

    Returned as readable fragments rather than offsets, because the only thing a
    reader does with the result is look at it and fix the row.

    **Why the character is dangerous HERE and nowhere else in Python.** These
    patterns are applied with `flags=re.M | re.S`, and `re.S` is exactly what
    turns `.` from "any character except a newline" into "any character". So
    r"^    for key in keys:.*$" matches from that line to the END OF FILE, and
    `re.subn(..., count=1)` replaces the whole tail of `template.py` with the
    replacement. The file stops parsing, pytest exits 2, and -- before `BROKEN`
    existed -- the table printed `BITES (collection error)` and the run exited 0.

    A pattern is checked rather than banned, because the safe spellings are
    ordinary:

    * **Escape it**: r"^MIN_SPREAD_MARGIN = 0\.5$". A backslash consumes the
      character after it, so the `.` is a literal.
    * **Take it out of the pattern**: a whole-line anchor needs no `.` at all, and
      `_SPREAD_SENTENCE` is written without one. This is the cheapest fix and the
      reason that anchor is the shape other rows are asked to copy.
    * **Spell the run**: r"^Write NO figures in the panel\.[^\n]*$". Inside a
      character class a `.` IS already a literal, which is why `[^\n]*` is safe and
      why this function has to track whether it is inside a class at all -- and why
      a check that simply banned the character would reject the spelling the table
      documents on two rows.

    Its own limit, stated: this reads the PATTERN. A replacement that does not
    parse is still only caught by `BROKEN`, which is why the two are both here
    rather than one standing in for the other. A decoy with a `.*`-free anchor and
    a replacement that is not valid Python is a `BROKEN` row, and it fails the run.
    """
    hits: list[str] = []
    in_class = False
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            # An escape consumes the next character, so neither this one nor the
            # one it hides can be a bare `.`. `i += 2` and not `i += 1`: a
            # `\\.` is a literal backslash followed by a wildcard, so skipping one
            # character would report the wildcard as safe.
            i += 2
            continue
        if in_class:
            if ch == "]":
                in_class = False
        elif ch == "[":
            in_class = True
        elif ch == ".":
            hits.append(pattern[max(0, i - 12):i + 13])
        i += 1
    return hits


def dot_problems(rows=None) -> list[tuple[str, str]]:
    """(label, fragment) for every row whose anchor holds a DOTALL-unsafe dot.

    Read from `MUTATIONS` by default, so a test that deletes rows cannot make the
    check vacuous -- an empty table passes this and the separate
    `test_every_marked_row_in_the_table_names_a_reason` is what holds the mechanism
    from being dropped wholesale.
    """
    return [(label, fragment)
            for label, pattern, _ in (MUTATIONS if rows is None else rows)
            for fragment in unescaped_dots(pattern)]


# --- the same check, asked as a property rather than as a spelling ----------
#
# `unescaped_dots` above reads the PATTERN and asks whether the character `.` is
# in it where the engine will read it as "any character". That is a spelling rule,
# and it is blind to every other way of writing the same property -- which is the
# problem, because the spellings below are what a reader writes *after* being told
# not to use a bare dot:
#
#     r"^    for key in keys:[\s\S]*$"     a character class meaning "anything"
#     r"^    for key in keys:(?:.|\n)*$"   the alternation, spelled out
#     r"^}\W*$"                            a non-word run, which includes \n
#
# All three report zero dots to the scan and are accepted by it, and the first two
# destroy 26,090 of `template.py`'s 40,396 characters -- byte for byte as
# destructive as `.*`, which the scan does catch. The old check could not produce a
# false PASS (`BROKEN` catches the run and exits 1), but its stated job is to
# refuse the table *before the baseline and before anything is written*, and for
# these spellings it did not.
#
# So the scan STAYS -- it is what names the character, which is the message a
# person can act on -- and this is added next to it: run the pattern against the
# real sources and refuse if what it matched contains a line break the pattern did
# not ask for.

#: The escape that means "this pattern wants a newline here", as it is spelled in
#: a source string. A pattern containing it is ALLOWED to match across a line,
#: because that is a deliberate multi-line anchor and the table has one: the
#: `'"nba": \("market_line"\),\n'` row, which matches a line AND the newline after
#: it on purpose. Reading the two characters `\n` out of the source rather than
#: testing for a compiled flag is deliberate -- it is what the person editing the
#: table can see.
_SPELLED_NEWLINE = "\\n"


def matched_spans(pattern: str, sources=None) -> list[tuple[str, int]]:
    """`(file, span length)` for the first match of `pattern` in each source.

    `re.search`, not `re.subn`, and the same `FLAGS`: the first match is the one
    `re.subn(..., count=1)` would replace, and matching it here is the only way to
    know how much the row would really touch. A pattern that matches nothing
    appears as no entry at all -- which is a `NOT APPLIED` row, reported by the
    loop, not a static-check failure.

    **A pattern the engine will not compile returns nothing rather than raising.**
    `re.search` is a different call from `re.compile` in exactly the way that
    matters here: it raises where the compile check would have reported. So the
    compile is done first and the row is skipped, and `invalid_patterns` is what
    reports it -- otherwise a table holding one bad pattern produces a traceback
    from inside the check that exists to prevent tracebacks, which is a worse
    failure than the one it was written for.
    """
    try:
        re.compile(pattern)
    except re.error:
        return []
    out: list[tuple[str, int]] = []
    for path, text in (ORIGINALS if sources is None else sources).items():
        found = re.search(pattern, text, flags=FLAGS)
        if found is not None:
            out.append((path.name, found.end() - found.start()))
    return out


def newline_crossings(rows=None, sources=None) -> list[tuple[str, str]]:
    """(label, detail) for every anchor whose MATCH swallows a line break.

    **The property, measured rather than guessed: does what this pattern matched
    contain MORE line breaks than the pattern asked for?** Asked against the real
    `template.py`, `config.py` and `prompts.py` with the flags `main` uses, so the
    answer is about the files the run is about to mutate.

    **The count, and not a yes/no, and here is why.** The obvious rule is "refuse
    if the match contains a newline and the pattern does not spell `\\n`", because
    the table has a row whose anchor is `'"nba": \\("market_line"\\),\\n'` and a
    yes/no would refuse a correct row. It also has a hole the size of the class
    this check exists for: `r"^    for key in keys:(?:.|\\n)*$"` spells `\\n` once
    and matches 26,089 line breaks, and a yes/no waves it through. So the test is
    the COUNT -- matched newlines above spelled ones -- which accepts the NBA row
    (one spelled, one matched) and refuses both the alternation and `\\W*`, and
    does it with no pattern analysis anywhere: nothing in this function knows what
    `*` or `\\W` mean to the engine.

    `(?:.|\\n)*` is caught by the `.` scan as well, since it holds a bare dot, so
    it was never going to reach a mutation. But it got through *this* check, and a
    check with a hole a reader can find by writing the pattern the check is about
    is not a check -- the whole reason this function exists is that the previous
    one could be defeated by `\\W*`.

    **A refusal here can be conservative, and that is the direction that is safe.**
    The property is "the match reaches further than the row's own `\\n`", not "the
    row is wrong": an anchor that swallows the newline at the end of the last line
    in a file is harmless to apply and is still refused. A false refusal costs a
    re-anchored row and a printed line; a false pass costs 26,090 characters of
    somebody's source file. The detail gives the span size precisely so a reader
    can tell the two apart in one look.

    Its own limit, stated twice because it is the part a reader will assume away.
    This measures the MATCH, not what the pattern could do: `\\W*` on an anchor
    followed by a word character stops at the first space and is accepted --
    correctly, because on that anchor it replaces one line. And a row whose anchor
    matches nothing is a `NOT APPLIED` row, which the loop reports and this check
    has nothing to say about. `unescaped_dots` is what catches the pattern that is
    merely wrong today, and both are kept.
    """
    out: list[tuple[str, str]] = []
    sources = ORIGINALS if sources is None else sources
    for label, pattern, _ in (MUTATIONS if rows is None else rows):
        spelled = pattern.count(_SPELLED_NEWLINE)
        for name, span in matched_spans(pattern, sources):
            body = next(t for p, t in sources.items() if p.name == name)
            found = re.search(pattern, body, flags=FLAGS)
            assert found is not None  # matched_spans just reported it
            matched = found.group(0).count("\n")
            if matched > spelled:
                out.append((label, f"matches {span} characters of {name} "
                                   f"({span / max(len(body), 1):.0%} of the file), "
                                   f"crossing {matched} newline(s) the pattern "
                                   f"spells {spelled} of"))
    return out


def invalid_patterns(rows=None) -> list[tuple[str, str]]:
    """(label, detail) for every anchor the regex engine will not compile.

    **A third failure mode, and the one that produced a traceback.** `unescaped_dots`
    walks the pattern as a string, so a pattern that does not compile passes it
    untouched; then `main` reaches `re.subn` and `re.error` propagates out of the
    tool. The reader gets a stack trace from the thing whose entire job is to
    report problems readably, with no table, no exit code and no `.bak` cleanup --
    and an uncompilable pattern is a bad row whichever way it is wrong, so it
    belongs beside the other two rather than as a crash.

    Compiled inside the check rather than trusted, which also means the compiler is
    the authority: this does not re-implement what `re` accepts, it asks `re`.
    """
    out: list[tuple[str, str]] = []
    for label, pattern, _ in (MUTATIONS if rows is None else rows):
        try:
            re.compile(pattern)
        except re.error as exc:
            out.append((label, f"does not compile: {exc}"))
    return out


def anchor_problems(rows=None, sources=None) -> list[tuple[str, str, str]]:
    """Every static reason to refuse a table, as `(label, kind, detail)`.

    **The single union, and it is single on purpose.** The three checks are
    gathered here and nowhere else, because the first version of this file had the
    reporter compute its own union of the same three lists -- and a survivor hunt
    found the consequence: setting `broken = []` in this function changed no test
    at all, because the reporter never asked this function, it asked
    `invalid_patterns` directly. Two implementations of "everything wrong with
    this table" is one more thing than there should be, and the one that survives
    is always the one the tests happen to call.

    The `kind` is the bucket, carried rather than re-derived, so the reporter can
    print three different fixes for three different mistakes without matching on
    the text of a message -- which is how a wording change silently reclassifies a
    finding.

    **The compile check runs FIRST and short-circuits**, because the other two need
    a pattern the engine will accept. Ordered by dependency rather than by
    severity, and stated because an ordering that looks arbitrary in the list is an
    ordering somebody will "tidy" -- and tidying it puts a `re.error` back on the
    path to the refusal.
    """
    broken = invalid_patterns(rows)
    if broken:
        # One finding per bad row and nothing else: the other two checks cannot
        # say anything true about a pattern that does not parse, and a report that
        # mixed a real crossing with a compile error would send the reader to fix
        # the wrong row.
        return [(label, "invalid", detail) for label, detail in broken]
    return ([(label, "dot", detail) for label, detail in dot_problems(rows)]
            + [(label, "crossing", detail)
               for label, detail in newline_crossings(rows, sources)])


def _report_anchor_problems() -> bool:
    """Print every static finding and say whether the run may proceed.

    **Every finding comes from `anchor_problems` and nothing else**, bucketed by
    the `kind` it carries. That is the whole contract: the reporter decides what a
    finding LOOKS like, and the function above decides what there is. A reporter
    with its own copy of the three checks is a second answer to the same question,
    and the survivor hunt found exactly that -- `anchor_problems` could stop
    refusing an uncompilable anchor without a single test noticing, because the
    reporter was not calling it.

    The refusal is still total: nothing has been written when this returns False,
    and it returns False before the baseline run. A row that is merely unusual and
    a row that would destroy the file are both refused, and the message says which
    is which by giving the span size.
    """
    found = anchor_problems()
    if not found:
        return True
    by_kind: dict[str, list[tuple[str, str, str]]] = {}
    for label, kind, detail in found:
        by_kind.setdefault(kind, []).append((label, kind, detail))

    if "dot" in by_kind:
        print(f"  {len(by_kind['dot'])} anchor(s) in the table hold a `.`, which under "
              f"re.S means 'any character")
        print("  including a newline' -- so the match runs to the end of the file and")
        print("  `re.subn(count=1)` replaces everything after it:")
        for label, _, fragment in by_kind["dot"]:
            print(f"    - {label}: ...{fragment}...")
        print("  Every row would report a collection error, which is not a bite, so")
        print("  the table would report coverage for rows that never ran. Write the")
        print("  anchor whole-line (`^...$`), spell any run as `[^\\n]*`, or escape the")
        print("  dot as `\\.`. No mutation has been written; the run stops here on purpose.")
    if "crossing" in by_kind:
        rows = by_kind["crossing"]
        print(f"  {len(rows)} anchor(s) in the table match ACROSS A NEWLINE the "
              f"pattern did not ask for.")
        print("  The spelling is not the problem -- `[\\s\\S]*`, `(?:.|\\n)*` and `\\W*` all")
        print("  cross a newline and none of them holds a bare dot, so the scan above")
        print("  cannot see them. Measured here against the real sources:")
        for label, _, detail in rows:
            print(f"    - {label}: {detail}")
        print("  `re.subn(count=1)` would replace all of it. Write the anchor")
        print("  whole-line (`^...$`) and spell any run as `[^\\n]*`; if the row really")
        print("  means to match a line break, spell it as `\\n` and it is allowed. No")
        print("  mutation has been written; the run stops here on purpose.")
    if "invalid" in by_kind:
        rows = by_kind["invalid"]
        print(f"  {len(rows)} anchor(s) in the table are not valid regexes:")
        for label, _, detail in rows:
            print(f"    - {label}: {detail}")
        print("  `re.subn` would raise `re.error` out of this tool and the run would")
        print("  die with a traceback instead of a table. No mutation has been written;")
        print("  the run stops here on purpose.")
    return False


def _purge_bytecode() -> None:
    """Delete every `__pycache__` so a mutation can never be masked by a stale
    `.pyc`. See the module docstring for why this is load-bearing."""
    for d in pathlib.Path(".").rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)


def run() -> tuple[int, int, int]:
    """(failed, passed, errored).

    **`errored` is returned rather than folded into `failed` or ignored.** A
    mutation that does not parse makes pytest exit 2 without collecting the
    suite, so `failed == 0` and the tally reads a row as SILENT -- "no test covers
    this" -- which is a statement about coverage derived from a run that never
    executed a test. The early return below is what stops that, and it is why
    the value exists: `count("failed")` on a collection-error output is a number
    about a traceback.
    """
    _purge_bytecode()
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    p = subprocess.run(
        # `--tb=no` is not a quietness setting; see `_last_count`. Without it
        # every failure prints its traceback, and a traceback is a page of text
        # containing both count words.
        ["uv", "run", "--extra", "dev", "python", "-m", "pytest", SUITE,
         "-q", "--tb=no", "-p", "no:cacheprovider"],
        capture_output=True, text=True, env=env,
    )
    out = p.stdout + p.stderr
    if p.returncode not in (0, 1):
        return -1, 0, 1

    def count(word: str) -> int:
        return _last_count(out, word)

    return count("failed"), count("passed"), 0


#: The words the tally reads, and the two test functions in
#: `tests/test_mutation_tally.py` that pin them. Kept here so a test can import
#: the same pair the harness uses rather than re-typing it and drifting.
COUNT_WORDS = ("failed", "passed")


def _last_count(out: str, word: str) -> int:
    """The count `word` reports, taken from the LAST mention in `out`.

    **The last, and the reason is that pytest's `-q` summary is the last thing it
    prints.** Everything before it is noise that happens to contain the same
    words: tracebacks quote the assertion that failed, `E   assert 1 == 2` lines
    carry the numbers, and a failure's own message can name a count. `re.search`
    took the FIRST match anywhere in `stdout + stderr`, so:

    * a run with 26 real failures reported `2 failed`, read out of an
      intermediate line, and the mutation looked like a partial bite;
    * 257 real passes reported as `26`, from the same line;
    * a run whose output echoed "0 passed" reported `passed: 0` and nothing else.

    That last one is the live path to a FALSE PASS. A mutation that breaks
    something is judged on `failed > 0`; if a `0 failed` is echoed anywhere
    earlier in the output, `re.search` reads THAT and calls the row silent, so a
    mutation that broke five tests is filed under "did not bite". A number read
    out of a traceback is a number about a traceback.

    `[-1]` because the summary line is last, not because "last" is a rule about
    how many numbers a pytest run prints. `--tb=no` is passed for the same
    reason and is load-bearing rather than cosmetic: with tracebacks on, the
    output is large enough that the last-match heuristic is being asked to find
    one line near the end of a page, and the page contains the words.
    """
    found = re.findall(rf"(\d+) {word}", out)
    return int(found[-1]) if found else 0


def classify(label: str, bite: bool, broken: bool = False) -> str:
    """Where a row goes, as one function so the rule can be tested directly.

    The FIVE outcomes a row can have, and the mark is checked AGAINST the
    observation rather than in place of it:

    * `BROKEN` -- the run ERRORED, so the row's mutation did not parse and the
      suite was never collected. The row did not bite, and it did not pass: it
      did not run. Checked FIRST, before the mark, because "was the
      expected-silent label right?" is unanswerable about a run that never
      happened, and because the old behaviour -- reading a collection error as
      `BITES` -- put the best possible news in a table cell that should have said
      the row is untested.
    * `EXPECTED` -- the row is marked expected-silent and did not bite. The mark
      is a claim about what should happen, and the run agreed.
    * `MISLABELLED` -- the row is marked expected-silent and DID bite. A
      contradiction between the table's own labelling and the table's own
      measurement, which is a defect in the harness. This case did not exist
      before: the mark was tested before `elif not bite`, so a marked row was
      filed as documented-silent whatever it did.
    * `SILENT` / `BITES` -- an unmarked row, reported as observed.

    Extracted from `main` because a rule that can only be exercised by running
    30 mutations is a rule nobody runs on purpose, and because the bug being
    fixed here is a rule about ORDER: a table that lists `not bite` after the
    mark has decided the outcome. As one function the order is the code, and
    `tests/test_mutation_tally.py` covers all cases without a subprocess.
    """
    if broken:
        return BROKEN
    marked = EXPECTED_SILENT_MARK in label
    if marked:
        return EXPECTED if not bite else MISLABELLED
    return BITES if bite else SILENT


def _drop_backups() -> None:
    """Remove the recovery copies, once the restore has been confirmed.

    They were written so an INTERRUPTED run cannot leave mutated source behind,
    which is why they exist; they are not a log and nothing reads them. The
    unlink used to sit at the end of the success path only, so every non-zero
    exit -- a silent mutation, a biting canary, a mislabelled row -- returned 1
    having left three untracked files in the working tree. That is litter after a
    run that finished, and it is the case where litter is least defensible: the
    interruption it protects against did not happen, or the run would not have
    reached the cleanup at all.

    A genuine crash still leaves them, which is the point of writing them: SIGKILL
    and a pulled power cord run no cleanup, and that is the one case where the
    `.bak` is the recovery path rather than litter.
    """
    for path in ORIGINALS:
        path.with_suffix(path.suffix + ".bak").unlink(missing_ok=True)


def main() -> int:
    # BEFORE the baseline run and before a single byte is written. A table whose
    # first row is wrong would otherwise cost a full sweep to discover, and a
    # refusal that came after the mutations had been applied would have put 30
    # mutated files on disk with the `.bak` as the only way back.
    if not _report_anchor_problems():
        return 1
    base_failed, base_passed, base_errored = run()
    if base_errored or base_failed:
        print(f"  BASELINE IS RED: {base_failed} failed, {base_errored} errored "
              f"({base_passed} passed).")
        print("  Every mutation would report BITES for free, so the table below would")
        print("  be meaningless. Fix the baseline first.")
        return 1
    names = ", ".join(p.name for p in ORIGINALS)
    print(f"  baseline: {base_passed} passed, 0 failed -- the table below is meaningful")
    print(f"  {len(MUTATIONS)} mutations against {names}\n")

    silent: list[str] = []
    expected: list[str] = []
    mislabelled: list[str] = []
    broken: list[str] = []
    canary_ok = False
    for path, text in ORIGINALS.items():
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_text(text)
    print(f"  originals also at " + ", ".join(
        f"{p.name}.bak" for p in ORIGINALS) + ", in case this run is interrupted")

    try:
        for label, pattern, replacement in MUTATIONS:
            # Every file may hold the anchor, and the row is applied to whichever
            # one does. The template, config.py and prompts.py are all writers,
            # so all three are fair game for a row that reinstates a deleted
            # claim.
            for target, keep in ORIGINALS.items():
                new, n = re.subn(pattern, replacement, keep, count=1, flags=re.M | re.S)
                if n == 1:
                    target.write_text(new)
                    try:
                        failed, passed, errored = run()
                    finally:
                        # Restore BEFORE reading the tally, and unconditionally.
                        # An exception out of `run()` used to leave the mutated
                        # source on disk until the outer `finally`, and the outer
                        # `finally` restores the OTHER files first, so a crash
                        # between the two wrote this one back over a mutation the
                        # next run's baseline would then have measured.
                        target.write_text(keep)
                    break
            else:
                print(f"  {label[:56]:<56} NOT APPLIED (anchor in no file)")
                silent.append(f"{label} [not applied]")
                continue
            if errored:
                # Its OWN verdict string, because "BITES" here would be a
                # statement about a guard and this is a statement about a row. A
                # mutation that did not parse tells the reader nothing about
                # whether any test covers the code it was aimed at, and printing
                # the good outcome is how two historical rows came to read as
                # coverage when they had destroyed the file they were mutating.
                verdict, bite = "BROKEN (collection error)", False
            elif failed > 0:
                verdict, bite = f"BITES ({failed} failed)", True
            else:
                verdict, bite = f"*** SILENT *** ({passed} passed)", False
            print(f"  {label[:56]:<56} {verdict}")
            if label == CANARY:
                # The canary must be SILENT. It was previously `canary_ok = True`
                # in BOTH the biting and the silent branch, which made the check
                # below unreachable and the closing line a lie: pointed at
                # `MAX_FACTORS` -- which this round pins, so it bites -- the run
                # printed "BITES (1 failed)" and then "the canary stayed silent as
                # it should", and exited 0. A control that cannot fail is not a
                # control, and this is the only negative control the tool has.
                #
                # A BROKEN canary is `not bite` and so would set `canary_ok`. A
                # canary that destroys the file is not a passing control either,
                # so `broken` is checked separately: the canary is the one row
                # whose own bucket is asserted, and a canary filed under BROKEN
                # means the run is not measuring anything.
                canary_ok = not bite
                if errored:
                    broken.append(CANARY)
            else:
                # The mark records an EXPECTATION and is checked against the
                # observation by `classify`; see its docstring for the case that
                # did not exist before, where a marked row was filed as
                # documented-silent whether it bit or not.
                #
                # An `else` and not a bare statement after the canary branch: the
                # canary is a control, not a row, and a silent canary is the
                # passing outcome. Filing it under "did not bite" as well would
                # make every clean run report a silent mutation and exit 1 -- the
                # mirror of the defect being fixed here, and one this refactor
                # introduced before it was caught by the first clean run.
                bucket = classify(label, bite, errored)
                if bucket == BROKEN:
                    broken.append(label)
                elif bucket == EXPECTED:
                    expected.append(label.split(" [")[0])
                elif bucket == MISLABELLED:
                    mislabelled.append(label)
                elif bucket == SILENT:
                    silent.append(label)
    finally:
        for path, text in ORIGINALS.items():
            path.write_text(text)

    failed, passed, errored = run()
    print(f"\n  restored: {passed} passed, {failed} failed, {errored} errored")
    if errored or failed:
        # No cleanup here on purpose. The tree is wrong and the `.bak` is what
        # fixes it, so removing the recovery copy would destroy the only
        # remaining copy of the original.
        print("  RESTORE FAILED -- do not trust the tree. The .bak files are the "
              "recovery path and have been left in place.")
        return 1
    # Every path from here on is a path where the tree was restored, so the
    # recovery copies are litter rather than a safety net.
    _drop_backups()
    if expected:
        print(f"  {len(expected)} mutation(s) silent as documented:")
        for s in expected:
            print(f"    - {s}")
    # Checked BEFORE the `silent` report and before the canary, because a
    # mislabelled row means the table's own labelling is wrong, and everything
    # the run says after this point is read against that labelling. Its own
    # return is 1 so a run that has one cannot exit 0.
    if mislabelled:
        print("  A ROW LABELLED EXPECTED-SILENT ACTUALLY BITES -- the harness is "
              "misreporting itself:")
        for s in mislabelled:
            print(f"    - {s}")
        print("  The label is a claim about what should happen; the run is what did.")
        print("  Either the expectation is now wrong (a test was added, so the row is "
              "a real guard and the mark must go) or the mark is on the wrong row.")
        return 1
    # Checked alongside the mislabelled rows and BEFORE the `silent` report, for
    # the reason the order is the fix rather than a style: a broken row is
    # simultaneously the loudest and the quietest finding in the table. It is not
    # on the silent list (so a reader stopping there concludes the table is
    # clean), and it used to be printed as a BITE (so a reader skimming the rows
    # concludes it is covered). Reported on its own, with its own return of 1, so
    # a run holding one cannot exit 0 -- which is what it did while a reviewer's
    # `.*` anchor was in the table.
    if broken:
        print(f"  {len(broken)} mutation(s) did not parse, so they were never "
              f"collected:")
        for s in broken:
            print(f"    - {s}")
        print("  A collection error is NOT a bite: it says the row's mutation broke")
        print("  the file, so the row tested nothing at all and proves no coverage.")
        print("  It is also the reason an anchor holding a DOTALL `.` is refused")
        print("  before this loop starts -- such a match runs to the end of the file.")
        print("  Fix the anchor (whole-line `^...$`, `[^\\n]*` for a run, `\\.` for a")
        print("  literal dot) or the replacement, and re-run.")
        return 1
    if silent:
        print(f"  {len(silent)} mutation(s) did not bite:")
        for s in silent:
            print(f"    - {s}")
        return 1
    if not canary_ok:
        print("  THE CANARY BIT -- the harness is misreporting; distrust the table "
              "above entirely.")
        print("  Either the canary now covers something real (a test was added for "
              "it, so it is no longer a control) or the mutations are not being "
              "applied. Fix the canary before reading any row.")
        return 1
    # The `.bak` files were already removed above, once the restore was
    # confirmed; nothing to do here. Named so a reader looking for the unlink
    # finds that it moved and why, rather than concluding it was dropped.
    #
    # Reached only when `silent`, `mislabelled` and `broken` are all empty and the
    # canary stayed silent, so every claim in this sentence is a list the run just
    # checked rather than a thing the reader has to take on trust.
    print("  every mutation bit, or was documented as expected-silent; none was "
          "broken, none was mislabelled, and the canary stayed silent as it should")
    return 0


if __name__ == "__main__":
    sys.exit(main())
