"""Player Impact model (replaces Goals Above Average as the ranking measure).

What it measures: how much a player changes his team's goal differential while he is on the ice,
compared with the same team when he is off it (so team quality is removed), valued per action by how
strongly that action signals real goal impact.

How the weights are set (no hand-tuning): for every skater-season 2008-09..2025-26, a statistical
plus-minus regression predicts the player's on-ice goal differential RELATIVE TO HIS TEAM in the
neighbouring seasons (the season before and after, i.e. out of sample) from what he did this season:
  relative on-ice expected goals for / against, relative shot attempts for / against, his own shot
  quality (ixG), finishing (goals minus ixG), primary and secondary assists, takeaways, giveaways,
  defensive-zone giveaways, shot blocks, hits, and zone starts (deployment control).
Separate fits for forwards and defensemen, for offense and defense, and for 5v5 / power play / penalty
kill. Actions that repeat and drive goals get weight; noise (one-game shooting luck) gets little.
Goalies: goals saved above expected, weighted by the same out-of-sample method. Penalties and faceoffs
use fixed goal values scaled by their measured repeatability.

Everything is in one unit: goals of team goal differential, per game or per season, so forwards,
defensemen and goalies sit on one axis and every value scales with ice time.
"""
import math
import numpy as np

SITS = ("5on5", "5on4", "4on5")
PEN_VALUE, FO_VALUE = 0.17, 0.01
# zone-start adjustment (per net offensive-zone start, 5v5), estimated in fit_impact.py from the same players'
# season-to-season changes in deployment. Only the attacking side is adjusted: the defensive-side estimates
# had implausible signs (confounded), so they are not used.
# Relative-to-team baseline. False: on-ice minus off-ice (team WITHOUT him). True: on-ice minus team average
# (= (on - off) x share of time he is NOT on the ice), which removes the inflation on-off gives heavy-minute
# players (their off-ice time is the weaker depth units). Chosen by the team-level validation in fit_impact.py.
REL_TEAMAVG = False
ZS = {"F": {"rel_xgf": 0.0, "rel_cf": 0.0}, "D": {"rel_xgf": 0.0, "rel_cf": 0.0}}

# feature sets per (situation, side)
FEATS = {
    ("5on5", "off"): ["rel_xgf", "rel_cf", "ixg", "fin", "a1", "a2", "tk"],
    ("5on5", "def"): ["rel_xga", "rel_ca", "tk", "gv", "dzgv", "blk"],
    ("5on4", "off"): ["rel_xgf", "ixg", "fin", "a1", "a2"],
    ("4on5", "def"): ["rel_xga"],
}
# plain-language groups for display
GROUP = {("off", "rel_xgf"): "play_driving", ("off", "rel_cf"): "play_driving", ("off", "ozs"): "deployment",
         ("off", "ixg"): "shot_creation", ("off", "fin"): "finishing", ("off", "a1"): "playmaking", ("off", "a2"): "playmaking",
         ("off", "tk"): "puck_battles", ("def", "rel_xga"): "defense", ("def", "rel_ca"): "defense", ("def", "blk"): "defense",
         ("def", "tk"): "puck_battles", ("def", "gv"): "puck_battles", ("def", "dzgv"): "puck_battles", ("def", "ozs"): "deployment"}
MIN_H = {"5on5": 300 / 60, "5on4": 40 / 60, "4on5": 40 / 60}   # hours for training


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def grp(pos):
    return "D" if pos == "D" else "F"


def team_ratios(team_rows, season):
    """Per (team, situation): actual goals / expected goals, for and against (to convert off-ice xG to goals)."""
    out = {}
    for r in team_rows:
        if r["season"] != season or r.get("position", "Team Level") != "Team Level":
            continue
        out[(r["team"], r["situation"])] = (num(r["goalsFor"]), num(r["xGoalsFor"]), num(r["goalsAgainst"]), num(r["xGoalsAgainst"]))
    return out


def off_rates(r):
    """Off-ice rates per hour (xGF, xGA, attempts for, attempts against) from one row."""
    hb = num(r.get("timeOnBench")) / 3600
    h = num(r.get("icetime")) / 3600
    if hb <= 0:
        return (0.0, 0.0, 0.0, 0.0, 1.0)
    return (num(r.get("OffIce_F_xGoals")) / hb, num(r.get("OffIce_A_xGoals")) / hb,
            num(r.get("OffIce_F_shotAttempts")) / hb, num(r.get("OffIce_A_shotAttempts")) / hb, hb / (h + hb))


