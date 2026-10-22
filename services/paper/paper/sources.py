"""Read the site repos' public artefacts: Kalshi line snapshots and model snapshots.

Two inputs, both git-tracked and public in the sibling site repos, both read
rather than fetched:

  data/lines/*.jsonl.gz            Kalshi market ladders, one gzipped JSON object per
                                   rung per snapshot. Written twice a day by
                                   NFL_Predictor's `.github/workflows/collect-kalshi-lines.yml`
                                   and NBA_Predictor's equivalent, and committed to
                                   those repos. Each row already carries `snapshot_ts`
                                   (when the price was seen), the quotes, and — for
                                   markets that have since resolved — Kalshi's own
                                   `result`. Rows are therefore self-settling: nothing
                                   here has to join a box score to find out who won.

  data/public_snapshot.json        the site's published model output. NFL's carries
                                   per-game probabilities keyed by game_id; NBA's
                                   carries results and aggregate model metrics but NO
                                   per-game probability. That asymmetry is why
                                   `snapshot_games()` returns nothing for NBA.

Nothing in this module writes, and nothing here reaches the network.
"""
from __future__ import annotations

import gzip
import json
from datetime import date, datetime, timezone
from pathlib import Path

# Kalshi series whose ladder is about a game rather than a player. Only these can
# ever pair with a game-level probability from a public snapshot.
#
# "spread" and "btts" are here for the same reason "total" is: the rung is
# about the game, not about a player. Kalshi's spread ladder is "<Team> wins by
# over N points", so the rung is priced from the model's predicted margin at the
# rung's own line; "btts" is priced from PL's published btts_yes_prob.
GAME_LEVEL_STATS = frozenset({"moneyline", "winner", "total", "btts", "spread"})

# Which sibling repo holds which sport's lines.
SITE_FOR_SPORT = {"nfl": "NFL_Predictor", "nba": "NBA_Predictor",
                  "pl": "PL_Predictor", "cfb": "CFB_Predictor"}

_SPORT_FOR_SERIES_PREFIX = {
    "KXNFL": "nfl",
    "KXNBA": "nba",
    "KXNCAAF": "cfb",
    "KXEPL": "pl",
}

#: PL clubs as Kalshi spells them (three-letter codes) -> the full names PL uses.
#: Kalshi's event ticker is `<SERIES>-<YYMMMDD><HOME><AWAY>`, home first, so the
#: first code is the home side. The list covers the 2025/26 season's clubs.
PL_TEAM_CODES = {
    "Arsenal": "ARS", "Aston Villa": "AVL", "Bournemouth": "BOU",
    "Brentford": "BRE", "Brighton": "BHA", "Burnley": "BUR",
    "Chelsea": "CHE", "Coventry": "COV", "Crystal Palace": "CRY",
    "Everton": "EVE", "Fulham": "FUL", "Hull": "HUL",
    "Ipswich": "IPS", "Leeds": "LEE", "Leicester": "LEI",
    "Liverpool": "LIV", "Luton": "LUT", "Man City": "MCI",
    "Man United": "MUN", "Newcastle": "NEW", "Nott'm Forest": "NFO",
    "Sheffield United": "SHU", "Southampton": "SOU", "Sunderland": "SUN",
    "Tottenham": "TOT", "West Ham": "WHU", "Wolves": "WOL",
}

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}


class SourceError(RuntimeError):
    """A source file exists but cannot be read as what it claims to be."""


def discover_sites_root(env=None, hub: Path | None = None, levels: int = 5) -> Path | None:
    """The directory holding the sibling site checkouts, or None.

    The Python half of the rule `scripts/sites-root.mjs` already implements for
    the hub's Node tests: `SITES_ROOT` wins, otherwise walk UP looking for a
    parent that holds at least one recognised site checkout. Walking up rather
    than down is because the hub is checked out both as a plain clone
    (`<root>/predictor-hub`) and as a worktree (`<root>/predictor-hub-worktrees/
    <branch>`), where the root is the parent in one case and the grandparent in
    the other.

    A directory qualifies on ONE recognised checkout rather than all of them:
    a root holding three of the sites is still a root, and insisting on all of
    them turns "three sites are missing" into "there is no sites root here".
    """
    import os
    env = os.environ if env is None else env
    if env.get("SITES_ROOT"):
        return Path(env["SITES_ROOT"])
    names = set(SITE_FOR_SPORT.values())
    if hub is None:
        hub = Path(__file__).resolve().parents[3]
    directory = Path(hub)
    for _ in range(levels):
        parent = directory.parent
        try:
            if any((parent / name).exists() for name in names):
                return parent
        except OSError:
            return None
        if parent == directory:
            break
        directory = parent
    return None



