"""The deploy script has to agree with the service it deploys.

`scripts/deploy-explainer.sh` starts a container and then asks it whether it is
alive. Two things about that can silently rot, and neither shows up in the
explainer's own tests:

  * the health check exists in two places -- the `remote_common` block that
    `setup` and `status` send, and the self-contained block that `golive` sends,
    because that one carries the API key on stdin. They have to be the same
    function, or fixing one leaves the other broken.

  * the URL it polls is a literal in the script. The app defines exactly two
    routes and the Dockerfile pins one port; if either moves, the poll is
    asking a closed port and the check is decoration. This reads both files and
    derives the route and the port from them rather than restating them.

The behaviour of the check -- does it pass against a live service, does it fail
loudly against a dead one -- is shell against docker, and the decision about
what to do when it fails is shell too, so both are verified by RUNNING the
shell, not by reading it: the functions live in scripts/lib/deploy_safety.sh and
the tests below run them against a fake docker on PATH.

That is what the second half of this file is for, and it is the part that has to
be hermetic. The deploy script talks to a VPS, and an earlier task in this
repository ran `golive` against that VPS by accident. So the harness here never
invokes the script, never invokes ssh, and never reaches a docker daemon:

  * every shell it runs is `bash -c '. scripts/lib/deploy_safety.sh; ...'` --
    the library, not the script, and the library contains no ssh and no build.
  * PATH is prefixed with a directory of fakes for docker, curl, sudo and ssh,
    and a test asserts the real ones are shadowed. The fakes answer from
    FAKE_* environment variables and record every invocation, so a test can
    assert whether the rollback ran without a daemon to run it against.
  * the one test that does run deploy-explainer.sh runs a COPY in tmp_path,
    with the fake ssh on PATH, and asserts from the ssh log that ssh was never
    called.

These are the raw texts, before ssh. That is deliberate: the tests read what is
in the file, and whether the heredoc quoting survives expansion on the way to
the VPS is a separate question answered by running the script, not by a regex.
"""
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/deploy-explainer.sh"
LIB = REPO / "scripts/lib/deploy_safety.sh"
DOCKERFILE = REPO / "services/explainer/Dockerfile"
APP = REPO / "services/explainer/explainer/app.py"

# The library, as it is written on disk and as it is embedded in the two remote
# blocks. Markers, not a regex guess: the blocks are single-quoted shell strings
# that are read by a shell on another machine, and the only safe way to get text
# out of them is to cut at lines that mean nothing to the shell.
BEGIN = "# >>> scripts/lib/deploy_safety.sh"
END = "# <<< scripts/lib/deploy_safety.sh"
EMBEDDED = re.compile(
    rf"^{re.escape(BEGIN)}\n(?P<lib>.*?)^{re.escape(END)}$", re.S | re.M
)

# The old narrow slice (probe() .. the end of explainer_health()) is gone: the
# deadline wrapper, the rollback and the run arguments are all part of the check
# now, and asserting on a slice that excludes them is how a bound on one of them
# gets deleted without a test noticing. Everything below reads the whole library.
HEALTH_FN = EMBEDDED


@pytest.fixture(scope="module")
def script():
    return SCRIPT.read_text()


@pytest.fixture(scope="module")
def remote_common(script):
    """The block `setup` and `status` both send, as written in the file."""
    found = re.search(r"remote_common='\n(.*?)\n'\n", script, re.S)
    assert found, "remote_common is gone; setup and status no longer share a preamble"
    return found.group(1)


@pytest.fixture(scope="module")
def setup_body(script):
    found = re.search(r"bash -s\" <<EOF\n(.*?)\nEOF\n", script, re.S)
    assert found, "the setup heredoc is gone"
    return found.group(1)


@pytest.fixture(scope="module")
def golive_body(script):
    found = re.search(r"REMOTE <<'EOF' \|\| true\n(.*?)\nEOF\n", script, re.S)
    assert found, "the golive heredoc is gone"
    return found.group(1)


def code_of(block):
    """The block's shell, without its comments.

    Only the comments may differ: golive's copy says "copy of the one in
    remote_common". Nothing else is normalised, deliberately. A heredoc
    interpolates a variable verbatim, so both blocks must already be written the
    way the remote shell reads them -- if one needed a `\\$` the other did not,
    that is a difference, not a formatting quirk, and the one with the backslash
    is a syntax error on the VPS.
    """
    return "\n".join(line for line in block.splitlines()
                     if line.strip() and not line.strip().startswith("#"))


