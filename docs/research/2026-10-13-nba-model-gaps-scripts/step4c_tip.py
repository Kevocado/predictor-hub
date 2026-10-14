from h import *
import json
F = pd.read_pickle("../F_team.pkl")
_, cols = base_frame()
snap = json.load(open("data/public_snapshot.json"))["schedule"]
tip = {g["game_id"]: pd.Timestamp(g["tip_off"]) for g in snap if g.get("tip_off")}
print("tip_off known for", sum(g in tip for g in F.game_id), "of", len(F), "frame games")
raw = RAW.sort_values(["game_date", "game_id"])
last = {}
rows = []
for r in raw.itertuples():
    t = tip.get(r.game_id)
    d = {"game_id": r.game_id}
    for side, team in (("home", r.home_team), ("away", r.away_team)):
        prev = last.get(team)
        d[f"{side}_rest_hours"] = min((t - prev).total_seconds() / 3600 - 2.5, 96) if (t is not None and prev is not None) else 96.0
    d["tip_hour_et"] = ((t.hour - 4) % 24) if t is not None else 19  # EDT approx; only used as a coarse "afternoon vs evening"
    rows.append(d)
    if t is not None:
        last[r.home_team] = t; last[r.away_team] = t
T = pd.DataFrame(rows)
for s in ("home", "away"): T[f"{s}_rest_hours_s"] = T[f"{s}_rest_hours"] / 24
T["afternoon"] = (T.tip_hour_et < 17).astype(float)
G = F.merge(T, on="game_id", how="left")
base = run_arm(G, cols)
arm = run_arm(G, [c for c in cols if not c.startswith(("home_rest","away_rest","home_back","away_back"))] + ["home_rest_hours_s","away_rest_hours_s","afternoon"])
evaluate(base, arm, "I tip-off: rest in hours tip-to-tip (cap 4d) + afternoon start (replaces day-count rest cols)")
arm2 = run_arm(G, cols + ["home_rest_hours_s","away_rest_hours_s","afternoon"])
evaluate(base, arm2, "I2 tip-off hours ADDED to the existing rest cols")
