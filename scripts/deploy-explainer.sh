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
# That wait has a ceiling over the WHOLE probe -- the `docker run` that carries the curl
# included, which --max-time cannot see -- and a deploy that cannot pass its health check
# rolls back to the image that was running before instead of leaving the broken one in place.
# Both of those live in scripts/lib/deploy_safety.sh, which is where the numbers are.
set -euo pipefail
VPS=${VPS:-ubuntu@40.160.91.131}
MODE=${1:-setup}
SSH="ssh -o ServerAliveInterval=30 $VPS"
SELF=${BASH_SOURCE[0]:-$0}
HERE=$(CDPATH='' cd -- "$(dirname -- "$SELF")" && pwd)
LIB=$HERE/lib/deploy_safety.sh
EMBED_BEGIN='# >>> scripts/lib/deploy_safety.sh'
EMBED_END='# <<< scripts/lib/deploy_safety.sh'

# scripts/lib/deploy_safety.sh is the source of truth for the probe, the deadlines and
# the rollback. What the VPS runs is the copy embedded in each remote block below,
# because the golive block cannot source a file on the far side: it is sent from a
# laptop that may be newer than the checkout on the host, and pairing a new script with
# an old library is how a fix arrives as a stale copy. So the copy travels with the
# script, and the cost of that is drift -- which is what this checks, locally, before
# anything is sent. It reads two files and runs sh -n; it never opens a socket.
_check_dir=""
check_remote_blocks() {
  local copy count=0
  if [ ! -r "$LIB" ]; then
    echo "$LIB is missing: the probe, the deadlines and the rollback live there" >&2
    exit 1
  fi
  if ! sh -n "$LIB"; then
    echo "$LIB does not parse under /bin/sh; not sending anything to the VPS" >&2
    exit 1
  fi
  _check_dir=$(mktemp -d)
  trap 'rm -rf "$_check_dir"' EXIT
  # The blocks are shell strings inside this file, so the only safe way to get text out
  # of them is to cut at the marker lines, which mean nothing to any shell.
  awk -v dir="$_check_dir" -v begin="$EMBED_BEGIN" -v end="$EMBED_END" '
    $0 == begin { n++; out = dir "/copy." n; copying = 1; next }
    $0 == end { copying = 0; next }
    copying { print > out }
  ' "$SELF"
  for copy in "$_check_dir"/copy.*; do
    [ -f "$copy" ] || continue
    count=$((count + 1))
    if ! cmp -s "$LIB" "$copy"; then
      echo "$SELF carries a copy of deploy_safety.sh that has drifted from $LIB." >&2
      echo "Run: $SELF --embed" >&2
      exit 1
    fi
  done
  if [ "$count" -ne 2 ]; then
    echo "expected the library embedded in both remote blocks; found $count copy in $SELF" >&2
    exit 1
  fi
  rm -rf "$_check_dir"
  _check_dir=""
  trap - EXIT
}
# The fix for the drift that check_remote_blocks refuses to deploy over: rewrite both
# copies from the library on disk. Local, offline, and idempotent. Without it the repair
# is a manual paste into two places, and a manual paste into two places is how a library
# and its copy come to disagree about a rollback.
embed_library() {
  local tmp
  tmp=$(mktemp)
  awk -v lib="$LIB" -v begin="$EMBED_BEGIN" -v end="$EMBED_END" '
    $0 == begin { print; while ((getline line < lib) > 0) print line; close(lib); skipping = 1; next }
    skipping { if ($0 == end) { skipping = 0; print } next }
    { print }
  ' "$SELF" >"$tmp"
  # Written back in place rather than renamed, to keep the mode and the ownership of the
  # file being edited.
  cat "$tmp" >"$SELF"
  rm -f "$tmp"
}
if [ "${1:-}" = "--embed" ]; then
  embed_library
  check_remote_blocks
  echo "embedded $(basename "$LIB") into both remote blocks of $SELF"
  exit 0
fi
check_remote_blocks

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
# incurl with a long per-attempt timeout, for the smoke test after a deploy. -f is not
# set here: this is there to print whatever the sport API says, and its /facts call is
# slower than a health probe. It is still bounded, because it is still a docker run that
# can hang on a pull -- EXPLAINER_REQUEST_DEADLINE, from the library below.
incurl() { explainer_within "$EXPLAINER_REQUEST_DEADLINE" docker run --rm --network "$NET" "$EXPLAINER_PROBE_IMAGE" -s --max-time "$EXPLAINER_REQUEST_MAX_TIME" "$@"; }
# The probe, the deadlines and the rollback. Byte-identical in both remote blocks, and
# this script refuses to send either one if it has drifted from the library on disk.
#
# Three traps in this block, all paid for. A heredoc interpolates a variable
# verbatim, so what is written here is what the remote shell reads: escaping a $
# to make it expand over there leaves the backslash in place, and \$( is a syntax
# error on arrival. (The \$p in port_of is the exception, and only because the
# double quotes on the far side consume it.) The block is inside single quotes, so
# one apostrophe in a comment ends the string and the rest of the file runs as
# remote code -- which is why the library has a test that it has none. And the
# golive block is a separate script, so a fix in one copy does not reach the
# other; hence the drift check.
# >>> scripts/lib/deploy_safety.sh
# shellcheck shell=sh
# Deploy safety for the explainer: bound every step that can hang, and put the
# previous working image back when the new one fails its health check.
#
# Sourced by scripts/deploy-explainer.sh, embedded verbatim in the block each
# deploy mode sends, and run directly by services/explainer/tests/
# test_deploy_script.py against a fake docker on PATH.
#
# POSIX sh, deliberately. The far side runs bash, but this file is also read by
# /bin/sh on a macOS laptop and by dash on a Linux CI runner. An earlier version
# of this logic used ${*##*-- } to pick an argument out of "$@", which neither
# can read, and a deploy is the worst possible place to find that out. So: no
# arrays, no ${var//from/to}, no local, no [[ ]], no $SECONDS arithmetic beyond
# adding to it. POSIX sh has no local, so every function below uses its own
# prefixed variable names instead.
#
# Two rules that the rest of the file obeys, both because of how it travels:
#
#   * No apostrophe anywhere. deploy-explainer.sh embeds this text inside a
#     single-quoted shell string, and one apostrophe would end that string and
#     turn the rest of this file into remote code.
#   * A dollar is written for the shell that will READ it, not the one writing
#     it. This is sent over ssh and expanded on the VPS.

