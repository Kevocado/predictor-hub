"""The CI workflow has to keep up with the service it runs.

`.github/workflows/explainer-ci.yml` names the five site repositories it clones,
because 20 of the tests cannot be checked without a checkout of each site to
compare against (`test_factor_keys.py` and `test_unserved_sport.py` read
`origin/main:src/<sport>_predictor/api/facts.py` and fail loudly rather than skip
when it is missing). That list is a hand-written copy of the sports the service
serves, in a different file, in a different syntax -- which is the same shape of
staleness the rest of this service is careful about.

So: a sport added to `config.SERVED_SPORTS` and wired up everywhere else would
leave the workflow cloning four repos and quietly not checking the fifth. These
tests fail first, and name what to add.

The workflow's own steps are checked here too, because a workflow file has no
test of its own and a typo in it is invisible until a run is red.
"""
import re
from pathlib import Path

import pytest

from explainer.config import SERVED_SPORTS

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github/workflows/explainer-ci.yml"


@pytest.fixture(scope="module")
def workflow():
    assert WORKFLOW.exists(), f"{WORKFLOW} is missing; the suite runs on 3.11 in no workflow"
    return WORKFLOW.read_text()


def test_every_served_sport_is_cloned_by_the_workflow(workflow):
    """A sport the service serves but the workflow does not clone is unchecked."""
    # Read the clone list itself, not every mention of a repo name: the *_REPO
    # paths below name the same repos, and matching those would let a sport drop
    # out of SITE_REPOS unnoticed.
    env = re.search(r"SITE_REPOS:\s*(.+)", workflow)
    assert env, "the workflow has no SITE_REPOS list to clone from"
    listed = set(env.group(1).split())
    wanted = {f"{sport.upper()}_Predictor" for sport in SERVED_SPORTS}
    assert not (wanted - listed), (
        f"the workflow does not clone {sorted(wanted - listed)}; the tests that "
        f"cross-check {sorted(wanted - listed)} against their own site will fail "
        f"for want of a checkout rather than for what they check"
    )
    # The other direction matters too: a repo nobody serves is a clone that can
    # only slow the job down or fail on a rename.
    assert not (listed - wanted), (
        f"the workflow clones {sorted(listed - wanted)}, which the service does "
        f"not serve (SERVED_SPORTS is {sorted(SERVED_SPORTS)})"
    )


@pytest.mark.parametrize("sport", sorted(SERVED_SPORTS))
def test_every_served_sport_gets_its_repo_env_var(workflow, sport):
    assert re.search(rf"^\s*{sport.upper()}_REPO:", workflow, re.M), (
        f"the Tests step sets no {sport.upper()}_REPO, so that sport's "
        "cross-checks will not find a checkout"
    )


def test_the_suite_runs_on_311_and_not_on_whatever_the_runner_has(workflow):
    assert "uv python install 3.11" in workflow, "3.11 is not installed explicitly"
    # The test step specifically, not the file: `--python 3.11` also appears on
    # the install and compile steps, so a whole-file search would keep passing
    # after the one line that matters lost the pin. Letting uv choose here is
    # exactly how #37 shipped.
    test_step = re.search(r"^\s*run:.*pytest.*$", workflow, re.M)
    assert test_step, "the workflow has no step that runs pytest"
    assert "--python 3.11" in test_step.group(0), (
        f"the test step does not pin 3.11: {test_step.group(0).strip()!r}"
    )
    # The Docker image is the reason. If this drifts, the job stops testing what
    # ships, which is the whole failure this workflow exists to prevent.
    dockerfile = (REPO / "services/explainer/Dockerfile").read_text()
    assert re.search(r"^FROM python:3\.11", dockerfile, re.M), (
        "the image is no longer python 3.11, so the pin in the workflow needs "
        "revisiting rather than the workflow following the image silently"
    )


def test_the_compile_check_covers_every_tracked_file(workflow):
    step = re.search(r"python -m py_compile[^\n]*", workflow)
    assert step, "the workflow has no py_compile step"
    # find would walk .venv; git ls-files is exactly what is committed.
    assert "git ls-files" in step.group(0), (
        "py_compile is not driven by git ls-files, so the file list can drift "
        "from what is committed or walk .venv"
    )
    assert "find " not in step.group(0), "py_compile is walking the filesystem rather than the index"


def test_the_workflow_runs_on_pull_requests_and_main(workflow):
    assert re.search(r"^on:", workflow, re.M), "no trigger block"
    triggers = re.search(r"^on:\n(.*?)(?=^\S)", workflow, re.S | re.M).group(1)
    assert "pull_request" in triggers, "a green branch that nobody checks is the #37 failure again"
    assert re.search(r"branches:\s*\[main\]", triggers), "main is not covered"
