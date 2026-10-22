"""Two guards on the rules themselves.

The first says the committed gate cannot be lowered. The second says this package
cannot grow the ability to place an order or hold a credential. Both exist because
the failure they catch is invisible in a passing test suite: a gate nobody
remembers lowering still reports numbers, and an order-placing path in a package
whose whole claim is "this is paper" would make every row in it untrustworthy.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from conftest import config

from paper.segments import (SEGMENTS_PATH, MIN_SETTLED_FLOOR, MIN_SETTLED_GAMES_FLOOR, load)

PACKAGE = Path(__file__).resolve().parents[1] / "paper"
COMMITTED = Path(__file__).resolve().parents[3] / SEGMENTS_PATH


def test_the_committed_gate_is_not_below_the_floor():
    """A gate that can be lowered by an edit is not a gate."""
    committed = load(COMMITTED)
    assert committed["gate"]["min_settled"] >= MIN_SETTLED_FLOOR, (
        f"min_settled was lowered below {MIN_SETTLED_FLOOR}; the gate may be raised, "
        "never lowered, and lowering it needs a deliberate change to this test too"
    )


def test_the_committed_game_floor_is_not_below_the_floor():
    """The second floor, on GAMES, cannot be lowered either.

    A Kalshi ladder is many contracts on one game, so the 300-BET floor can be
    met by about twenty-five games of evidence. This floor is what stops that,
    and it is the same kind of guard as the bet floor: it may be raised, never
    lowered, and lowering it needs a deliberate change to this test too.
    """
    committed = load(COMMITTED)
    assert committed["gate"]["min_settled_games"] >= MIN_SETTLED_GAMES_FLOOR, (
        f"min_settled_games was lowered below {MIN_SETTLED_GAMES_FLOOR}; the gate may "
        "be raised, never lowered, and lowering it needs a deliberate change to this test too"
    )


def test_the_edge_threshold_is_the_pre_stated_four_points():
    """Pre-stated, not tuned. If this is ever swept on the data it is applied to,
    the sweep belongs in an exploratory section, not in this file."""
    assert load(COMMITTED)["edge_threshold_points"] == 4.0


def test_the_gate_cannot_be_switched_off_in_the_committed_config():
    gate = load(COMMITTED)["gate"]
    assert gate["require_ci_excludes_zero"] is True
    assert gate["require_calibration_not_widening"] is True


def test_the_allow_list_still_covers_the_segments_the_brief_names():
    names = {e["segment"] for e in load(COMMITTED)["segments"]}
    assert {"nfl:receptions", "nba:moneyline", "cfb:total"} <= names


def test_every_allow_list_entry_explains_itself():
    """Each entry says something about its own availability, so a reader does not
    have to work out why a listed segment has never logged a row."""
    for entry in load(COMMITTED)["segments"]:
        assert entry.get("note"), f"{entry['segment']} has no note explaining its state"


# --- paper only ---------------------------------------------------------------

FORBIDDEN = {
    "order placement": r"\b(place_order|submit_order|create_order|/orders\b|POST\s+.*orders)",
    "credentials": r"\b(api_key|api_secret|private_key|secret_key|bearer_token|password)\b",
    "trading enable switch": r"\b(live_trading|enable_trading|kill_switch|assert_live)\b",
}


def test_the_paper_package_contains_no_order_placement_or_credential_code():
    """The strongest claim this PR makes is "paper only", so it is checked in CI
    rather than asserted in a description."""
    for path in sorted(PACKAGE.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        # Strip the module docstring: prose about what is forbidden is fine.
        body = re.sub(r'^""".*?"""', "", text, flags=re.DOTALL)
        for what, pattern in FORBIDDEN.items():
            assert not re.search(pattern, body, re.IGNORECASE), f"{path.name}: {what}"


def test_the_paper_package_opens_no_socket():
    """Reads committed files, writes two of its own, and stops.

    `backtest.py` is the one exception: a backtest has to fetch Kalshi's own
    settled history, and there is no committed copy of it. It is the only file
    in the package that imports `requests`, and it is not on the live path.
    """
    for path in sorted(PACKAGE.glob("*.py")):
        if path.name == "backtest.py":
            continue
        text = path.read_text(encoding="utf-8")
        for banned in ("import socket", "import urllib", "import http",
                       "requests", "httpx", "urlopen"):
            assert banned not in text, f"{path.name} reaches the network via {banned}"


def test_no_order_or_credential_code_anywhere_in_this_pr():
    """The scripts the brief names are the other way in, so they are checked too."""
    scripts = Path(__file__).resolve().parents[3] / "scripts"
    for path in sorted(scripts.glob("paper_*.py")):
        text = path.read_text(encoding="utf-8")
        for what, pattern in FORBIDDEN.items():
            assert not re.search(pattern, text, re.IGNORECASE), f"{path.name}: {what}"


def test_the_fixture_config_agrees_with_the_committed_gate():
    """The tests build their own allow-list; it must not be laxer than the real one."""
    assert config()["gate"]["min_settled"] >= MIN_SETTLED_FLOOR
    assert config()["gate"]["min_settled_games"] >= MIN_SETTLED_GAMES_FLOOR
    assert config()["edge_threshold_points"] == json.loads(
        COMMITTED.read_text())["edge_threshold_points"]