# --------------------------------------------------------------------------
# The numbers. Every one of these is a ceiling on something that can hang on a
# bad network, and every one is ${VAR:-default} so a test -- or a one-off
# emergency deploy -- can move it from the environment without editing a file
# that is already on the host.
EXPLAINER_NAME=${EXPLAINER_NAME:-predictor-explainer}
EXPLAINER_IMAGE=${EXPLAINER_IMAGE:-predictor-explainer}
EXPLAINER_PREVIOUS_IMAGE=${EXPLAINER_PREVIOUS_IMAGE:-predictor-explainer:prev}
EXPLAINER_PROBE_IMAGE=${EXPLAINER_PROBE_IMAGE:-curlimages/curl}
# The probe container is named so that a probe killed at its deadline, whose
# `docker run` client did not get to clean it up, can still be removed.
EXPLAINER_PROBE_CONTAINER=${EXPLAINER_PROBE_CONTAINER:-explainer-probe}
# /status is the only health-shaped route the app defines (explainer/app.py
# defines /explain/{sport}/{id} and /status, and /health and /ready both 404).
EXPLAINER_HEALTH_URL=${EXPLAINER_HEALTH_URL:-http://predictor-explainer:8090/status}
EXPLAINER_ENV_FILE=${EXPLAINER_ENV_FILE:-/etc/predictor/explainer.env}
EXPLAINER_PREVIOUS_ENV_FILE=${EXPLAINER_PREVIOUS_ENV_FILE:-/etc/predictor/explainer.env.prev}
EXPLAINER_BUILD_CONTEXT=${EXPLAINER_BUILD_CONTEXT:-$HOME/predictor-hub/services/explainer}
EXPLAINER_VOLUME=${EXPLAINER_VOLUME:-explainer-data:/data}
NET=${NET:-}

# curl gives up on the HTTP call after this many seconds. It says nothing about
# the command that carries it: by the time curl counts, the container is already
# running. See explainer_watchdog for what this number does not cover.
EXPLAINER_CURL_MAX_TIME=${EXPLAINER_CURL_MAX_TIME:-5}
# The ceiling on ONE probe attempt, the `docker run` included: 5 seconds for the
# request plus the container start, rounded up. A hung attempt cannot spend more
# than this, which is what leaves the loop below budget to try again.
EXPLAINER_ATTEMPT_DEADLINE=${EXPLAINER_ATTEMPT_DEADLINE:-10}
# How long the health check keeps trying while the container boots.
EXPLAINER_HEALTH_BUDGET=${EXPLAINER_HEALTH_BUDGET:-30}
# The ceiling on the whole health check, whatever any child does. The budget and
# the attempt deadline already bound it in practice; this is the number that
# bounds it when the bounding itself is what is broken.
EXPLAINER_HEALTH_CEILING=${EXPLAINER_HEALTH_CEILING:-45}
# One cold pull of the probe image, once, before the attempts start, and a build.
# Both are given longer than a probe attempt on purpose: neither has to fit in
# ten seconds, and both hang the same way when a registry stops answering.
EXPLAINER_PULL_DEADLINE=${EXPLAINER_PULL_DEADLINE:-300}
EXPLAINER_BUILD_DEADLINE=${EXPLAINER_BUILD_DEADLINE:-900}
# The post-deploy smoke test asks the sport APIs for a fixture, which is slower than
# a health probe, so it gets its own pair. It is still a docker run that can hang on
# a pull, which is why it is bounded at all.
EXPLAINER_REQUEST_MAX_TIME=${EXPLAINER_REQUEST_MAX_TIME:-30}
EXPLAINER_REQUEST_DEADLINE=${EXPLAINER_REQUEST_DEADLINE:-45}
# Seconds between a TERM and a KILL, for a command that ignores the first one.
EXPLAINER_GRACE=${EXPLAINER_GRACE:-2}
# auto prefers GNU timeout(1) when it is on PATH and falls back to the portable
# watchdog. shell forces the watchdog, timeout forces timeout(1): both exist so
# that a test can cover the branch this host does not have.
EXPLAINER_DEADLINE_IMPL=${EXPLAINER_DEADLINE_IMPL:-auto}

# --------------------------------------------------------------------------
# The outer deadline.
#
# Why this file exists at all: curl has --max-time, but the command that carries
# curl does not. probe runs `docker run --rm curlimages/curl ...`, and everything
# before curl starts is inside that command -- the daemon pulling
# curlimages/curl if it is not cached, creating the container, attaching the
# network, DNS, the runtime starting. --max-time cannot see any of it, because it
# starts counting once the container is running.
#
# The health loop around it has a 30 second budget, and that budget does not help:
# a loop can only spend time it is running. It re-reads the clock between
# attempts, so a single `docker run` that never returns means the budget is never
# checked again. That is the hang this closes -- the deploy sitting on a command
# with no output and no timeout, on a machine an operator is watching to see
# whether the deploy is stuck.
#
# Two implementations, because there is no timeout(1) on macOS:
#
#   timeout  GNU coreutils. Preferred when present: -k bounds how long it waits
#           for a child that ignores TERM, and it signals the process group, so
#           the container goes with the client. On the VPS; not on a laptop.
#
#   shell   A watchdog: run the command in the background, poll for its exit
#           until the limit, kill it if it is still there. POSIX sh only, which
#           is what the two implementations have in common -- and the reason the
#           portable one is not the GNU one is that macOS has no timeout(1).
#
# Which one runs is decided by what the command IS, not by a preference, because
# the two are not interchangeable. timeout(1) execs a program: it resolves its
# target through PATH, so it can run a file and nothing else. A shell function, an
# alias and a keyword have no file, and when a name is both -- docker, on the VPS,
# where the login user is not in the docker group and the remote block defines
# docker() { command sudo docker "$@"; } -- the file is exactly the thing that must
# not be run. Handing a function to timeout(1) does not fail loudly: it runs the
# bare binary, which answers permission denied, and the wrapper reports that as a
# timeout. A deadline that silently stops applying looks like a command that
# finished quickly, which is how a green deploy skipped a deadline and nobody
# noticed until the build came back in four minutes instead of four seconds.
#
# So: the watchdog runs whatever the shell itself can call, timeout(1) runs only
# what exec can find, and a name that is neither is refused out loud. See
# explainer_resolve_kind, which is the only place that question is asked.

# explainer_watchdog LIMIT COMMAND... -- run COMMAND, killed at LIMIT.
#
# A deadline kill exits 124, which is what GNU timeout returns for the same
# event, so nothing downstream has to know which implementation ran it.
#
# The poll is the point of the ordering below. The watchdog watches for the
# child to disappear and kills only while it is still there, rather than sleeping
# once and killing a pid it no longer owns -- a pid the shell has already reaped
# can belong to something else by then, and "everything works except the tests
# that kill a random process" is not a deploy script. The residual race is the
# one poll between a child dying and the shell reaping it, which is the same
# race GNU timeout has and is not closable from a POSIX shell.
#
# The watchdog itself is redirected to /dev/null and is never killed by hand,
# and both of those are load-bearing. It inherits stdout from the shell that
# spawned it, and every probe result is read through a command substitution --
# `body=$(probe ...)`. A command substitution waits for the last writer on the
# pipe to close it, so a watchdog holding that pipe holds the whole health check
# for its full limit even when the probe answered in a millisecond. And a
# hand-written kill would not have helped: a non-interactive shell does not act
# on a signal while it is waiting for a foreground child, so the TERM would sit
# unread until the sleep finished. The watchdog exits by itself within one poll
# of the command it is watching, which is the whole of its job.
explainer_watchdog() {
  explainer_wd_limit=$1
  shift
  "$@" &
  explainer_wd_child=$!
  (
    explainer_wd_left=$explainer_wd_limit
    while kill -0 "$explainer_wd_child" 2>/dev/null; do
      if [ "$explainer_wd_left" -le 0 ]; then
        kill -TERM "$explainer_wd_child" 2>/dev/null || exit 0
        explainer_wd_grace=0
        while kill -0 "$explainer_wd_child" 2>/dev/null; do
          if [ "$explainer_wd_grace" -ge "$EXPLAINER_GRACE" ]; then
            kill -KILL "$explainer_wd_child" 2>/dev/null || true
            exit 0
          fi
          sleep 1
          explainer_wd_grace=$((explainer_wd_grace + 1))
        done
        exit 0
      fi
      sleep 1
      explainer_wd_left=$((explainer_wd_left - 1))
    done
  ) >/dev/null 2>&1 &
  if wait "$explainer_wd_child"; then explainer_wd_rc=0; else explainer_wd_rc=$?; fi
  # A shell reports a killed child as 128+signal, which is not an exit code any
  # caller can compare against.
  if [ "$explainer_wd_rc" -ge 128 ]; then explainer_wd_rc=124; fi
  return "$explainer_wd_rc"
}

# explainer_path_of NAME -- the file that exec would run for NAME, on stdout, or
# nothing at all.
#
# This is `type -P` written out, because `type -P` is a bashism and this file is
# read by dash and ksh93 as well as bash. It asks about FILES ONLY, on purpose: it
# ignores functions, builtins, aliases and keywords, because for a name that is
# both a function and a file -- docker, on the VPS -- the file is precisely the one
# that must not be run.
explainer_path_of() {
  explainer_po_name=${1:-}
  case "$explainer_po_name" in
    */*)
      # A name with a slash is used as written, which is what exec does with it too.
      if [ -f "$explainer_po_name" ] && [ -x "$explainer_po_name" ]; then
        printf "%s\n" "$explainer_po_name"
        return 0
      fi
      return 1
      ;;
  esac
  explainer_po_left=${PATH:-}
  while [ -n "$explainer_po_left" ]; do
    explainer_po_dir=${explainer_po_left%%:*}
    if [ "$explainer_po_dir" = "$explainer_po_left" ]; then
      explainer_po_left=
    else
      explainer_po_left=${explainer_po_left#*:}
    fi
    # An empty PATH element means the current directory, which is what exec says too.
    [ -n "$explainer_po_dir" ] || explainer_po_dir=.
    if [ -f "$explainer_po_dir/$explainer_po_name" ] && [ -x "$explainer_po_dir/$explainer_po_name" ]; then
      printf "%s\n" "$explainer_po_dir/$explainer_po_name"
      return 0
    fi
  done
  return 1
}

# explainer_resolve_kind NAME -- what a bare NAME would run here, in the order the
# shell itself resolves it, on stdout: function, alias, keyword, builtin or file.
# Returns non-zero, and prints nothing, when this shell has no idea what NAME is.
#
# `command -V` is the portable question -- POSIX has it, and bash, dash and ksh93 all
# answer it -- but the answer is prose, and the prose differs per shell: "NAME is a
# function" (bash, ksh93), "NAME is a shell function" (dash), "NAME is a shell
# builtin", "NAME is /bin/sleep". So the WORDING is matched rather than the status,
# because the status is not usable either: dash reports an unknown name on stdout and
# still exits 0. Only the first line is read, because bash prints the entire body of
# a function after it and a function body can contain any word at all.
#
# `type -t` is the tidier question and is not portable: dash has no -t and dies on the
# attempt, and ksh93 maps type to whence and rejects -t. That is not cosmetic. The
# first fix for the VPS bug classified with `type -t`, so on dash and ksh93 the
# classification came back empty, the function was not recognised, and the deadline
# wrapper handed the name to timeout(1) -- which execs the bare docker, which is not
# in the docker group. The fix that was meant to stop that failure did not fire on
# two of the three shells this file is written for.
#
# A name that classifies as neither is not guessed at. The caller is expected to
# refuse it out loud, because the alternative is timeout(1) reporting "not found" for
# a program on a host where the real problem was a function all along.
explainer_resolve_kind() {
  explainer_rk_name=${1:-}
  if [ -z "$explainer_rk_name" ]; then
    return 2
  fi
  # `|| :` because command -V is allowed to fail on a name it does not know, and
  # this file is read under set -e. The description is the answer; the status is not.
  explainer_rk_desc=$(command -V "$explainer_rk_name" 2>&1) || :
  # A newline held in a variable, because cutting the description at one is the only
  # way to read the first line of it in a POSIX shell. Double quotes, not single:
  # this file has no apostrophes in it at all (see the top of the file).
  explainer_rk_nl="
"
  case "$explainer_rk_desc" in
    *"$explainer_rk_nl"*) explainer_rk_line=${explainer_rk_desc%%"$explainer_rk_nl"*} ;;
    *) explainer_rk_line=$explainer_rk_desc ;;
  esac
  case "$explainer_rk_line" in
    *function*) explainer_rk_kind="function" ;;
    *alias*) explainer_rk_kind="alias" ;;
    *keyword*) explainer_rk_kind="keyword" ;;
    *builtin*) explainer_rk_kind="builtin" ;;
    *)
      # Either a path, or a name this shell does not know at all. Only the PATH walk
      # tells those apart, and since dash exits 0 for the second case, the walk --
      # not the status of command -V -- is what decides.
      if explainer_path_of "$explainer_rk_name" >/dev/null; then
        explainer_rk_kind="file"
      else
        return 1
      fi
      ;;
  esac
  printf "%s\n" "$explainer_rk_kind"
}

# explainer_within LIMIT COMMAND... -- the outer deadline around one command.
explainer_within() {
  explainer_within_limit=$1
  shift
  if [ "$#" -eq 0 ]; then
    echo "explainer_within: no command was given to run within ${explainer_within_limit}s" >&2
    return 2
  fi
  # What the first argument actually is, which is the only thing that says whether an
  # exec-based wrapper can run it at all. Asked once, here, so that no second deadline
  # entry point can answer it differently.
  if ! explainer_within_kind=$(explainer_resolve_kind "$1"); then
    echo "explainer_within: $1 is not a command this shell can run: it is not a function, a builtin, or an executable on PATH" >&2
    return 127
  fi
  case "$explainer_within_kind" in
    function | alias | keyword)
      # timeout(1) execs a program, and none of these is one. The watchdog runs the
      # command the way the shell around it would, which is the whole reason the
      # remote block defines docker as a function at all.
      explainer_watchdog "$explainer_within_limit" "$@" || return $?
      return 0
      ;;
    builtin)
      # A builtin is exec-able only when PATH has a file of the same name, because
      # execvp has no other way to find one. With one -- true, cat -- timeout(1) runs
      # the same thing the shell would. Without one, only this shell knows what the
      # builtin does, so only the watchdog can run it.
      if ! explainer_path_of "$1" >/dev/null; then
        explainer_watchdog "$explainer_within_limit" "$@" || return $?
        return 0
      fi
      ;;
  esac
  case "${EXPLAINER_DEADLINE_IMPL:-auto}" in
    shell) explainer_watchdog "$explainer_within_limit" "$@" ;;
    timeout) timeout -k "$EXPLAINER_GRACE" "$explainer_within_limit" "$@" ;;
    auto)
      if command -v timeout >/dev/null 2>&1; then
        timeout -k "$EXPLAINER_GRACE" "$explainer_within_limit" "$@"
      else
        explainer_watchdog "$explainer_within_limit" "$@"
      fi
      ;;
    *)
      echo "EXPLAINER_DEADLINE_IMPL=${EXPLAINER_DEADLINE_IMPL} is not auto, shell or timeout" >&2
      return 2
      ;;
  esac
}

# --------------------------------------------------------------------------
# The probe.
#
# A probe container that is killed at its deadline outlives the `docker run`
# client that started it, and --rm only fires when that client exits normally.
# So the probe container is named and removed on the way in as well as on the way
# out: on the way out so a hang does not leak a container, and on the way in so
# a container leaked by an earlier hang cannot make the next attempt fail with
# "name already in use" -- which would look exactly like an unhealthy service.
explainer_discard_probe() {
  docker rm -f "$EXPLAINER_PROBE_CONTAINER" >/dev/null 2>&1 || true
}

probe() {
  explainer_discard_probe
  if explainer_within "$EXPLAINER_ATTEMPT_DEADLINE" \
      docker run --rm --name "$EXPLAINER_PROBE_CONTAINER" --network "$NET" \
      "$EXPLAINER_PROBE_IMAGE" -sfS --max-time "$EXPLAINER_CURL_MAX_TIME" "$@"
  then
    explainer_probe_rc=0
  else
    explainer_probe_rc=$?
  fi
  explainer_discard_probe
  return "$explainer_probe_rc"
}

# The probe image, pulled once with its own ceiling, before the first attempt.
# Without this the first attempt pays for the pull inside a ten second attempt
# ceiling, so the first deploy on a host that has never run curlimages/curl fails
# for a reason that has nothing to do with the explainer. A pull that cannot
# reach the registry is not fatal: the cached copy may be perfectly good, and the
# probe will say so if it is not.
explainer_prefetch_probe_image() {
  if ! explainer_within "$EXPLAINER_PULL_DEADLINE" docker pull "$EXPLAINER_PROBE_IMAGE" >/dev/null 2>&1; then
    echo "could not pull $EXPLAINER_PROBE_IMAGE; the probe will use the cached copy if there is one" >&2
  fi
}

# --------------------------------------------------------------------------
# The health check.
#
# date +%s rather than $SECONDS, on purpose: $SECONDS is a bashism, dash does
# not have it, and an unset $SECONDS inside an arithmetic expansion is a syntax
# error rather than a wrong number. The budget is wall clock, and an attempt
# that overruns it is not counted against the next one -- which is exactly what
# the ceiling below is for.
explainer_health_loop() {
  explainer_health_until=$(($(date +%s) + EXPLAINER_HEALTH_BUDGET))
  while [ "$(date +%s)" -lt "$explainer_health_until" ]; do
    if explainer_body=$(probe "$EXPLAINER_HEALTH_URL" 2>/dev/null) && [ -n "$explainer_body" ]; then
      echo "healthy: $explainer_body"
      return 0
    fi
    sleep 1
  done
  return 1
}

# This replaces a fixed six-second sleep followed by printing whatever came back,
# which printed an empty "status: " for a container still booting or crash-looping
# and then reported success. It also runs under a hard ceiling, which the loop
# inside it does not need in order to work but which is what makes it a bound
# rather than a plan: a loop bug, a sleep that blocks, a child that ignores both
# deadlines below -- none of them can push this past EXPLAINER_HEALTH_CEILING.
explainer_health() {
  # The probe image, pulled once and out of the way, before any attempt is capped at
  # ten seconds. Doing this here rather than in each deploy is what guarantees it
  # happens on every path that probes, including a rollback.
  explainer_prefetch_probe_image
  # explainer_health_loop is a shell function, so explainer_within classifies it and
  # runs it with the watchdog rather than handing it to timeout(1), which cannot call
  # a function. One deadline entry point means that decision is made in one place.
  if explainer_within "$EXPLAINER_HEALTH_CEILING" explainer_health_loop; then
    return 0
  else
    explainer_health_rc=$?
  fi
  if [ "$explainer_health_rc" -eq 124 ]; then
    echo "the health probe was still running ${EXPLAINER_HEALTH_CEILING}s after the container started" >&2
  fi
  echo "DEPLOY FAILED: $EXPLAINER_HEALTH_URL did not answer 200 within ${EXPLAINER_HEALTH_BUDGET}s of the container starting." >&2
  echo "--- last 30 lines of $EXPLAINER_NAME ---" >&2
  docker logs --tail 30 "$EXPLAINER_NAME" >&2 || true
  return "$explainer_health_rc"
}

# --------------------------------------------------------------------------
# Starting it, and putting it back.
#
# explainer_run_detached is the only place that knows how the explainer is
# started. The deploy and the rollback both call it and differ by exactly one
# argument: the image. Same name, same restart policy, same network, same volume,
# same env file. That is not tidiness, it is the requirement -- a rollback that
# came back on a different network, or without the env file, would be a different
# service pretending to be the old one.
explainer_run_detached() {
  docker run -d --name "$EXPLAINER_NAME" --restart unless-stopped --network "$NET" \
    -v "$EXPLAINER_VOLUME" --env-file "$EXPLAINER_ENV_FILE" "$1"
}

explainer_start() {
  explainer_run_detached "$EXPLAINER_IMAGE"
}

explainer_stop() {
  docker rm -f "$EXPLAINER_NAME" >/dev/null 2>&1 || true
}

explainer_sudo() {
  if [ "$(id -u)" -ne 0 ]; then
    sudo "$@"
  else
    "$@"
  fi
}

# Tag what is running NOW, before the build replaces the tag. The ordering is the
# whole mechanism: `docker tag predictor-explainer predictor-explainer:prev` run
# after the build points :prev at the image that just failed, and the rollback
# becomes a restart of the broken image.
explainer_tag_previous() {
  if docker image inspect "$EXPLAINER_IMAGE" >/dev/null 2>&1; then
    docker tag "$EXPLAINER_IMAGE" "$EXPLAINER_PREVIOUS_IMAGE"
    echo "kept the running image as $EXPLAINER_PREVIOUS_IMAGE"
  else
    # A first deploy on this host, or the image was pruned. A :prev tag left
    # behind by some older deploy is worse than none: a failure would roll back
    # to an image that nobody chose and nobody has looked at since.
    docker rmi -f "$EXPLAINER_PREVIOUS_IMAGE" >/dev/null 2>&1 || true
    echo "no $EXPLAINER_IMAGE image on this host to keep; if this deploy fails there is nothing to roll back to" >&2
  fi
}

# On success the :prev tag names the image that is already running, and leaving
# it is not harmless: it is what the next failed deploy rolls back to, so the
# next failure would report a rollback that changed nothing.
explainer_drop_previous() {
  docker rmi -f "$EXPLAINER_PREVIOUS_IMAGE" >/dev/null 2>&1 || true
}

explainer_rollback_to_previous_image() {
  explainer_stop
  if ! docker image inspect "$EXPLAINER_PREVIOUS_IMAGE" >/dev/null 2>&1; then
    echo "ROLLBACK NOT POSSIBLE: $EXPLAINER_PREVIOUS_IMAGE is not on this host. $EXPLAINER_NAME is stopped and nothing is serving the explainer." >&2
    return 1
  fi
  echo "rolling back to $EXPLAINER_PREVIOUS_IMAGE" >&2
  if explainer_run_detached "$EXPLAINER_PREVIOUS_IMAGE" >/dev/null; then
    # One probe, not the full budget: the point of this line is to say whether
    # the service came back, and a rollback that cannot be seen is a rollback
    # that has to be believed.
    if probe "$EXPLAINER_HEALTH_URL" >/dev/null 2>&1; then
      echo "ROLLED BACK: $EXPLAINER_NAME is running $EXPLAINER_PREVIOUS_IMAGE again, on the same network with the same env file." >&2
    else
      echo "ROLLED BACK: $EXPLAINER_NAME is running $EXPLAINER_PREVIOUS_IMAGE again, but $EXPLAINER_HEALTH_URL did not answer on the first probe. Read the logs before trusting it." >&2
    fi
    return 0
  fi
  echo "ROLLBACK FAILED: $EXPLAINER_PREVIOUS_IMAGE would not start. $EXPLAINER_NAME is stopped and nothing is serving the explainer." >&2
  echo "--- last 30 lines of $EXPLAINER_NAME ---" >&2
  docker logs --tail 30 "$EXPLAINER_NAME" >&2 || true
  return 1
}

# The one place that decides whether a failed health check rolls back. Both
# deploy paths go through it, so both are covered by one test and neither can
# grow a second opinion. UNDO is the name of a rollback function.
explainer_verify_or_undo() {
  explainer_undo_message=$1
  shift
  if explainer_health; then
    return 0
  fi
  echo "$explainer_undo_message" >&2
  "$@" || true
  return 1
}

# setup: build a new image, start it, and put the old one back if it is broken.
explainer_deploy() {
  explainer_tag_previous
  # The build gets a ceiling for the same reason the probe does: an unbounded
  # `docker build` waiting on a stalled layer download is the identical hang.
  # Nothing has been stopped yet at this point, so a build that dies has to
  # leave the running container alone rather than take the service down on its
  # way out.
  if ! explainer_within "$EXPLAINER_BUILD_DEADLINE" \
      docker build -q -t "$EXPLAINER_IMAGE" "$EXPLAINER_BUILD_CONTEXT"; then
    echo "DEPLOY FAILED: docker build did not finish within ${EXPLAINER_BUILD_DEADLINE}s. $EXPLAINER_NAME was never stopped and is still serving the previous image." >&2
    return 1
  fi
  explainer_stop
  if explainer_start >/dev/null; then
    if explainer_verify_or_undo \
        "DEPLOY FAILED: the new $EXPLAINER_IMAGE did not come up; rolling back to $EXPLAINER_PREVIOUS_IMAGE" \
        explainer_rollback_to_previous_image; then
      explainer_drop_previous
      return 0
    fi
  else
    echo "DEPLOY FAILED: the new $EXPLAINER_IMAGE would not start at all; rolling back to $EXPLAINER_PREVIOUS_IMAGE" >&2
    explainer_rollback_to_previous_image || true
  fi
  return 1
}

# golive replaces no image -- it rewrites /etc/predictor/explainer.env -- so
# there is no earlier image to go back to. There is an earlier env file. Same
# rule, other half: keep one before the edit and put it back, with the same run
# arguments, if the service does not come up.
explainer_snapshot_env() {
  explainer_sudo cp "$EXPLAINER_ENV_FILE" "$EXPLAINER_PREVIOUS_ENV_FILE"
}

explainer_restore_env() {
  explainer_sudo cp "$EXPLAINER_PREVIOUS_ENV_FILE" "$EXPLAINER_ENV_FILE"
}

explainer_drop_env_snapshot() {
  explainer_sudo rm -f "$EXPLAINER_PREVIOUS_ENV_FILE"
}

explainer_reconfigure() {
  explainer_stop
  if explainer_start >/dev/null; then
    if explainer_verify_or_undo \
        "DEPLOY FAILED: the new configuration in $EXPLAINER_ENV_FILE did not come up; restoring $EXPLAINER_PREVIOUS_ENV_FILE" \
        explainer_rollback_to_previous_env; then
      explainer_drop_env_snapshot
      return 0
    fi
  else
    echo "DEPLOY FAILED: $EXPLAINER_NAME would not start with the new configuration in $EXPLAINER_ENV_FILE; restoring $EXPLAINER_PREVIOUS_ENV_FILE" >&2
    explainer_rollback_to_previous_env || true
  fi
  return 1
}

explainer_rollback_to_previous_env() {
  explainer_stop
  if ! explainer_restore_env; then
    echo "ROLLBACK NOT POSSIBLE: $EXPLAINER_PREVIOUS_ENV_FILE is gone or unreadable. $EXPLAINER_NAME is stopped and nothing is serving the explainer." >&2
    return 1
  fi
  if explainer_run_detached "$EXPLAINER_IMAGE" >/dev/null; then
    if probe "$EXPLAINER_HEALTH_URL" >/dev/null 2>&1; then
      echo "ROLLED BACK: $EXPLAINER_NAME is running $EXPLAINER_IMAGE again, with $EXPLAINER_PREVIOUS_ENV_FILE restored." >&2
    else
      echo "ROLLED BACK: $EXPLAINER_NAME is running $EXPLAINER_IMAGE again with $EXPLAINER_PREVIOUS_ENV_FILE restored, but $EXPLAINER_HEALTH_URL did not answer on the first probe. Read the logs before trusting it." >&2
    fi
    return 0
  fi
  echo "ROLLBACK FAILED: $EXPLAINER_NAME would not start with the previous configuration restored. It is stopped and nothing is serving the explainer." >&2
  return 1
}
# <<< scripts/lib/deploy_safety.sh
'

case "$MODE" in
setup)
  $SSH "NET='${NET:-}' NFL='${NFL:-}' CFB='${CFB:-}' PL='${PL:-}' NBA='${NBA:-}' F1='${F1:-}' bash -s" <<EOF
$remote_common
[ -d ~/predictor-hub ] || git clone https://github.com/Kevocado/predictor-hub ~/predictor-hub
git -C ~/predictor-hub pull --ff-only

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

# The whole of the deploy: tag the running image as predictor-explainer:prev BEFORE the
# build replaces it, build, start the new one, and if it does not answer /status then put
# :prev back on the same network with the same env file, exiting non-zero and saying
# which of the two happened. The old sequence here -- rm -f, run, health, leave whatever
# came up -- meant a failed deploy left the broken container in place and had already
# replaced the image, so there was nothing to go back to.
explainer_deploy || exit 1
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
curl -s --max-time 20 https://openrouter.ai/api/v1/models | python3 -c 'import json,sys
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
# The probe, the deadlines and the rollback. Byte-identical to the copy in remote_common,
# and this script refuses to send this block if it has drifted from the library on disk.
# >>> scripts/lib/deploy_safety.sh
# shellcheck shell=sh
# Deploy safety for the explainer: bound every step that can hang, and put the
# previous working image back when the new one fails its health check.
#
# Sourced by scripts/deploy-explainer.sh, embedded verbatim in the block each
# deploy mode sends, and run directly by services/explainer/tests/
# test_deploy_script.py against a fake docker on PATH.
#
# POSIX sh, deliberately. The far side runs bash, but this file is also read by
# /bin/sh on a macOS laptop and by dash on a Linux CI runner. An earlier version
# of this logic used ${*##*-- } to pick an argument out of "$@", which neither
# can read, and a deploy is the worst possible place to find that out. So: no
# arrays, no ${var//from/to}, no local, no [[ ]], no $SECONDS arithmetic beyond
# adding to it. POSIX sh has no local, so every function below uses its own
# prefixed variable names instead.
#
# Two rules that the rest of the file obeys, both because of how it travels:
#
#   * No apostrophe anywhere. deploy-explainer.sh embeds this text inside a
#     single-quoted shell string, and one apostrophe would end that string and
#     turn the rest of this file into remote code.
#   * A dollar is written for the shell that will READ it, not the one writing
#     it. This is sent over ssh and expanded on the VPS.

# --------------------------------------------------------------------------
# The numbers. Every one of these is a ceiling on something that can hang on a
# bad network, and every one is ${VAR:-default} so a test -- or a one-off
# emergency deploy -- can move it from the environment without editing a file
# that is already on the host.
EXPLAINER_NAME=${EXPLAINER_NAME:-predictor-explainer}
EXPLAINER_IMAGE=${EXPLAINER_IMAGE:-predictor-explainer}
EXPLAINER_PREVIOUS_IMAGE=${EXPLAINER_PREVIOUS_IMAGE:-predictor-explainer:prev}
EXPLAINER_PROBE_IMAGE=${EXPLAINER_PROBE_IMAGE:-curlimages/curl}
# The probe container is named so that a probe killed at its deadline, whose
# `docker run` client did not get to clean it up, can still be removed.
EXPLAINER_PROBE_CONTAINER=${EXPLAINER_PROBE_CONTAINER:-explainer-probe}
# /status is the only health-shaped route the app defines (explainer/app.py
# defines /explain/{sport}/{id} and /status, and /health and /ready both 404).
EXPLAINER_HEALTH_URL=${EXPLAINER_HEALTH_URL:-http://predictor-explainer:8090/status}
EXPLAINER_ENV_FILE=${EXPLAINER_ENV_FILE:-/etc/predictor/explainer.env}
EXPLAINER_PREVIOUS_ENV_FILE=${EXPLAINER_PREVIOUS_ENV_FILE:-/etc/predictor/explainer.env.prev}
EXPLAINER_BUILD_CONTEXT=${EXPLAINER_BUILD_CONTEXT:-$HOME/predictor-hub/services/explainer}
EXPLAINER_VOLUME=${EXPLAINER_VOLUME:-explainer-data:/data}
NET=${NET:-}

# curl gives up on the HTTP call after this many seconds. It says nothing about
# the command that carries it: by the time curl counts, the container is already
# running. See explainer_watchdog for what this number does not cover.
EXPLAINER_CURL_MAX_TIME=${EXPLAINER_CURL_MAX_TIME:-5}
# The ceiling on ONE probe attempt, the `docker run` included: 5 seconds for the
# request plus the container start, rounded up. A hung attempt cannot spend more
# than this, which is what leaves the loop below budget to try again.
EXPLAINER_ATTEMPT_DEADLINE=${EXPLAINER_ATTEMPT_DEADLINE:-10}
# How long the health check keeps trying while the container boots.
EXPLAINER_HEALTH_BUDGET=${EXPLAINER_HEALTH_BUDGET:-30}
# The ceiling on the whole health check, whatever any child does. The budget and
# the attempt deadline already bound it in practice; this is the number that
# bounds it when the bounding itself is what is broken.
EXPLAINER_HEALTH_CEILING=${EXPLAINER_HEALTH_CEILING:-45}
# One cold pull of the probe image, once, before the attempts start, and a build.
# Both are given longer than a probe attempt on purpose: neither has to fit in
# ten seconds, and both hang the same way when a registry stops answering.
EXPLAINER_PULL_DEADLINE=${EXPLAINER_PULL_DEADLINE:-300}
EXPLAINER_BUILD_DEADLINE=${EXPLAINER_BUILD_DEADLINE:-900}
# The post-deploy smoke test asks the sport APIs for a fixture, which is slower than
# a health probe, so it gets its own pair. It is still a docker run that can hang on
# a pull, which is why it is bounded at all.
EXPLAINER_REQUEST_MAX_TIME=${EXPLAINER_REQUEST_MAX_TIME:-30}
EXPLAINER_REQUEST_DEADLINE=${EXPLAINER_REQUEST_DEADLINE:-45}
# Seconds between a TERM and a KILL, for a command that ignores the first one.
EXPLAINER_GRACE=${EXPLAINER_GRACE:-2}
# auto prefers GNU timeout(1) when it is on PATH and falls back to the portable
# watchdog. shell forces the watchdog, timeout forces timeout(1): both exist so
# that a test can cover the branch this host does not have.
EXPLAINER_DEADLINE_IMPL=${EXPLAINER_DEADLINE_IMPL:-auto}

# --------------------------------------------------------------------------
# The outer deadline.
#
# Why this file exists at all: curl has --max-time, but the command that carries
# curl does not. probe runs `docker run --rm curlimages/curl ...`, and everything
# before curl starts is inside that command -- the daemon pulling
# curlimages/curl if it is not cached, creating the container, attaching the
# network, DNS, the runtime starting. --max-time cannot see any of it, because it
# starts counting once the container is running.
#
# The health loop around it has a 30 second budget, and that budget does not help:
# a loop can only spend time it is running. It re-reads the clock between
# attempts, so a single `docker run` that never returns means the budget is never
# checked again. That is the hang this closes -- the deploy sitting on a command
# with no output and no timeout, on a machine an operator is watching to see
# whether the deploy is stuck.
#
# Two implementations, because there is no timeout(1) on macOS:
#
#   timeout  GNU coreutils. Preferred when present: -k bounds how long it waits
#           for a child that ignores TERM, and it signals the process group, so
#           the container goes with the client. On the VPS; not on a laptop.
#
#   shell   A watchdog: run the command in the background, poll for its exit
#           until the limit, kill it if it is still there. POSIX sh only, which
#           is what the two implementations have in common -- and the reason the
#           portable one is not the GNU one is that macOS has no timeout(1).
#
# Which one runs is decided by what the command IS, not by a preference, because
# the two are not interchangeable. timeout(1) execs a program: it resolves its
# target through PATH, so it can run a file and nothing else. A shell function, an
# alias and a keyword have no file, and when a name is both -- docker, on the VPS,
# where the login user is not in the docker group and the remote block defines
# docker() { command sudo docker "$@"; } -- the file is exactly the thing that must
# not be run. Handing a function to timeout(1) does not fail loudly: it runs the
# bare binary, which answers permission denied, and the wrapper reports that as a
# timeout. A deadline that silently stops applying looks like a command that
# finished quickly, which is how a green deploy skipped a deadline and nobody
# noticed until the build came back in four minutes instead of four seconds.
#
# So: the watchdog runs whatever the shell itself can call, timeout(1) runs only
# what exec can find, and a name that is neither is refused out loud. See
# explainer_resolve_kind, which is the only place that question is asked.

# explainer_watchdog LIMIT COMMAND... -- run COMMAND, killed at LIMIT.
#
# A deadline kill exits 124, which is what GNU timeout returns for the same
# event, so nothing downstream has to know which implementation ran it.
#
# The poll is the point of the ordering below. The watchdog watches for the
# child to disappear and kills only while it is still there, rather than sleeping
# once and killing a pid it no longer owns -- a pid the shell has already reaped
# can belong to something else by then, and "everything works except the tests
# that kill a random process" is not a deploy script. The residual race is the
# one poll between a child dying and the shell reaping it, which is the same
# race GNU timeout has and is not closable from a POSIX shell.
#
# The watchdog itself is redirected to /dev/null and is never killed by hand,
# and both of those are load-bearing. It inherits stdout from the shell that
# spawned it, and every probe result is read through a command substitution --
# `body=$(probe ...)`. A command substitution waits for the last writer on the
# pipe to close it, so a watchdog holding that pipe holds the whole health check
# for its full limit even when the probe answered in a millisecond. And a
# hand-written kill would not have helped: a non-interactive shell does not act
# on a signal while it is waiting for a foreground child, so the TERM would sit
# unread until the sleep finished. The watchdog exits by itself within one poll
# of the command it is watching, which is the whole of its job.
explainer_watchdog() {
  explainer_wd_limit=$1
  shift
  "$@" &
  explainer_wd_child=$!
  (
    explainer_wd_left=$explainer_wd_limit
    while kill -0 "$explainer_wd_child" 2>/dev/null; do
      if [ "$explainer_wd_left" -le 0 ]; then
        kill -TERM "$explainer_wd_child" 2>/dev/null || exit 0
        explainer_wd_grace=0
        while kill -0 "$explainer_wd_child" 2>/dev/null; do
          if [ "$explainer_wd_grace" -ge "$EXPLAINER_GRACE" ]; then
            kill -KILL "$explainer_wd_child" 2>/dev/null || true
            exit 0
          fi
          sleep 1
          explainer_wd_grace=$((explainer_wd_grace + 1))
        done
        exit 0
      fi
      sleep 1
      explainer_wd_left=$((explainer_wd_left - 1))
    done
  ) >/dev/null 2>&1 &
  if wait "$explainer_wd_child"; then explainer_wd_rc=0; else explainer_wd_rc=$?; fi
  # A shell reports a killed child as 128+signal, which is not an exit code any
  # caller can compare against.
  if [ "$explainer_wd_rc" -ge 128 ]; then explainer_wd_rc=124; fi
  return "$explainer_wd_rc"
}

# explainer_path_of NAME -- the file that exec would run for NAME, on stdout, or
# nothing at all.
#
# This is `type -P` written out, because `type -P` is a bashism and this file is
# read by dash and ksh93 as well as bash. It asks about FILES ONLY, on purpose: it
# ignores functions, builtins, aliases and keywords, because for a name that is
# both a function and a file -- docker, on the VPS -- the file is precisely the one
# that must not be run.
explainer_path_of() {
  explainer_po_name=${1:-}
  case "$explainer_po_name" in
    */*)
      # A name with a slash is used as written, which is what exec does with it too.
      if [ -f "$explainer_po_name" ] && [ -x "$explainer_po_name" ]; then
        printf "%s\n" "$explainer_po_name"
        return 0
      fi
      return 1
      ;;
  esac
  explainer_po_left=${PATH:-}
  while [ -n "$explainer_po_left" ]; do
    explainer_po_dir=${explainer_po_left%%:*}
    if [ "$explainer_po_dir" = "$explainer_po_left" ]; then
      explainer_po_left=
    else
      explainer_po_left=${explainer_po_left#*:}
    fi
    # An empty PATH element means the current directory, which is what exec says too.
    [ -n "$explainer_po_dir" ] || explainer_po_dir=.
    if [ -f "$explainer_po_dir/$explainer_po_name" ] && [ -x "$explainer_po_dir/$explainer_po_name" ]; then
      printf "%s\n" "$explainer_po_dir/$explainer_po_name"
      return 0
    fi
  done
  return 1
}

# explainer_resolve_kind NAME -- what a bare NAME would run here, in the order the
# shell itself resolves it, on stdout: function, alias, keyword, builtin or file.
# Returns non-zero, and prints nothing, when this shell has no idea what NAME is.
#
# `command -V` is the portable question -- POSIX has it, and bash, dash and ksh93 all
# answer it -- but the answer is prose, and the prose differs per shell: "NAME is a
# function" (bash, ksh93), "NAME is a shell function" (dash), "NAME is a shell
# builtin", "NAME is /bin/sleep". So the WORDING is matched rather than the status,
# because the status is not usable either: dash reports an unknown name on stdout and
# still exits 0. Only the first line is read, because bash prints the entire body of
# a function after it and a function body can contain any word at all.
#
# `type -t` is the tidier question and is not portable: dash has no -t and dies on the
# attempt, and ksh93 maps type to whence and rejects -t. That is not cosmetic. The
# first fix for the VPS bug classified with `type -t`, so on dash and ksh93 the
# classification came back empty, the function was not recognised, and the deadline
# wrapper handed the name to timeout(1) -- which execs the bare docker, which is not
# in the docker group. The fix that was meant to stop that failure did not fire on
# two of the three shells this file is written for.
#
# A name that classifies as neither is not guessed at. The caller is expected to
# refuse it out loud, because the alternative is timeout(1) reporting "not found" for
# a program on a host where the real problem was a function all along.
explainer_resolve_kind() {
  explainer_rk_name=${1:-}
  if [ -z "$explainer_rk_name" ]; then
    return 2
  fi
  # `|| :` because command -V is allowed to fail on a name it does not know, and
  # this file is read under set -e. The description is the answer; the status is not.
  explainer_rk_desc=$(command -V "$explainer_rk_name" 2>&1) || :
  # A newline held in a variable, because cutting the description at one is the only
  # way to read the first line of it in a POSIX shell. Double quotes, not single:
  # this file has no apostrophes in it at all (see the top of the file).
  explainer_rk_nl="
"
  case "$explainer_rk_desc" in
    *"$explainer_rk_nl"*) explainer_rk_line=${explainer_rk_desc%%"$explainer_rk_nl"*} ;;
    *) explainer_rk_line=$explainer_rk_desc ;;
  esac
  case "$explainer_rk_line" in
    *function*) explainer_rk_kind="function" ;;
    *alias*) explainer_rk_kind="alias" ;;
    *keyword*) explainer_rk_kind="keyword" ;;
    *builtin*) explainer_rk_kind="builtin" ;;
    *)
      # Either a path, or a name this shell does not know at all. Only the PATH walk
      # tells those apart, and since dash exits 0 for the second case, the walk --
      # not the status of command -V -- is what decides.
      if explainer_path_of "$explainer_rk_name" >/dev/null; then
        explainer_rk_kind="file"
      else
        return 1
      fi
      ;;
  esac
  printf "%s\n" "$explainer_rk_kind"
}

