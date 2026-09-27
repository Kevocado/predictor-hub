#!/usr/bin/env bash
# Deploy the Predictor explainer to the VPS over SSH. Run from a machine that can `ssh ubuntu@40.160.91.131`.
#
#   ./scripts/deploy-explainer.sh setup    # build + run template-only (EXPLAINER_ENABLED=false), smoke-test every sport
#   ./scripts/deploy-explainer.sh golive   # prompt locally for the OpenRouter key, enable the model + pre-generation
#   ./scripts/deploy-explainer.sh status   # budget / health
#
# Optional overrides: VPS=user@host  NET=<docker network>  NFL= CFB= PL= NBA= F1=  (host:port of each sport API)
# The OpenRouter key travels over ssh stdin only: never argv, a repo, a log, or shell history.
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
sleep 6
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
  printf '%s\n%s\n%s\n' "$KEY" "${M1:-}" "${M2:-}" | $SSH 'bash -s' 3<&0 <<'EOF'
set -euo pipefail
S=""; [ "$(id -u)" -ne 0 ] && S="sudo"
docker ps >/dev/null 2>&1 || docker() { command sudo docker "$@"; }
IFS= read -r KEY <&3; IFS= read -r M1 <&3; IFS= read -r M2 <&3
F=/etc/predictor/explainer.env
$S test -f "$F" || { echo "run setup first"; exit 1; }
NET=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' predictor-explainer | awk '{print $1}')
$S sed -i '/^OPENROUTER_API_KEY=/d;s/^EXPLAINER_ENABLED=.*/EXPLAINER_ENABLED=true/' "$F"
[ -n "$M1" ] && $S sed -i '/^EXPLAINER_MODEL=/d' "$F"
[ -n "$M2" ] && $S sed -i '/^EXPLAINER_FALLBACK_MODEL=/d' "$F"
{ echo "OPENROUTER_API_KEY=$KEY"; [ -n "$M1" ] && echo "EXPLAINER_MODEL=$M1"; [ -n "$M2" ] && echo "EXPLAINER_FALLBACK_MODEL=$M2"; true; } | $S tee -a "$F" >/dev/null
$S chmod 600 "$F"
docker rm -f predictor-explainer >/dev/null
docker run -d --name predictor-explainer --restart unless-stopped --network "${NET:?network not found}" \
  -v explainer-data:/data --env-file "$F" predictor-explainer >/dev/null
sleep 6
docker run --rm --network "$NET" curlimages/curl -s http://predictor-explainer:8090/status; echo
echo "Live: the model writes summaries; pre-generation runs every 3 h. Watch used_today with: status"
EOF
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
