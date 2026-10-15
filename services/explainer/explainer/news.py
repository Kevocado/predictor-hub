"""Free, dated ESPN headlines for the teams in a match. News is a bonus:
any error, timeout or odd payload gives [] and the explanation goes on."""
from __future__ import annotations

import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

ESPN_NEWS = {
    "nfl": "https://site.api.espn.com/apis/site/v2/sports/football/nfl/news",
    "cfb": "https://site.api.espn.com/apis/site/v2/sports/football/college-football/news",
    "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/news",
    "pl": "https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/news",
    "f1": "https://site.api.espn.com/apis/site/v2/sports/racing/f1/news",
}
#: The sites title a game "SEA at DEN". A bare "sea"/"den" substring matches "season" and "Bowden", and misses the one headline
#: that matters ("Seahawks rule out ..." matches "sea" only by accident). Abbreviations are expanded to the team's nickname and
#: every term is matched as a whole word.
TEAM_NAMES = {
    "nfl": {
    "ARI": "Cardinals", "ATL": "Falcons", "BAL": "Ravens", "BUF": "Bills", "CAR": "Panthers", "CHI": "Bears",
    "CIN": "Bengals", "CLE": "Browns", "DAL": "Cowboys", "DEN": "Broncos", "DET": "Lions", "GB": "Packers",
    "HOU": "Texans", "IND": "Colts", "JAX": "Jaguars", "KC": "Chiefs", "LA": "Rams", "LAC": "Chargers",
    "LAR": "Rams", "LV": "Raiders", "MIA": "Dolphins", "MIN": "Vikings", "NE": "Patriots", "NO": "Saints",
    "NYG": "Giants", "NYJ": "Jets", "PHI": "Eagles", "PIT": "Steelers", "SEA": "Seahawks", "SF": "49ers",
    "TB": "Buccaneers", "TEN": "Titans", "WAS": "Commanders", "WSH": "Commanders",
    },
    "nba": {
    "ATL": "Hawks", "BKN": "Nets", "BOS": "Celtics", "CHA": "Hornets", "CHI": "Bulls", "CLE": "Cavaliers",
    "DAL": "Mavericks", "DEN": "Nuggets", "DET": "Pistons", "GS": "Warriors", "GSW": "Warriors", "HOU": "Rockets",
    "IND": "Pacers", "LAC": "Clippers", "LAL": "Lakers", "MEM": "Grizzlies", "MIA": "Heat", "MIL": "Bucks",
    "MIN": "Timberwolves", "NO": "Pelicans", "NOP": "Pelicans", "NY": "Knicks", "NYK": "Knicks", "OKC": "Thunder",
    "ORL": "Magic", "PHI": "76ers", "PHX": "Suns", "POR": "Trail Blazers", "SA": "Spurs", "SAC": "Kings",
    "SAS": "Spurs", "TOR": "Raptors", "UTA": "Jazz", "UTAH": "Jazz", "WAS": "Wizards", "WSH": "Wizards",
    },
}


def _patterns(sport: str, names: list[str]) -> list[re.Pattern]:
    """Whole-word, case-insensitive patterns for each term, with abbreviations expanded to the nickname."""
    table = TEAM_NAMES.get(sport, {})
    words: set[str] = set()
    for n in names:
        words.add(n)
        nickname = table.get(n.upper())
        if nickname:
            words.add(nickname.lower())
    return [re.compile(rf"(?<!\w){re.escape(w)}(?!\w)", re.IGNORECASE) for w in words if w]


TTL_SECONDS = 30 * 60
FAILED_TTL_SECONDS = 5 * 60  # don't stack 6 s timeouts across a pre-generation run
TIMEOUT_SECONDS = 6.0

_CACHE: dict[str, tuple[float, list[dict]]] = {}


async def _articles(client: httpx.AsyncClient, sport: str) -> list[dict]:
    now = time.monotonic()
    hit = _CACHE.get(sport)
    if hit and hit[0] > now:
        return hit[1]
    try:
        res = await client.get(ESPN_NEWS[sport], timeout=TIMEOUT_SECONDS)
        res.raise_for_status()
        articles = [a for a in (res.json().get("articles") or []) if isinstance(a, dict) and a.get("headline")]
        _CACHE[sport] = (now + TTL_SECONDS, articles)
    except Exception as exc:  # network, HTTP status, JSON, shape
        logger.info("ESPN news unavailable for %s: %s", sport, type(exc).__name__)
        articles = []
        _CACHE[sport] = (now + FAILED_TTL_SECONDS, articles)
    return articles


async def headlines(client: httpx.AsyncClient, sport: str, teams: list[str], limit: int = 4) -> list[dict]:
    """Newest-first headlines mentioning any of `teams` (case-insensitive)."""
    names = [t.strip().lower() for t in teams if isinstance(t, str) and t.strip()]
    if sport not in ESPN_NEWS or not names:
        return []
    try:
        out = []
        patterns = _patterns(sport, names)
        for a in await _articles(client, sport):
            if not isinstance(a, dict) or not isinstance(a.get("headline"), str):
                continue
            blob = f"{a['headline']} {a.get('description') or ''}"
            if any(p.search(blob) for p in patterns):
                out.append({"headline": a["headline"], "published": str(a.get("published") or ""), "source": "ESPN"})
        out.sort(key=lambda o: o["published"], reverse=True)
        return out[:limit]
    except Exception as exc:  # news is a bonus; an odd payload never breaks an explanation
        logger.info("ESPN news skipped for %s: %s", sport, type(exc).__name__)
        return []