def parse_ts(value: str | None) -> datetime | None:
    """An ISO-8601 instant as an aware UTC datetime, or None if it is not one.

    Returns None rather than raising for every malformed input on purpose: the
    no-hindsight rules are stated as "if you cannot prove the ordering, do not
    log it", so an unreadable timestamp has to be a usable value that fails the
    check, not an exception that stops the run.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # A naive stamp cannot be ordered against an aware one without inventing
        # a timezone, so it is treated as unprovable rather than assumed UTC.
        return None
    return parsed.astimezone(timezone.utc)


def read_line_files(paths) -> list[dict]:
    """Every rung from every given gzipped JSONL file, in file order.

    A line that will not parse is skipped rather than fatal: these files are
    committed by a scheduled collector, and one truncated final line must not
    cost the whole ledger its other ten thousand rows.
    """
    rows: list[dict] = []
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt", encoding="utf-8") as handle:  # type: ignore[operator]
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    return rows


def lines_files(sites_root: Path, sport: str) -> list[Path]:
    """The committed Kalshi line snapshots for one sport, oldest file first."""
    site = SITE_FOR_SPORT.get(sport)
    if site is None:
        return []
    directory = Path(sites_root) / site / "data" / "lines"
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.jsonl.gz"))


def kickoff(row: dict) -> datetime | None:
    """When the event this rung belongs to starts.

    `occurrence` is the game time; `close_time` is when Kalshi finishes
    settling, which is LATER (typically days afterwards). The no-hindsight rule
    is about kickoff, so `occurrence` is the field that has to be compared, and
    `close_time` is only a fallback for a row that lacks it.

    This distinction is the whole leak test. A league whose markets stay open
    after the game would let a post-final price back in if the cutoff were
    `close_time`.
    """
    for field in ("occurrence", "close_time"):
        stamp = parse_ts(row.get(field))
        if stamp is not None:
            return stamp
    return None


def buyable_price(row: dict, side: str) -> float | None:
    """The price we could actually have paid for `side`, in 0-1, or None.

    YES is bought at `yes_ask` and NO at `no_ask`. Not the midpoint: NFL's own
    `kalshi_lines.implied_probability` returns (bid+ask)/2, and a midpoint is not
    a price anybody pays. Using it would overstate every edge in this ledger.

    None means "not tradeable, do not log it", which covers three cases:
    no quote at all, a quote at 0 or 1 cents (an empty or dead side), and a
    crossed book (ask below bid), which means the feed is wrong rather than rich.
    """
    if side not in ("yes", "no"):
        return None
    ask = row.get(f"{side}_ask")
    bid = row.get(f"{side}_bid")
    if not isinstance(ask, (int, float)):
        return None
    ask = float(ask)
    if not (0.0 < ask < 1.0):
        return None
    if isinstance(bid, (int, float)) and float(bid) > ask:
        return None  # crossed
    return ask


def event_parts(event_ticker: str | None) -> dict | None:
    """Split a Kalshi event ticker into sport, date and the two team codes.

    Kalshi event tickers are `<SERIES>-<YY><MMM><DD><TEAMCODE><TEAMCODE>`, e.g.
    `KXNBAGAME-26OCT21SACLAC` — two-digit year, a three-letter month, two-digit
    day, then the teams. The date is the game's LOCAL date, so it matches a
    site snapshot's naive `gameday` without any timezone conversion; that is
    convenient here and is also why nothing in this module compares it to an
    aware timestamp.

    The two team codes cannot be split by length — they run from `NE` to `LAL` —
    so they are NOT split here. The remainder is returned whole and matched
    against a specific game's two known codes in `join_games`, which is the only
    place the ambiguity can be resolved without guessing.
    """
    if not isinstance(event_ticker, str) or "-" not in event_ticker:
        return None
    series, _, rest = event_ticker.partition("-")
    if len(rest) < 7:
        return None
    sport = None
    for prefix, name in _SPORT_FOR_SERIES_PREFIX.items():
        if series.startswith(prefix):
            sport = name
            break
    stamp = rest[:7]
    month = _MONTHS.get(stamp[2:5].upper())
    if month is None or not stamp[0:2].isdigit() or not stamp[5:7].isdigit():
        return None
    year, day = 2000 + int(stamp[0:2]), int(stamp[5:7])
    try:
        date = f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        return None
    return {
        "sport": sport,
        "series": series,
        "date": date,
        "teams": rest[7:].upper(),
    }


def read_snapshot(path: Path) -> dict | None:
    """A site's `data/public_snapshot.json`, or None if it is not there."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceError(f"{path} is not valid JSON: {exc}") from exc
    return data if isinstance(data, dict) else None


