from h import *
F = pd.read_pickle("../F_team.pkl")
_, cols = base_frame()
H = ["elo_diff_s","home_adj_off_s","away_adj_off_s","home_adj_def_s","away_adj_def_s","home_pace_roll_s","away_pace_roll_s"]
AV = ["home_absent_min_share","away_absent_min_share","home_absent_prod_share","away_absent_prod_share"]
Hh = run_arm(F, cols + H)
HF = run_arm(F, cols + H + AV)
evaluate(Hh, HF, "HF vs H: availability proxy ON TOP of the combined power+adjusted+pace block (baseline arm here = H)")
base = run_arm(F, cols)
evaluate(base, HF, "HF vs repo baseline")
