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
import shutil
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

# FAKE_DOCKER_NO_GROUP models the VPS login user exactly. That user is not in the
# docker group, so the bare binary on PATH answers permission denied and exits
# 126 to everything. The remote block notices this at its first line --
# `docker ps ... || docker() { command sudo docker "$@"; }` -- and from then on
# `docker` is a shell FUNCTION that goes through sudo, not the program on PATH.
#
# This is the shape every other test here mocks wrongly. Set it and the fakes put
# the harness in the same shape as the host: bare docker fails, sudo docker works,
# and a deadline wrapper that cannot call a function has nothing to call.
if [ "${FAKE_DOCKER_NO_GROUP:-0}" = 1 ] && [ -z "${FAKE_DOCKER_VIA_SUDO:-}" ]; then
  echo "permission denied while trying to connect to the Docker daemon socket" >&2
  exit 126
fi

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
    # `docker inspect -f FORMAT NAME` prints a field. The golive block reads the
    # network name out of one and fails on an empty answer, so the fake has to print
    # something: a fake host that cannot say what network it is on is not shaped like
    # the host the block was written for. Only for the -f form; a bare `inspect` is
    # used for its exit status and prints nothing, which is also what the real one
    # does when the format string asks for no fields.
    for arg in "$@"; do
      if [ "$arg" = -f ]; then
        printf '%s\n' "${FAKE_NETWORK:-bridge}"
        break
      fi
    done
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
#
# It also records what it was asked to run. That log is what proves a command
# went through the sudo wrapper rather than straight to the binary, which on the
# VPS is the whole difference between a deploy that works and one that dies with
# permission denied.
FAKE_SUDO = r"""#!/usr/bin/env bash
printf 'sudo %s\n' "$*" >>"${FAKE_SUDO_LOG:-/dev/null}"
# Mark the environment so the fake docker can tell sudo docker from bare docker.
# The real host tells them apart by uid, and the two take different paths: only
# one of them is allowed to reach the daemon socket.
FAKE_DOCKER_VIA_SUDO=1 exec "$@"
"""

# A host curl. Nothing under test calls it; it is here so that a stray one is
# visibly a fake rather than a real request to openrouter.ai.
FAKE_CURL = r"""#!/usr/bin/env bash
echo "curl: refused, these tests do not touch the network" >&2
exit 7
"""

