#!/usr/bin/env bash
# Build one site image ON THE VPS from its checkout and swap the running container.
# Run as root on the VPS, piped from your machine (the script is not stored there):
#
#   ssh ubuntu@40.160.91.131 "sudo bash -s <Repo> <image> <service> <TAGVAR> <port> <health>" < scripts/deploy-site.sh
#
# Per site (repo image service tagvar port health):
#   NFL_Predictor   nfl-predictor         nfl    NFL_TAG    8001 /
#   CFB_Predictor   cfb-predictor         cfb    CFB_TAG    8003 /
#   NBA_Predictor   nba-predictor-deploy  nba    NBA_TAG    8000 /health
#   PL_Predictor    pl-predictor          pl     PL_TAG     8000 /api/health
#   F1_Predictor    f1-predictor          f1     F1_TAG     8000 /
#   Sports_Predictor sports-predictor     sports SPORTS_TAG 80   /
#
# It pulls main in /home/ubuntu/src/<Repo>, builds ghcr.io/kevocado/<image>:<sha> locally,
# sets <TAGVAR> in /opt/stack/.env, `compose up -d --no-deps`, health-checks through caddy and
# rolls back to the previous tag on failure. Prints "OK <service> -> <sha12>" on success.
# Disk is 38 GB and each image ~2 GB: run /opt/stack/bin/prune-images between deploys
# (a daily cron does it at 04:30). Do NOT use `git add -A` or switch branches in agent clones.
# usage (as root): deploy-one.sh <repo> <image> <service> <TAGVAR> <port> <health>
set -uo pipefail
repo=$1; img=$2; svc=$3; var=$4; port=$5; hp=$6
cd /home/ubuntu/src/$repo || exit 1
sudo -u ubuntu git fetch -q origin main && sudo -u ubuntu git checkout -q --force main && sudo -u ubuntu git reset -q --hard origin/main || { echo "git failed"; exit 1; }
sha=$(git rev-parse HEAD)
docker build -q -t ghcr.io/kevocado/$img:$sha . >/var/tmp/build-$repo-$$.log 2>&1 || { echo "build failed"; tail -5 /var/tmp/build-$repo-$$.log; exit 1; }
cd /opt/stack
prev=$(grep "^$var=" .env | cut -d= -f2-)
sed -i "s|^$var=.*|$var=$sha|" .env
docker compose --project-directory /opt/stack up -d --no-deps $svc >/dev/null 2>&1
for i in $(seq 1 24); do
  if docker compose --project-directory /opt/stack exec -T caddy wget -q -T 5 -O /dev/null "http://$svc:$port$hp" 2>/dev/null; then echo "OK $svc -> ${sha:0:12}"; exit 0; fi
  sleep 5
done
echo "FAILED health, rolling back to $prev"
sed -i "s|^$var=.*|$var=$prev|" .env
docker compose --project-directory /opt/stack up -d --no-deps $svc >/dev/null 2>&1
exit 1