def raw_features(r, rates=None):
    """Totals for one player-situation row. rel_* = on-ice minus (off-ice rate x on-ice hours); with REL_TEAMAVG,
    scaled by the off-ice share so it equals on-ice minus the team average.
    rates: optional off-ice rates to use instead of this row's own (per-game rows use the season's, which makes
    game values add up exactly to the season total)."""
    h = num(r["icetime"]) / 3600
    hb = num(r.get("timeOnBench")) / 3600
    offF, offA = num(r.get("OffIce_F_xGoals")), num(r.get("OffIce_A_xGoals"))
    offCF, offCA = num(r.get("OffIce_F_shotAttempts")), num(r.get("OffIce_A_shotAttempts"))
    rF, rA, rCF, rCA, nshare = rates if rates else off_rates(r)
    sc = nshare if REL_TEAMAVG else 1.0
    gv_all, dz = num(r.get("I_F_giveaways")), num(r.get("I_F_dZoneGiveaways"))
    return {
        "h": h, "hb": hb,
        "rel_xgf": sc * (num(r["OnIce_F_xGoals"]) - rF * h), "rel_xga": sc * (num(r["OnIce_A_xGoals"]) - rA * h),
        "rel_cf": sc * (num(r.get("OnIce_F_shotAttempts")) - rCF * h), "rel_ca": sc * (num(r.get("OnIce_A_shotAttempts")) - rCA * h),
        "ixg": num(r["I_F_xGoals"]), "fin": num(r["I_F_goals"]) - num(r["I_F_xGoals"]),
        "a1": num(r.get("I_F_primaryAssists")), "a2": num(r.get("I_F_secondaryAssists")),
        "tk": num(r.get("I_F_takeaways")), "gv": gv_all - dz, "dzgv": dz,
        "blk": num(r.get("shotsBlockedByPlayer")), "hit": num(r.get("I_F_hits")),
        "ozs": num(r.get("I_F_oZoneShiftStarts")) - num(r.get("I_F_dZoneShiftStarts")),
        # for targets / variance
        "onGF": num(r.get("OnIce_F_goals")), "onGA": num(r.get("OnIce_A_goals")), "offF": offF, "offA": offA,
        "ush": num(r.get("I_F_unblockedShotAttempts")), "onUF": num(r.get("OnIce_F_unblockedShotAttempts")),
        "onUA": num(r.get("OnIce_A_unblockedShotAttempts")),
    }


def season_table(skater_rows, team_rows, season, off_override=None):
    """{(pid, sit): features} plus position-season mean rates for every feature."""
    ratios = team_ratios(team_rows, season)
    P, info = {}, {}
    for r in skater_rows:
        if r["season"] != season or r["situation"] not in SITS + ("all",):
            continue
        info[r["playerId"]] = (r["name"], r["team"], r["position"])
        if r["situation"] == "all":
            P[(r["playerId"], "all")] = r
            continue
        f = raw_features(r, (off_override or {}).get((r["playerId"], r["situation"])))
        if r["situation"] == "5on5":
            for c, a in ZS[grp(r["position"])].items():
                f[c] -= a * f["ozs"]
        # off-ice goals = off-ice xG x the team's finishing ratio WITHOUT this player's own on-ice events
        tgf, txf, tga, txa = ratios.get((r["team"], r["situation"]), (0, 0, 0, 0))
        dxf, dxa = txf - num(r["OnIce_F_xGoals"]), txa - num(r["OnIce_A_xGoals"])
        rf = (tgf - f["onGF"]) / dxf if dxf > 1 and tgf - f["onGF"] >= 0 else 1.0
        ra = (tga - f["onGA"]) / dxa if dxa > 1 and tga - f["onGA"] >= 0 else 1.0
        if f["h"] > 0 and f["hb"] > 0:
            tsc = f["hb"] / (f["h"] + f["hb"]) if REL_TEAMAVG else 1.0
            f["t_relGF60"] = tsc * (f["onGF"] / f["h"] - f["offF"] * rf / f["hb"])
            f["t_relGA60"] = tsc * (f["onGA"] / f["h"] - f["offA"] * ra / f["hb"])
        P[(r["playerId"], r["situation"])] = f
    means = {}
    for g in ("F", "D"):
        rows = [r for (pid, s), r in P.items() if s == "all" and grp(info[pid][2]) == g]
        H = sum(num(r["icetime"]) for r in rows) / 3600 or 1.0
        means[("all", g)] = {"pen": sum(num(r["penaltiesDrawn"]) - num(r["penalties"]) for r in rows) / H,
                             "fo": sum(num(r["faceoffsWon"]) - num(r["faceoffsLost"]) for r in rows) / H}
    for sit in SITS:
        for g in ("F", "D"):
            rows = [f for (pid, s), f in P.items() if s == sit and grp(info[pid][2]) == g and f["h"] > 0]
            H = sum(f["h"] for f in rows) or 1.0
            m = {c: sum(f[c] for f in rows) / H for c in ("rel_xgf", "rel_xga", "rel_cf", "rel_ca", "ixg", "fin", "a1", "a2", "tk", "gv", "dzgv", "blk", "hit", "ozs")}
            for t in ("t_relGF60", "t_relGA60"):
                rr = [f for f in rows if t in f]
                hh = sum(f["h"] for f in rr) or 1.0
                m[t] = sum(f[t] * f["h"] for f in rr) / hh
            means[(sit, g)] = m
    return P, info, means


