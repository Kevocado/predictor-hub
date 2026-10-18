#!/usr/bin/env python3
"""Log paper-trade candidates from the sites' Kalshi line snapshots. PAPER ONLY.

Thin entry point; the logic is in `services/paper/paper/log.py`. Run from the
repo root:  python3 scripts/paper_log.py --sites-root <dir with the site checkouts>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "paper"))

from paper.log import main  # noqa: E402 - the path has to be set first

if __name__ == "__main__":
    sys.exit(main())
