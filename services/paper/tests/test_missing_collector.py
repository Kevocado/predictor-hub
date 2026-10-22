"""A missing collector must fail loudly, not skip the sport silently.

The ledger reads Kalshi ladders from the sibling site repos. If one of those
repos has no collector, the ledger logs the sports whose collectors ARE there
and silently omits the one whose is not -- and every count it reports is then
wrong in a way nothing shows. The reader sees "no markets today" where the
truth is "we never looked".

Three states, and only the middle one is an error:

  * the checkout is not there at all -- the clone failed;
  * the checkout is there with a collector workflow but no ladders yet -- the
    collector has not run, which is normal on its first day;
  * the checkout is there with neither -- there is no collector.
"""
from __future__ import annotations

import pytest

from paper import sources


def _site(root, name: str, *, lines: bool = False, workflow: bool = False) -> None:
    """Build a fake sibling checkout."""
    site = root / name
    site.mkdir(parents=True, exist_ok=True)
    if lines:
        (site / "data" / "lines").mkdir(parents=True, exist_ok=True)
    if workflow:
        wf = site / sources.COLLECTOR_WORKFLOW
        wf.parent.mkdir(parents=True, exist_ok=True)
        wf.write_text("name: Collect\n", encoding="utf-8")


def test_a_missing_checkout_is_a_missing_collector(tmp_path):
    assert sources.collector_present(tmp_path, "nfl") is False


def test_a_checkout_with_ladders_has_a_collector(tmp_path):
    _site(tmp_path, "NFL_Predictor", lines=True)
    assert sources.collector_present(tmp_path, "nfl") is True


def test_a_checkout_with_a_collector_workflow_but_no_ladders_yet_has_a_collector(tmp_path):
    # The collector's first run has not happened yet. That is normal, not an
    # error, and must not stop the other sports from being logged.
    _site(tmp_path, "CFB_Predictor", workflow=True)
    assert sources.collector_present(tmp_path, "cfb") is True


def test_a_checkout_with_neither_is_a_missing_collector(tmp_path):
    _site(tmp_path, "PL_Predictor")
    assert sources.collector_present(tmp_path, "pl") is False


def test_strict_lines_files_raises_on_a_missing_collector(tmp_path):
    _site(tmp_path, "PL_Predictor")
    with pytest.raises(sources.MissingCollector) as excinfo:
        sources.lines_files(tmp_path, "pl", strict=True)
    assert "pl" in str(excinfo.value)


def test_strict_lines_files_does_not_raise_on_a_collector_that_has_not_run(tmp_path):
    _site(tmp_path, "CFB_Predictor", workflow=True)
    assert sources.lines_files(tmp_path, "cfb", strict=True) == []


def test_an_empty_ladders_directory_is_not_an_error(tmp_path):
    # The collector ran and found no markets today. That is a real answer.
    _site(tmp_path, "NFL_Predictor", lines=True)
    assert sources.lines_files(tmp_path, "nfl", strict=True) == []


def test_the_lenient_default_is_unchanged(tmp_path):
    # Without `strict`, a missing collector is still an empty list: the old
    # callers keep their behaviour, and only the workflows opt into the error.
    _site(tmp_path, "PL_Predictor")
    assert sources.lines_files(tmp_path, "pl") == []


def test_check_collectors_raises_on_the_first_missing_one(tmp_path):
    _site(tmp_path, "NFL_Predictor", lines=True)
    _site(tmp_path, "PL_Predictor")
    with pytest.raises(sources.MissingCollector):
        sources.check_collectors(tmp_path, ["nfl", "pl"])


def test_check_collectors_passes_when_every_collector_is_there(tmp_path):
    _site(tmp_path, "NFL_Predictor", lines=True)
    _site(tmp_path, "PL_Predictor", lines=True)
    assert sources.check_collectors(tmp_path, ["nfl", "pl"]) == ["nfl", "pl"]


def test_the_log_job_refuses_to_run_without_every_collector(tmp_path, capsys):
    # The end-to-end shape: the logger is given a root where one sport's
    # collector is missing, and it must stop rather than log the rest.
    from paper.log import main
    _site(tmp_path, "NFL_Predictor", lines=True)
    _site(tmp_path, "PL_Predictor")   # no collector
    code = main(["--sites-root", str(tmp_path), "--sport", "nfl", "--sport", "pl",
                 "--ledger", str(tmp_path / "ledger.jsonl"),
                 "--segments", str(tmp_path / "segments.json"),
                 "--dry-run"])
    # 3 is the missing-collector exit code, distinct from 2 (no checkouts at
    # all) so the workflow can tell the two apart.
    assert code == 3
    assert "missing" in capsys.readouterr().err.lower()
