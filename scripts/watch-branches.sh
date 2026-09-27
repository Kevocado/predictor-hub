#!/usr/bin/env bash
# The reviewer's watcher: wake when any predictor repo's work branch or PR ref moves.
# Polls every 15 min (cheap while sleeping); prints the refs that changed and exits 0.
# Run it in the background; when it exits, review what moved, then start it again.
#
#   ROOT=~/code ./scripts/watch-branches.sh      # ROOT holds clones of all seven repos (default: parent of this repo)
set -u
B=${B:-claude/sports-predictors-frontend-plan-qpab3v}
ROOT=${ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}
REPOS="predictor-hub NFL_Predictor CFB_Predictor NBA_Predictor PL_Predictor F1_Predictor Sports_Predictor"
INTERVAL=${INTERVAL:-900}

heads() {
  for r in $REPOS; do
    echo "$r $(git -C "$ROOT/$r" ls-remote origin "refs/heads/$B" 2>/dev/null | cut -c1-12)"
    git -C "$ROOT/$r" ls-remote origin 'refs/pull/*/head' 2>/dev/null | awk -v r="$r" '{print r " " $2 " " substr($1,1,12)}'
  done
}

base=$(heads)
while true; do
  sleep "$INTERVAL"
  now=$(heads)
  # Ignore a transient empty answer (network hiccup): every branch line must carry a sha.
  if [ -n "$now" ] && ! echo "$now" | grep -qE '^[A-Za-z0-9_-]+ $' && [ "$now" != "$base" ]; then
    diff <(echo "$base") <(echo "$now") | grep '^>'
    exit 0
  fi
done