def snapshot_games(snapshot: dict | None, sport: str) -> dict[str, dict]:
    """Game-level probabilities from a public snapshot, keyed by game_id.

    NFL publishes them: `weeks.<w>.predictions[<game_id>]` carries home_win_prob,
    away_win_prob, over_prob, under_prob, home_cover_prob and away_cover_prob,
    and the sibling `weeks.<w>.games` entry carries the teams and whether the
    game has a final score. Those unplayed games are the only ones a candidate
    can come from.

    CFB publishes the same shape (`weeks.<w>.predictions[<game_id>]` with
    home_win_prob, away_win_prob, predicted_margin, predicted_total and the
    two sigmas), but its teams are CFBD's NAMES while Kalshi's event ticker
    carries the league's CODES. `cfb_games` therefore resolves the codes from
    the Kalshi market titles and matches on those, because the codes do not
    have the ambiguity the names do ("Appalachian St." and "App State" are one
    school, "San José State" is spelled two ways).

    NBA publishes `schedule` (results) and `manifest.metrics` (aggregate
    accuracy, sigma, n) and nothing per-game, so this returns {} for NBA. That
    is a real gap and not a parsing failure — see the PR description.
    """
    if sport == "nba":
        root = discover_sites_root()
        picks = _picks_history(root) if root is not None else []
        return {
            str(pick.get("game_id")): _nba_pick_snapshot(pick)
            for pick in _latest_pick_per_game(picks).values()
        }

    if not snapshot:
        return {}
    games: dict[str, dict] = {}
    if sport == "cfb":
        return cfb_games(snapshot)
    if sport == "nfl":
        generated_at = snapshot.get("generated_at")
        for week in (snapshot.get("weeks") or {}).values():
            if not isinstance(week, dict):
                continue
            finals = {
                g.get("game_id"): g
                for g in (week.get("games") or [])
                if isinstance(g, dict) and g.get("game_id")
            }
            for game_id, probs in (week.get("predictions") or {}).items():
                if not isinstance(probs, dict):
                    continue
                game = finals.get(game_id) or {}
                # A game with a final score is over; its probability is history,
                # not something a candidate could have been logged against.
                if game.get("home_score") is not None or game.get("away_score") is not None:
                    continue
                games[game_id] = {
                    "game_id": game_id,
                    "sport": sport,
                    "generated_at": generated_at,
                    "model_fingerprint": snapshot.get("model_fingerprint"),
                    "date": str(game.get("gameday") or "")[:10],
                    "home": game.get("home_team"),
                    "away": game.get("away_team"),
                    # The model's predicted total and its sigma: a total rung's
                    # probability is evaluated at the rung's own line from these.
                    "total_mu": probs.get("predicted_total"),
                    "total_sigma": probs.get("total_sigma"),
                    "probs": {
                        "home_win": probs.get("home_win_prob"),
                        "away_win": probs.get("away_win_prob"),
                        "over": probs.get("over_prob"),
                        "under": probs.get("under_prob"),
                        "home_cover": probs.get("home_cover_prob"),
                        "away_cover": probs.get("away_cover_prob"),
                    },
                }
    elif sport == "pl":
        generated_at = snapshot.get("generated_at")
        for event_id, detail in ((snapshot.get("fixture_detail_by_event_id") or {}).items()):
            if not isinstance(detail, dict):
                continue
            commence = detail.get("commence_time")
            if not isinstance(commence, str):
                continue
            # A fixture with a post-match record has already been played; its
            # probability is history, not something a candidate could have been
            # logged against.
            if detail.get("post_match"):
                continue
            home_name = detail.get("team_home")
            away_name = detail.get("team_away")
            home_code = PL_TEAM_CODES.get(home_name)
            away_code = PL_TEAM_CODES.get(away_name)
            if not home_code or not away_code:
                continue
            hw = (detail.get("home_win") or {}).get("prob")
            dr = (detail.get("draw") or {}).get("prob")
            aw = (detail.get("away_win") or {}).get("prob")
            if not all(isinstance(x, (int, float)) for x in (hw, dr, aw)):
                continue
            games[event_id] = {
                "game_id": event_id,
                "sport": sport,
                "generated_at": generated_at,
                "model_fingerprint": snapshot.get("model_fingerprint"),
                "date": commence[:10],
                "home": home_code,
                "away": away_code,
                "probs": {
                    "home_win": float(hw),
                    "draw": float(dr),
                    "away_win": float(aw),
                    # P(btts) is published outright, so it is read rather than
                    # derived. A fixture that does not publish one has no BTTS
                    # probability, and none is guessed from the grid.
                    "btts_yes": _num_or_none(detail.get("btts_yes_prob")),
                },
                # The joint (home goals, away goals) distribution. The totals
                # ladder is a threshold on the sum of the two, so the grid is
                # what prices it: a Normal fit of a skewed, discrete goal
                # distribution was wrong by up to four points at the middle
                # rungs, which is the size of the edge threshold itself.
                "score_grid": _score_grid(detail.get("score_grid")),
            }
    if sport == "nba":
        root = discover_sites_root()
        picks = _picks_history(root) if root is not None else []
        return {
            str(pick.get("game_id")): _nba_pick_snapshot(pick)
            for pick in _latest_pick_per_game(picks).values()
        }
    return games


def _picks_history(root: Path | None) -> list[dict]:
    """Every pick row the NBA refresh has appended, oldest first.

    The refresh appends every version a model has published, so a game can
    appear many times; the caller decides which version to trust.
    """
    if root is None:
        return []
    path = root / "NBA_Predictor" / "data" / "picks_history.jsonl.gz"
    return read_line_files([path]) if path.exists() else []


