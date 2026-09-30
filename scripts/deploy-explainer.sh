#!/usr/bin/env bash
# Deploy the Predictor explainer to the VPS over SSH. Run from a machine that can `ssh ubuntu@40.160.91.131`.
#
#   ./scripts/deploy-explainer.sh setup    # build + run template-only (EXPLAINER_ENABLED=false), smoke-test every sport
#   ./scripts/deploy-explainer.sh golive   # prompt locally for the OpenRouter key, enable the model + pre-generation
#   ./scripts/deploy-explainer.sh status   # budget / health
#
# Optional overrides: VPS=user@host  NET=<docker network>  NFL= CFB= PL= NBA= F1=  (host:port of each sport API)
# The OpenRouter key travels over ssh stdin only: never argv, a repo, a log, or shell history.
# setup and golive wait up to 30s for the explainer to answer /status and exit non-zero with
# its container log if it never does. A deploy that prints "healthy:" is a deploy that booted.
set -euo pipefail
VPS=${VPS:-ubuntu@40.160.91.131}
MODE=${1:-setup}
SSH="ssh -o ServerAliveInterval=30 $VPS"

remote_common='
set -euo pipefail
S=""; [ "$(id -u)" -ne 0 ] && S="sudo"
docker ps >/dev/null 2>&1 || docker() { command sudo docker "$@"; }
cname() { docker ps --format "{{.Names}}" | grep -iE "$1" | head -1; }
port_of() { docker inspect -f "{{range \$p, \$c := .Config.ExposedPorts}}{{\$p}} {{end}}" "$1" 2>/dev/null | grep -oE "^[0-9]+" | head -1; }
guess() { local n; n=$(cname "$1"); [ -n "$n" ] && echo "$n:$(port_of "$n")" || echo "$2"; }
NFL=${NFL:-$(guess "nfl" nfl-predictor:8001)}
CFB=${CFB:-$(guess "cfb" cfb-predictor:8003)}
PL=${PL:-$(guess "(^|[-_])pl([-_]|$)|premier" pl-predictor:8000)}
NBA=${NBA:-$(guess "nba" nba-predictor:8000)}
F1=${F1:-$(guess "f1" f1-predictor:8000)}
NET=${NET:-$(docker inspect -f "{{range \$k, \$v := .NetworkSettings.Networks}}{{\$k}} {{end}}" "${NFL%%:*}" 2>/dev/null | awk "{print \$1}")}
[ -n "$NET" ] || { echo "Could not detect the docker network; rerun with NET=<name> (see: docker network ls)"; exit 1; }
echo "network=$NET  NFL=$NFL CFB=$CFB PL=$PL NBA=$NBA F1=$F1"
incurl() { docker run --rm --network "$NET" curlimages/curl -s --max-time 30 "$@"; }
# incurl with a short per-attempt timeout, for the poll below. -f is the point:
# a 5xx must not read as healthy. The golive block carries its own copy of
# probe/explainer_health, because that block is a separate script; change both.
#
# Two traps in this block, both paid for. A heredoc interpolates a variable
# verbatim, so what is written here is what the remote shell reads: escaping a $
# to make it expand over there leaves the backslash in place, and \$( is a syntax
# error on arrival. (The \$p in port_of is the exception, and only because the
# double quotes on the far side consume it.) And the block is inside single
# quotes, so one apostrophe in a comment ends the string and the rest runs as code.
probe() { docker run --rm --network "$NET" curlimages/curl -sfS --max-time 5 "$@"; }
# Is the explainer actually serving? The app defines exactly two routes
# (explainer/app.py): /explain/{sport}/{id} and /status. There is no /health and
# no /ready -- both return 404 -- so /status is the health endpoint, and it can
# only answer after the lifespan has run: a 200 there means the app booted, not
# merely that the container exists.
#
# This replaces "sleep 6; print whatever came back", which printed an empty
# "status: " for a container still booting or crash-looping and then reported
# success. 30 seconds of patience, then it fails loudly with the log.
explainer_health() {
  local deadline=$((SECONDS + 30)) body
  while [ "$SECONDS" -lt "$deadline" ]; do
    if body=$(probe http://predictor-explainer:8090/status 2>/dev/null) && [ -n "$body" ]; then
      echo "healthy: $body"
      return 0
    fi
    sleep 1
  done
  echo "DEPLOY FAILED: http://predictor-explainer:8090/status did not answer 200 within 30s of the container starting." >&2
  echo "--- last 30 lines of predictor-explainer ---" >&2
  docker logs --tail 30 predictor-explainer >&2 || true
  return 1
}
'

case "$MODE" in
setup)
  $SSH "NET='${NET:-}' NFL='${NFL:-}' CFB='${CFB:-}' PL='${PL:-}' NBA='${NBA:-}' F1='${F1:-}' bash -s" <<EOF
$remote_common
[ -d ~/predictor-hub ] || git clone https://github.com/Kevocado/predictor-hub ~/predictor-hub
git -C ~/predictor-hub pull --ff-only
docker build -q -t predictor-explainer ~/predictor-hub/services/explainer

\$S mkdir -p /etc/predictor
# Keep an existing key if golive already ran; otherwise start template-only.
KEYLINE=\$(\$S grep -s "^OPENROUTER_API_KEY=" /etc/predictor/explainer.env || true)
MODELS=\$(\$S grep -sE "^EXPLAINER_(FALLBACK_)?MODEL=" /etc/predictor/explainer.env || true)
ENABLED=\$( [ -n "\$KEYLINE" ] && echo true || echo false )
\$S tee /etc/predictor/explainer.env >/dev/null <<ENV
EXPLAINER_ENABLED=\$ENABLED
EXPLAINER_DAILY_CAP=900
SPORT_API_NFL=http://\$NFL
SPORT_API_CFB=http://\$CFB
SPORT_API_PL=http://\$PL
SPORT_API_NBA=http://\$NBA
SPORT_API_F1=http://\$F1
\$MODELS
\$KEYLINE
ENV
\$S chmod 600 /etc/predictor/explainer.env