# A sed that accepts `sed -i EXPR FILE`, which is GNU sed and is what the golive
# block writes. BSD sed, which is what ships on a macOS, reads the argument after
# -i as a backup suffix and fails on the expression instead, so on this platform the
# golive block dies in a way it cannot die on the VPS -- and the test would report a
# broken block rather than a platform difference. This translates to the local form
# and delegates to the real sed, so the edit is still a real edit to a real tmp_path
# file and only the flag syntax is adapted.
FAKE_SED = r"""#!/usr/bin/env bash
set -u
args=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    -i) shift; args+=("-i" ""); continue ;;
    -i*) suffix=${1#-i}; shift; args+=("-i" "$suffix"); continue ;;
    *) args+=("$1"); shift; continue ;;
  esac
done
exec /usr/bin/sed "${args[@]}"
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

    PATH is prefixed, not replaced: `sleep`, `kill`, `bash`, `tee`, `cp` and `rm` are
    real. The entries in front are fakes, which is what
    `test_the_fakes_shadow_every_binary_that_could_reach_a_host_or_a_daemon` asserts,
    and what makes this harness unable to reach a daemon or a host even if a test asked
    it to. `sed` is here for a platform reason rather than a safety one, and says so in
    its own comment: it exists so the golive block can run its in-place edit the way
    the VPS runs it rather than dying on BSD sed flag syntax.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exec(bin_dir / "docker", FAKE_DOCKER)
    _write_exec(bin_dir / "ssh", FAKE_SSH)
    _write_exec(bin_dir / "sudo", FAKE_SUDO)
    _write_exec(bin_dir / "curl", FAKE_CURL)
    _write_exec(bin_dir / "timeout", FAKE_TIMEOUT)
    _write_exec(bin_dir / "sed", FAKE_SED)
    paths = {
        "bin": bin_dir,
        "docker_log": tmp_path / "docker.log",
        "ssh_log": tmp_path / "ssh.log",
        "sudo_log": tmp_path / "sudo.log",
        "timeout_log": tmp_path / "timeout.log",
        "images": tmp_path / "images",
        "env_file": tmp_path / "explainer.env",
        "dir": tmp_path,
    }
    paths["docker_log"].write_text("")
    paths["ssh_log"].write_text("")
    paths["sudo_log"].write_text("")
    paths["timeout_log"].write_text("")
    # The image the deploy is about to replace, as if a previous deploy left one.
    paths["images"].write_text("predictor-explainer\n")
    paths["env_file"].write_text("EXPLAINER_ENABLED=false\n")
    return paths


_PIPEFAIL_CACHE = {}


def _bash4_or_newer():
    """A bash that is not the macOS system bash, or None.

    The system bash on macOS is 3.2 and it has a bug that matters here exactly:
    when a shell function whose first command is `command <external>` is invoked
    with `&`, bash 3.2 EXECs into that external and the rest of the function body
    is silently discarded. No error, no message. The remote block defines
    `docker() { command sudo docker "$@"; }`, which is precisely that shape, and
    the library runs its commands with `&` -- so under bash 3.2 the watchdog runs
    `docker build`, the sudo wrapper execs, and every line after that call in the
    function is gone. A test asserts on output that never arrives and reports the
    library as broken when the library is fine.

    bash 4, bash 5, dash and ksh93 all run it correctly, and the VPS is Linux with
    a current bash, so the harness prefers any of those. Verified rather than
    assumed: the probe below runs the failing shape and checks the tail arrives, so
    a machine with no usable bash falls back to `/bin/bash` and the tests behave the
    way the platform behaves rather than the way the VPS does.
    """
    probe = 'd() { command true; echo TAIL; }\nd & wait\n'
    for candidate in ("/opt/homebrew/bin/bash", "/usr/local/bin/bash", "/bin/bash"):
        path = shutil.which(candidate) or (candidate if os.path.exists(candidate) else None)
        if not path:
            continue
        check = subprocess.run([path, "-c", probe], capture_output=True, text=True)
        if check.returncode == 0 and "TAIL" in check.stdout:
            return path
    return None


# Resolved once. A missing modern bash is not fatal: the suite then runs on whatever
# bash the machine has and the section that depends on this documents the difference.
GOOD_BASH = _bash4_or_newer() or "bash"


def _supports_pipefail(shell):
    """Whether this shell accepts `set -o pipefail`, asked once per shell.

    dash has no pipefail and exits on the attempt, so the harness cannot simply
    assume it. Probed by running it, not by reading its name: several shells on this
    list alias each other and the answer has varied across macOS releases.
    """
    if shell not in _PIPEFAIL_CACHE:
        check = subprocess.run([shell, "-c", "set -o pipefail"],
                               capture_output=True, text=True)
        _PIPEFAIL_CACHE[shell] = check.returncode == 0
    return _PIPEFAIL_CACHE[shell]


def run_library(fake_host, body, *, limit_s=180, shell=None, **overrides):
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
    env["FAKE_SUDO_LOG"] = str(fake_host["sudo_log"])
    env["FAKE_TIMEOUT_LOG"] = str(fake_host["timeout_log"])
    env["FAKE_IMAGES"] = str(fake_host["images"])
    env["EXPLAINER_ENV_FILE"] = str(fake_host["env_file"])
    env["EXPLAINER_PREVIOUS_ENV_FILE"] = str(fake_host["dir"] / "explainer.env.prev")
    env["EXPLAINER_BUILD_CONTEXT"] = str(fake_host["dir"] / "context")
    env["NET"] = "bridge"
    # GOOD_BASH by default, because of the bash 3.2 bug documented on
    # _bash4_or_newer: it would silently truncate every block that calls a function
    # starting with `command`, which is every one of them on this host.
    shell = shell or GOOD_BASH
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
        # `set -euo pipefail` is what the remote blocks use, but pipefail is not
        # POSIX: dash rejects it outright and the shell dies before it reads a line
        # of the library. The shells that do not have it get `set -eu`, which is the
        # part that is actually load-bearing here.
        strict = "set -euo pipefail" if _supports_pipefail(shell) else "set -eu"
        done = subprocess.run(
            [shell, "-c", f'{strict}\n. "{LIB}"\n{body}\n'],
            env=env, stdout=out_fh, stderr=err_fh, timeout=limit_s,
        )
    done.stdout, done.stderr = out.read_text(), err.read_text()
    return done, time.perf_counter() - started


def docker_calls(fake_host):
    return [line for line in fake_host["docker_log"].read_text().splitlines() if line.strip()]


def sudo_calls(fake_host):
    """Every command that reached the daemon THROUGH sudo, in docker-log shape.

    This is the observable that separates the VPS failure from a working deploy.
    On the host, `docker` is a function that wraps `sudo docker`, so a build that
    reaches the daemon at all is a build that went through sudo. A build that ran
    the bare binary -- which is what happens when a deadline wrapper execs `docker`
    instead of calling it -- never appears here, and on the real host it dies with
    "permission denied while trying to connect to the Docker daemon socket".

    The fake sudo records `sudo <argv>`, so the leading `sudo ` is stripped and the
    entries read the same way `docker_calls` does. That way a test can write the same
    predicate against both logs -- `docker build` reached the wrapper or it did not --
    rather than one test matching "sudo docker build" and another matching
    "build -q", which is a difference in spelling and not in behaviour.
    """
    lines = (line for line in fake_host["sudo_log"].read_text().splitlines() if line.strip())
    return [line[len("sudo "):] if line.startswith("sudo ") else line for line in lines]


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
    r"""The claim this whole section rests on: no test here can leave the machine.

    PATH is prefixed with the fakes, so `docker`, `ssh`, `sudo` and `curl` all
    resolve into tmp_path. If one of them did not, a test could reach a docker
    daemon or the VPS -- and this repository has already had a task run golive
    against that VPS by accident.

    `command -v` is not the check for that, and it is worth saying why because it is
    the obvious one. For a FUNCTION it prints the bare word `docker`, not a path: the
    shell has a thing called docker, and that is all `command -v` reports. So it
    answers "does this name exist", which is not the question. The question is which
    FILE a bare exec of the name would open, and `type -P` is the one that answers it
    -- it ignores functions entirely and prints the PATH entry, or nothing at all when
    the name is not a file. `type -t` alongside it says which KIND it is, which is the
    distinction this whole file turns on and the one `command -v` cannot express.

    That is the same check the production code now uses, in explainer_path_of and
    explainer_resolve_kind, and it is the check a reviewer should read the library
    with: `type -P` for the file, `type -t` for the kind, and never `command -v`.
    """
    done, _ = run_library(
        fake_host,
        'type -P docker; type -P ssh; type -P curl; type -P sudo; '
        'printf "KIND=%s\\n" "$(type -t docker)"',
    )
    found = done.stdout.split()
    # docker is a PROGRAM here -- no remote block has run -- so type -P answers for
    # all four and the kinds line confirms the premise rather than the fakes.
    wanted = [str(fake_host["bin"] / name) for name in ("docker", "ssh", "curl", "sudo")]
    wanted.append("KIND=file")
    assert found == wanted, f"PATH does not point at the fakes: {found}"
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


def test_a_shell_function_named_docker_is_what_the_deadline_wrapper_runs(fake_host):
    """The VPS user is not in the docker group, so the remote block defines
    `docker() { sudo docker "$@"; }`. `timeout` execs a PROGRAM and cannot call a
    function, so `timeout 900 docker build` silently ran the bare binary and failed
    with "permission denied" -- reported as "did not finish within 900s". Every
    other test here mocks `docker` as a program, which is exactly why none saw it.
    This one makes `docker` a function and asserts the FUNCTION ran."""
    done, _ = run_library(
        fake_host,
        'docker() { echo FUNCTION-WRAPPER-USED; }\n'
        'explainer_within 20 docker build -t x .\n',
        EXPLAINER_DEADLINE_IMPL="auto",
    )
    assert done.returncode == 0, done.stderr
    assert "FUNCTION-WRAPPER-USED" in done.stdout, (
        "explainer_within ran the docker PROGRAM instead of the shell function: "
        f"stdout={done.stdout!r} stderr={done.stderr!r}")


def test_a_real_program_still_goes_through_timeout(fake_host):
    done, _ = run_library(fake_host, 'explainer_within 20 true\n', EXPLAINER_DEADLINE_IMPL="timeout")
    assert done.returncode == 0, done.stderr
    assert fake_host["timeout_log"].read_text().strip(), "a plain program no longer reaches timeout(1)"


# --------------------------------------------------------------------------
# The remote block on a host where docker is a FUNCTION.
#
# Everything above builds its own shell snippet. That is the gap this section
# closes: hub#61 passed every test in this file and then failed on the VPS, because
# these tests all mock `docker` as a PROGRAM on PATH while on the host `docker` is
#
#     docker() { command sudo docker "$@"; }
#
# `timeout(1)` execs a program. It cannot call a function, so on the VPS the
# deadline wrapper ran the bare binary, which is not in the docker group, which
# fails with permission denied -- reported, misleadingly, as a timeout. 655 tests
# were green because every one of them had a program where the host has a function.
#
# So these tests run the REAL remote block text, unmodified, out of the script file,
# against a fake docker that refuses to work unless it was reached through sudo.
# Nothing is hand-written here: if the block stops defining the wrapper, or the
# library stops being able to call one, these fail.
# --------------------------------------------------------------------------

def run_remote_block(fake_host, block, body, *, shell=None, limit_s=180, **overrides):
    """Run the actual remote block from the script, then BODY, against the fakes.

    This is the same environment `run_library` builds, but the shell it runs is the
    text the script SENDS -- `remote_common` verbatim, which includes its own
    `docker() { command sudo docker "$@"; }` definition and the embedded copy of the
    library. That is deliberate: the point is to run the shipped text in the shape
    the VPS runs it, and a test that sourced a hand-written copy would be testing
    the copy.

    The two blocks are not the same length and do not read the same way. remote_common
    is a preamble and ends at the library; the golive block goes on to read the API
    key and the two model names from stdin, rewrite the env file, and end in
    `explainer_reconfigure || exit 1`. So stdin is fed THREE empty lines, which is
    what "the operator pressed enter at each prompt" looks like. Three, not two: the
    third `read` hits EOF instead, and under `set -e` a read that returns non-zero
    ends the block -- which is the shell being correct, not the harness being wrong.

    No key is invented and none is written anywhere: the env file the golive block
    rewrites is the tmp_path one, and on a real run the key travels over ssh stdin
    only. What the block writes into it here is `OPENROUTER_API_KEY=` with nothing
    after it.

    Returns (CompletedProcess, seconds, shape) where `shape` is what the block left
    bound to the name `docker` -- "function", "file", or empty. A test that does not
    look at this can pass without ever having exercised a function, because on a host
    where the login user IS in the docker group the block leaves `docker` as the
    program and everything works. The check is `type -t`, which answers the KIND; see
    the note on test_the_fakes_shadow_every_binary_that_could_reach_a_host_or_a_daemon
    for why `command -v` is the wrong tool for this and `type -P` is the right one.
    """
    env = dict(os.environ)
    env["PATH"] = f"{fake_host['bin']}{os.pathsep}{os.environ.get('PATH', '/usr/bin:/bin')}"
    env["FAKE_DOCKER_LOG"] = str(fake_host["docker_log"])
    env["FAKE_SSH_LOG"] = str(fake_host["ssh_log"])
    env["FAKE_SUDO_LOG"] = str(fake_host["sudo_log"])
    env["FAKE_TIMEOUT_LOG"] = str(fake_host["timeout_log"])
    env["FAKE_IMAGES"] = str(fake_host["images"])
    env["EXPLAINER_ENV_FILE"] = str(fake_host["env_file"])
    env["EXPLAINER_PREVIOUS_ENV_FILE"] = str(fake_host["dir"] / "explainer.env.prev")
    env["EXPLAINER_BUILD_CONTEXT"] = str(fake_host["dir"] / "context")
    # The block resolves the sport containers and the network before the library
    # runs. Handing it the answers keeps those lookups out of the way so the test
    # measures the deadline wrapper, not the container-name guessing.
    env.setdefault("NET", "bridge")
    for name, value in (("NFL", "nfl-predictor:8001"), ("CFB", "cfb-predictor:8003"),
                        ("PL", "pl-predictor:8000"), ("NBA", "nba-predictor:8000"),
                        ("F1", "f1-predictor:8001")):
        env.setdefault(name, value)
    # The defining condition: this user is not in the docker group. Set here rather
    # than in the fixture so that every other test in this file keeps the host it
    # already had -- a user who can reach the daemon, where `docker` is a program.
    # The point of this section is the one host where that is not true.
    env["FAKE_DOCKER_NO_GROUP"] = "1"
    for key, value in overrides.items():
        env[key] = str(value)
    # GOOD_BASH, not plain "bash": see _bash4_or_newer. bash 3.2 execs into the sudo
    # wrapper and drops the rest of the block, so on a stock macOS these tests would
    # be asserting against a shell that does not exist on the VPS.
    shell = shell or GOOD_BASH
    script = f'{block}\nprintf "SHAPE:%s\\n" "$(type -t docker 2>/dev/null)"\n{body}\n'
    out = fake_host["dir"] / "stdout"
    err = fake_host["dir"] / "stderr"
    started = time.perf_counter()
    with out.open("w") as out_fh, err.open("w") as err_fh:
        done = subprocess.run([shell, "-c", script], env=env, input=b"\n\n\n",
                              stdout=out_fh, stderr=err_fh, timeout=limit_s)
    done.stdout, done.stderr = out.read_text(), err.read_text()
    shape = ""
    for line in done.stdout.splitlines():
        if line.startswith("SHAPE:"):
            shape = line.split(":", 1)[1].strip()
    return done, time.perf_counter() - started, shape


@pytest.mark.parametrize("mode", ["setup", "golive"])
def test_the_remote_block_leaves_docker_as_a_function_on_a_host_that_needs_sudo(
        request, fake_host, mode):
    """The premise, asserted before anything else uses it.

    The remote block's first act is `docker ps >/dev/null 2>&1 || docker() { command
    sudo docker "$@"; }`. On a host where the login user is not in the docker group
    the left side fails and the function is defined, and from that point on every
    `docker` in the library is a FUNCTION. If a test below does not check this, it
    can pass while exercising a program -- so it is checked here, for both blocks,
    against a fake docker that refuses to work unless it was reached through sudo.
    """
    block = request.getfixturevalue("remote_common" if mode == "setup" else "golive_body")
    # FAKE_PROBE_MODE=ok because the golive block does not stop after the library: it
    # runs `explainer_reconfigure || exit 1` and exits the whole shell if the service
    # does not come up, so a probe left in its default state fails the deploy and the
    # body below never runs. The probe is not what this test is about, so it is
    # answered immediately rather than waited out.
    done, _, shape = run_remote_block(
        fake_host, block,
        'explainer_within 20 docker build -q -t predictor-explainer "$EXPLAINER_BUILD_CONTEXT"',
        EXPLAINER_BUILD_MODE="ok", FAKE_PROBE_MODE="ok",
    )
    assert shape == "function", (
        f"the {mode} block left docker as {shape!r} rather than a shell function, so "
        f"this host is not shaped like the VPS and the tests below prove nothing. "
        f"stdout={done.stdout!r} stderr={done.stderr!r}"
    )
    assert any(c.startswith("docker build") for c in sudo_calls(fake_host)), (
        "the build did not go through the sudo wrapper, so docker was not a "
        f"function here after all: sudo log={sudo_calls(fake_host)} "
        f"docker log={docker_calls(fake_host)}"
    )
    assert not fake_host["ssh_log"].read_text().strip(), "ssh was called"


def test_the_deadline_wrapper_still_applies_when_docker_is_a_function(fake_host, remote_common):
    """The thing hub#61 got wrong, run in the shape that broke it.

    On the host, `docker` is a function wrapping `sudo docker`, and the build is
    given a 900s deadline. If the deadline wrapper execs `docker` instead of calling
    it, the bare binary runs, it is not in the docker group, and the deploy dies with
    permission denied -- which the wrapper then reports as a timeout. 655 tests did
    not catch that because they all mocked docker as a program.

    So this hangs the build, in a shell where docker really is a function, and
    asserts BOTH halves of the claim: the deadline bit (killed, ~the limit, not the
    600s hang), and the wrapper applied (the build reached sudo). Asserting only the
    first would pass on a bare `docker build` that failed instantly; asserting only
    the second would pass on an unbounded function call that hung forever.
    """
    done, elapsed, shape = run_remote_block(
        fake_host, remote_common, "explainer_deploy",
        EXPLAINER_BUILD_DEADLINE=3, EXPLAINER_DEADLINE_IMPL="auto",
        FAKE_BUILD_MODE="hang", FAKE_BUILD_HANG=600, EXPLAINER_PROBE_MODE="ok",
    )
    assert shape == "function", f"docker was {shape!r}, not a function: {done.stdout!r}"
    # Half one: the deadline actually stopped a hang. The build wanted 600s.
    assert done.returncode != 0, "a build that hung reported success"
    assert elapsed < 30, f"a 3s build deadline took {elapsed:.1f}s: the wrapper did not apply"
    assert not [c for c in docker_calls(fake_host) if c.startswith("run -d")], (
        f"the deploy restarted the container despite the build failing: {docker_calls(fake_host)}"
    )
    # Half two: it got there through the function, i.e. through sudo. This is the
    # assertion the mocked-as-a-program tests could not make.
    builds = [c for c in sudo_calls(fake_host) if c.startswith("docker build")]
    assert builds, (
        "the build did not go through sudo, so the deadline wrapper ran the bare "
        "docker program instead of calling the function. On the real host that is "
        f"permission denied, reported as a timeout. sudo={sudo_calls(fake_host)} "
        f"docker={docker_calls(fake_host)} stderr={done.stderr!r}"
    )
    # And nothing reached a host: these tests are hermetic, and the log is the proof.
    assert not fake_host["ssh_log"].read_text().strip(), "ssh was called"


def test_a_function_the_wrapper_cannot_exec_fails_loudly_rather_than_running_unbounded(fake_host):
    r"""The general rule, pinned: a wrapper built on exec degrades SILENTLY.

    `timeout(1)` -- and `exec`, and any wrapper that forks-and-execs -- resolves its
    target through PATH as a PROGRAM. A shell function, an alias and a builtin are
    not on PATH, so the wrapper does not run the command that was asked for; it runs
    a different one with the same name, or nothing. There is no error. That is the
    dangerous half: a deadline that silently stops applying looks exactly like a
    command that finished quickly.

    The production code therefore does not let the choice be silent. It works out
    what the first argument actually is and takes a path that can call it, and when
    it cannot classify the target at all it says so on stderr instead of guessing.
    """
    # A function: the shape the VPS has. `type -t` must classify it, and the
    # classification must be the one that routes to a caller rather than an execer.
    done, _ = run_library(
        fake_host,
        'docker() { echo VIA-FUNCTION; }\n'
        'printf "kind=%s\\n" "$(explainer_resolve_kind docker 2>&1)"\n'
        'explainer_within 20 docker build .\n',
        EXPLAINER_DEADLINE_IMPL="auto",
    )
    assert "kind=function" in done.stdout, (
        "the wrapper cannot tell a shell function from a program, so it cannot "
        f"choose a wrapper that can call one: stdout={done.stdout!r} stderr={done.stderr!r}"
    )
    assert "VIA-FUNCTION" in done.stdout, (
        f"the function was not called: stdout={done.stdout!r} stderr={done.stderr!r}"
    )
    # A builtin and an alias are the same class of problem and are classified the
    # same way. `true` is a builtin in every shell, so execvp finds /bin/true
    # instead -- it happens to work, which is exactly why the class is easy to miss.
    done, _ = run_library(
        fake_host,
        'printf "builtin=%s\\n" "$(explainer_resolve_kind true 2>&1)"\n',
    )
    assert "builtin=builtin" in done.stdout, (
        f"a builtin was not classified as one: stdout={done.stdout!r} stderr={done.stderr!r}"
    )
    # A real program is the one case where timeout(1) is correct, and it has to be
    # recognised as such or every deploy pays for the portable path.
    done, _ = run_library(
        fake_host,
        'printf "prog=%s\\n" "$(explainer_resolve_kind sleep 2>&1)"\n',
    )
    assert "prog=file" in done.stdout, (
        f"a program on PATH was not recognised: stdout={done.stdout!r} stderr={done.stderr!r}"
    )


def test_the_harness_is_not_measuring_a_shell_the_vps_does_not_have():
    """The harness bug that would have made this whole section lie.

    macOS ships bash 3.2, and bash 3.2 execs into the first command of a function
    invoked with `&` when that command is `command <external>`, discarding the rest
    of the body. The remote block defines `docker() { command sudo docker "$@"; }`
    and the library runs commands with `&`, so under bash 3.2 every block in this
    section is truncated at its first `command`: the tests would fail while the code
    was correct, and a later reader would go looking for a bug in the library.

    So the harness resolves its shell once, by running that shape and checking the
    tail arrives, and this asserts the resolved shell is one that passes. It is a
    test about the test suite, which is not a strange thing to have: the alternative
    is a green suite that means nothing on the platform it runs on.
    """
    probe = 'docker() { command true; echo TAIL; }\ndocker & wait\n'
    done = subprocess.run([GOOD_BASH, "-c", probe], capture_output=True, text=True)
    assert "TAIL" in done.stdout, (
        f"{GOOD_BASH} drops the rest of a function whose first command is `command` "
        f"when it is run with &, so this section would be measuring that and not the "
        f"library. Install a current bash, or run this suite on Linux. "
        f"stdout={done.stdout!r} stderr={done.stderr!r}"
    )
    version = subprocess.run([GOOD_BASH, "--version"], capture_output=True, text=True)
    assert "bash" in version.stdout.lower()


def test_the_classifier_works_on_every_shell_the_library_claims(fake_host):
    """`type -t` is a bashism, and the library is read by more than bash.

    This is the second half of the failure and the reason it went unnoticed. The
    merged fix classifies the target with `type -t`, which bash and ksh93 and dash
    do not all agree on: dash has no `-t` flag and prints an error, and ksh93 maps
    `type` to `whence` and rejects `-t`. On both, the classification comes back
    empty, the function is not recognised, and the wrapper goes to `timeout` -- which
    execs the bare program. The fix that was supposed to stop the VPS failure does
    not fire on two of the three shells this library is explicitly written for.

    So the classification is asserted in the shells that are present, and a shell
    that cannot classify a function fails the test rather than silently taking the
    timeout path. `type -t` in the assertion on purpose: it is the thing that was
    wrong, and this is where its absence is pinned.
    """
    snippet = (
        'docker() { echo VIA-FUNCTION; }\n'
        'printf "kind=%s\\n" "$(explainer_resolve_kind docker 2>/dev/null)"\n'
        'explainer_within 20 docker build .\n'
    )
    import shutil
    for shell in ("bash", "/bin/sh", "dash", "ksh"):
        path = shutil.which(shell) or (shell if os.path.exists(shell) else None)
        if not path:
            continue
        done, _ = run_library(fake_host, snippet, shell=path,
                              EXPLAINER_DEADLINE_IMPL="auto")
        if done.returncode == 126 or not done.stdout:
            continue  # this build of the shell cannot run the snippet at all
        assert "kind=function" in done.stdout, (
            f"{path} cannot classify a shell function (it said "
            f"{done.stdout!r}), so a deadline wrapper there execs the bare program "
            f"and the deploy runs without sudo: {done.stderr!r}"
        )
        assert "VIA-FUNCTION" in done.stdout, (
            f"{path} did not call the function: stdout={done.stdout!r} stderr={done.stderr!r}"
        )
        fake_host["timeout_log"].write_text("")


def test_an_unclassifiable_target_is_refused_loudly_not_guessed(fake_host):
    """The remaining case: the wrapper cannot tell what it was handed.

    A command that is not on PATH and not a function is not a thing the wrapper can
    run, whichever implementation it picks. The rule is that this is announced on
    stderr and refused, because the alternative -- handing it to `timeout` and
    letting execvp report "not found" -- is a message about a program, on a host
    where the failure was a function all along.
    """
    done, _ = run_library(
        fake_host,
        'explainer_within 5 definitely-not-a-command-on-this-host --flag\n',
        EXPLAINER_DEADLINE_IMPL="auto",
    )
    assert done.returncode != 0, "a command that does not exist reported success"
    assert "not a command" in done.stderr or "not found" in done.stderr, (
        f"the failure did not say the command does not exist: {done.stderr!r}"
    )


def test_no_test_in_this_file_can_reach_a_host_or_a_daemon(fake_host, remote_common):
    """The hermetic claim, restated against the section that runs the block.

    The block under test is the remote half of a deploy. Running it locally is safe
    only because the fakes are in front of it, so this asserts both directions: the
    fakes shadow the real binaries, and nothing reached ssh. If a future edit to the
    block ever calls something not on the fake PATH, this is the test that says so.
    """
    r"""Both halves, in the shape the VPS runs it.

    `type -P`, not `command -v`, for the reason given on the test above: the block
    has just defined docker as a function, so `command -v docker` prints the word
    "docker" and this assertion would be about a name rather than about a path. What
    has to hold here is that the PROGRAM under the function -- the file that a bare
    exec of the name would open -- is the fake, and that sudo and ssh, which are not
    wrapped, are the fakes too.
    """
    done, _, shape = run_remote_block(
        fake_host, remote_common,
        'type -P docker; type -P sudo; type -P ssh; printf "KIND=%s\\n" "$(type -t docker)"',
        FAKE_BUILD_MODE="ok",
    )
    assert shape == "function", (
        f"docker is {shape!r} rather than a function here, so this block is not shaped "
        f"like the VPS and the check below is about something else: {done.stdout!r}"
    )
    # The block echoes its own preamble (network=, NFL=, ...) before this body runs,
    # so the paths are read as the lines after it rather than the whole output.
    found = [line for line in done.stdout.splitlines() if line.startswith(str(fake_host["bin"]))]
    assert found == [str(fake_host["bin"] / name) for name in ("docker", "sudo", "ssh")], (
        f"the block resolved a real binary instead of a fake: {done.stdout!r}"
    )
    assert "KIND=function" in done.stdout, done.stdout
    assert not fake_host["ssh_log"].read_text().strip(), (
        f"running the remote block reached ssh: {fake_host['ssh_log'].read_text()}"
    )
