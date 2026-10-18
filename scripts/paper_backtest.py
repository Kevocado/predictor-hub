#!/usr/bin/env python3
"""Run the paper candidate rule over Kalshi's own settled history. EXPLORATORY.

Writes data/paper/backtest.jsonl (never data/paper/ledger.jsonl). Every row is
flagged exploratory. See services/paper/paper/backtest.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "paper"))

from paper.backtest import main

if __name__ == "__main__":
    sys.exit(main())