def dev60(f, mean, cols):
    """Per-60 deviation from the position-season average rate."""
    return [(f[c] / f["h"] - mean[c]) for c in cols]


# ------------------------------------------------------------------ fitting
def wls(X, y, w, lam=1e-3):
    X = np.asarray(X); y = np.asarray(y); w = np.asarray(w)
    sd = X.std(axis=0); sd[sd == 0] = 1
    Z = X / sd
    W = w / w.mean()
    A = Z.T @ (Z * W[:, None]) + lam * len(y) * np.eye(Z.shape[1])
    b = np.linalg.solve(A, Z.T @ (W * y))
    return b / sd


def build_pairs(tables, seasons, sit, side, g):
    """Rows: features in season s (per-60 deviations); target = hours-weighted mean of the player's
    relative on-ice goal rate in s-1 and s+1 (deviation from that season's position mean)."""
    cols = FEATS[(sit, side)]
    tcol = "t_relGF60" if side == "off" else "t_relGA60"
    X, y, w, ss = [], [], [], []
    for i, s in enumerate(seasons):
        P, info, means = tables[s]
        for (pid, st_), f in P.items():
            if st_ != sit or f["h"] < MIN_H[sit] or pid not in info or grp(info[pid][2]) != g:
                continue
            tv, th = 0.0, 0.0
            for j in (i - 1, i + 1):
                if 0 <= j < len(seasons):
                    P2, info2, means2 = tables[seasons[j]]
                    f2 = P2.get((pid, sit))
                    if f2 and f2["h"] >= MIN_H[sit] and tcol in f2 and pid in info2 and grp(info2[pid][2]) == g:
                        tv += (f2[tcol] - means2[(sit, g)][tcol]) * f2["h"]; th += f2["h"]
            if th <= 0:
                continue
            X.append(dev60(f, means[(sit, g)], cols)); y.append(tv / th)
            w.append(1 / (1 / f["h"] + 1 / th)); ss.append(s)
    return np.array(X), np.array(y), np.array(w), np.array(ss)


def wcorr(a, b, w):
    w = w / w.sum(); ma, mb = (w * a).sum(), (w * b).sum()
    c = (w * (a - ma) * (b - mb)).sum()
    return c / math.sqrt((w * (a - ma) ** 2).sum() * (w * (b - mb) ** 2).sum())


