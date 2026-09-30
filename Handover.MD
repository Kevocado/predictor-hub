HANDOVER — player-model accuracy remediation
Written 2026-09-28, at the end of a long session. Everything below was verified at the time it was written; re-verify before relying on it.

1. What happened, in one paragraph
A visibly wrong "total yards" figure in the CFB player panel turned out to be the visible end of a habit: across all four repos, tests asserted that a value was produced, never that it was correct. Ten pull requests were merged fixing specific instances, four adversarial reviews were run, and two of my own claims were retracted because they did not survive proper measurement. A large number of the defects were in work done earlier in the same session, and several "fixes" were regressions I had introduced while fixing something else.

2. Merged and verified on main
Repo	PRs	Tests	Verified on main
NFL_Predictor	#9 8619539, #10 b027e03, #11 a50302b	231	yes
CFB_Predictor	#12 6ab8e1, #13 7697c03, #17 7cf0192a1	289	yes (checked by content)
Sports_Predictor	#8 162094, #9 04aad6e	189	yes
PL_Predictor	#7 4975f22c, #13 4dc6115	489 / 93 in affected suites	yes (checked by content)
predictor-hub	#20 237001f1 (docs)	n/a	yes
Open PRs not ours — do not touch: Sports_Predictor#6, predictor-hub#18, #5, #4.

Verify-on-main block (run this first)
cd /Users/sigey/Documents/Projects.nosync
for r in NFL_Predictor CFB_Predictor Sports_Predictor PL_Predictor; do
  git -C $r fetch -q --prune origin
  echo "=== $r $(git -C $r rev-parse --abbrev-ref HEAD) behind=$(git -C $r rev-list --count HEAD..origin/main)"
done
# content checks, not ref checks
git -C PL_Predictor       show origin/main:src/pl_predictor/evaluate/promotion_rule.py | grep -c "majority must be in"   # expect 1
git -C PL_Predictor       show origin/main:docs/AI_CONTINUITY.md | grep -c "vs threshold 0.000081"                        # expect 1
git -C CFB_Predictor      show origin/main:src/cfb_predictor/data/team_stats.py | grep -c "fillna(0) > 0"                        # expect 1
# CFB expects 3, not 1: one definition plus two call sites. NFL's helper is named
# _present, so grep NFL for the filter in _summarize_games, not for the symbol.
git -C CFB_Predictor      show origin/main:src/cfb_predictor/tracking/store.py | grep -c "_pair_present"                        # expect 3
git -C NFL_Predictor     show origin/main:src/nfl_predictor/tracking/store.py | grep -c 'ats_hit"\].notna() & _pair_present'  # expect 1 (was 0 = the defect)
git -C NFL_Predictor     cat-file -e origin/main:docs/player-prop-accuracy-blocker.md                                                          # expect present
# WARNING: the NFL check above returned 0 on 2026-09-28 and it was NOT a stale
# check -- it was a live defect (the aggregate had no pair-presence filter, so
# pct_ats_correct counted fabricated calls). An unexpected result from one of these
# is a FINDING, not a stale check. Trace it to the line that does the work before
# explaining it away. Fixed in NFL #15; see the ledger, "Session 2".
3. The one thing to understand
Every defect across four repos and four reviews was the same shape: a test asserted that a value came out, never that it was the right value. So these all shipped green:

a join on (season, week, team) — not unique, and CFBD labels every bowl week: 1
a min_count presence check that could never fire, because groupby.sum() coerces an all-NaN column to 0.0
a function asking for a column only its hand-built fixtures had
a lint step that could never pass, because the linter was not installed (3 repos)
a KeyError from inside pandas that was two hops from the actual cause
a committed tolerance measured on one week, which was false at 22-season scale
The sharpest instance: in CFB, the first version of a fix passed 22 green tests while doing nothing, because one of its two guards had no test. Mutation verification found it. Nothing else would have.

4. Outstanding tasks, in priority order
Task 1 — PL CI: split the warm step into its own job (highest value)
PL_Predictor/.github/workflows/tests.yml. The gating suite needs data/cache/, which is gitignored, so a fresh CI runner has none of it. Two attempts so far:

