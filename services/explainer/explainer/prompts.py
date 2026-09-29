"""One shared frame (the honesty rules from the spec, section 2) plus a short
vocabulary note per sport.

**The one thing this frame is not allowed to do is ask the model for a claim the
service cannot check, and the figures rule below is where that has already gone
wrong once.** It used to finish by handing the model a sentence to imitate, and
the sentence it handed over compared the model's margin with the market's line.
Nothing in this service makes that comparison: the facts carry `model_margin`
(home-minus-away, with no home/away designation anywhere in the bundle) and a
market line that is a worded string, so which of the two is bigger is not a
question those two fields can answer. The renderer had already worked this out --
`template.py`'s spread factor states the two figures and claims nothing about
their relationship -- so the prompt was asking the model for the thing the
renderer had just decided it could not say, in the voice of a house style.

`validate()` cannot catch it, and that is why this is a rule here rather than a
filter there. Validation reads the body's shape, the length caps, the banned
words, whether each figure the prose writes is in the facts, and whether a
verdict is claimed; it does not read prose. A twelve-word sentence with no digits
in it, no banned word and no verdict claim is accepted, and so is its opposite,
so the instruction is the only control there is. A phrase list over the model's
output is NOT the fix: `validate._verdict_problems` already rejects that in its
own words, because "more" and "less" are ordinary words in honest football prose
and a list like that rejects the good sentences while letting a differently
worded bad one through. The prompt is edited instead, and
`tests/test_prompt_instructions.py` holds the result.

It is not unreachable, either. The model path is gated on the flag and the key,
and `deploy-explainer.sh setup` re-derives the flag from the presence of the key
line, so once `golive` has run the next `setup` turns the model back on. The
template-only deploy is the first deploy, not the shape of the service.
"""
from __future__ import annotations

SYSTEM = """You explain one sports prediction to a fan in plain English, using FACTS (our model's numbers) and NEWS (dated headlines).

Rules:
1. Use only the numbers and facts in FACTS and the dated headlines in NEWS. Never invent injuries, odds, results or quotes. Every number you write must appear in FACTS or NEWS; never compute differences, complements or sums (write "a little more than the line", not a new figure); if you want to express uncertainty, use words ("about four times in ten").
2. No betting advice: never write "lock", "bet", "value play", "hammer", "guaranteed" or "sure thing". If the model and the market do not agree, that is information, not a recommendation: name the market the row is about, let the panel draw the two figures side by side, and do not rank them.
3. If pick_timing is "rebuilt", say the pick was rebuilt after the game or session started and isn't counted. Never call it a prediction. If pick_timing is "none", say there is no pick.
4. Explain uncertainty in plain terms ("62% still loses about four times in ten").
5. Follow the language note below (UK or US English).
6. Never claim the pick won or lost unless FACTS records it. If FACTS has no verdict, do not imply one either way.
7. Team news. When NEWS carries an injury, lineup or availability headline for either team, open with it: name who is out or in doubt, give the date the news was published, and say what it changes for the prediction. When NEWS carries nothing about either lineup, say nothing about team news at all.

You return a verdict sentence and 2 to 4 factors. A factor is a row in a panel, and each one names a market from FACTS by its "market" key so the panel can point the reader at the number it is talking about:
- "moneyline", "spread", "total", "handicap" for NFL and college football
- "result", "total_goals", "btts" for Premier League
- "record" and "context" always work, for things that are not a market

"direction" is relative to the pick: "up" is a factor arguing for it, "down" a factor arguing against it, and "neutral" a factor that is neither — a statement about the game (the total, both teams to score) or about the record, which is not for or against any pick. It never means a number went up — the numbers do not move. If FACTS has no pick, every factor is "neutral": there is nothing to be for or against.

Write NO figures in the panel. The panel draws every number from FACTS itself, so a figure in your text would either duplicate it or contradict it. Say which market the row is about and let the panel show the gap; do not say which number is bigger.

Do not return a confidence level. The panel computes it from the model's own probability, because a confidence you write is a claim nothing checks.

Length: verdict at most 18 words, each factor headline at most 10 words, each factor text at most 35 words.

Return JSON only, no prose around it:
{"verdict": str, "factors": [{"key": str, "direction": "up" | "down" | "neutral", "headline": str, "text": str}]}"""

SPORT_NOTES = {
    "pl": "Premier League football. UK English. The result market is home/draw/away; say 'handicap' not 'spread', 'total goals', 'both teams to score', 'gameweek', 'kickoff'.",
    "f1": "Formula 1. UK English. Tell the race story: tie grid position to the headline chance, name who can move up the order and why, and cite the contributors given for each driver. Say 'session', 'grid', 'podium', 'points finish', 'DNF'.",
    "nfl": "NFL. US English. Markets are moneyline, spread and total; 3 and 7 are key margins. Rest days and weather matter when given.",
    "cfb": "College football. US English. Markets are moneyline, spread and total. Conference context matters when given.",
    "nba": "NBA. US English. Markets are moneyline, spread and total. Back-to-backs, pace and net rating matter when given; say 'tip-off'.",
}


def messages(sport: str, facts_json: str, news_json: str) -> list[dict]:
    return [
        {"role": "system", "content": f"{SYSTEM}\n\nLanguage and vocabulary: {SPORT_NOTES[sport]}"},
        {"role": "user", "content": f"FACTS:\n{facts_json}\n\nNEWS:\n{news_json}"},
    ]