# explainer_within LIMIT COMMAND... -- the outer deadline around one command.
explainer_within() {
  explainer_within_limit=$1
  shift
  if [ "$#" -eq 0 ]; then
    echo "explainer_within: no command was given to run within ${explainer_within_limit}s" >&2
    return 2
  fi
  # What the first argument actually is, which is the only thing that says whether an
  # exec-based wrapper can run it at all. Asked once, here, so that no second deadline
  # entry point can answer it differently.
  if ! explainer_within_kind=$(explainer_resolve_kind "$1"); then
    echo "explainer_within: $1 is not a command this shell can run: it is not a function, a builtin, or an executable on PATH" >&2
    return 127
  fi
  case "$explainer_within_kind" in
    function | alias | keyword)
      # timeout(1) execs a program, and none of these is one. The watchdog runs the
      # command the way the shell around it would, which is the whole reason the
      # remote block defines docker as a function at all.
      explainer_watchdog "$explainer_within_limit" "$@" || return $?
      return 0
      ;;
    builtin)
      # A builtin is exec-able only when PATH has a file of the same name, because
      # execvp has no other way to find one. With one -- true, cat -- timeout(1) runs
      # the same thing the shell would. Without one, only this shell knows what the
      # builtin does, so only the watchdog can run it.
      if ! explainer_path_of "$1" >/dev/null; then
        explainer_watchdog "$explainer_within_limit" "$@" || return $?
        return 0
      fi
      ;;
  esac
  case "${EXPLAINER_DEADLINE_IMPL:-auto}" in
    shell) explainer_watchdog "$explainer_within_limit" "$@" ;;
    timeout) timeout -k "$EXPLAINER_GRACE" "$explainer_within_limit" "$@" ;;
    auto)
      if command -v timeout >/dev/null 2>&1; then
        timeout -k "$EXPLAINER_GRACE" "$explainer_within_limit" "$@"
      else
        explainer_watchdog "$explainer_within_limit" "$@"
      fi
      ;;
    *)
      echo "EXPLAINER_DEADLINE_IMPL=${EXPLAINER_DEADLINE_IMPL} is not auto, shell or timeout" >&2
      return 2
      ;;
  esac
}