attempt 1: gate fetched on the gated run → 60 min, timed out
attempt 2: added a warm step inside the same 60-min job → still timed out at 59m15s, because the cold fetch needs >60 minutes (understat fetches one file per match, ~4,600 requests). Zero test failures; purely the ceiling.
So it has to be a separate job with its own budget, which also keeps the gate fast. Replace the single pytest: job with these two. Leave the on: and concurrency: blocks alone.

  warm-cache:
    # Populates data/cache/ from FPL, ClubElo and football-data.co.uk.
    #
    # Separate job from the gate because it does not fit the gate's budget: the
    # understat shot loader fetches one file per match with a 0.3s delay, ~4,600
    # requests for the full historical window. Measured on CI: killed at 59m15s by a
    # 60-minute job ceiling, having produced no test output. Own job is also what
    # keeps the *gate* fast, which is the point of having a gate.
    #
    # Once this succeeds the post-job cache step persists data/cache/ and later runs
    # are cache hits: the gate drops from 60+ minutes to minutes.
    runs-on: ubuntu-latest
    timeout-minutes: 150
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: pyproject.toml
      - name: Stamp the day
        # Same key as the gate job, so the gate restores exactly what this saved.
        id: date
        run: echo "stamp=$(date -u +%Y-%m-%d)" >> "$GITHUB_OUTPUT"
      - name: Restore any partial upstream cache
        # So an interrupted warm resumes. Prefix match, not the same key:
        # actions/cache skips a save when the key already exists.
        uses: actions/cache@v4
        with:
          path: data/cache
          key: pl-upstream-caches-${{ steps.date.outputs.stamp }}
          restore-keys: pl-upstream-caches-
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]" || pip install -e . pytest pytest-mock ruff
      - name: Warm the upstream cache
        # continue-on-error on the STEP deliberately: a run killed partway has usually
        # downloaded most of the data, and we want the post-job step to save that
        # partial cache so the next attempt resumes instead of restarting.
        continue-on-error: true
        env:
          PYTHONPATH: ${{ github.workspace }}/src
          PL_ALLOW_NETWORK: "1"
        run: pytest tests/ -q 2>&1 | tail -30

  pytest:
    # The gate. Network guard ON, against the warmed cache, so it does not depend on
    # any third party being available at gate time.
    needs: warm-cache
    # always() so a warm failure still produces a verdict. Without it a failed warm
    # skips the gate and a broken PR looks green because nothing ran.
    if: always()
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: pyproject.toml
      - name: Stamp the day
        id: date
        run: echo "stamp=$(date -u +%Y-%m-%d)" >> "$GITHUB_OUTPUT"
      - name: Restore the cache warmed above
        uses: actions/cache@v4
        with:
          path: data/cache
          key: pl-upstream-caches-${{ steps.date.outputs.stamp }}
          restore-keys: pl-upstream-caches-
      - name: Install
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]" || pip install -e . pytest pytest-mock ruff
      - name: Gating suite
        env:
          PYTHONPATH: ${{ github.workspace }}/src
        run: pytest tests/ -q -m "not network"
      - name: Network-marked tests (live upstreams)
        if: github.event_name == 'workflow_dispatch'
        env:
          PYTHONPATH: ${{ github.workspace }}/src
        run: pytest tests/ -q -m network
      - name: Lint
        env:
          PYTHONPATH: ${{ github.workspace }}/src
        run: |
          ruff check src tests --select E9,F63,F7,F82 || \
            (echo "::error::ruff found blocking errors"; exit 1)
Validate before pushing: python -c "import yaml; yaml.safe_load(open('.github/workflows/tests.yml'))". Then delete the now-stale "Warm the upstream cache" step and the KNOWN LIMITATION comment that are still in the current file.

Task 2 — delete the cache_HIDDEN duplicate

*** DO NOT RUN THE rm -rf. Measured 2026-09-28: it is NOT a duplicate. ***
It holds 772 files the real cache does not have, across four sources the real cache
lacks entirely: fpl_players (659 files, real cache: 0), pulselive (80 vs 0),
sportsbook (21 vs 0), odds (1 vs 0) — 4.8MB, dated 2026-08-23 to 09-12. The two
sources present in both are OLDER in cache_HIDDEN (Aug) than in the real cache
(Sep 27), the signature of a stretch when CACHE_DIR pointed one level too deep,
later corrected and re-fetched for two of the six sources and never for the rest.

The `git log -S cache_HIDDEN` evidence below is TRUE but does not imply the
conclusion: it shows no code names the *directory*, not that the *data* is unneeded.
Consumers address data/cache/<source> and would simply re-fetch — and that re-fetch
is the >60-minute problem this whole task list is about.

The verification below is also incapable of detecting the loss. CACHE_DIR is fixed
at PROJECT_ROOT/data/cache, with no env override and no nested-cache construction, so
data/cache/cache_HIDDEN is unreachable by any code path. Deleting it cannot change a
single test result; the two named test files would pass either way, and that pass is
worthless.

