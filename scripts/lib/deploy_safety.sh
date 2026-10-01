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

# explainer_within LIMIT COMMAND... -- the outer deadline around one command.
explainer_within() {
  explainer_within_limit=$1
  shift
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

# explainer_within_function LIMIT FUNCTION... -- the same ceiling for a shell
# FUNCTION. GNU timeout execs a program and cannot call one, so this always takes
# the watchdog path. The ceiling it enforces is identical; only the mechanism
# for enforcing it differs, because there is no portable way to make execvp call
# a function.
explainer_within_function() {
  explainer_wfn_limit=$1
  shift
  explainer_watchdog "$explainer_wfn_limit" "$@"
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
  if explainer_within_function "$EXPLAINER_HEALTH_CEILING" explainer_health_loop; then
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
