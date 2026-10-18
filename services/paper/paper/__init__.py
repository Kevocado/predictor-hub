"""Paper-trading ledger, settlement and segment report. PAPER ONLY.

No order placement, no credentials, no network. Everything here reads public
files that the sibling site repos commit, and writes an append-only JSONL ledger.
See `paper/log.py` for the no-hindsight rules and `paper/ledger.py` for why the
file is append-only.
"""
