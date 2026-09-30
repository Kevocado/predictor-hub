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
loudly against a dead one -- is shell against docker, and is verified by running
both paths, not by this file.

These are the raw texts, before ssh. That is deliberate: the tests read what is
in the file, and whether the heredoc quoting survives expansion on the way to
the VPS is a separate question answered by running the script, not by a regex.
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/deploy-explainer.sh"
DOCKERFILE = REPO / "services/explainer/Dockerfile"
APP = REPO / "services/explainer/explainer/app.py"

HEALTH_FN = re.compile(r"^probe\(\).*?^explainer_health\(\) \{.*?^\}(?:\n|\Z)", re.S | re.M)


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
    assert "explainer_health || exit 1" in body, (
        f"{mode} starts the container without failing if the service never comes up"
    )
    # `sleep 6` is what it replaced: it printed an empty "status:" for a container
    # still booting, and then reported success.
    assert "sleep 6" not in body, f"{mode} still waits a fixed 6s and hopes"


def test_the_health_check_fails_loudly_with_a_budget_and_a_log(remote_common):
    health = HEALTH_FN.search(remote_common).group(0)
    assert "SECONDS + 30" in health, "the wait is not bounded at 30 seconds"
    assert "DEPLOY FAILED" in health, "a service that never comes up is not announced"
    assert "docker logs" in health, "the failure does not show the log that explains it"
    # A 5xx must not pass for healthy, and a dead container must not spin forever.
    assert "-sfS" in health, "the probe does not fail on an HTTP error status"


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
