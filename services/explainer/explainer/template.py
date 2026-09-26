"""The fallback when no model is available, over budget, or its output fails
validation: plain sentences built only from the facts."""
from __future__ import annotations

_TENS = ["none", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
_START = {"f1": "the session started", "pl": "kickoff"}


def _pct(p: float) -> str:
    if p <= 0.005:
        return "<1%"
    if p >= 0.995:
        return ">99%"
    return f"{round(p * 100)}%"


def explain_from_template(facts: dict) -> dict:
    title = facts.get("title", "")
    pick = facts.get("pick") or None
    label = pick.get("label") if pick else None
    prob = pick.get("prob") if pick else None
    sport = facts.get("sport", "")
    unit = "goals" if sport == "pl" else "points"
    sections: list[dict] = []

    if label and prob is not None:
        sections.append({"market": "result", "title": "The pick",
                         "text": f"The model makes {label} the pick at {_pct(prob)}."})
    else:
        sections.append({"market": "result", "title": "The pick", "text": "There is no pick for this one yet."})

    for m in facts.get("markets") or []:
        kind = m.get("market")
        if kind in ("spread", "handicap") and m.get("model_margin") is not None and label:
            sections.append({"market": kind, "title": "The line",
                             "text": f"It rates {label} {abs(m['model_margin'])} {unit} better; the line is {m.get('line')}."})
        elif kind in ("total", "total_goals") and m.get("model_total") is not None:
            sections.append({"market": kind, "title": "The total",
                             "text": f"It projects {m['model_total']} against a line of {m.get('line')}."})

    players = (facts.get("players") or [])[:2]
    if players:
        names = "; ".join(f"{p['name']} ({p.get('team', '')}): {p.get('projection', '')}".strip() for p in players)
        sections.append({"market": "players", "title": "Players to watch", "text": f"Players to watch: {names}."})

    trust = []
    if prob is not None:
        misses = _TENS[max(0, min(10, round((1 - max(prob, 1 - prob)) * 10)))]
        trust.append(f"Even a {_pct(max(prob, 1 - prob))} call misses about {misses} times in ten.")
    record = facts.get("record")
    if record and record.get("settled"):
        what = (record.get("label") or "Picks made before kickoff").lower()
        trust.append(f"Its record: {record['hits']}/{record['settled']} {what} correct.")
    if facts.get("pick_timing") == "rebuilt":
        trust.append(f"This pick was rebuilt after {_START.get(sport, 'kickoff')}, so it isn't counted in the record.")
    if trust:
        sections.append({"market": "trust", "title": "How much to trust it", "text": " ".join(trust)})

    headline = f"{title}: {label} at {_pct(prob)}" if label and prob is not None else f"{title}: no pick yet"
    return {"headline": headline, "sections": sections}