# --------------------------------------------------------------------------
# The probe.
#
# A probe container that is killed at its deadline outlives the `docker run`
# client that started it, and --rm only fires when that client exits normally.
# So the probe container is named and removed on the way in as well as on the way
# out: on the way out so a hang does not leak a container, and on the way in so
# a container leaked by an earlier hang cannot make the next attempt fail with
# "name already in use" -- which would look exactly like an unhealthy service.
explainer_discard_probe() {
  docker rm -f "$EXPLAINER_PROBE_CONTAINER" >/dev/null 2>&1 || true
}

probe() {
  explainer_discard_probe
  if explainer_within "$EXPLAINER_ATTEMPT_DEADLINE" \
      docker run --rm --name "$EXPLAINER_PROBE_CONTAINER" --network "$NET" \
      "$EXPLAINER_PROBE_IMAGE" -sfS --max-time "$EXPLAINER_CURL_MAX_TIME" "$@"
  then
    explainer_probe_rc=0
  else
    explainer_probe_rc=$?
  fi
  explainer_discard_probe
  return "$explainer_probe_rc"
}

# The probe image, pulled once with its own ceiling, before the first attempt.
# Without this the first attempt pays for the pull inside a ten second attempt
# ceiling, so the first deploy on a host that has never run curlimages/curl fails
# for a reason that has nothing to do with the explainer. A pull that cannot
# reach the registry is not fatal: the cached copy may be perfectly good, and the
# probe will say so if it is not.
explainer_prefetch_probe_image() {
  if ! explainer_within "$EXPLAINER_PULL_DEADLINE" docker pull "$EXPLAINER_PROBE_IMAGE" >/dev/null 2>&1; then
    echo "could not pull $EXPLAINER_PROBE_IMAGE; the probe will use the cached copy if there is one" >&2
  fi
}

