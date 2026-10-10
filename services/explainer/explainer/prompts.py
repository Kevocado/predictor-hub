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

SYSTEM = """You write the tactical read of one sports fixture for a fan in plain English. Your input is FACTS (our model's numbers) and NEWS (dated headlines).

What the read is about: how the two sides' units meet. Build it from FACTS.context.matchups (ranked offence-versus-defence duels: each has the two teams, what each unit is, and its league rank), FACTS.context.player_context (named top rushers, passers or receivers, NFL only: you may name these players) and FACTS.context.form_rows (Formula 1: driver and constructor form, qualifying pace, track history). Any of these may be absent; use only what is there, and if none is there write about the fixture's shape from the headlines and say little.

The reader already sees the pick, its probability, the spread, the total, the moneyline and the rest days on the same screen. Those are background for you only: never write the pick's probability, the spread, the total, the moneyline price, or rest days, and never write any number that is not a rank, a league size, a player stat or a form value from the rows above. A read that repeats one of those figures is discarded and the reader gets a template instead.

Duels are neutral. A duel's "toward_pick" tells you whether the code has checked that it matters; do not say a unit "has the advantage", "favours" a side or "should win" a matchup unless toward_pick is true or false, and then say only that it points toward or against the pick.

Rules:
1. Use only the numbers and facts in FACTS and the dated headlines in NEWS. Never invent injuries, odds, results, players or quotes. Every number you write must appear in FACTS or NEWS; never compute differences, complements or sums.
2. No betting advice: never write "lock", "bet", "value play", "hammer", "guaranteed" or "sure thing".
3. If pick_timing is "rebuilt", say the pick was rebuilt after the game or session started and isn't counted. Never call it a prediction. If pick_timing is "none", say there is no pick.
4. Follow the language note below (UK or US English).
5. Never claim the pick won or lost unless FACTS records it. If FACTS has no verdict, do not imply one either way.
6. Team news. When NEWS carries an injury, lineup or availability headline for either team, open with it: name who is out or in doubt, give the date the news was published, and say what it changes for the prediction. When NEWS carries nothing about either lineup, say nothing about team news at all.
7. Name only the markets FACTS actually carries WITH A QUOTED LINE, in the words you use for them. A market being present in FACTS is not enough: if its line is the MODEL's own figure rather than a quoted book price, do not write "the spread", "the total", "the moneyline", "covering" or "the price" for it either. This matters most when FACTS shows a figure without saying whose it is: an NBA `spread` row holds the MODEL's own margin, so calling it "the market line" tells the reader a book agreed with the model when no book was quoted at all. If you want to refer to the model's own figure, say "the model" or "the projection" — not "the line". Anything you write that names a market with no quoted line is discarded and the reader gets a template instead, so the safe phrasing is also the useful one.

Output: a "verdict" of at most 18 words that names the pick plainly and nothing more, and a "read" of two or three sentences (at most 90 words) about the matchup. Do not return a confidence level, a list of factors or a band: the panel computes what it shows.

Return JSON only, no prose around it:
{"verdict": str, "read": str}"""

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