def fit_all(tables, seasons, log=print):
    """Fit weights for each (sit, side, pos) and report leave-one-season-out out-of-sample correlation."""
    W, report = {}, {}
    for (sit, side), cols in FEATS.items():
        for g in ("F", "D"):
            X, y, w, ss = build_pairs(tables, seasons, sit, side, g)
            b = wls(X, y, w)
            pred = np.zeros(len(y))
            order = sorted(set(ss))
            for s in order:
                i = order.index(s); m = ss == s
                tr = ~np.isin(ss, order[max(0, i - 2): i + 3])
                pred[m] = X[m] @ wls(X[tr], y[tr], w[tr])
            r_oos = wcorr(pred, y, w)
            # baseline: relative expected goals alone
            j = cols.index("rel_xgf" if side == "off" else "rel_xga")
            base = np.zeros(len(y))
            for s in order:
                i = order.index(s); m = ss == s
                tr = ~np.isin(ss, order[max(0, i - 2): i + 3])
                bb = wls(X[tr][:, [j]], y[tr], w[tr]); base[m] = X[m][:, [j]] @ bb
            r_base = wcorr(base, y, w)
            key = f"{sit}|{side}|{g}"
            W[key] = dict(zip(cols, [float(v) for v in b]))
            report[key] = {"n": int(len(y)), "r_oos": round(r_oos, 3), "r_relxg_only": round(r_base, 3)}
            log(f"  {key}: n={len(y)} out-of-sample r={r_oos:.3f} (rel xG alone {r_base:.3f}) weights " +
                ", ".join(f"{c} {v:+.3f}" for c, v in W[key].items()))
    return W, report


# ------------------------------------------------------------------ applying
def ep2_default():
    return {"5on5": 0.012, "5on4": 0.02, "4on5": 0.015, "all": 0.014}


def compute(skater_rows, goalie_rows, team_rows, season, params, ep2=None, team=None, means_override=None, off_override=None):
    """Impact for every player (or one team). Returns rows shaped like the old gaa.compute output."""
    W = params["weights"]; ep2 = ep2 or ep2_default()
    if params.get("zs"):
        ZS.update(params["zs"])
    global REL_TEAMAVG
    REL_TEAMAVG = bool(params.get("rel_teamavg", False))
    P, info, means = season_table(skater_rows, team_rows, season, off_override)
    if means_override:
        means = means_override
    pen_w, fo_w, g_w = params.get("pen_w", 1.0), params.get("fo_w", 1.0), params.get("goalie_w", 1.0)
    scale = params.get("scale", {})
    relp = params.get("reliability", {})
    def emp_se(g, toi):
        """Empirical noise of a season total at this many minutes, from 18 seasons of year-to-year data:
        noise variance per 60 = true variance x k / minutes."""
        if toi <= 0:
            return 0.0
        nz = params.get("noise", {}).get(g)
        if nz:   # calibrated on split halves of 2021-22..2024-25 seasons: var(rate per 60) = a / minutes + c
            return math.sqrt(nz["a"] / toi + nz["c"]) * toi / 60
        rp = relp.get(g)
        if not rp:
            return 0.0
        return math.sqrt(rp["var_true60"] * rp["k_min"] / toi) * toi / 60
    out = []
    for pid, (nm, tm, pos) in info.items():
        if team and tm != team:
            continue
        al = P.get((pid, "all"))
        if al is None:
            continue
        g = grp(pos)
        comp, var, parts = {}, 0.0, {}
        for (sit, side), cols in FEATS.items():
            name = {"5on5|off": "ev_off", "5on5|def": "ev_def", "5on4|off": "pp_off", "4on5|def": "pk_def"}[f"{sit}|{side}"]
            f = P.get((pid, sit))
            if not f or f["h"] <= 0:
                comp[name] = 0.0
                continue
            w = W[f"{sit}|{side}|{g}"]
            m = means[(sit, g)]
            # total = hours x sum(w * per-60 deviation)  -> goals of relative goal differential
            sign = 1 if side == "off" else -1
            for c in cols:
                if c == "ozs":
                    continue   # zone starts are a control in the fit, never credited
                part = sign * w[c] * (f[c] - m[c] * f["h"])
                key = GROUP[(side, c)]
                parts[key] = parts.get(key, 0.0) + part
            val = sum(w[c] * (f[c] - m[c] * f["h"]) for c in cols if c != "ozs")
            comp[name] = val if side == "off" else -val
            # event-level variance of the inputs
            e = ep2.get(sit, 0.012)
            for c in cols:
                wc = w[c]
                if c in ("rel_xgf",): v = f["onUF"] * e
                elif c in ("rel_xga",): v = f["onUA"] * e
                elif c in ("rel_cf",): v = max(f["onUF"], 1) * 1.3
                elif c in ("rel_ca",): v = max(f["onUA"], 1) * 1.3
                elif c == "ixg": v = f["ush"] * e
                elif c == "fin": v = max(f["ixg"] - f["ush"] * e, 0)
                elif c == "ozs": v = 0.0
                else: v = max(f[c], 0)
                var += wc ** 2 * v
        sc = scale.get(g, 1.0)
        comp = {k: v * sc for k, v in comp.items()}; parts = {k: v * sc for k, v in parts.items()}; var *= sc ** 2
        pd_, pt = num(al["penaltiesDrawn"]), num(al["penalties"])
        h_all = num(al["icetime"]) / 3600; ma = means.get(("all", g), {"pen": 0.0, "fo": 0.0})
        comp["penalties"] = pen_w * PEN_VALUE * ((pd_ - pt) - ma["pen"] * h_all); var += (pen_w * PEN_VALUE) ** 2 * (pd_ + pt)
        fw, fl = num(al["faceoffsWon"]), num(al["faceoffsLost"])
        comp["faceoffs"] = fo_w * FO_VALUE * ((fw - fl) - ma["fo"] * h_all); var += (fo_w * FO_VALUE) ** 2 * (fw + fl)
        total = sum(comp.values())
        toi = num(al["icetime"]) / 60
        se = max(math.sqrt(var), emp_se(g, toi))
        out.append({"id": pid, "name": nm, "team": tm, "pos": pos, "grp": g, "gp": int(num(al["games_played"])), "toi": round(toi, 1),
                    "gaa": round(total, 2), "se": round(se, 2), "lo": round(total - 1.96 * se, 2), "hi": round(total + 1.96 * se, 2),
                    "per60": round(total / (toi / 60), 3) if toi else 0, "comp": {k: round(v, 2) for k, v in comp.items()},
                    "parts": {**{k: round(v, 2) for k, v in parts.items()}, "penalties": round(comp["penalties"], 2), "faceoffs": round(comp["faceoffs"], 2)}})
    for r in goalie_rows:
        if r["season"] != season or r["situation"] != "all" or (team and r["team"] != team):
            continue
        xga, ga, n = num(r["xGoals"]), num(r["goals"]), num(r["unblocked_shot_attempts"])
        total = g_w * (xga - ga)
        toi = num(r["icetime"]) / 60
        se = max(g_w * math.sqrt(max(0.0, xga - n * ep2["all"])), emp_se("G", toi))
        out.append({"id": r["playerId"], "name": r["name"], "team": r["team"], "pos": "G", "grp": "G", "gp": int(num(r["games_played"])),
                    "toi": round(toi, 1), "gaa": round(total, 2), "se": round(se, 2), "lo": round(total - 1.96 * se, 2), "hi": round(total + 1.96 * se, 2),
                    "per60": round(total / (toi / 60), 3) if toi else 0, "comp": {"goaltending": round(total, 2)}, "parts": {"goaltending": round(total, 2)}})
    return out