# --------------------------------------------------------------------------
# The health check.
#
# date +%s rather than $SECONDS, on purpose: $SECONDS is a bashism, dash does
# not have it, and an unset $SECONDS inside an arithmetic expansion is a syntax
# error rather than a wrong number. The budget is wall clock, and an attempt
# that overruns it is not counted against the next one -- which is exactly what
# the ceiling below is for.
explainer_health_loop() {
  explainer_health_until=$(($(date +%s) + EXPLAINER_HEALTH_BUDGET))
  while [ "$(date +%s)" -lt "$explainer_health_until" ]; do
    if explainer_body=$(probe "$EXPLAINER_HEALTH_URL" 2>/dev/null) && [ -n "$explainer_body" ]; then
      echo "healthy: $explainer_body"
      return 0
    fi
    sleep 1
  done
  return 1
}

# This replaces a fixed six-second sleep followed by printing whatever came back,
# which printed an empty "status: " for a container still booting or crash-looping
# and then reported success. It also runs under a hard ceiling, which the loop
# inside it does not need in order to work but which is what makes it a bound
# rather than a plan: a loop bug, a sleep that blocks, a child that ignores both
# deadlines below -- none of them can push this past EXPLAINER_HEALTH_CEILING.
explainer_health() {
  # The probe image, pulled once and out of the way, before any attempt is capped at
  # ten seconds. Doing this here rather than in each deploy is what guarantees it
  # happens on every path that probes, including a rollback.
  explainer_prefetch_probe_image
  # explainer_health_loop is a shell function, so explainer_within classifies it and
  # runs it with the watchdog rather than handing it to timeout(1), which cannot call
  # a function. One deadline entry point means that decision is made in one place.
  if explainer_within "$EXPLAINER_HEALTH_CEILING" explainer_health_loop; then
    return 0
  else
    explainer_health_rc=$?
  fi
  if [ "$explainer_health_rc" -eq 124 ]; then
    echo "the health probe was still running ${EXPLAINER_HEALTH_CEILING}s after the container started" >&2
  fi
  echo "DEPLOY FAILED: $EXPLAINER_HEALTH_URL did not answer 200 within ${EXPLAINER_HEALTH_BUDGET}s of the container starting." >&2
  echo "--- last 30 lines of $EXPLAINER_NAME ---" >&2
  docker logs --tail 30 "$EXPLAINER_NAME" >&2 || true
  return "$explainer_health_rc"
}

