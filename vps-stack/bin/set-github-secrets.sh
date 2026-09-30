#!/usr/bin/env bash
# Run on your Mac with the gh CLI logged in. Gives every deploying repo what
# its "vps" workflow job needs:
#   variable VPS_HOST         the server's IP (or hostname)
#   secret   VPS_SSH_KEY      private half of the CI deploy key
#   secret   VPS_KNOWN_HOSTS  the server's pinned SSH host key
#
#   bin/set-github-secrets.sh <vps-ip> ~/.ssh/vps_ci_deploy
#
# Setting VPS_HOST is what switches the vps job on. At cutover, also run
#   bin/set-github-secrets.sh --disable-azure
# to stop the (by then failing) Azure deploy jobs.
set -euo pipefail
REPOS=(
  Kevocado/PL_Predictor
  Kevocado/F1_Predictor
  Kevocado/NBA_Predictor
  Kevocado/NFL_Predictor
  Kevocado/CFB_Predictor
  Kevocado/Sports_Predictor
  Kevocado/predictor-hub
  Kevocado/algo-trade-hub-prod
)

if [[ "${1:-}" == "--disable-azure" ]]; then
  for r in "${REPOS[@]}"; do gh variable set DEPLOY_AZURE --repo "$r" --body false; echo "$r: azure off"; done
  exit 0
fi

HOST=${1:?usage: set-github-secrets.sh <vps-ip> <ci-private-key-file> | --disable-azure}
KEYFILE=${2:?usage: set-github-secrets.sh <vps-ip> <ci-private-key-file>}
KNOWN=$(ssh-keyscan -t ed25519 "$HOST" 2>/dev/null)
[[ -n "$KNOWN" ]] || { echo "could not read the host key of $HOST" >&2; exit 1; }
echo "Host key to pin (compare with the fingerprint bootstrap printed):"
echo "$KNOWN" | ssh-keygen -lf -
read -r -p "Matches? [y/N] " ok; [[ "$ok" == y ]] || exit 1

for r in "${REPOS[@]}"; do
  gh variable set VPS_HOST --repo "$r" --body "$HOST"
  gh secret set VPS_SSH_KEY --repo "$r" <"$KEYFILE"
  gh secret set VPS_KNOWN_HOSTS --repo "$r" --body "$KNOWN"
  echo "$r: done"
done