def _latest_pick_per_game(picks: list[dict]) -> dict[str, dict]:
    """One row per game: the pick published latest.

    The ledger pairs a price with the model state that existed when the price
    was seen, so the latest pick is what a reader has to compare against -- a
    pick made after the price cannot have influenced it, and anything earlier
    is superseded by this one.
    """
    latest: dict[str, dict] = {}
    for row in picks:
        game_id = str(row.get("game_id") or "")
        if not game_id:
            continue
        held = latest.get(game_id)
        if held is None or str(row.get("created_at") or "") > str(held.get("created_at") or ""):
            latest[game_id] = row
    return latest


#: Each CFBD team name -> (Kalshi league code, the name Kalshi uses).
#:
#: Kalshi's CFB event ticker names the two teams by code
#: (`KXNCAAFGAME-26OCT24BUFFMOH`) and the codes are not a fixed width -- `BUFF`
#: is four letters and `MOH` is three -- so the ticker's team string cannot be
#: split without knowing the two teams. The snapshot carries CFBD's names, so
#: the codes have to be mapped to them somewhere.
#:
#: This is an explicit table rather than a fuzzy match on purpose. "App State"
#: and "Appalachian St." are one school, "San José State" is spelled two ways
#: across the two sources, and five codes (CSU, KSU, NCST, WSU, WEB) are shared
#: between an FBS school and an FCS one of the same initials. A normalising
#: match would silently pair the wrong games, and a wrong pairing is a wrong
#: probability on a real bet.
#:
#: The second element of each pair is the name KALSHI uses, which is not always
#: the name CFBD uses: Kalshi writes "Northern Colorado" where CFBD writes
#: "Northern Colo.", and "Ohio St." where CFBD writes "Ohio State". The
#: ledger matches Kalshi's own market titles, so it needs Kalshi's spelling.
#:
#: Every entry is a fact about Kalshi's own published market titles, not a
#: guess: each code was read off the `<Team> wins` title of the market that
#: carries it, and each Kalshi name was checked to be a real title for that
#: code. A team missing from the table simply does not join, and the ledger
#: says so rather than guessing.
CFB_TEAM_CODES: dict[str, tuple[str, str]] = {
    "Abilene Christian": ("AC", "Abilene Christian"),
    "Air Force": ("AFA", "Air Force"),
    "Akron": ("AKR", "Akron"),
    "Alabama": ("ALA", "Alabama"),
    "Alabama State": ("ALST", "Alabama St."),
    "Alcorn State": ("ALCN", "Alcorn St."),
    "App State": ("APP", "Appalachian St."),
    "Arizona": ("ARIZ", "Arizona"),
    "Arizona State": ("ASU", "Arizona St."),
    "Arkansas": ("ARK", "Arkansas"),
    "Arkansas State": ("ARST", "Arkansas St."),
    "Arkansas-Pine Bluff": ("ARPB", "Arkansas-Pine Bluff"),
    "Army": ("ARMY", "Army"),
    "Auburn": ("AUB", "Auburn"),
    "Austin Peay": ("PEAY", "Austin Peay"),
    "BYU": ("BYU", "BYU"),
    "Ball State": ("BALL", "Ball St."),
    "Baylor": ("BAY", "Baylor"),
    "Bethune-Cookman": ("COOK", "Bethune-Cookman"),
    "Boise State": ("BSU", "Boise St."),
    "Boston College": ("BC", "Boston College"),
    "Bowling Green": ("BGSU", "Bowling Green"),
    "Bryant": ("BRY", "Bryant"),
    "Bucknell": ("BUCK", "Bucknell"),
    "Buffalo": ("BUFF", "Buffalo"),
    "Cal Poly": ("CP", "Cal Poly"),
    "California": ("CAL", "California"),
    "Campbell": ("CAMP", "Campbell"),
    "Central Arkansas": ("CARK", "Central Arkansas"),
    "Central Connecticut": ("CCSU", "Central Connecticut St."),
    "Central Michigan": ("CMU", "Central Michigan"),
    "Charleston Southern": ("CHSO", "Charleston Southern"),
    "Charlotte": ("CHAR", "Charlotte"),
    "Chattanooga": ("CHAT", "Chattanooga"),
    "Cincinnati": ("CIN", "Cincinnati"),
    "Clemson": ("CLEM", "Clemson"),
    "Coastal Carolina": ("CCAR", "Coastal Carolina"),
    "Colgate": ("COLG", "Colgate"),
    "Colorado": ("COLO", "Colorado"),
    "Colorado State": ("CSU", "Colorado St."),
    "Delaware": ("DEL", "Delaware"),
    "Delaware State": ("DSU", "Delaware St."),
    "Duke": ("DUKE", "Duke"),
    "Duquesne": ("DUQ", "Duquesne"),
    "East Carolina": ("ECU", "East Carolina"),
    "East Tennessee State": ("ETSU", "East Tennessee St."),
    "East Texas A&M": ("ETAM", "East Texas A&M"),
    "Eastern Illinois": ("EIU", "Eastern Illinois"),
    "Eastern Kentucky": ("EKY", "Eastern Kentucky"),
    "Eastern Michigan": ("EMU", "Eastern Michigan"),
    "Eastern Washington": ("EWU", "Eastern Washington"),
    "Elon": ("ELON", "Elon"),
    "Florida": ("FLA", "Florida"),
    "Florida A&M": ("FAMU", "Florida A&M"),
    "Florida Atlantic": ("FAU", "Florida Atlantic"),
    "Florida International": ("FIU", "Florida International"),
    "Florida State": ("FSU", "Florida St."),
    "Fordham": ("FOR", "Fordham"),
    "Fresno State": ("FRES", "Fresno St."),
    "Furman": ("FUR", "Furman"),
    "Gardner-Webb": ("WEBB", "Gardner-Webb"),
    "Georgia": ("UGA", "Georgia"),
    "Georgia Southern": ("GASO", "Georgia Southern"),
    "Georgia State": ("GAST", "Georgia St."),
    "Georgia Tech": ("GT", "Georgia Tech"),
    "Grambling": ("GRAM", "Grambling St."),
    "Hampton": ("HAMP", "Hampton"),
    "Hawai'i": ("HAW", "Hawai'i"),
    "Holy Cross": ("HC", "Holy Cross"),
    "Houston": ("HOU", "Houston"),
    "Houston Christian": ("HCU", "Houston Christian"),
    "Howard": ("HOW", "Howard"),
    "Idaho": ("IDHO", "Idaho"),
    "Idaho State": ("IDST", "Idaho St."),
    "Illinois": ("ILL", "Illinois"),
    "Illinois State": ("ILST", "Illinois St."),
    "Incarnate Word": ("IW", "Incarnate Word"),
    "Indiana": ("IND", "Indiana"),
    "Indiana State": ("INST", "Indiana St."),
    "Iowa": ("IOWA", "Iowa"),
    "Iowa State": ("ISU", "Iowa St."),
    "Jacksonville State": ("JVST", "Jacksonville St."),
    "James Madison": ("JMU", "James Madison"),
    "Kansas": ("KU", "Kansas"),
    "Kansas State": ("KSU", "Kansas St."),
    "Kennesaw State": ("KENN", "Kennesaw St."),
    "Kent State": ("KENT", "Kent St."),
    "Kentucky": ("UK", "Kentucky"),
    "LSU": ("LSU", "LSU"),
    "Lafayette": ("LAF", "Lafayette"),
    "Lamar": ("LAM", "Lamar"),
    "Liberty": ("LIB", "Liberty"),
    "Lindenwood": ("LINW", "Lindenwood"),
    "Long Island University": ("LIU", "LIU"),
    "Louisiana": ("ULL", "Louisiana"),
    "Louisiana Tech": ("LT", "Louisiana Tech"),
    "Louisville": ("LOU", "Louisville"),
    "Maine": ("ME", "Maine"),
    "Marshall": ("MRSH", "Marshall"),
    "Maryland": ("MD", "Maryland"),
    "Massachusetts": ("MASS", "UMass"),
    "McNeese": ("MCNS", "McNeese"),
    "Memphis": ("MEM", "Memphis"),
    "Mercer": ("MER", "Mercer"),
    "Mercyhurst": ("MHU", "Mercyhurst"),
    "Merrimack": ("MRMK", "Merrimack"),
    "Miami": ("MIA", "Miami (FL)"),
    "Miami (OH)": ("MOH", "Miami (OH)"),
    "Michigan": ("MICH", "Michigan"),
    "Michigan State": ("MSU", "Michigan St."),
    "Middle Tennessee": ("MTU", "Middle Tennessee"),
    "Minnesota": ("MINN", "Minnesota"),
    "Mississippi State": ("MSST", "Mississippi St."),
    "Mississippi Valley State": ("MVSU", "Mississippi Valley St."),
    "Missouri": ("MIZZ", "Missouri"),
    "Missouri State": ("MOSU", "Missouri St."),
    "Monmouth": ("MONM", "Monmouth"),
    "Montana": ("MONT", "Montana"),
    "Montana State": ("MTST", "Montana St."),
    "Morgan State": ("MORG", "Morgan St."),
    "Murray State": ("MURR", "Murray St."),
    "NC State": ("NCST", "NC St."),
    "Navy": ("NAVY", "Navy"),
    "Nebraska": ("NEB", "Nebraska"),
    "Nevada": ("NEV", "Nevada"),
    "New Hampshire": ("UNH", "New Hampshire"),
    "New Mexico": ("UNM", "New Mexico"),
    "New Mexico State": ("NMSU", "New Mexico St."),
    "Nicholls": ("NICH", "Nicholls St."),
    "Norfolk State": ("NORF", "Norfolk St."),
    "North Alabama": ("UNA", "North Alabama"),
    "North Carolina": ("UNC", "North Carolina"),
    "North Carolina A&T": ("NCAT", "North Carolina A&T"),
    "North Carolina Central": ("NCCU", "North Carolina Central"),
    "North Dakota": ("UND", "North Dakota"),
    "North Dakota State": ("NDSU", "North Dakota St."),
    "North Texas": ("UNT", "North Texas"),
    "Northern Arizona": ("NAU", "Northern Arizona"),
    "Northern Colorado": ("UNCO", "Northern Colorado"),
    "Northern Illinois": ("NIU", "Northern Illinois"),
    "Northern Iowa": ("UNI", "Northern Iowa"),
    "Northwestern": ("NW", "Northwestern"),
    "Northwestern State": ("NWST", "Northwestern St."),
    "Notre Dame": ("ND", "Notre Dame"),
    "Ohio": ("OHIO", "Ohio"),
    "Ohio State": ("OSU", "Ohio St."),
    "Oklahoma": ("OKLA", "Oklahoma"),
    "Oklahoma State": ("OKST", "Oklahoma St."),
    "Old Dominion": ("ODU", "Old Dominion"),
    "Ole Miss": ("MISS", "Ole Miss"),
    "Oregon": ("ORE", "Oregon"),
    "Oregon State": ("ORST", "Oregon St."),
    "Penn State": ("PSU", "Penn St."),
    "Pittsburgh": ("PITT", "Pittsburgh"),
    "Portland State": ("PRST", "Portland St."),
    "Prairie View A&M": ("PV", "Prairie View A&M"),
    "Purdue": ("PUR", "Purdue"),
    "Rhode Island": ("URI", "Rhode Island"),
    "Rice": ("RICE", "Rice"),
    "Richmond": ("RICH", "Richmond"),
    "Robert Morris": ("RMU", "Robert Morris"),
    "Rutgers": ("RUTG", "Rutgers"),
    "SE Louisiana": ("SELA", "Southeastern Louisiana"),
    "SMU": ("SMU", "SMU"),
    "Sacramento State": ("SAC", "Sacramento St."),
    "Sacred Heart": ("SHU", "Sacred Heart"),
    "Sam Houston": ("SHSU", "Sam Houston"),
    "Samford": ("SAM", "Samford"),
    "San Diego State": ("SDSU", "San Diego St."),
    "San José State": ("SJSU", "San Jose St."),
    "South Alabama": ("USA", "South Alabama"),
    "South Carolina": ("SCAR", "South Carolina"),
    "South Dakota": ("SDAK", "South Dakota"),
    "South Dakota State": ("SDST", "South Dakota St."),
    "South Florida": ("USF", "South Florida"),
    "Southeast Missouri State": ("SEMO", "Southeast Missouri St."),
    "Southern": ("SOU", "Southern University"),
    "Southern Illinois": ("SIU", "Southern Illinois"),
    "Southern Miss": ("USM", "Southern Miss"),
    "Southern Utah": ("SUU", "Southern Utah"),
    "Stanford": ("STAN", "Stanford"),
    "Stonehill": ("STNH", "Stonehill"),
    "Stony Brook": ("STON", "Stony Brook"),
    "Syracuse": ("SYR", "Syracuse"),
    "TCU": ("TCU", "TCU"),
    "Tarleton State": ("TARL", "Tarleton St."),
    "Temple": ("TEM", "Temple"),
    "Tennessee": ("TENN", "Tennessee"),
    "Tennessee State": ("TNST", "Tennessee St."),
    "Tennessee Tech": ("TNTC", "Tennessee Tech"),
    "Texas": ("TEX", "Texas"),
    "Texas A&M": ("TXAM", "Texas A&M"),
    "Texas Southern": ("TXSO", "Texas Southern"),
    "Texas State": ("TXST", "Texas St."),
    "Texas Tech": ("TTU", "Texas Tech"),
    "The Citadel": ("CIT", "The Citadel"),
    "Toledo": ("TOL", "Toledo"),
    "Towson": ("TOWS", "Towson"),
    "Troy": ("TROY", "Troy"),
    "Tulane": ("TULN", "Tulane"),
    "Tulsa": ("TLSA", "Tulsa"),
    "UAB": ("UAB", "UAB"),
    "UAlbany": ("ALBY", "University at Albany"),
    "UC Davis": ("UCD", "UC Davis"),
    "UCF": ("UCF", "UCF"),
    "UCLA": ("UCLA", "UCLA"),
    "UConn": ("CONN", "UConn"),
    "UL Monroe": ("ULM", "Louisiana-Monroe"),
    "UNLV": ("UNLV", "UNLV"),
    "USC": ("USC", "USC"),
    "UT Martin": ("UTM", "Tennessee-Martin"),
    "UT Rio Grande Valley": ("UTRGV", "UT Rio Grande Valley"),
    "UTEP": ("UTEP", "UTEP"),
    "UTSA": ("UTSA", "UTSA"),
    "Utah": ("UTAH", "Utah"),
    "Utah State": ("USU", "Utah St."),
    "Utah Tech": ("UTU", "Utah Tech"),
    "VMI": ("VMI", "VMI"),
    "Vanderbilt": ("VAN", "Vanderbilt"),
    "Villanova": ("VILL", "Villanova"),
    "Virginia": ("UVA", "Virginia"),
    "Virginia Tech": ("VT", "Virginia Tech"),
    "Wagner": ("WAG", "Wagner"),
    "Wake Forest": ("WAKE", "Wake Forest"),
    "Washington": ("WASH", "Washington"),
    "Washington State": ("WSU", "Washington St."),
    "Weber State": ("WEB", "Weber St."),
    "West Georgia": ("UWGA", "West Georgia"),
    "West Virginia": ("WVU", "West Virginia"),
    "Western Carolina": ("WCU", "Western Carolina"),
    "Western Illinois": ("WIU", "Western Illinois"),
    "Western Kentucky": ("WKU", "Western Kentucky"),
    "Western Michigan": ("WMU", "Western Michigan"),
    "William & Mary": ("WM", "William & Mary"),
    "Wisconsin": ("WIS", "Wisconsin"),
    "Wofford": ("WOF", "Wofford"),
    "Wyoming": ("WYO", "Wyoming"),
    "Youngstown State": ("YSU", "Youngstown St."),
}

