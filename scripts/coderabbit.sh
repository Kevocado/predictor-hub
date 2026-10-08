#!/usr/bin/env bash
# Read CodeRabbit's findings on a PR BEFORE merging it.
#
#   scripts/coderabbit.sh Kevocado/NBA_Predictor 18        # Critical/Major that are still open
#   scripts/coderabbit.sh Kevocado/NBA_Predictor 18 --all  # everything, including Minor and addressed
#
# Exit status: 0 = no unaddressed Critical/Major finding, 2 = at least one, 1 = usage/API error.
# Chainable:  scripts/coderabbit.sh R N && gh pr merge N -R R --merge --match-head-commit SHA
#
# A finding CodeRabbit marks "Addressed in commit ..." is shown as ADDRESSED and does not fail the
# gate, and neither does one where CodeRabbit ITSELF replied in the thread with "Review thread resolved"
# (it posts that only after re-checking the code). A reviewer's own "verified" reply does not clear it.
# For a Critical/Major, check the fix rather than trusting the marker.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=${1:-}; PR=${2:-}; MODE=${3:-}
[ -n "$REPO" ] && [ -n "$PR" ] || { echo "usage: $0 owner/repo pr-number [--all]" >&2; exit 1; }
gh api "repos/$REPO/pulls/$PR/comments?per_page=100" --paginate 2>/dev/null | python3 "$HERE/lib/coderabbit_report.py" "$MODE"
exit "${PIPESTATUS[1]}"