Left in place deliberately. 93MB in a gitignored directory is a fair price for an
irreversible deletion resting on a disproven premise. See the ledger, "Session 2".

Original (unsafe) instructions retained below for context only:

PL_Predictor/data/cache/cache_HIDDEN is 93M — 55% of what looked like a 176M cache — and it is a complete duplicate of the real cache: same ten subdirectory names, same sources. git log -S cache_HIDDEN -- . returns nothing, so no tracked code in any commit has ever referenced it. It is a local artifact of a CACHE_DIR pointed one level too deep.

grep -rn "cache_HIDDEN" PL_Predictor 2>/dev/null | head     # find what created it
mv PL_Predictor/data/cache/cache_HIDDEN /tmp/cache_HIDDEN_aside
cd PL_Predictor && PYTHONPATH=src .venv/bin/python -m pytest tests/test_public_snapshot.py tests/test_facts.py -q
rm -rf /tmp/cache_HIDDEN_aside     # only if the above passes
Move rather than delete, so a re-fetch is recoverable.

Task 3 — decide the cache question with a measurement
Real cache after Task 2: 86M.

dir	size	verdict
fpl_history	41M	real, daily-changing, upstream-owned
understat_shots	40M	real, and the >60-min one-file-per-match fetcher
football_data + fpl_events + other_competitions	4.3M	small, possibly deterministic
understat	584K	real
rest	0B	empty placeholders
Do not commit all 86M: a daily-changing snapshot of someone else's data, carried by every clone and every agent, 10k files of merge churn.

But the 4.3M seed is worth testing. If the network-blocked tests only read football_data and fpl_events, committing that slice (un-ignore just those paths in .gitignore) removes the warm step entirely and CI goes green today.

The measurement needed:

cd /Users/sigey/Documents/Projects.nosync/PL_Predictor
PYTHONPATH=src .venv/bin/python -m pytest tests/ -q -p no:randomly 2>&1 | grep FAILED | head -25
23 tests fail with outbound network blocked in tests. Find which cache dirs they read. That decides seed-vs-warm-step. If it is fpl_history, the warm/gate split is unavoidable and 41M is too big and too churny to commit.

Task 4 — CFB container cache seeding
The 351-call CFBD backfill ran and produced 42,190 team-games across 21,095 games, 2004-2025, plus 436,801 player-games. But it filled a local gitignored cache. data/cache/ is gitignored and the Dockerfile creates the cache dirs empty, so production still starts cold. Needs either a one-off operator step on the VPS or an idempotent startup job. Also: the Azure workflow does not pass CFBD_API_KEY and does not invoke the script. Nothing blocks on this — the reconciliation has no serving caller — but a reader could easily assume the backfill reached production.

Task 5 — user decision, not work
NFL pre-kickoff window. min-replicas: 0 means the next tick can land after kickoff, so no genuine pre-game snapshot exists. This is the binding constraint on prop accuracy — fixing the nflverse 404 alone changes nothing. Options: (a) min-replicas: 1 (costs money), (b) timer-triggered pre-kickoff tick, (c) accept it.