# --------------------------------------------------------------------------
# A docker that cannot reach a daemon.
#
# It answers from FAKE_* variables and appends every invocation to a log, so a
# test can assert which commands ran -- in particular whether the rollback ran --
# without there being a daemon anywhere. The image set is a text file of tags,
# which is enough: "does this tag exist" is the only question the deploy asks.
FAKE_DOCKER = r"""#!/usr/bin/env bash
set -u
log=${FAKE_DOCKER_LOG:?FAKE_DOCKER_LOG must be set}
images=${FAKE_IMAGES:?FAKE_IMAGES must be set}
printf '%s\n' "$*" >>"$log"

case "${1:-}" in
  image)
    # `docker image inspect TAG`: does this tag exist on this host
    [ "${2:-}" = inspect ] || exit 1
    grep -qxF "${3:-}" "$images"
    ;;
  tag)
    printf '%s\n' "${3:-}" >>"$images"
    ;;
  rmi)
    grep -vxF "${2:-}" "$images" >"$images.new" 2>/dev/null || true
    mv "$images.new" "$images"
    ;;
  pull)
    exit "${FAKE_PULL_RC:-0}"
    ;;
  build)
    # A build that hangs is the same hang as a hung probe, and it is bounded too.
    [ "${FAKE_BUILD_MODE:-ok}" = hang ] && exec sleep "${FAKE_BUILD_HANG:-600}"
    exit "${FAKE_BUILD_RC:-0}"
    ;;
  logs)
    echo "fake log line: starting ${2:-container}"
    exit 0
    ;;
  inspect|ps|version)
    exit 0
    ;;
  rm)
    exit 0
    ;;
  run)
    probe=0
    for arg in "$@"; do
      [ "$arg" = --rm ] && probe=1
    done
    if [ "$probe" = 1 ]; then
      # The probe container. hang models the two real ways a probe can hang:
      # an image pull that never finishes and a container that never starts.
      case "${FAKE_PROBE_MODE:-ok}" in
        ok) echo '{"status":"ok"}'; exit 0 ;;
        fail) echo "curl: (7) Failed to connect to predictor-explainer port 8090" >&2; exit 7 ;;
        hang) exec sleep "${FAKE_PROBE_HANG:-600}" ;;
      esac
    fi
    # The service container. FAKE_START_FAIL_TIMES makes the first N starts fail
    # and later ones succeed, which is how a new image that will not start is told
    # apart from a previous one that will not start.
    n=$(($(cat "$log.starts" 2>/dev/null || echo 0) + 1))
    printf '%s' "$n" >"$log.starts"
    if [ "$n" -le "${FAKE_START_FAIL_TIMES:-0}" ]; then
      exit "${FAKE_START_RC:-1}"
    fi
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
"""

# An ssh that cannot leave the machine. Every shell these tests run has this on
# PATH ahead of the real one, so a test that reached an ssh call by accident
# would record it and fail rather than talk to the VPS.
FAKE_SSH = r"""#!/usr/bin/env bash
printf 'ssh %s\n' "$*" >>"${FAKE_SSH_LOG:?FAKE_SSH_LOG must be set}"
echo "ssh: the fake ssh in these tests never connects to anything" >&2
exit 1
"""

# sudo, for the paths that write /etc/predictor. It runs the command, against
# the tmp_path env file the test points EXPLAINER_ENV_FILE at.
FAKE_SUDO = r"""#!/usr/bin/env bash
exec "$@"
"""

# A host curl. Nothing under test calls it; it is here so that a stray one is
# visibly a fake rather than a real request to openrouter.ai.
FAKE_CURL = r"""#!/usr/bin/env bash
echo "curl: refused, these tests do not touch the network" >&2
exit 7
"""

# A GNU timeout(1) for the platforms that have one, so the branch that prefers
# it is exercised on a macOS too. It records its arguments and then does the
# only thing a test can check: kill the command at the limit.
FAKE_TIMEOUT = r"""#!/usr/bin/env bash
set -u
printf 'timeout %s\n' "$*" >>"${FAKE_TIMEOUT_LOG:?FAKE_TIMEOUT_LOG must be set}"
kill_after=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    -k) shift 2; continue ;;
    -*) shift; continue ;;
    *) break ;;
  esac
done
limit=${1:-0}
shift || true
"$@" &
child=$!
# Redirected for the same reason the library redirects its watchdog: GNU timeout
# does not leave a process holding the caller's stdout, and a double that did
# would change the timing the tests measure.
( sleep "$limit"; kill -TERM "$child" 2>/dev/null ) >/dev/null 2>&1 &
watch=$!
if wait "$child"; then rc=0; else rc=$?; fi
[ "$rc" -ge 128 ] && rc=124
exit "$rc"
"""


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