# --------------------------------------------------------------------------
# Starting it, and putting it back.
#
# explainer_run_detached is the only place that knows how the explainer is
# started. The deploy and the rollback both call it and differ by exactly one
# argument: the image. Same name, same restart policy, same network, same volume,
# same env file. That is not tidiness, it is the requirement -- a rollback that
# came back on a different network, or without the env file, would be a different
# service pretending to be the old one.
explainer_run_detached() {
  docker run -d --name "$EXPLAINER_NAME" --restart unless-stopped --network "$NET" \
    -v "$EXPLAINER_VOLUME" --env-file "$EXPLAINER_ENV_FILE" "$1"
}

explainer_start() {
  explainer_run_detached "$EXPLAINER_IMAGE"
}

explainer_stop() {
  docker rm -f "$EXPLAINER_NAME" >/dev/null 2>&1 || true
}

explainer_sudo() {
  if [ "$(id -u)" -ne 0 ]; then
    sudo "$@"
  else
    "$@"
  fi
}

# Tag what is running NOW, before the build replaces the tag. The ordering is the
# whole mechanism: `docker tag predictor-explainer predictor-explainer:prev` run
# after the build points :prev at the image that just failed, and the rollback
# becomes a restart of the broken image.
explainer_tag_previous() {
  if docker image inspect "$EXPLAINER_IMAGE" >/dev/null 2>&1; then
    docker tag "$EXPLAINER_IMAGE" "$EXPLAINER_PREVIOUS_IMAGE"
    echo "kept the running image as $EXPLAINER_PREVIOUS_IMAGE"
  else
    # A first deploy on this host, or the image was pruned. A :prev tag left
    # behind by some older deploy is worse than none: a failure would roll back
    # to an image that nobody chose and nobody has looked at since.
    docker rmi -f "$EXPLAINER_PREVIOUS_IMAGE" >/dev/null 2>&1 || true
    echo "no $EXPLAINER_IMAGE image on this host to keep; if this deploy fails there is nothing to roll back to" >&2
  fi
}

