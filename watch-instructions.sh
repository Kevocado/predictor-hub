#!/usr/bin/env bash
# Wait for the next [claude-review-instructions] comment on any predictor PR, print it, exit.
REPOS="predictor-hub NFL_Predictor CFB_Predictor NBA_Predictor PL_Predictor F1_Predictor Sports_Predictor"
STATE="${HOME}/.claude-review-seen"; touch "$STATE"
while true; do
  for r in $REPOS; do
    gh api "repos/Kevocado/$r/issues/comments?sort=created&direction=desc&per_page=20" \
      --jq '.[] | select(.body | startswith("[claude-review-instructions]")) | "\(.id)\t\(.html_url)"' 2>/dev/null |
    while IFS=$'\t' read -r id url; do
      grep -qx "$id" "$STATE" && continue
      echo "$id" >> "$STATE"
      echo "=== NEW INSTRUCTIONS: $url"
      gh api "repos/Kevocado/$r/issues/comments/$id" --jq .body
      exit 10
    done
    [ "${PIPESTATUS[1]}" = 10 ] && exit 0
  done
  sleep 300
done