#: How far apart a Kalshi event date and a snapshot game date may be and still
#: be the same game.
#:
#: Kalshi's event ticker carries the game's LOCAL date and the snapshot's
#: `gameday` is a UTC instant, so an evening kickoff is the 24th in New York
#: and the 25th in UTC. One day either way covers that. Two days would start
#: admitting a different game on the same weekend, so it is one.
CFB_DATE_TOLERANCE_DAYS = 1


def cfb_games(snapshot: dict | None) -> dict[str, dict]:
    """CFB games from the snapshot, keyed by game_id, with Kalshi's team codes.

    The snapshot's `weeks.<w>.games` carries CFBD's team names and the
    `weeks.<w>.predictions[<game_id>]` entry carries the model's per-game
    numbers. A game with a final score is over, so its probability is history
    rather than something a candidate could have been logged against, and it
    is left out exactly as NFL's are.
    """
    if not snapshot:
        return {}
    generated_at = snapshot.get("generated_at")
    games: dict[str, dict] = {}
    for week in (snapshot.get("weeks") or {}).values():
        if not isinstance(week, dict):
            continue
        finals = {
            g.get("game_id"): g
            for g in (week.get("games") or [])
            if isinstance(g, dict) and g.get("game_id")
        }
        for game_id, probs in (week.get("predictions") or {}).items():
            if not isinstance(probs, dict):
                continue
            game = finals.get(game_id) or {}
            if game.get("home_score") is not None or game.get("away_score") is not None:
                continue
            home_entry = CFB_TEAM_CODES.get(game.get("home_team"))
            away_entry = CFB_TEAM_CODES.get(game.get("away_team"))
            if not home_entry or not away_entry:
                continue
            home_code, home_kalshi_name = home_entry
            away_code, away_kalshi_name = away_entry
            games[str(game_id)] = {
                "game_id": str(game_id),
                "sport": "cfb",
                "generated_at": generated_at,
                "model_fingerprint": probs.get("model_version"),
                "date": str(game.get("gameday") or "")[:10],
                # The Kalshi codes, so the ticker joins on them.
                "home": home_code,
                "away": away_code,
                # The team's names too: the spread rungs are named after a team
                # ("Dartmouth wins by over 6.5 points") and the ledger has to
                # know which side a rung is about. The Kalshi spelling is the
                # one the rung's own title uses.
                "home_name": game.get("home_team"),
                "away_name": game.get("away_team"),
                "home_kalshi_name": home_kalshi_name,
                "away_kalshi_name": away_kalshi_name,
                "total_mu": probs.get("predicted_total"),
                "total_sigma": probs.get("total_sigma"),
                # The model's predicted margin and its sigma: Kalshi's spread
                # ladder is a margin market ("<Team> wins by over N points"),
                # so a rung's probability is P(that team's margin > N).
                "margin_mu": probs.get("predicted_margin"),
                "margin_sigma": probs.get("sigma"),
                "probs": {
                    "home_win": probs.get("home_win_prob"),
                    "away_win": probs.get("away_win_prob"),
                    "over": None,
                    "under": None,
                    "home_cover": None,
                    "away_cover": None,
                },
            }
    return games


