#!/usr/bin/env bash
# Poll the predictor repos. Print what moved. Exit 0.
#
#   ./watch.sh            one poll: diff against baseline, update baseline
#   ./watch.sh --quiet    same, but print nothing when nothing moved
#   ./watch.sh --watch    loop forever, every 2 min
#
# This does one job: notice change and exit. It does not act on it. A baseline
# is written on the first poll so a starting checkout is not reported as a flood
# of activity.
set -u

ROOT=${ROOT:-/Users/sigey/Documents/Projects.nosync}
REPOS="predictor-hub PL_Predictor F1_Predictor Sports_Predictor NBA_Predictor NFL_Predictor"
BASE=${BASE:-/tmp/repo-watcher.baseline}
LOG=${LOG:-/tmp/repo-watcher.log}
INTERVAL=${INTERVAL:-120}
QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

say() { printf '%s %s\n' "$(date -u +%FT%TZ)" "$*"; echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

snapshot() {
  for r in $REPOS; do
    echo "$r main $(git -C "$ROOT/$r" ls-remote origin refs/heads/main 2>/dev/null | cut -c1-12)"

    # PR state: number, branch, review decision.
    gh api "repos/Kevocado/$r/pulls?state=open&per_page=100" --paginate \
      --jq ".[]|\"pr $r #\(.number) \(.head.ref) \(.review_decision // \"\")\"" 2>/dev/null

    # Comments, by ID. NOT by timestamp.
    #
    # A pull's updated_at is not a reliable change signal: measured here, it
    # lagged a fresh comment by seconds and then did not advance on the next
    # poll, so a diff keyed on it reported "no change" for a comment that had
    # demonstrably landed. Comment IDs are monotonic and immutable, so the
    # newest one is a sound high-water mark: if it has not moved, nothing new
    # was said. Also uses the core API, not `gh pr list` — pr list is backed by
    # the eventually-consistent search index and serves stale rows.
    local newest
    newest=$(gh api "repos/Kevocado/$r/issues/comments?per_page=100" --paginate \
      --jq '.[].id' 2>/dev/null | sort -n | tail -1)
    echo "$r comments $newest"
  done
}

poll() {
  # The snapshot goes to a FILE, not into a variable that is then handed to
  # diff. This is the bug that made this watcher silently useless: `now` was a
  # multi-line string, `diff "$BASE" "$now"` treated it as a FILENAME, diff
  # errored into /dev/null, and every poll reported "no change" forever — while
  # looking exactly like a healthy idle watcher. Caught with `bash -x`, which
  # showed diff being handed the snapshot text as its second argument.
  local now="$BASE.now"
  snapshot > "$now"

  if [ ! -f "$BASE" ]; then
    cp "$now" "$BASE"
    say "baseline written ($(wc -l < "$BASE" | tr -d ' ') lines)"
    return
  fi

  # Only '>' lines: a line that disappeared is a PR closing, which is not work.
  local moved
  moved=$(diff "$BASE" "$now" 2>/dev/null | grep '^>' | sed 's/^> //')
  if [ -n "$moved" ]; then
    printf '%s\n' "$moved" | while read -r line; do say "MOVED  $line"; done
    cp "$now" "$BASE"
    say "---"
  elif [ "$QUIET" -eq 0 ]; then
    say "no change"
  fi
}

case "${1:-}" in
  --watch)
    say "watching $REPOS every ${INTERVAL}s (log: $LOG)"
    while true; do
      poll
      # A laptop sleeps. Catch up on everything missed, do not replay it.
      sleep "$INTERVAL"
    done
    ;;
  *) poll ;;
esac