docker rm -f predictor-explainer >/dev/null 2>&1 || true
docker run -d --name predictor-explainer --restart unless-stopped --network "\$NET" \\
  -v explainer-data:/data --env-file /etc/predictor/explainer.env predictor-explainer >/dev/null
explainer_health || exit 1
echo "status: \$(incurl http://predictor-explainer:8090/status)"
for pair in "nfl \$NFL" "cfb \$CFB" "pl \$PL" "nba \$NBA" "f1 \$F1"; do
  set -- \$pair
  id=\$(incurl "http://\$2/facts/upcoming?hours=336" | python3 -c 'import json,sys
try: ids=json.load(sys.stdin).get("ids",[])
except Exception: ids=[]
print(ids[0] if ids else "")')
  if [ -z "\$id" ]; then echo "\$1: no upcoming ids, or /facts unreachable at \$2"; continue; fi
  echo "\$1 \$id: \$(incurl "http://predictor-explainer:8090/explain/\$1/\$id" | head -c 160)"
done
echo "free models on OpenRouter matching the defaults:"
curl -s https://openrouter.ai/api/v1/models | python3 -c 'import json,sys
[print("  "+m["id"]) for m in json.load(sys.stdin)["data"] if m["id"].endswith(":free") and ("deepseek-chat" in m["id"] or "llama-3.3-70b" in m["id"])]' || echo "  (could not reach openrouter.ai)"
echo
echo "Next: point the sites at it and redeploy them —"
echo "  Sports Caddy container:  EXPLAINER_UPSTREAM=predictor-explainer:8090"
echo "  PL / NBA / F1 APIs:      EXPLAINER_URL=http://predictor-explainer:8090"
EOF
  ;;
golive)
  read -rsp "OpenRouter API key (not echoed): " KEY; echo
  [ -n "$KEY" ] || { echo "no key given"; exit 1; }
  read -rp "Primary model [keep current / default]: " M1
  read -rp "Fallback model [keep current / default]: " M2
  # The script travels as the remote command; stdin carries only the key and models.
  # (ssh forwards stdin alone, so the secrets cannot ride on another fd.)
  IFS= read -r -d '' REMOTE <<'EOF' || true
set -euo pipefail
S=""; [ "$(id -u)" -ne 0 ] && S="sudo"
docker ps >/dev/null 2>&1 || docker() { command sudo docker "$@"; }
IFS= read -r KEY; IFS= read -r M1; IFS= read -r M2
F=/etc/predictor/explainer.env
$S test -f "$F" || { echo "run setup first"; exit 1; }
NET=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' predictor-explainer | awk '{print $1}')
$S sed -i '/^OPENROUTER_API_KEY=/d;s/^EXPLAINER_ENABLED=.*/EXPLAINER_ENABLED=true/' "$F"
[ -n "$M1" ] && $S sed -i '/^EXPLAINER_MODEL=/d' "$F"
[ -n "$M2" ] && $S sed -i '/^EXPLAINER_FALLBACK_MODEL=/d' "$F"
{ echo "OPENROUTER_API_KEY=$KEY"; [ -n "$M1" ] && echo "EXPLAINER_MODEL=$M1"; [ -n "$M2" ] && echo "EXPLAINER_FALLBACK_MODEL=$M2"; true; } | $S tee -a "$F" >/dev/null
$S chmod 600 "$F"
docker rm -f predictor-explainer >/dev/null
probe() { docker run --rm --network "$NET" curlimages/curl -sfS --max-time 5 "$@"; }
# Copy of the explainer_health in remote_common; see the note there. /status is
# the only health-shaped route the app defines (explainer/app.py).
explainer_health() {
  local deadline=$((SECONDS + 30)) body
  while [ "$SECONDS" -lt "$deadline" ]; do
    if body=$(probe http://predictor-explainer:8090/status 2>/dev/null) && [ -n "$body" ]; then
      echo "healthy: $body"
      return 0
    fi
    sleep 1
  done
  echo "DEPLOY FAILED: http://predictor-explainer:8090/status did not answer 200 within 30s of the container starting." >&2
  echo "--- last 30 lines of predictor-explainer ---" >&2
  docker logs --tail 30 predictor-explainer >&2 || true
  return 1
}
docker run -d --name predictor-explainer --restart unless-stopped --network "${NET:?network not found}" \
  -v explainer-data:/data --env-file "$F" predictor-explainer >/dev/null
explainer_health || exit 1
docker run --rm --network "$NET" curlimages/curl -s http://predictor-explainer:8090/status; echo
echo "Live: the model writes summaries; pre-generation runs every 3 h. Watch used_today with: status"
EOF
  printf '%s\n%s\n%s\n' "$KEY" "${M1:-}" "${M2:-}" | $SSH "bash -c $(printf %q "$REMOTE")"
  ;;
status)
  $SSH 'bash -s' <<EOF
$remote_common
incurl http://predictor-explainer:8090/status; echo
docker logs --tail 20 predictor-explainer 2>&1 | grep -v " 200 " || true
EOF
  ;;
*) echo "usage: $0 setup|golive|status"; exit 1;;
esac
