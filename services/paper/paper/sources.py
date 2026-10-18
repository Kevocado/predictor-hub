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
from datetime import datetime, timezone
from pathlib import Path

# Kalshi series whose ladder is about a game rather than a player. Only these can
# ever pair with a game-level probability from a public snapshot.
GAME_LEVEL_STATS = frozenset({"moneyline", "winner"})

# Which sibling repo holds which sport's lines. The collectors only exist for
# these two: there is no CFB collector at all, which is why CFB is shadow-only.
SITE_FOR_SPORT = {"nfl": "NFL_Predictor", "nba": "NBA_Predictor", "pl": "PL_Predictor"}

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

    NBA publishes `schedule` (results) and `manifest.metrics` (aggregate
    accuracy, sigma, n) and nothing per-game, so this returns {} for NBA. That
    is a real gap and not a parsing failure — see the PR description.
    """
    if not snapshot:
        return {}
    games: dict[str, dict] = {}
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
                },
            }
    return games


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
    """
    teams, date = parts["teams"], parts["date"]
    for game in games.values():
        home, away = game.get("home"), game.get("away")
        if not home or not away:
            continue
        if game.get("date") != date:
            continue
        pair = f"{home}{away}"
        if teams == pair:
            return game
        if teams == f"{away}{home}":
            return game
    return None


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