def age_shift(params, grp_, age, prior_share):
    """Aging adjustment per 60 (fitted on 18 seasons, validated out of sample), applied to the share of the
    estimate that comes from earlier seasons: a 22-year-old's old data understates him now, a 34-year-old's overstates."""
    if age is None:
        return 0.0
    cv = params.get("age", {}).get("curve", {}).get(grp_)
    if cv:   # piecewise-linear: improves by 'up' per year before the peak, declines by 'down' per year after
        d = cv["up"] * (cv["peak"] - age) if age < cv["peak"] else -cv["down"] * (age - cv["peak"])
        return params.get("age_scale", 0.0) * d * prior_share
    ins = params.get("age", {}).get("inseason", {}).get(grp_)
    if not ins:
        return 0.0
    b1, b2 = ins
    return params.get("age_scale", 0.0) * (b1 * (age - 27) + b2 * (age - 27) ** 2) * prior_share


def talent(cur, prev, params, prior_mean=0.0, age=None):
    """True-talent estimate per 60. Pools this season with up to three previous seasons, each season's minutes
    counted at a backtested weight (config/talent_weights.json), then regresses toward the prior (position average,
    or the newcomer average) by reliability T / (T + k). prev: one season row, or a list [last, two ago, three ago]."""
    rp = params["reliability"].get(cur["grp"])
    prevs = prev if isinstance(prev, (list, tuple)) else [prev]
    tw = params.get("talent_w", {}).get(cur["grp"])
    if tw and "prior_w_override" not in params:
        ws, ks = tw["w"], tw.get("kscale", 1.0)
    else:   # legacy: last season only, at weight prior_w
        w0 = params.get("noise", {}).get(cur["grp"], {}).get("prior_w", 1.0) if "prior_w_override" not in params else params["prior_w_override"]
        ws, ks = [w0], 1.0
    T, G, t_prev = cur["toi"], cur["gaa"], 0.0
    for w_, p_ in zip(ws, prevs):
        if p_ and p_.get("grp") == cur["grp"] and p_.get("toi", 0) > 0:
            T += w_ * p_["toi"]; G += w_ * p_["gaa"]; t_prev += w_ * p_["toi"]
    if T <= 0 or not rp:
        return None
    raw60 = G / T * 60
    pm = params.get("prior_model", {}).get(cur["grp"])
    if pm:   # prior = typical player with this much previous NHL ice time (and age), instead of the plain average
        prior_mean = pm["a"] + pm["b"] * math.log1p(t_prev / 1000) + pm.get("c", 0.0) * ((age if age is not None else 27) - 27)
    fn = params.get("_prior_fn")
    if fn:
        prior_mean = fn(cur["grp"], t_prev, age)
    rel = T / (T + rp["k_min"] * ks)
    rate = prior_mean + rel * (raw60 - prior_mean)   # prior: position average (0), or the newcomer average for players with no prior NHL season
    rate += age_shift(params, cur["grp"], age, t_prev / T)
    drift = params.get("noise", {}).get(cur["grp"], {}).get("c", 0.0)
    mult = params.get("noise", {}).get(cur["grp"], {}).get("talent_mult", 1.0)   # calibrated so 95% ranges hold 95% (split-half backtest)
    sd = mult * math.sqrt(rp["var_true60"] * (1 - rel) + drift)
    return {"rate60": rate, "lo60": rate - 1.96 * sd, "hi60": rate + 1.96 * sd, "minutes": T, "rel": rel, "prevMinutes": t_prev}