Task 6 — open review findings, not yet fixed
PL tests/test_blend_validation.py: the "tripwire" that should fire if someone unifies the two blend unions cannot fire — it asserts on a dict literal the test itself defines, and on a hasattr for a name that appears nowhere else in the tree.
PL date_keys.py: astype("datetime64[ns]") raises OutOfBoundsDatetime for year-2500 dates, so it is not total. It raises rather than corrupting, which is right.
PL player_goals.py: the documented None fallback is now unreachable, and reaching it would blend 50/50 against an uncalibrated union — an undisclosed behaviour change.
CFB/NFL ats_hit data migration. Rows the old build fabricated (non-null ats_hit with a null cover probability) are excluded from the aggregate now but are still in the database. Identifiable; needs a migration with its own verification.
Sports_Predictor src/lib/playerRank.ts still repeats a POSITION_MARKETS claim that the symbol contradicts. Left alone deliberately — different concern.
Sports_Predictor: tsconfig.*.tsbuildinfo are tracked, not gitignored, and the committed copy lists deleted files.
5. Environment gotchas that will waste your time
Venvs: NFL_Predictor/.venv, CFB_Predictor/.venv, PL_Predictor/.venv. Each repo's tests run with PYTHONPATH=$(pwd)/src <that repo's venv>/bin/python -m pytest.
CFB tests need the key: set -a && . ./.env && set +a first. The network-marked reconciliation test spends metered CFBD quota — ~1,765 calls remained at last check. Use -m "not network" to skip it.
PL worktrees need data symlinked or you get RuntimeError: No FPL player-gameweek history could be loaded: rm -rf data && ln -s /Users/sigey/Documents/Projects.nosync/PL_Predictor/data data
PL has a network guard (from main, another agent's work). Tests must not reach the network. Warm with PL_ALLOW_NETWORK=1. It made the suite go from 60 min to 4m47s on CI.
ruff is a gating step in all three Python repos. It was missing from dev in two of them, which is why the step could never pass.
zsh gotcha: # only starts a comment at the start of a word. cmd # note passes # and the words to the command. Put comments on their own line.
Merging deploys nothing — every deploy-azure*.yml is workflow_dispatch-only.
6. Uncommitted work that is NOT ours — do not touch
CFB_Predictor/.github/workflows/deploy-azure-cfb.yml — VPS cutover
Sports_Predictor/.github/workflows/deploy-azure.yml and src/api/client.ts — VPS cutover
predictor-hub/index.html and .github/workflows/azure-static-web-apps-brave-moss-064ee9b0f.yml
PL_Predictor/.claude/worktrees/weather-and-manager-tenure-experiments (untracked)
predictor-hub/index.html needs your eye. The uncommitted change was the VPS cutover applied to the old grid layout. main has since been rewritten to a new layout that already points at the VPS, so the change's substance is already there by another route, and the conflict was resolved in favour of main. Your version is preserved in stash@{0}, on branch backup/pre-hub-tidy, and in the scratchpad. Drop the stash only after eyeballing the new page.

7. Other agents working in these repos right now
Re-fetch origin before every claim about main — it moves constantly (automated public snapshot refreshes commit to main).

PL: fix/pl-suite-network, fix/pl-state-denominators, worktrees at /private/var/folders/.../opencode/pl-deploy and .../pl-origin
Worktrees at Projects.nosync/ci-worktrees/PL_Predictor and Projects.nosync/phase4-worktrees/PL_Predictor
Someone is actively editing PL_Predictor/.github/workflows/tests.yml. Do not reconstruct that file from memory — read it first. This is why the warm/gate split in Task 1 is a replacement for the jobs block, not a whole-file overwrite.
8. Local worktrees
All are clean and pushed; none hold unsaved work.

path	branch	note
PL_Predictor/pl-fix-worktree	fix/promotion-rule-holes	merged, remote deleted
Projects.nosync/cfb-fix-worktree	fix/cfb-review-fixes	merged, remote deleted
Projects.nosync/nfl-fix-worktree	fix/player-prop-accuracy-blocker	merged
Projects.nosync/sp-push-worktree	fix/team-yardage-total	merged
Projects.nosync/hub-docs-worktree	docs/player-model-remediation-2026-09-27	merged as #20
Projects.nosync/predictor-hub	main	1 ahead (local impeccable skill), 0 behind
The hub-docs-worktree is a separate worktree created because the main checkout had uncommitted user work. That is the pattern to follow: never switch branches in a checkout that has uncommitted work; use a worktree.

9. Where the documentation lives
All merged to predictor-hub main:

docs/superpowers/2026-09-28-what-changed-and-why.md — plain-language intro, start here
docs/superpowers/ledgers/2026-09-28-player-model-accuracy-remediation.md — the full record: every ruling, measurement, retraction, and open decision
docs/superpowers/handoff/2026-09-28-player-model-remediation-handoff.md — engineering orientation
docs/superpowers/plans/2026-09-27-player-model-accuracy-remediation.md — task list
PL_Predictor/docs/AI_CONTINUITY.md — PL's own ledger (EXP-2026-24…28)
NFL_Predictor/docs/player-prop-accuracy-blocker.md — why prop accuracy reads 0
The ledger is append-only and deliberately records the retractions rather than quietly correcting them. Keep appending to it.

10. Two things to carry forward
A merged PR is not the same as deployed. CFB #13 merged at 02:25; a further commit was pushed to the same branch at 03:0x; a merged PR does not pick up later commits. For two hours main served a tolerance I had already retracted, an unguarded add_total_yards, and an aggregate still counting fabricated verdicts — reviewed, mutation-verified, and not deployed. Found by diffing main against the branch. A green "Merged" badge is not evidence; git log origin/main..origin/<branch> must be empty, or a content check.

Do not measure a property on one sample. Two of this session's retractions came from a tolerance computed on 2023 week 1 and presented as universal. At 22 seasons it was 92.4% and a max of 337, not 95% and 35. If a number is going into a docstring as a property of a source, it needs the whole source.