# On success the :prev tag names the image that is already running, and leaving
# it is not harmless: it is what the next failed deploy rolls back to, so the
# next failure would report a rollback that changed nothing.
explainer_drop_previous() {
  docker rmi -f "$EXPLAINER_PREVIOUS_IMAGE" >/dev/null 2>&1 || true
}

explainer_rollback_to_previous_image() {
  explainer_stop
  if ! docker image inspect "$EXPLAINER_PREVIOUS_IMAGE" >/dev/null 2>&1; then
    echo "ROLLBACK NOT POSSIBLE: $EXPLAINER_PREVIOUS_IMAGE is not on this host. $EXPLAINER_NAME is stopped and nothing is serving the explainer." >&2
    return 1
  fi
  echo "rolling back to $EXPLAINER_PREVIOUS_IMAGE" >&2
  if explainer_run_detached "$EXPLAINER_PREVIOUS_IMAGE" >/dev/null; then
    # One probe, not the full budget: the point of this line is to say whether
    # the service came back, and a rollback that cannot be seen is a rollback
    # that has to be believed.
    if probe "$EXPLAINER_HEALTH_URL" >/dev/null 2>&1; then
      echo "ROLLED BACK: $EXPLAINER_NAME is running $EXPLAINER_PREVIOUS_IMAGE again, on the same network with the same env file." >&2
    else
      echo "ROLLED BACK: $EXPLAINER_NAME is running $EXPLAINER_PREVIOUS_IMAGE again, but $EXPLAINER_HEALTH_URL did not answer on the first probe. Read the logs before trusting it." >&2
    fi
    return 0
  fi
  echo "ROLLBACK FAILED: $EXPLAINER_PREVIOUS_IMAGE would not start. $EXPLAINER_NAME is stopped and nothing is serving the explainer." >&2
  echo "--- last 30 lines of $EXPLAINER_NAME ---" >&2
  docker logs --tail 30 "$EXPLAINER_NAME" >&2 || true
  return 1
}

