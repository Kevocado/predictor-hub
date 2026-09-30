#!/usr/bin/env bash
# Run on your Mac (logged into az), BEFORE the Azure credits run out.
# Downloads the three Azure Files shares the container apps mount, then copies
# them to the VPS volumes compose.yml bind-mounts:
#
#   nba-tracking -> volumes/nba-tracking   (NBA track record: tracking.db)
#   nfl-cache    -> volumes/nfl-cache      (NFL cache + tracking backup)
#   cfb-cache    -> volumes/cfb-cache      (CFB cache + tracking backup)
#
#   bin/pull-azure-volumes.sh <vps-ip>
#
# Re-run it right before cutover so the VPS gets the newest track record.
# PL and F1 have no volumes: their data ships inside the image.
set -euo pipefail
VPS=${1:?usage: pull-azure-volumes.sh <vps-ip>}
ACCOUNT=predictorhubcache
RG=predictor-hub-rg
HERE=$(cd "$(dirname "$0")/.." && pwd)
OUT="$HERE/azure-volumes"

KEY=$(az storage account keys list -g "$RG" -n "$ACCOUNT" --query '[0].value' -o tsv)
for share in nba-tracking nfl-cache cfb-cache; do
  echo "==> $share"
  mkdir -p "$OUT/$share"
  az storage file download-batch --account-name "$ACCOUNT" --account-key "$KEY" \
    --source "$share" --destination "$OUT/$share" --no-progress -o none
done

echo "==> copying to $VPS (the three apps are stopped during the copy)"
ssh "deploy@$VPS" 'cd /opt/stack && docker compose stop nba nfl cfb'
# Always bring the apps back, even if a copy below fails.
trap 'ssh "deploy@$VPS" "cd /opt/stack && docker compose up -d nba nfl cfb"' EXIT
# The containers run as root, so files they wrote are root-owned; hand them
# back to deploy (which has docker, not sudo) so rsync can replace them.
ssh "deploy@$VPS" 'docker run --rm -v /opt/stack/volumes:/v alpine chown -R "$(id -u):$(id -g)" /v'
for share in nba-tracking nfl-cache cfb-cache; do
  rsync -az --delete "$OUT/$share/" "deploy@$VPS:/opt/stack/volumes/$share/"
done
echo "done"
