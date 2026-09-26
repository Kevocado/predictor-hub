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


def _pool(node, key: str = "") -> tuple[set[float], set[float]]:
    """(numbers, written percents) a text may cite. Ids and dates/times are
    left out: their digits ("00:20", "2026-10-05") would otherwise excuse
    invented figures."""
    nums: set[float] = set()
    pcts: set[float] = set()

    def walk(n, k=""):
        if isinstance(n, bool) or n is None:
            return
        if isinstance(n, (int, float)):
            nums.add(float(n))
        elif isinstance(n, str):
            if k == "id" or k.endswith("_id") or _DATE_RE.search(n):
                return
            for tok in _NUM_RE.findall(n):
                v = _candidates(tok)[-1][0]
                (pcts if tok.endswith("%") else nums).add(v)
                if tok.endswith("%"):
                    nums.add(v)
        elif isinstance(n, dict):
            for kk, v in n.items():
                walk(v, kk)
        elif isinstance(n, list):
            for v in n:
                walk(v, k)

    walk(node, key)
    return nums, pcts


def _known(token: str, nums: set[float], pcts: set[float]) -> bool:
    t = token.replace("−", "-").replace(",", "")
    decimals = len(t.rstrip("%").split(".")[1]) if "." in t else 0
    tol = 0.5 * 10 ** -decimals
    v = abs(float(t.rstrip("%")))
    if t.endswith("%"):
        # A percent is a probability (a fraction in the facts) or a percent
        # the facts themselves wrote; never a raw count like 41 hits.
        return any(abs(v / 100 - p) <= tol / 100 + 1e-9 for p in nums if 0 <= p <= 1) \
            or any(abs(v - q) <= tol + 1e-9 for q in pcts)
    if decimals == 0:
        # A whole number may round a decimal (48 for 47.8) but not a half
        # line (46 for 45.5), and never stands for a probability.
        return any(abs(v - abs(p)) < tol or v == abs(p) for p in nums if abs(p) >= 1 or p == 0)
    return any(abs(v - abs(p)) <= tol + 1e-9 for p in nums)


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
    # "Hammers" is West Ham's nickname, not betting slang.
    banned = [m.group(0) for m in _BANNED_RE.finditer(body) if m.group(0) != "Hammers"]
    if banned:
        problems.append(f"banned word: {banned[0]!r}")

    facts = json.loads(facts_json)
    fn, fp = _pool(facts)
    nn, np_ = _pool(json.loads(news_json or "[]"))
    nums, pcts = fn | nn, fp | np_
    unknown = sorted({tok for tok in _NUM_RE.findall(body) if not _known(tok, nums, pcts)})
    if unknown:
        problems.append("number not in the facts or news: " + ", ".join(unknown))

    if facts.get("pick_timing") == "rebuilt" and not any(w in body.lower() for w in REBUILT_WORDS):
        problems.append("pick is rebuilt but the text doesn't say it was rebuilt after the start")
    return problems
