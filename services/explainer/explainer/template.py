"""The fallback when no model is available, over budget, or its output fails
validation: plain sentences built only from the facts. Facts fields beyond
the contract's core are loose dicts, so every read here is defensive: the
template is the last resort and must never raise."""
from __future__ import annotations

_TENS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
_START = {"f1": "the session started", "pl": "kickoff"}


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _pct(p: float) -> str:
    if p <= 0.005:
        return "<1%"
    if p >= 0.995:
        return ">99%"
    return f"{round(p * 100)}%"


def _dicts(xs) -> list[dict]:
    return [x for x in xs if isinstance(x, dict)] if isinstance(xs, list) else []


def explain_from_template(facts: dict) -> dict:
    title = str(facts.get("title") or "This match")
    pick = facts.get("pick") if isinstance(facts.get("pick"), dict) else {}
    label = pick.get("label")
    label = str(label) if label not in (None, "") else None
    prob = _num(pick.get("prob"))
    if prob is not None and not 0 <= prob <= 1:
        prob = None
    sport = facts.get("sport", "")
    unit = "goals" if sport == "pl" else "points"
    timing = facts.get("pick_timing")
    sections: list[dict] = []

    result = facts.get("result") if isinstance(facts.get("result"), dict) else None
    if facts.get("status") == "final" and result and result.get("score"):
        text = f"Final: {result['score']}."
        # Only a pick made before the start is judged.
        if timing == "pre_kickoff" and isinstance(result.get("pick_won"), bool) and label:
            text += f" The pick was {'right' if result['pick_won'] else 'wrong'}: {label}."
        sections.append({"market": "result", "title": "How it finished", "text": text})

    if label and prob is not None:
        sections.append({"market": "pick", "title": "The pick",
                         "text": f"The model makes {label} the pick at {_pct(prob)}."})
    else:
        sections.append({"market": "pick", "title": "The pick", "text": "There is no pick for this one yet."})

    for m in _dicts(facts.get("markets")):
        kind = m.get("market")
        margin, total = _num(m.get("model_margin")), _num(m.get("model_total"))
        if kind in ("spread", "handicap") and margin is not None and label and m.get("line"):
            sections.append({"market": kind, "title": "The line",
                             "text": f"It rates {label} {abs(margin):g} {unit} better; the line is {m['line']}."})
        elif kind in ("total", "total_goals") and total is not None and m.get("line") is not None:
            sections.append({"market": kind, "title": "The total",
                             "text": f"It projects {total:g} against a line of {m['line']}."})

    players = [p for p in _dicts(facts.get("players")) if p.get("name")][:2]
    if players:
        names = "; ".join(
            f"{p['name']}" + (f" ({p['team']})" if p.get("team") else "") + (f": {p['projection']}" if p.get("projection") else "")
            for p in players)
        sections.append({"market": "players", "title": "Players to watch", "text": f"Players to watch: {names}."})

    trust = []
    if prob is not None and 0 < prob < 1:
        misses = _TENS[max(0, min(10, round((1 - prob) * 10)))]
        trust.append(f"A {_pct(prob)} pick still misses about {misses} times in ten.")
    record = facts.get("record") if isinstance(facts.get("record"), dict) else None
    hits, settled = (_num(record.get("hits")), _num(record.get("settled"))) if record else (None, None)
    if hits is not None and settled:
        what = str(record.get("label") or "Picks made before kickoff").lower()
        trust.append(f"Its record: {int(hits)}/{int(settled)} {what} correct.")
    if timing == "rebuilt":
        trust.append(f"This pick was rebuilt after {_START.get(sport, 'kickoff')}, so it isn't counted in the record.")
    if trust:
        sections.append({"market": "trust", "title": "How much to trust it", "text": " ".join(trust)})

    headline = f"{title}: {label} at {_pct(prob)}" if label and prob is not None else f"{title}: no pick yet"
    return {"headline": headline, "sections": sections}


def minimal(facts: dict) -> dict:
    """If even the template fails: say so, never error."""
    return {"headline": str(facts.get("title") or "No explanation yet"),
            "sections": [{"market": "note", "title": "Not ready", "text": "No explanation is available for this one yet."}]}
