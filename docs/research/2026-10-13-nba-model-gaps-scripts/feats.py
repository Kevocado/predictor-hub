"""Candidate features, every one computed in a single chronological pass: the value for game G is read BEFORE G's own
result is folded into any state. Inputs: RAW (team box + scores, data/cache/training/games.json), players.pkl (player box).
Nothing here uses the injury feed, odds, or anything dated after the game's own tip."""
import numpy as np, pandas as pd
from collections import defaultdict, deque

WIN = 10
ELO_K, ELO_SCALE = 20.0, 400.0


def _poss(fga, oreb, tov, fta):
    return fga - oreb + tov + 0.44 * fta


def team_blocks(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per game_id with home_/away_ columns for: elo, elo_mov, pace_roll, ortg_roll, drtg_roll, adj_off_roll,
    adj_def_roll, adj_net_roll, fg3a_rate_roll, fg3_pct_shrunk, rest_team (capped 7), g_last7, exp_total."""
    raw = raw.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    elo = defaultdict(lambda: 1500.0)
    elo_mov = defaultdict(lambda: 1500.0)
    hist = defaultdict(lambda: defaultdict(lambda: deque(maxlen=WIN)))  # team -> stat -> last WIN values
    cum = defaultdict(lambda: defaultdict(float))  # team -> running sums (season-to-date) for opp-adjustment
    ngames = defaultdict(int)
    last_date = {}
    dates_played = defaultdict(list)
    lg_n, lg_ortg_sum = 0, 0.0
    lg3_made = lg3_att = 0.0
    out = []

    def roll(team, stat):
        d = hist[team][stat]
        return float(np.mean(d)) if len(d) else np.nan

    for r in raw.itertuples():
        h, a = r.home_team, r.away_team
        lg_ortg = lg_ortg_sum / lg_n if lg_n else np.nan
        lg3 = lg3_made / lg3_att if lg3_att else 0.35
        row = {"game_id": r.game_id}
        for side, t, o in (("home", h, a), ("away", a, h)):
            row[f"{side}_elo"] = elo[t]
            row[f"{side}_elo_mov"] = elo_mov[t]
            for s in ("pace", "ortg", "drtg", "adj_off", "adj_def", "fg3a_rate"):
                row[f"{side}_{s}_roll"] = roll(t, s)
            # shrunk 3P%: prior of 50 attempts at the league-to-date rate, over the team's last 10 games
            m, att = sum(hist[t]["fg3m"]), sum(hist[t]["fg3a"])
            row[f"{side}_fg3_pct_shrunk"] = (m + 50 * lg3) / (att + 50)
            ld = last_date.get(t)
            gap = (pd.Timestamp(r.game_date) - pd.Timestamp(ld)).days - 1 if ld else 7
            row[f"{side}_rest_team"] = min(gap, 7)
            row[f"{side}_g_last7"] = sum(1 for d in dates_played[t] if 0 < (pd.Timestamp(r.game_date) - pd.Timestamp(d)).days <= 7)
        out.append(row)
        # ---- fold this game's result into state AFTER the row is recorded
        ph = _poss(r.home_fga, r.home_oreb, r.home_tov, r.home_fta)
        pa = _poss(r.away_fga, r.away_oreb, r.away_tov, r.away_fta)
        poss = (ph + pa) / 2
        res = {}
        for side, t, o, pts, opp_pts, fga, fg3m, fg3a in (
            ("home", h, a, r.home_pts, r.away_pts, r.home_fga, r.home_fg3m, getattr(r, "home_fg3a", np.nan)),
            ("away", a, h, r.away_pts, r.home_pts, r.away_fga, r.away_fg3m, getattr(r, "away_fg3a", np.nan)),
        ):
            ortg, drtg = pts / poss * 100, opp_pts / poss * 100
            # opponent-adjusted: vs what the opponent typically allowed / scored, season-to-date (league mean if none)
            o_alld = cum[o]["drtg"] / ngames[o] if ngames[o] else (lg_ortg if lg_n else ortg)
            o_scor = cum[o]["ortg"] / ngames[o] if ngames[o] else (lg_ortg if lg_n else drtg)
            res[t] = dict(pace=poss, ortg=ortg, drtg=drtg, adj_off=ortg - o_alld, adj_def=drtg - o_scor,
                          fg3a_rate=(fg3a / fga) if fga and not np.isnan(fg3a) else np.nan, fg3m=fg3m, fg3a=fg3a)
        for t, d in res.items():
            for k, v in d.items():
                if not (isinstance(v, float) and np.isnan(v)):
                    hist[t][k].append(v)
            cum[t]["ortg"] += d["ortg"]; cum[t]["drtg"] += d["drtg"]; ngames[t] += 1
            lg_n += 1; lg_ortg_sum += d["ortg"]
            if not np.isnan(d["fg3a"]):
                lg3_made += d["fg3m"]; lg3_att += d["fg3a"]
            last_date[t] = r.game_date; dates_played[t].append(r.game_date)
        # Elo (repo constants) and a margin-of-victory variant
        exp = 1.0 / (1.0 + 10 ** (-(elo[h] - elo[a]) / ELO_SCALE))
        win = 1.0 if r.home_pts > r.away_pts else 0.0
        elo[h] += ELO_K * (win - exp); elo[a] -= ELO_K * (win - exp)
        expm = 1.0 / (1.0 + 10 ** (-(elo_mov[h] - elo_mov[a] + 50) / ELO_SCALE))  # +50 = home-court points-ish prior
        mult = np.log(abs(r.home_pts - r.away_pts) + 1.0) * 0.7 + 0.5
        elo_mov[h] += ELO_K * mult * (win - expm); elo_mov[a] -= ELO_K * mult * (win - expm)
    df = pd.DataFrame(out).set_index("game_id")
    # league-to-date fill for the first games, so no row is dropped for lack of history
    for c in df.columns:
        if df[c].isna().any():
            df[c] = df[c].fillna(df[c].expanding().mean().shift(1)).fillna(df[c].mean())
    df["elo_diff"] = df.home_elo - df.away_elo
    df["elo_mov_diff"] = df.home_elo_mov - df.away_elo_mov
    df["pace_sum_roll"] = df.home_pace_roll + df.away_pace_roll
    # classic pace x efficiency total: mean pace x (home off vs away def + away off vs home def)/2 per 100
    df["exp_total"] = (df.home_pace_roll + df.away_pace_roll) / 2 * ((df.home_ortg_roll + df.away_drtg_roll) + (df.away_ortg_roll + df.home_drtg_roll)) / 200
    df["adj_net_diff"] = (df.home_adj_off_roll - df.home_adj_def_roll) - (df.away_adj_off_roll - df.away_adj_def_roll)
    df["rest_team_diff"] = df.home_rest_team - df.away_rest_team
    return df.reset_index()


def availability_proxy(P: pd.DataFrame, games: pd.DataFrame) -> pd.DataFrame:
    """Lagged availability: share of a team's rotation (top-8 by season-to-date minutes before G) that did NOT play in the
    team's PREVIOUS game. Known before tip; a player absent last game is more likely to be absent now. Uses box scores only."""
    P = P.sort_values(["game_date", "game_id"])
    by_team_game = {}
    for (gid, team), g in P.groupby(["game_id", "team"]):
        by_team_game[(gid, team)] = g
    order = {t: [] for t in pd.unique(pd.concat([games.home_team, games.away_team]))}
    for r in games.sort_values(["game_date", "game_id"]).itertuples():
        order[r.home_team].append(r.game_id); order[r.away_team].append(r.game_id)
    feat = {}
    for team, gids in order.items():
        cum_min, cum_prod = defaultdict(float), defaultdict(float)
        prev_played = None
        for gid in gids:
            g = by_team_game.get((gid, team))
            if prev_played is None or not cum_min:
                m_share = p_share = np.nan
            else:
                top = sorted(cum_min, key=cum_min.get, reverse=True)[:8]
                tot = sum(cum_min[p] for p in top)
                absent = [p for p in top if p not in prev_played]
                m_share = sum(cum_min[p] for p in absent) / tot if tot else np.nan
                totp = sum(cum_prod[p] for p in top)
                p_share = sum(cum_prod[p] for p in absent) / totp if totp else np.nan
            feat[(gid, team)] = (m_share, p_share)
            if g is not None:
                prev_played = set(g.loc[g.minutes > 0, "player_id"])
                for r in g.itertuples():
                    cum_min[r.player_id] += r.minutes
                    cum_prod[r.player_id] += r.points + 1.2 * r.rebounds + 1.5 * r.assists
    out = games[["game_id", "home_team", "away_team"]].copy()
    out["home_absent_min_share"] = [feat.get((g, t), (np.nan, np.nan))[0] for g, t in zip(out.game_id, out.home_team)]
    out["away_absent_min_share"] = [feat.get((g, t), (np.nan, np.nan))[0] for g, t in zip(out.game_id, out.away_team)]
    out["home_absent_prod_share"] = [feat.get((g, t), (np.nan, np.nan))[1] for g, t in zip(out.game_id, out.home_team)]
    out["away_absent_prod_share"] = [feat.get((g, t), (np.nan, np.nan))[1] for g, t in zip(out.game_id, out.away_team)]
    for c in [c for c in out.columns if c.endswith("share")]:
        out[c] = out[c].fillna(0.0)  # no history -> 0 absent (documented; first game of each team only)
    return out.drop(columns=["home_team", "away_team"])
