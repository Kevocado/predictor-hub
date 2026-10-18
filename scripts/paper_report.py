#!/usr/bin/env python3
"""Print the per-segment paper-trading report and write data/paper/report.json.

PAPER ONLY. Reads the append-only ledger plus the sites' public Kalshi line
snapshots; writes one JSON file. Places no orders and reads no credentials.

    python3 scripts/paper_report.py --sites-root <dir with the site checkouts>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "paper"))

from paper.report import main  # noqa: E402 - the path has to be set first

if __name__ == "__main__":
    sys.exit(main())