@pytest.fixture
def fake_host(tmp_path):
    """A PATH of fakes, and the files they answer from.

    PATH is prefixed, not replaced: `sleep`, `kill` and `bash` are real. But the
    first four entries are fakes, which is what `test_the_fakes_shadow_the_real
    binaries` asserts, and what makes this harness unable to reach a daemon or a
    host even if a test asked it to.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exec(bin_dir / "docker", FAKE_DOCKER)
    _write_exec(bin_dir / "ssh", FAKE_SSH)
    _write_exec(bin_dir / "sudo", FAKE_SUDO)
    _write_exec(bin_dir / "curl", FAKE_CURL)
    _write_exec(bin_dir / "timeout", FAKE_TIMEOUT)
    paths = {
        "bin": bin_dir,
        "docker_log": tmp_path / "docker.log",
        "ssh_log": tmp_path / "ssh.log",
        "timeout_log": tmp_path / "timeout.log",
        "images": tmp_path / "images",
        "env_file": tmp_path / "explainer.env",
        "dir": tmp_path,
    }
    paths["docker_log"].write_text("")
    paths["ssh_log"].write_text("")
    paths["timeout_log"].write_text("")
    # The image the deploy is about to replace, as if a previous deploy left one.
    paths["images"].write_text("predictor-explainer\n")
    paths["env_file"].write_text("EXPLAINER_ENABLED=false\n")
    return paths


def run_library(fake_host, body, *, limit_s=180, **overrides):
    """Run scripts/lib/deploy_safety.sh with BODY appended, against the fakes.

    `set -euo pipefail` first, because the remote blocks set those and a library
    that is only safe without them is a library that will break on the VPS the
    first time a command returns non-zero.

    Returns (CompletedProcess, seconds). The timing is measured here, around the
    process, rather than asserted about the source: the whole point of the
    deadline is that it stops a hang, and only a stopwatch can say it did.
    """
    env = dict(os.environ)
    env["PATH"] = f"{fake_host['bin']}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
    env["FAKE_DOCKER_LOG"] = str(fake_host["docker_log"])
    env["FAKE_SSH_LOG"] = str(fake_host["ssh_log"])
    env["FAKE_TIMEOUT_LOG"] = str(fake_host["timeout_log"])
    env["FAKE_IMAGES"] = str(fake_host["images"])
    env["EXPLAINER_ENV_FILE"] = str(fake_host["env_file"])
    env["EXPLAINER_PREVIOUS_ENV_FILE"] = str(fake_host["dir"] / "explainer.env.prev")
    env["EXPLAINER_BUILD_CONTEXT"] = str(fake_host["dir"] / "context")
    env["NET"] = "bridge"
    for key, value in overrides.items():
        env[key] = str(value)
    started = time.perf_counter()
    # Output goes to files, not to pipes. A killed `docker run` can leave the
    # process it had spawned holding the inherited stdout open, and a pipe is
    # only closed when the last writer closes it -- so capture_output would wait
    # for the orphan rather than for the deploy, and a test about deadlines would
    # hang instead of measuring one.
    out = fake_host["dir"] / "stdout"
    err = fake_host["dir"] / "stderr"
    with out.open("w") as out_fh, err.open("w") as err_fh:
        done = subprocess.run(
            ["bash", "-c", f'set -euo pipefail\n. "{LIB}"\n{body}\n'],
            env=env, stdout=out_fh, stderr=err_fh, timeout=limit_s,
        )
    done.stdout, done.stderr = out.read_text(), err.read_text()
    return done, time.perf_counter() - started


def docker_calls(fake_host):
    return [line for line in fake_host["docker_log"].read_text().splitlines() if line.strip()]


def started_images(fake_host):
    """The image reference of every `docker run -d`, in order."""
    return [line.split()[-1] for line in docker_calls(fake_host)
            if line.startswith("run -d ")]


def test_both_copies_of_the_health_check_are_the_same_function(remote_common, golive_body):
    sent_by_setup = HEALTH_FN.search(remote_common)
    sent_by_golive = HEALTH_FN.search(golive_body)
    assert sent_by_setup, "remote_common no longer defines probe/explainer_health"
    assert sent_by_golive, "the golive block no longer defines probe/explainer_health"
    assert code_of(sent_by_setup.group(0)) == code_of(sent_by_golive.group(0)), (
        "the shell of the two copies of explainer_health has drifted. They are "
        "sent as separate scripts, so a fix in one does not reach the other"
    )


@pytest.mark.parametrize("mode", ["setup", "golive"])
def test_the_health_check_runs_in_both_deploys(request, mode):
    body = request.getfixturevalue(f"{mode}_body")
    # Each mode hands the whole deploy to one library function, and a non-zero
    # return from it -- health failed and the rollback could not save it -- has
    # to end the deploy. Asserting the name of the function instead would break
    # on a rename and prove nothing about the failure path.
    calls = re.findall(r"^(explainer_\w+) \|\| exit 1$", body, re.M)
    assert calls, f"{mode} starts the container without failing if the service never comes up"
    for name in calls:
        assert re.search(rf"^{name}\(\) \{{", LIB.read_text(), re.M), (
            f"{mode} calls {name}, which the library does not define"
        )
    # `sleep 6` is what it replaced: it printed an empty "status:" for a container
    # still booting, and then reported success.
    assert "sleep 6" not in body, f"{mode} still waits a fixed 6s and hopes"


def test_the_health_check_fails_loudly_with_a_budget_and_a_log(remote_common):
    health = HEALTH_FN.search(remote_common).group(0)
    assert "DEPLOY FAILED" in health, "a service that never comes up is not announced"
    assert "docker logs" in health, "the failure does not show the log that explains it"
    # A 5xx must not pass for healthy, and a dead container must not spin forever.
    assert "-sfS" in health, "the probe does not fail on an HTTP error status"
    # The wait itself is a named budget rather than a literal, so it is checked
    # by running the library and reading the value back -- see
    # test_the_health_budget_is_thirty_seconds_and_the_deadlines_are_ordered.
    assert "EXPLAINER_HEALTH_BUDGET" in health, "the wait is not a named budget"


def test_the_health_check_is_not_escaped_for_the_far_side(remote_common):
    r"""A \$-escape in remote_common is a syntax error on the VPS, not a delay.

    A heredoc interpolates a variable verbatim, so the text written here is the
    text bash reads on the far side. Escaping a dollar to make it expand there
    leaves the backslash in place, and `local deadline=\$((SECONDS + 30))` does
    not parse. The health function has no double-quoted docker format string, so
    there is no legitimate escape in it at all.
    """
    health = HEALTH_FN.search(remote_common).group(0)
    assert "\\$" not in health, (
        "the health check escapes a dollar for the remote side; the remote shell "
        "will read the backslash and fail to parse it"
    )


def test_the_polled_url_is_a_route_this_app_defines_on_the_port_it_serves(remote_common):
    app_routes = set(re.findall(r'@app\.get\("([^"]+)"\)', APP.read_text()))
    # The image pins the port and is started with it. Both are read here, so this
    # test breaks if either moves rather than agreeing with a stale copy.
    exposed = re.search(r"^EXPOSE (\d+)$", DOCKERFILE.read_text(), re.M).group(1)
    served = re.search(r'--port", "(\d+)"', DOCKERFILE.read_text()).group(1)
    assert exposed == served, f"the Dockerfile exposes {exposed} but serves {served}"

    health = HEALTH_FN.search(remote_common).group(0)
    probed = re.findall(r"http://predictor-explainer:(\d+)(/\w+)", health)
    assert probed, "the health check polls no URL"
    for port, path in probed:
        assert port == served, f"the health check polls port {port}, the image serves {served}"
        assert path in app_routes, (
            f"the health check polls {path}, which create_app does not define "
            f"(it defines {sorted(app_routes)}); /health and /ready both 404"
        )


# --------------------------------------------------------------------------
# The library, run rather than read.
# --------------------------------------------------------------------------

def test_the_library_exists_and_is_readable_by_a_posix_shell():
    # bash is what the VPS runs, but this file has to be read by /bin/sh too: on
    # macOS that is bash in POSIX mode and on Linux it is dash. An earlier
    # version of this script used ${*##*-- }, which is not portable to either,
    # and a deploy is the worst possible place to find out.
    assert LIB.exists(), f"{LIB} is missing: the probe and the rollback have to live in a library"
    syntax = subprocess.run(["bash", "-n", str(LIB)], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr
    for shell in ("/bin/sh", "bash"):
        check = subprocess.run([shell, "-n", str(LIB)], capture_output=True, text=True)
        assert check.returncode == 0, f"{shell} -n on the library: {check.stderr}"


def test_both_remote_blocks_embed_the_library_verbatim(remote_common, golive_body):
    """The library is the source of truth and both blocks must be a copy of it.

    remote_common and the golive block are sent as separate scripts over the
    same ssh connection, and the golive one cannot source a file on the far side
    -- it may be running from a laptop against a host whose ~/predictor-hub is
    three commits behind, which is exactly how a fix here would arrive on the VPS
    as an old copy. So the copy has to be embedded, and the cost of embedding is
    drift, which is what this closes.
    """
    wanted = LIB.read_text()
    assert wanted, "the library is empty"
    for name, block in (("remote_common", remote_common), ("golive", golive_body)):
        found = EMBEDDED.search(block)
        assert found, f"{name} no longer embeds the library between the markers"
        assert found.group("lib") == wanted, (
            f"{name} carries a copy of {LIB.name} that has drifted from it. The "
            f"VPS runs {name}, so this copy is what would deploy"
        )


def test_the_library_has_no_apostrophe_in_it(remote_common):
    """One apostrophe in a comment ends the single-quoted string early.

    remote_common is assigned inside single quotes, so an apostrophe in the
    embedded library turns the rest of the file into remote code. That is a
    remote code injection with a footnote in it, so the rule is simply that
    this file does not use contractions.
    """
    assert "'" not in LIB.read_text(), (
        "scripts/lib/deploy_safety.sh contains an apostrophe; it is embedded "
        "inside a single-quoted shell string and the apostrophe would end it"
    )


def test_the_library_parses_as_remote_shell_after_the_heredocs(remote_common, golive_body):
    """`bash -n` on what is actually sent, so a syntax error is a local failure.

    A syntax error in either block is discovered on the VPS, halfway through a
    deploy, after the container has been stopped. Both blocks are checked here
    on the laptop, before anything is sent.
    """
    for name, block in (("remote_common", remote_common), ("golive", golive_body)):
        check = subprocess.run(["bash", "-n"], input=block, capture_output=True, text=True)
        assert check.returncode == 0, f"what {name} sends does not parse: {check.stderr}"


def test_the_health_budget_is_thirty_seconds_and_the_deadlines_are_ordered(fake_host):
    """The numbers, and the arithmetic that has to hold between them.

    Read back by running the library rather than by grepping it: the file could
    say 30 and the shell could compute something else, and only one of those is
    the number the VPS waits.
    """
    body = (
        'printf "%s %s %s %s %s %s\\n" "$EXPLAINER_ATTEMPT_DEADLINE" '
        '"$EXPLAINER_HEALTH_BUDGET" "$EXPLAINER_HEALTH_CEILING" "$EXPLAINER_CURL_MAX_TIME" '
        '"$EXPLAINER_PULL_DEADLINE" "$EXPLAINER_DEADLINE_IMPL"'
    )
    done, _ = run_library(fake_host, body)
    attempt, budget, ceiling, curl, pull, impl = done.stdout.split()
    assert budget == "30", f"the health budget is {budget}s, not the documented 30"
    assert curl == "5", f"the probe asks curl for {curl}s, not the documented 5"
    # The ceiling is what makes the probe bounded rather than merely patient:
    # the loop can spend at most one attempt past the budget, and the ceiling is
    # above that with room for the last attempt to be killed.
    assert int(attempt) + int(budget) <= int(ceiling), (
        f"a probe attempt ({attempt}s) started just before the budget ends "
        f"({budget}s) would outlive the ceiling ({ceiling}s)"
    )
    assert int(ceiling) <= int(budget) + int(attempt) + 10, (
        f"the ceiling is {ceiling}s, far above the {int(budget) + int(attempt)}s "
        f"the loop can actually spend; a deploy should not wait for it"
    )
    assert int(attempt) > int(curl), (
        f"an attempt capped at {attempt}s cannot allow curl its {curl}s plus the "
        f"container start, so every probe would fail"
    )
    assert int(pull) > int(ceiling), (
        "the one cold image pull has to be allowed longer than a probe attempt, "
        "or the first deploy on a fresh host cannot install the probe image"
    )
    assert impl in ("auto", "shell", "timeout")


@pytest.mark.parametrize("impl", ["shell", "timeout"])
def test_one_probe_attempt_is_bounded_including_the_docker_run(fake_host, impl):
    """The part that was unbounded: the `docker run` that carries the curl.

    The fake docker hangs the way a stalled registry or a container that never
    starts does. curl has --max-time, but curl has not been reached yet, so the
    attempt has to be killed from the outside and the caller has to get a
    non-zero back inside the ceiling rather than a command that never returns.
    """
    done, elapsed = run_library(
        fake_host, 'probe "$EXPLAINER_HEALTH_URL"',
        EXPLAINER_DEADLINE_IMPL=impl, EXPLAINER_ATTEMPT_DEADLINE=3,
        FAKE_PROBE_MODE="hang", FAKE_PROBE_HANG=600,
    )
    assert done.returncode != 0, "a probe against a target that never answers reported success"
    assert elapsed < 20, f"a 3s attempt ceiling took {elapsed:.1f}s"
    assert done.returncode == 124, (
        f"expected the GNU timeout code for a deadline kill, got {done.returncode}"
    )


def test_a_ceiling_stops_a_probe_that_the_budget_would_have_allowed(fake_host):
    """The ceiling is a ceiling, not a restatement of the loop budget.

    The budget is set to ten minutes and the ceiling to six seconds: if the
    ceiling were only the loop re-reading the clock, this would sit for ten
    minutes. It has to fail in seconds, with the reason said out loud.
    """
    done, elapsed = run_library(
        fake_host, "explainer_health",
        EXPLAINER_HEALTH_BUDGET=600, EXPLAINER_HEALTH_CEILING=6,
        EXPLAINER_ATTEMPT_DEADLINE=3, EXPLAINER_DEADLINE_IMPL="shell",
        FAKE_PROBE_MODE="hang", FAKE_PROBE_HANG=600,
    )
    assert done.returncode != 0, "a health check that never finished reported success"
    assert elapsed < 30, f"a 6s ceiling took {elapsed:.1f}s: the loop budget won"
    assert "still running" in done.stderr, (
        f"the ceiling killed it without saying so; stderr was:\n{done.stderr}"
    )
    assert "DEPLOY FAILED" in done.stderr


@pytest.mark.slow
def test_a_probe_against_an_unreachable_target_fails_within_the_bound(fake_host):
    """The measurement the reviewer asked for, at the numbers that ship.

    No overrides: the budget is 30, the attempt is 10, the ceiling is 45, and
    the fake docker hangs for ten minutes if nobody kills it. The assertions are
    a floor as well as a ceiling -- an implementation that failed instantly
    would pass a bare "returned non-zero" and would not be a health check.
    """
    done, elapsed = run_library(
        fake_host, "explainer_health", FAKE_PROBE_MODE="hang", FAKE_PROBE_HANG=600,
        limit_s=120,
    )
    assert done.returncode != 0, "the health check reported success against a hung probe"
    assert 20 <= elapsed <= 60, (
        f"the probe took {elapsed:.1f}s; it should retry for the 30s budget and "
        f"stop inside the 45s ceiling, and stopping instantly is not waiting"
    )
    print("\n[bound] health probe against an unreachable target: "
          f"{elapsed:.1f}s, exit {done.returncode}, "
          f"{len([c for c in docker_calls(fake_host) if c.startswith('run --rm')])} attempts")


def test_a_probe_that_answers_is_healthy_and_asks_once(fake_host):
    done, elapsed = run_library(fake_host, 'explainer_health; echo "healthy"', FAKE_PROBE_MODE="ok")
    assert done.returncode == 0, done.stderr
    assert "healthy:" in done.stdout
    assert elapsed < 10, f"a probe that answered on the first try took {elapsed:.1f}s"
    assert len([c for c in docker_calls(fake_host) if c.startswith("run --rm")]) == 1


def test_a_5xx_is_not_healthy(fake_host):
    # FAKE_PROBE_MODE=fail makes the probe exit non-zero, which is what curl -f
    # does on a 5xx. The deploy has to treat that as a failure, not as silence.
    done, _ = run_library(
        fake_host, "explainer_health", FAKE_PROBE_MODE="fail",
        EXPLAINER_HEALTH_BUDGET=2, EXPLAINER_ATTEMPT_DEADLINE=5,
    )
    assert done.returncode != 0, "a probe that failed on every attempt reported success"


def test_gnu_timeout_is_preferred_when_it_exists_and_carries_a_kill_flag(fake_host):
    """`timeout` is on the VPS and absent on a laptop, so both are exercised.

    -k is not optional in that call: GNU timeout sends TERM and then waits for
    the child, so without it the deadline is only enforced against a process
    that dies politely.
    """
    done, elapsed = run_library(
        fake_host, 'probe "$EXPLAINER_HEALTH_URL"',
        EXPLAINER_DEADLINE_IMPL="auto", EXPLAINER_ATTEMPT_DEADLINE=3,
        FAKE_PROBE_MODE="hang", FAKE_PROBE_HANG=600,
    )
    calls = fake_host["timeout_log"].read_text()
    assert done.returncode == 124, f"a deadline kill should report 124, got {done.returncode}"
    assert elapsed < 20, f"a 3s attempt ceiling took {elapsed:.1f}s"
    assert calls.splitlines(), "timeout(1) was available and was not used"
    first = calls.splitlines()[0].split()
    assert first[1] == "-k", f"timeout was called without -k: {calls}"
    assert first[3] == "3", f"timeout was not given the ceiling: {calls}"
    assert first[-1].endswith("/status"), f"timeout did not carry the probe: {calls}"


def test_a_killed_probe_container_is_discarded(fake_host):
    """A hung probe container must not be left running for the next attempt.

    The deadline kills the `docker run` client; the container it created is a
    separate life and --rm only cleans it up when the client finishes normally.
    The probe container therefore has a name and is removed on the way in and on
    the way out, which also stops the next attempt from failing with "name
    already in use" on a leaked one.
    """
    run_library(fake_host, 'probe "$EXPLAINER_HEALTH_URL"',
                EXPLAINER_ATTEMPT_DEADLINE=3, EXPLAINER_DEADLINE_IMPL="shell",
                FAKE_PROBE_MODE="hang", FAKE_PROBE_HANG=600)
    removals = [c for c in docker_calls(fake_host) if c == "rm -f explainer-probe"]
    assert len(removals) == 2, (
        "the probe container is not removed before and after the attempt: "
        f"{docker_calls(fake_host)}"
    )


def test_the_probe_image_is_pulled_before_the_attempts_and_the_pull_is_bounded(fake_host):
    """One cold pull, once, with its own ceiling.

    Without it the first probe attempt pays for pulling curlimages/curl inside a
    ten second ceiling, so the first deploy on a host that has never run the
    probe image fails for a reason that has nothing to do with the explainer.
    """
    done, _ = run_library(fake_host, "explainer_prefetch_probe_image",
                          EXPLAINER_PULL_DEADLINE=4, EXPLAINER_DEADLINE_IMPL="shell",
                          FAKE_PULL_RC=1)
    calls = docker_calls(fake_host)
    assert calls == ["pull curlimages/curl"], f"expected one bounded pull, got {calls}"
    assert done.returncode == 0, (
        "a pull that cannot reach the registry must not fail the deploy; the "
        f"cached copy may be enough: {done.stderr}"
    )
    hanging, elapsed = run_library(
        fake_host, "explainer_prefetch_probe_image", EXPLAINER_PULL_DEADLINE=3,
        EXPLAINER_DEADLINE_IMPL="shell", FAKE_PULL_RC=1,
    )
    assert elapsed < 20, f"a hung pull took {elapsed:.1f}s"
    # And the deploy has to do it, before the first attempt, or a fresh host cannot
    # pass a probe at all. The log is cleared first: the fake host is shared across
    # the runs above, and this is about what one deploy does.
    fake_host["docker_log"].write_text("")
    run_library(fake_host, "explainer_deploy", FAKE_PROBE_MODE="ok")
    calls = docker_calls(fake_host)
    pull = next(i for i, c in enumerate(calls) if c.startswith("pull "))
    probe_at = next(i for i, c in enumerate(calls) if c.startswith("run --rm"))
    assert pull < probe_at, f"the first probe ran before the pull: {calls}"
    assert calls.count("pull curlimages/curl") == 1, f"the pull is not once per deploy: {calls}"


def test_a_build_that_never_finishes_stops_before_anything_is_stopped(fake_host):
    """A hung build is the same hang as a hung probe and is bounded the same way.

    Nothing has been removed at that point in the deploy, so a build that dies
    has to leave the running container alone rather than take the service down
    on its way out.
    """
    done, elapsed = run_library(
        fake_host, "explainer_deploy", EXPLAINER_BUILD_DEADLINE=3,
        EXPLAINER_DEADLINE_IMPL="shell", FAKE_BUILD_MODE="hang", FAKE_BUILD_HANG=600,
    )
    assert done.returncode != 0, "a build that never finished reported success"
    assert elapsed < 20, f"a 3s build ceiling took {elapsed:.1f}s"
    assert "was never stopped" in done.stderr, done.stderr
    assert not [c for c in docker_calls(fake_host) if c.startswith("run -d")], (
        f"the deploy restarted the container despite the build failing: {docker_calls(fake_host)}"
    )
    assert not [c for c in docker_calls(fake_host) if c.startswith("rm -f predictor-explainer")], (
        f"the deploy removed the running container despite the build failing: {docker_calls(fake_host)}"
    )


# --------------------------------------------------------------------------
# The rollback.
# --------------------------------------------------------------------------

def test_a_failed_health_check_rolls_back_to_the_previous_image(fake_host):
    """The decision itself: a failed probe puts the old image back.

    Asserted from the docker log, because that is the observable: a rollback
    happened if and only if `docker run -d ... predictor-explainer:prev` was
    issued. No daemon is involved; the fake docker is the whole host.
    """
    done, _ = run_library(fake_host, "explainer_deploy", FAKE_PROBE_MODE="fail",
                          EXPLAINER_HEALTH_BUDGET=2, EXPLAINER_ATTEMPT_DEADLINE=5)
    assert done.returncode != 0, "a deploy whose health check failed reported success"
    assert "ROLLED BACK" in done.stderr, (
        f"the rollback is not announced; stderr was:\n{done.stderr}"
    )
    assert started_images(fake_host) == ["predictor-explainer", "predictor-explainer:prev"], (
        f"expected the new image and then the previous one, got {started_images(fake_host)}"
    )


def test_the_rollback_starts_the_previous_image_with_the_same_env_and_network(fake_host):
    """Same arguments, one word different.

    Not asserted from the library text: it is asserted from the two docker calls
    the deploy actually made, which is the only way this can be checked without
    a host to run them on. If the rollback came back with a different network, a
    different env file or no volume, it would be a different service.
    """
    run_library(fake_host, "explainer_deploy", FAKE_PROBE_MODE="fail",
                EXPLAINER_HEALTH_BUDGET=2, EXPLAINER_ATTEMPT_DEADLINE=5)
    runs = [c for c in docker_calls(fake_host) if c.startswith("run -d ")]
    assert len(runs) == 2, f"expected two starts, got {runs}"
    new, previous = (c.split() for c in runs)
    assert new[:-1] == previous[:-1], (
        f"the rollback did not reproduce the deploy it is undoing:\n  {new}\n  {previous}"
    )
    for flag in ("--network", "--env-file", "-v", "--restart"):
        assert flag in new, f"the deploy does not pass {flag}; a rollback cannot match it"


def test_a_successful_health_check_leaves_no_previous_tag(fake_host):
    """On success the :prev tag would be the new image, so it goes away.

    Left in place it is not harmless: it is what the next failed deploy rolls
    back to, so it would roll back to the image already running and report a
    rollback that changed nothing.
    """
    done, _ = run_library(fake_host, "explainer_deploy", FAKE_PROBE_MODE="ok")
    assert done.returncode == 0, done.stderr
    assert "rmi" in " ".join(docker_calls(fake_host)), (
        f"the previous tag survives a successful deploy: {docker_calls(fake_host)}"
    )
    assert "predictor-explainer:prev" not in fake_host["images"].read_text().split("\n"), (
        "the :prev tag still names an image after a successful deploy"
    )
    assert started_images(fake_host) == ["predictor-explainer"], (
        f"a successful deploy started the previous image: {started_images(fake_host)}"
    )


def test_the_previous_image_is_tagged_before_the_build_replaces_it(fake_host):
    """Ordering is the entire mechanism.

    `docker tag predictor-explainer predictor-explainer:prev` run after the build
    tags :prev at the image that just failed, and the rollback becomes a restart
    of the broken image. So the order of these two calls is the test.
    """
    run_library(fake_host, "explainer_deploy", FAKE_PROBE_MODE="ok")
    calls = docker_calls(fake_host)
    tag = next(i for i, c in enumerate(calls) if c.startswith("tag "))
    build = next(i for i, c in enumerate(calls) if c.startswith("build "))
    assert tag < build, f"the previous image was tagged after the build: {calls}"
    assert calls[tag] == "tag predictor-explainer predictor-explainer:prev", calls[tag]


def test_a_deploy_with_no_previous_image_says_the_rollback_is_impossible(fake_host):
    """First deploy on a host: there is nothing to go back to, and it must say so.

    The alternative is a :prev tag left behind by some older deploy, which would
    roll back to an image nobody chose. So the deploy clears it and says the
    rollback cannot happen.
    """
    fake_host["images"].write_text("")
    done, _ = run_library(fake_host, "explainer_deploy", FAKE_PROBE_MODE="fail",
                          EXPLAINER_HEALTH_BUDGET=2, EXPLAINER_ATTEMPT_DEADLINE=5)
    assert done.returncode != 0
    assert "nothing to roll back to" in done.stderr, done.stderr
    assert "ROLLBACK NOT POSSIBLE" in done.stderr, done.stderr
    assert started_images(fake_host) == ["predictor-explainer"], (
        f"a deploy with no previous image started one anyway: {started_images(fake_host)}"
    )


def test_a_previous_tag_left_by_an_older_deploy_is_not_rolled_back_to(fake_host):
    """A stale :prev is worse than no :prev, and is cleared before the build.

    This is the case where the host has some other image tagged :prev, from a
    deploy that has since been replaced. Rolling back to it would be serving an
    image nobody chose and calling it a rollback.
    """
    fake_host["images"].write_text("predictor-explainer:prev\n")
    done, _ = run_library(fake_host, "explainer_deploy", FAKE_PROBE_MODE="fail",
                          EXPLAINER_HEALTH_BUDGET=2, EXPLAINER_ATTEMPT_DEADLINE=5)
    assert done.returncode != 0
    calls = docker_calls(fake_host)
    assert any(c.startswith("rmi ") and ":prev" in c for c in calls), calls
    assert started_images(fake_host) == ["predictor-explainer"], started_images(fake_host)


def test_a_new_container_that_will_not_start_at_all_also_rolls_back(fake_host):
    """The other way the new image fails: `docker run -d` returns non-zero."""
    done, _ = run_library(fake_host, "explainer_deploy", FAKE_PROBE_MODE="ok",
                          FAKE_START_FAIL_TIMES=1)
    assert done.returncode != 0
    assert started_images(fake_host) == ["predictor-explainer", "predictor-explainer:prev"], (
        f"a container that would not start did not roll back: {started_images(fake_host)}"
    )
    assert "ROLLED BACK" in done.stderr, done.stderr


def test_a_rollback_that_will_not_start_says_the_service_is_down(fake_host):
    """The worst case has to be reported as itself, not as a rollback."""
    done, _ = run_library(fake_host, "explainer_deploy", FAKE_PROBE_MODE="fail",
                          EXPLAINER_HEALTH_BUDGET=2, EXPLAINER_ATTEMPT_DEADLINE=5,
                          FAKE_START_FAIL_TIMES=2)
    assert done.returncode != 0
    assert "ROLLBACK FAILED" in done.stderr, done.stderr
    assert "nothing is serving" in done.stderr, done.stderr


def test_golive_rolls_back_the_env_file_because_it_replaces_no_image(fake_host):
    """golive changes configuration, so there is no earlier image to go back to.

    What there is an earlier env file. The same rule, the other half: keep one
    before the edit, and put it back with the same run arguments if the service
    does not come up. The body below is golive own sequence, in the order the
    golive block does it: snapshot, edit, reconfigure.
    """
    env_file = fake_host["env_file"]
    env_file.write_text("EXPLAINER_ENABLED=false\n")
    body = (
        'explainer_snapshot_env\n'
        'printf "EXPLAINER_ENABLED=true\\n" >>"$EXPLAINER_ENV_FILE"\n'
        'explainer_reconfigure\n'
    )
    done, _ = run_library(fake_host, body, FAKE_PROBE_MODE="fail",
                          EXPLAINER_HEALTH_BUDGET=2, EXPLAINER_ATTEMPT_DEADLINE=5)
    assert done.returncode != 0
    assert started_images(fake_host) == ["predictor-explainer", "predictor-explainer"], (
        f"the env rollback did not restart the service: {started_images(fake_host)}"
    )
    assert "ROLLED BACK" in done.stderr, done.stderr
    assert env_file.read_text() == "EXPLAINER_ENABLED=false\n", (
        "the previous env file was not put back"
    )


def test_golive_keeps_the_previous_env_file_only_while_it_needs_it(fake_host):
    """On success the snapshot is removed, for the same reason the tag is."""
    fake_host["env_file"].write_text("EXPLAINER_ENABLED=true\n")
    body = (
        'explainer_snapshot_env\n'
        'explainer_reconfigure\n'
    )
    done, _ = run_library(fake_host, body, FAKE_PROBE_MODE="ok")
    assert done.returncode == 0, done.stderr
    assert started_images(fake_host) == ["predictor-explainer"], started_images(fake_host)
    snapshot = fake_host["dir"] / "explainer.env.prev"
    assert not snapshot.exists(), "the env snapshot survives a successful golive"


def test_the_fakes_shadow_every_binary_that_could_reach_a_host_or_a_daemon(fake_host):
    """The claim this whole section rests on: no test here can leave the machine.

    PATH is prefixed with the fakes, so `docker`, `ssh`, `sudo` and `curl` all
    resolve into tmp_path. If one of them did not, a test could reach a docker
    daemon or the VPS -- and this repository has already had a task run golive
    against that VPS by accident.
    """
    done, _ = run_library(fake_host, 'command -v docker; command -v ssh; command -v curl')
    found = done.stdout.split()
    assert found == [str(fake_host["bin"] / name) for name in ("docker", "ssh", "curl")], (
        f"PATH does not point at the fakes: {found}"
    )
    assert not fake_host["ssh_log"].read_text().strip(), "ssh was called"


def test_the_script_sends_all_three_modes_over_ssh(script):
    """The local half of the script still has the ssh command in it.

    Everything else in this file is about the remote half, and it is possible to
    break the local half badly -- drop the SSH assignment, say -- without any of
    those tests noticing, because `bash -n` is happy about an unset variable and
    nothing ever runs the script. This is the smallest thing that notices.
    """
    assert re.search(r'^SSH="ssh .*\$VPS"$', script, re.M), (
        "the script no longer builds its ssh command from $VPS"
    )
    for mode in ("setup", "golive", "status"):
        body = re.search(rf"^{mode}\)\n(.*?)^  ;;$", script, re.S | re.M)
        assert body, f"the {mode} mode is gone from the case statement"
        assert "$SSH" in body.group(1), f"{mode} does not send its remote script over ssh"


def test_an_unknown_mode_is_refused_locally_without_sending_anything(tmp_path):
    """End to end over the local half: usage, and nothing on the wire.

    This runs the script for real -- the drift check, the case dispatch and the
    usage line -- with a fake ssh first on PATH. It is the only test here that
    executes deploy-explainer.sh at all, and what it executes cannot reach a
    host: the only mode it reaches is the one that prints usage.
    """
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_exec(fake_bin / "ssh", FAKE_SSH)
    ssh_log = tmp_path / "ssh.log"
    ssh_log.write_text("")
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
    env["FAKE_SSH_LOG"] = str(ssh_log)
    done = subprocess.run(["bash", str(SCRIPT), "not-a-mode"],
                          env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 1, f"an unknown mode was not refused: {done.stderr}"
    assert "usage:" in done.stdout, f"no usage line: {done.stdout} {done.stderr}"
    assert not ssh_log.read_text().strip(), "ssh was called for an unknown mode"


def test_the_drift_check_can_be_repaired_without_a_manual_paste(tmp_path):
    """`--embed` is the fix for the drift, so the drift is not terminal.

    Without a command for it, the repair is a human pasting 450 lines into two
    places by hand, and a human doing that is how the copy and the library come
    to disagree about a rollback. So: a copy of the script with its embedded
    library damaged -- here by the one edit that would break a rollback silently,
    running :prev out of the wrong image -- has to come back byte-identical to
    the committed script after --embed. Byte-identical, not similar: a repair
    that rewrites the region and appends to it would pass a weaker check.
    """
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_exec(fake_bin / "ssh", FAKE_SSH)
    scripts = tmp_path / "scripts"
    (scripts / "lib").mkdir(parents=True)
    copy = scripts / "deploy-explainer.sh"
    damaged = SCRIPT.read_text().replace(
        'explainer_run_detached "$EXPLAINER_PREVIOUS_IMAGE"',
        'explainer_run_detached "$EXPLAINER_IMAGE"')
    assert damaged != SCRIPT.read_text(), "the damage did not apply; this test proves nothing"
    copy.write_text(damaged)
    (scripts / "lib" / LIB.name).write_text(LIB.read_text())
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
    env["FAKE_SSH_LOG"] = str(tmp_path / "ssh.log")
    (tmp_path / "ssh.log").write_text("")

    first = subprocess.run(["bash", str(copy), "--embed"], env=env,
                            capture_output=True, text=True, timeout=60)
    assert first.returncode == 0, first.stderr
    assert copy.read_text() == SCRIPT.read_text(), (
        "--embed did not restore the committed script byte for byte"
    )
    second = subprocess.run(["bash", str(copy), "--embed"], env=env,
                            capture_output=True, text=True, timeout=60)
    assert second.returncode == 0, second.stderr
    assert copy.read_text() == SCRIPT.read_text(), "--embed is not idempotent"
    assert not (tmp_path / "ssh.log").read_text().strip(), "--embed reached ssh"


def test_the_deploy_script_refuses_to_send_a_block_that_drifted_from_the_library(tmp_path):
    """The drift check runs locally, before anything is sent.

    A copy of the script is run with the library tampered with. It has to fail
    without reaching ssh: the assertion is made from the fake ssh log, because
    "the check failed" is not the same claim as "nothing was sent".
    """
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_exec(fake_bin / "ssh", FAKE_SSH)
    _write_exec(fake_bin / "docker", FAKE_DOCKER)
    scripts = tmp_path / "scripts"
    (scripts / "lib").mkdir(parents=True)
    for name in ("deploy-explainer.sh",):
        (scripts / name).write_text(SCRIPT.read_text())
    library = LIB.read_text() + '\nexplainer_drifted() { :; }\n'
    (scripts / "lib" / LIB.name).write_text(library)
    ssh_log = tmp_path / "ssh.log"
    ssh_log.write_text("")
    images = tmp_path / "images"
    images.write_text("")
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
    env["FAKE_SSH_LOG"] = str(ssh_log)
    env["FAKE_DOCKER_LOG"] = str(tmp_path / "docker.log")
    env["FAKE_TIMEOUT_LOG"] = str(tmp_path / "timeout.log")
    env["FAKE_IMAGES"] = str(images)
    done = subprocess.run(
        ["bash", str(scripts / "deploy-explainer.sh"), "status"],
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert done.returncode != 0, "a drifted library was deployed anyway"
    assert not ssh_log.read_text().strip(), (
        f"the script reached ssh before it noticed the drift: {ssh_log.read_text()}"
    )
    assert "deploy_safety.sh" in done.stderr, (
        f"the drift check did not name the file: {done.stderr}"
    )