def _nba_pick_snapshot(pick: dict) -> dict:
    """One game's latest pick, shaped like a snapshot game entry.

    `generated_at` is the pick's own `created_at`: the model probability may
    only be paired with a price observed at or after it.
    """
    home_win_prob = pick.get("home_win_prob")
    away_win_prob = None if home_win_prob is None else 1.0 - float(home_win_prob)
    return {
        "game_id": str(pick.get("game_id")),
        "sport": "nba",
        "generated_at": str(pick.get("created_at") or ""),
        "model_fingerprint": pick.get("model_version"),
        "date": str(pick.get("game_date") or "")[:10],
        "home": pick.get("home_team"),
        "away": pick.get("away_team"),
        "probs": {
            "home_win": home_win_prob,
            "away_win": away_win_prob,
            "over": None,
            "under": None,
            "home_cover": None,
            "away_cover": None,
        },
        # Priced at each rung's own line from the model's total and sigma.
        "total_mu": pick.get("predicted_total"),
        "total_sigma": pick.get("total_sigma"),
    }


def _num_or_none(value) -> float | None:
    """A number, or None. Booleans are not numbers here."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _score_grid(grid) -> list[list[float]] | None:
    """The joint (home goals, away goals) distribution, or None.

    A rectangular grid of non-negative numbers. The mass does not have to sum
    to one: PL's grid stops at six goals a side, so a little probability sits
    outside it, and the tail is what the ladder's top rungs ask about. The
    caller normalises by the grid's own mass, which is the best this
    distribution can say; a rung above the grid's reach is priced as the
    remainder, not as zero.
    """
    if not isinstance(grid, list) or not grid:
        return None
    rows: list[list[float]] = []
    width = None
    for row in grid:
        if not isinstance(row, list) or not row:
            return None
        if width is None:
            width = len(row)
        elif len(row) != width:
            return None  # ragged: not a joint distribution
        cells: list[float] = []
        for cell in row:
            value = _num_or_none(cell)
            if value is None or value < 0:
                return None
            cells.append(value)
        rows.append(cells)
    return rows


def grid_p_over(grid: list[list[float]], line: float) -> float | None:
    """P(total goals > line) from the joint grid, or None if it cannot be said.

    The ladder's threshold is on the SUM of the two teams' goals, so the
    probability is the mass of every cell above that sum, divided by the
    grid's own mass.
    """
    try:
        threshold = float(line)
    except (TypeError, ValueError):
        return None
    if not grid:
        return None
    mass = sum(sum(row) for row in grid)
    if mass <= 0:
        return None
    over = sum(grid[i][j] for i in range(len(grid)) for j in range(len(grid[i]))
               if i + j > threshold)
    return over / mass


def snapshot_positions(snapshot: dict | None) -> dict[str, str]:
    """Player name -> position, from a snapshot's `hub_players` block.

    Only NFL publishes one. PL has none, so the allow-list's position filter is
    a no-op for it, which is fine: pl:moneyline has no position restriction.
    """
    if not snapshot:
        return {}
    block = (snapshot.get("hub_players") or {}).get("players")
    if not isinstance(block, list):
        return {}
    return {p["name"]: p.get("position")
            for p in block if isinstance(p, dict) and p.get("name")}


def join_games(parts: dict, games: dict[str, dict]) -> dict | None:
    """The one snapshot game a Kalshi event ticker names, or None.

    Resolves the team-code ambiguity by trying both orderings against a
    specific game's two known codes rather than guessing a split length.

    The date is compared with a one-day tolerance, because Kalshi's event
    ticker carries the game's LOCAL date while the snapshot's `gameday` is a
    UTC instant: an evening kickoff is the 24th in New York and the 25th in
    UTC. Two teams can only be within a day of each other once in a season, so
    the tolerance cannot pair two different games.
    """
    teams, date = parts["teams"], parts["date"]
    for game in games.values():
        home, away = game.get("home"), game.get("away")
        if not home or not away:
            continue
        if not _dates_within(game.get("date"), date, CFB_DATE_TOLERANCE_DAYS):
            continue
        pair = f"{home}{away}"
        if teams == pair:
            return game
        if teams == f"{away}{home}":
            return game
    return None


def _dates_within(game_date, ticker_date, tolerance_days: int) -> bool:
    """True when two ISO dates are the same day, or within `tolerance_days`."""
    if not isinstance(game_date, str) or not isinstance(ticker_date, str):
        return False
    if game_date == ticker_date:
        return True
    try:
        parsed_game = date.fromisoformat(game_date[:10])
        parsed_ticker = date.fromisoformat(ticker_date[:10])
    except ValueError:
        return False
    return abs((parsed_game - parsed_ticker).days) <= tolerance_days


def selection(row: dict) -> str | None:
    """Who a rung is about: a player for a prop, a team code for a game market.

    Kalshi puts it in the ticker after the event ticker: the last segment of
    `KXNBAGAME-26OCT21SACLAC-SAC` is the team being backed, and for a prop rung
    it is the player token. Normalised rows carry it in `player` and NBA rows in
    `title`; the ticker is the one field present in both.
    """
    event = row.get("event_ticker")
    ticker = row.get("ticker")
    if not isinstance(ticker, str):
        return None
    if isinstance(event, str) and ticker.startswith(event + "-"):
        return ticker[len(event) + 1:]
    parts = event_parts(event)
    return parts["teams"] if parts else None