def box_impact(s, toi_min, pos, params):
    """Box-score approximation of Impact for one game (fallback when no exact MoneyPuck snapshot)."""
    b = params["box"]["D" if pos == "D" else "F"]
    h = toi_min / 60
    x = {"g": s.get("g", 0), "a1": s.get("a1", s.get("a", 0) * 0.55), "a2": s.get("a2", s.get("a", 0) * 0.45), "sog": s.get("sog", 0),
         "hits": s.get("hits", 0), "blk": s.get("blk", 0), "gv": s.get("gv", 0), "tk": s.get("tk", 0), "pm": s.get("pm", 0),
         "pd": s.get("pd", 0), "pt": s.get("pt", 0 if "pd" in s else (1 if s.get("pim", 0) == 5 else s.get("pim", 0) // 2))}
    return sum(b["w"][c] * (x[c] - b["mean"][c] * h) for c in b["w"])


def load_params(base):
    """impact_params.json + calibrated interval noise + aging curve (each written by its own validation script)."""
    import json, os
    p = json.load(open(os.path.join(base, "params", "impact_params.json")))
    for key, fn in (("noise", "interval_params.json"), ("age", "age_params.json"), ("talent_w", "talent_weights.json")):
        path = os.path.join(base, "params", fn)
        if os.path.exists(path):
            p[key] = json.load(open(path))
    if p.get("talent_w", {}).get("prior_model"):
        p["prior_model"] = p["talent_w"]["prior_model"]
    p["age_scale"] = (p.get("age", {}).get("_decision") or {}).get("age_scale", 0.0)
    return p


def ages(base, on_date):
    import csv, os, datetime as dt
    out = {}
    # MoneyPuck's lookup first, then inputs/bio_supplement.csv (NHL API birth dates for players the lookup lacks)
    for name in ("allPlayersLookup.csv", "bio_supplement.csv"):
        path = os.path.join(base, "inputs", name)
        if not os.path.exists(path):
            continue
        for r in csv.DictReader(open(path, encoding="utf-8")):
            if r.get("playerId") in out:
                continue
            try:
                out[r["playerId"]] = (on_date - dt.date.fromisoformat(r["birthDate"])).days / 365.25
            except (ValueError, KeyError, TypeError):
                pass
    return out
