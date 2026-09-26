"""The main guard against invented numbers: every figure the model writes
must come from the facts or the news it was given. Also shape, length,
banned words, and the rebuilt-pick disclosure."""
from __future__ import annotations

import json
import re

BANNED = ["lock", "bet", "betting advice", "hammer", "guaranteed", "sure thing", "value play"]
_BANNED_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in BANNED) + r")s?\b", re.I)
_NUM_RE = re.compile(r"[-−+]?\d+(?:,\d{3})*(?:\.\d+)?%?")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
REBUILT_WORDS = ("rebuilt", "after kickoff", "after the start", "after the session")


def _candidates(token: str) -> list[tuple[float, float]]:
    """(value, tolerance) readings of a written number. The tolerance is
    rounding of what was written, half a unit of its last digit: "3.4"
    covers 3.35–3.45, "48" covers 47.8, "62%" covers 61.5–62.5% (never
    64%)."""
    t = token.replace("−", "-").replace(",", "")
    pct = t.endswith("%")
    t = t.rstrip("%")
    decimals = len(t.split(".")[1]) if "." in t else 0
    v, tol = float(t), 0.5 * 10 ** -decimals
    if pct:
        return [(v / 100, tol / 100), (v, tol)]  # "62%" matches 0.62 or 62
    return [(v, tol)]


def _values(token: str) -> list[float]:
    return [v for v, _ in _candidates(token)]


def numbers_in(text: str) -> set[float]:
    return {v for tok in _NUM_RE.findall(text) for v in _values(tok)}


def _pool(node, key: str = "") -> set[float]:
    """Numbers a text may cite. Ids and dates/times are left out: their
    digits ("00:20", "2026-10-05") would otherwise excuse invented figures."""
    if isinstance(node, bool) or node is None:
        return set()
    if isinstance(node, (int, float)):
        return {float(node)}
    if isinstance(node, str):
        if key == "id" or key.endswith("_id") or _DATE_RE.search(node):
            return set()
        return numbers_in(node)
    if isinstance(node, dict):
        return set().union(*(_pool(v, k) for k, v in node.items())) if node else set()
    if isinstance(node, list):
        return set().union(*(_pool(v, key) for v in node)) if node else set()
    return set()


def _known(token: str, pool: set[float]) -> bool:
    return any(abs(abs(v) - abs(p)) <= tol + 1e-9 for v, tol in _candidates(token) for p in pool)


def validate(output: dict, facts_json: str, news_json: str) -> list[str]:
    """Problems with a model's output; [] means it may be shown."""
    sections = output.get("sections") if isinstance(output, dict) else None
    headline = output.get("headline") if isinstance(output, dict) else None
    if not isinstance(headline, str) or not isinstance(sections, list) \
            or not all(isinstance(s, dict) and isinstance(s.get("text"), str) for s in sections):
        return ["output must be {headline: str, sections: [{text: str, ...}]}"]

    problems = []
    if not 3 <= len(sections) <= 6:
        problems.append(f"needs 3–6 sections, got {len(sections)}")
    if len(headline.split()) > 18:
        problems.append("headline is over 18 words")
    for i, s in enumerate(sections):
        if len(s["text"].split()) > 60:
            problems.append(f"section {i + 1} text is over 60 words")
        if len(str(s.get("title", "")).split()) > 6:
            problems.append(f"section {i + 1} title is over 6 words")
    total = sum(len(s["text"].split()) for s in sections)
    if not 120 <= total <= 220:
        problems.append(f"body is {total} words; needs 120–220")

    texts = [headline] + [s["text"] for s in sections] + [str(s.get("title", "")) for s in sections]
    body = " ".join(texts)
    if m := _BANNED_RE.search(body):
        problems.append(f"banned word: {m.group(0)!r}")

    facts = json.loads(facts_json)
    pool = _pool(facts) | _pool(json.loads(news_json or "[]"))
    unknown = sorted({tok for tok in _NUM_RE.findall(body) if not _known(tok, pool)})
    if unknown:
        problems.append("number not in the facts or news: " + ", ".join(unknown))

    if facts.get("pick_timing") == "rebuilt" and not any(w in body.lower() for w in REBUILT_WORDS):
        problems.append("pick is rebuilt but the text doesn't say it was rebuilt after the start")
    return problems