# The one place that decides whether a failed health check rolls back. Both
# deploy paths go through it, so both are covered by one test and neither can
# grow a second opinion. UNDO is the name of a rollback function.
explainer_verify_or_undo() {
  explainer_undo_message=$1
  shift
  if explainer_health; then
    return 0
  fi
  echo "$explainer_undo_message" >&2
  "$@" || true
  return 1
}

# setup: build a new image, start it, and put the old one back if it is broken.
explainer_deploy() {
  explainer_tag_previous
  # The build gets a ceiling for the same reason the probe does: an unbounded
  # `docker build` waiting on a stalled layer download is the identical hang.
  # Nothing has been stopped yet at this point, so a build that dies has to
  # leave the running container alone rather than take the service down on its
  # way out.
  if ! explainer_within "$EXPLAINER_BUILD_DEADLINE" \
      docker build -q -t "$EXPLAINER_IMAGE" "$EXPLAINER_BUILD_CONTEXT"; then
    echo "DEPLOY FAILED: docker build did not finish within ${EXPLAINER_BUILD_DEADLINE}s. $EXPLAINER_NAME was never stopped and is still serving the previous image." >&2
    return 1
  fi
  explainer_stop
  if explainer_start >/dev/null; then
    if explainer_verify_or_undo \
        "DEPLOY FAILED: the new $EXPLAINER_IMAGE did not come up; rolling back to $EXPLAINER_PREVIOUS_IMAGE" \
        explainer_rollback_to_previous_image; then
      explainer_drop_previous
      return 0
    fi
  else
    echo "DEPLOY FAILED: the new $EXPLAINER_IMAGE would not start at all; rolling back to $EXPLAINER_PREVIOUS_IMAGE" >&2
    explainer_rollback_to_previous_image || true
  fi
  return 1
}

# golive replaces no image -- it rewrites /etc/predictor/explainer.env -- so
# there is no earlier image to go back to. There is an earlier env file. Same
# rule, other half: keep one before the edit and put it back, with the same run
# arguments, if the service does not come up.
explainer_snapshot_env() {
  explainer_sudo cp "$EXPLAINER_ENV_FILE" "$EXPLAINER_PREVIOUS_ENV_FILE"
}

explainer_restore_env() {
  explainer_sudo cp "$EXPLAINER_PREVIOUS_ENV_FILE" "$EXPLAINER_ENV_FILE"
}

explainer_drop_env_snapshot() {
  explainer_sudo rm -f "$EXPLAINER_PREVIOUS_ENV_FILE"
}

explainer_reconfigure() {
  explainer_stop
  if explainer_start >/dev/null; then
    if explainer_verify_or_undo \
        "DEPLOY FAILED: the new configuration in $EXPLAINER_ENV_FILE did not come up; restoring $EXPLAINER_PREVIOUS_ENV_FILE" \
        explainer_rollback_to_previous_env; then
      explainer_drop_env_snapshot
      return 0
    fi
  else
    echo "DEPLOY FAILED: $EXPLAINER_NAME would not start with the new configuration in $EXPLAINER_ENV_FILE; restoring $EXPLAINER_PREVIOUS_ENV_FILE" >&2
    explainer_rollback_to_previous_env || true
  fi
  return 1
}

explainer_rollback_to_previous_env() {
  explainer_stop
  if ! explainer_restore_env; then
    echo "ROLLBACK NOT POSSIBLE: $EXPLAINER_PREVIOUS_ENV_FILE is gone or unreadable. $EXPLAINER_NAME is stopped and nothing is serving the explainer." >&2
    return 1
  fi
  if explainer_run_detached "$EXPLAINER_IMAGE" >/dev/null; then
    if probe "$EXPLAINER_HEALTH_URL" >/dev/null 2>&1; then
      echo "ROLLED BACK: $EXPLAINER_NAME is running $EXPLAINER_IMAGE again, with $EXPLAINER_PREVIOUS_ENV_FILE restored." >&2
    else
      echo "ROLLED BACK: $EXPLAINER_NAME is running $EXPLAINER_IMAGE again with $EXPLAINER_PREVIOUS_ENV_FILE restored, but $EXPLAINER_HEALTH_URL did not answer on the first probe. Read the logs before trusting it." >&2
    fi
    return 0
  fi
  echo "ROLLBACK FAILED: $EXPLAINER_NAME would not start with the previous configuration restored. It is stopped and nothing is serving the explainer." >&2
  return 1
}
# <<< scripts/lib/deploy_safety.sh
IFS= read -r KEY; IFS= read -r M1; IFS= read -r M2
$S test -f "$EXPLAINER_ENV_FILE" || { echo "run setup first"; exit 1; }
NET=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' predictor-explainer | awk '{print $1}')
# golive replaces no image -- it rewrites the env file -- so there is no earlier image to
# go back to. There is an earlier env file: keep one before the first sed, and
# explainer_reconfigure puts it back with the same run arguments if the service does not
# come up. The snapshot is removed once the service is healthy, for the same reason the
# :prev tag is.
explainer_snapshot_env
$S sed -i '/^OPENROUTER_API_KEY=/d;s/^EXPLAINER_ENABLED=.*/EXPLAINER_ENABLED=true/' "$EXPLAINER_ENV_FILE"
[ -n "$M1" ] && $S sed -i '/^EXPLAINER_MODEL=/d' "$EXPLAINER_ENV_FILE"
[ -n "$M2" ] && $S sed -i '/^EXPLAINER_FALLBACK_MODEL=/d' "$EXPLAINER_ENV_FILE"
{ echo "OPENROUTER_API_KEY=$KEY"; [ -n "$M1" ] && echo "EXPLAINER_MODEL=$M1"; [ -n "$M2" ] && echo "EXPLAINER_FALLBACK_MODEL=$M2"; true; } | $S tee -a "$EXPLAINER_ENV_FILE" >/dev/null
$S chmod 600 "$EXPLAINER_ENV_FILE"
explainer_reconfigure || exit 1
explainer_within "$EXPLAINER_ATTEMPT_DEADLINE" docker run --rm --network "${NET:?network not found}" "$EXPLAINER_PROBE_IMAGE" -s "$EXPLAINER_HEALTH_URL"; echo
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
