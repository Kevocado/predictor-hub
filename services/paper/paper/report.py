"""The segment report: does any market actually have an edge after fees?

Prints one row per segment and writes the same numbers to `data/paper/report.json`.

The gate, exactly as the brief states it. A segment may be called "has an edge"
only when ALL of:

  * at least 300 settled paper bets in that segment,
  * a paired bootstrap confidence interval on mean pnl whose LOWER bound is above
    zero — not merely one that excludes zero, since a segment which lost all 300
    of its bets also excludes zero, and
  * a calibration gap that is not widening.

None of the three can be waived, and there is no override flag. The first run
will almost certainly print "no" for everything, and that is the expected and
correct result: the interesting claim is the one the data refuses to support,
and a report that says so is the product working.

CLOSING-LINE VALUE is reported next to pnl because pnl is noisy and CLV is not:
CLV asks whether we found the price before the market did, which is the part of
the edge that should persist. Positive pnl with negative CLV is luck.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import segments as segments_mod
from . import sources, stats
from .ledger import KIND_CANDIDATE, KIND_SHADOW, STATUS_SETTLED, Ledger, resolved

REPORT_PATH = Path("data/paper/report.json")


def _won(row: dict) -> bool:
    return row.get("outcome") == "yes"


def summarise(rows: list[dict], *, closing: dict[str, dict], gate_cfg: dict,
              force_no: str | None = None) -> dict:
    """Every number the report prints for one segment."""
    settled = [r for r in rows if r.get("status") == STATUS_SETTLED]
    outcomes = [1 if _won(r) else 0 for r in settled]

    pnls = [float(r.get("pnl_per_contract") or 0.0) for r in settled]
    stakes = [float(r.get("stake") or 0.0) for r in settled]
    staked = sum(stakes)

    realised_edge = None
    if settled:
        # What the bets were actually worth, against what we claimed they were
        # worth: (hit rate - mean model_p) in points. Compare against the edge we
        # logged; the gap between them is the model's calibration, not its edge.
        realised_edge = round((sum(outcomes) / len(outcomes)
                               - stats.fmean(r["model_p"] for r in settled)) * 100.0, 4)

    ci = stats.bootstrap_mean_ci(pnls)
    trend = stats.calibration_trend(settled, min_n=gate_cfg["min_for_calibration_trend"])
    clvs = [v for v in (stats.clv_points(r, closing) for r in settled) if v is not None]

    reasons: list[str] = []
    if force_no:
        reasons.append(force_no)
    if len(settled) < gate_cfg["min_settled"]:
        reasons.append(f"only {len(settled)} settled bets, need {gate_cfg['min_settled']}")
    if gate_cfg["require_ci_excludes_zero"]:
        if ci is None:
            reasons.append("no settled bets to put an interval on")
        elif not stats.is_profitable(ci):
            # Named separately from "includes zero" because a segment that lost
            # money consistently fails here while its interval still excludes
            # zero, and printing "includes zero" for that would be a lie.
            verdict = ("includes zero" if stats.excludes_zero(ci) is False
                       else "is entirely below zero")
            reasons.append(f"pnl interval [{ci[0]:.4f}, {ci[1]:.4f}] {verdict}")
    if gate_cfg["require_calibration_not_widening"]:
        if not trend["measurable"]:
            reasons.append(f"calibration trend needs {trend['min_n']} settled bets, have {trend['n_settled']}")
        elif trend["widening"]:
            reasons.append(f"calibration gap widening ({trend['gap_early']:.2f} -> {trend['gap_late']:.2f} pts)")

    return {
        "n_logged": len(rows),
        "n_settled": len(settled),
        "n_open": len(rows) - len(settled),
        "n_void": sum(1 for r in rows if r.get("status") == "void"),
        "hit_rate": round(sum(outcomes) / len(outcomes), 4) if outcomes else None,
        "mean_model_p": round(stats.fmean(r["model_p"] for r in settled), 4) if settled else None,
        "mean_market_price": round(stats.fmean(r["market_price"] for r in settled), 4) if settled else None,
        "mean_edge_points": round(stats.fmean(r["edge"] for r in settled), 4) if settled else None,
        "realised_edge_points": realised_edge,
        "mean_clv_cents": round(stats.fmean(clvs), 4) if clvs else None,
        "n_clv": len(clvs),
        "calibration_gap_points": (round(trend["gap_late"], 4) if trend["measurable"]
                                   else stats.calibration_gap(
                                       [r["model_p"] for r in settled], outcomes)),
        "calibration_trend": trend,
        "pnl": round(sum(pnls), 4),
        "staked": round(staked, 4),
        "roi": round(sum(pnls) / staked, 4) if staked else None,
        "pnl_ci95": [round(ci[0], 4), round(ci[1], 4)] if ci else None,
        "max_drawdown": round(stats.max_drawdown(pnls), 4),
        "qualifies_for_edge_claim": not reasons,
        "disqualifying": reasons,
    }


def build(rows: list[dict], *, closing: dict[str, dict], gate_cfg: dict) -> dict:
    by_segment: dict[str, list[dict]] = {}
    for row in rows:
        by_segment.setdefault(row["segment"], []).append(row)
    table = {
        name: summarise(bucket, closing=closing, gate_cfg=gate_cfg,
                        force_no=None if any(r.get("kind") != KIND_SHADOW for r in bucket)
                        else "shadow rows carry no stake and cannot support an edge claim")
        for name, bucket in sorted(by_segment.items())
    }
    return {
        "schema_version": 1,
        "gate": gate_cfg,
        "totals": {
            "n_logged": len(rows),
            "n_settled": sum(1 for r in rows if r.get("status") == STATUS_SETTLED),
            "n_candidates": sum(1 for r in rows if r.get("kind") != KIND_SHADOW),
            "n_shadow": sum(1 for r in rows if r.get("kind") == KIND_SHADOW),
            "segments": len(table),
            "segments_qualifying": sum(1 for v in table.values() if v["qualifies_for_edge_claim"]),
        },
        "segments": table,
    }


def render(report: dict) -> str:
    """The printed table. Fixed width, no dependency on a table library."""
    header = (f"{'segment':<26} {'n':>5} {'settled':>7} {'hit':>6} {'model_p':>8} {'price':>6} "
              f"{'edge':>7} {'real.':>7} {'clv':>7} {'pnl':>9} {'roi':>7} {'dd':>7} {'edge?':>6}")
    lines = [
        "paper-trading segment report — PAPER ONLY, no orders, no credentials",
        f"gate: >= {report['gate']['min_settled']} settled bets AND bootstrap CI on pnl "
        f"entirely above zero AND calibration gap not widening",
        "",
        header,
        "-" * len(header),
    ]

    def num(value, fmt="{:.4f}", width=None):
        return "—" if value is None else fmt.format(value)

    for name, s in sorted(report["segments"].items()):
        lines.append(
            f"{name:<26} {s['n_logged']:>5} {s['n_settled']:>7} {num(s['hit_rate'], '{:.3f}'):>6} "
            f"{num(s['mean_model_p']):>8} {num(s['mean_market_price']):>6} "
            f"{num(s['mean_edge_points'], '{:.2f}'):>7} {num(s['realised_edge_points'], '{:.2f}'):>7} "
            f"{num(s['mean_clv_cents'], '{:+.2f}'):>7} {s['pnl']:>9.2f} {num(s['roi'], '{:+.3f}'):>7} "
            f"{s['max_drawdown']:>7.3f} {('yes' if s['qualifies_for_edge_claim'] else 'no'):>6}"
        )
    if not report["segments"]:
        lines.append("(no segments: the ledger is empty)")
    totals = report["totals"]
    lines += [
        "",
        f"{totals['n_logged']} rows logged ({totals['n_candidates']} candidates, "
        f"{totals['n_shadow']} shadow), {totals['n_settled']} settled, "
        f"{totals['segments_qualifying']}/{totals['segments']} segments qualify for an edge claim.",
    ]
    for name, s in sorted(report["segments"].items()):
        if s["disqualifying"]:
            lines.append(f"  {name}: " + "; ".join(s["disqualifying"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", default="data/paper/ledger.jsonl")
    parser.add_argument("--segments", default="data/paper/segments.json")
    parser.add_argument("--sites-root", default=None,
                        help="directory holding the sibling site checkouts")
    parser.add_argument("--lines", nargs="*", default=None,
                        help="Kalshi line .jsonl.gz files to read closing prices from")
    parser.add_argument("--out", default=str(REPORT_PATH))
    args = parser.parse_args(argv)

    config = segments_mod.load(args.segments)
    ledger = Ledger(args.ledger)
    rows = resolved(ledger)

    files = [Path(p) for p in args.lines] if args.lines else []
    if not files:
        from .sources import discover_sites_root, SITE_FOR_SPORT
        root = args.sites_root or discover_sites_root()
        if root:
            for sport in sorted(set(SITE_FOR_SPORT.values())):
                files.extend(sources.lines_files(root, sport))
    closing = stats.closing_prices(stats.annotate_observed(sources.read_line_files(files)))

    report = build(rows, closing=closing, gate_cfg=segments_mod.gate(config))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(render(report))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
