"""Fit and validate the Player Impact model on 2008-09..2025-26. Writes config/impact_params.json.
Run after adding a season of history. ~1 minute."""
import csv, json, os, sys, pickle, statistics as st
import numpy as np
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [_HERE, os.path.join(os.path.dirname(_HERE), "engine"), os.path.dirname(_HERE)]
import impact, gaa
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the Dashboard folder
H = os.path.join(BASE, "inputs", "history", "moneypuck"); SRC = os.path.join(os.path.dirname(BASE), "Source Data")


def load(p, sits=None):
    with open(p, newline="") as fh:
        return [r for r in csv.DictReader(fh) if not sits or r.get("situation") in sits]


def load_all():
    # cache lives on local scratch disk (rebuilt automatically if missing), not in the synced folder
    cdir = os.environ.get("MAMMOTH_CACHE", os.path.join(os.path.expanduser("~"), ".mammoth_cache"))
    os.makedirs(cdir, exist_ok=True)
    cache = os.path.join(cdir, "hist_cache.pkl")
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    sits = {"all", "5on5", "5on4", "4on5"}
    sk = load(os.path.join(H, "skaters_2008_to_2024.csv"), sits) + load(os.path.join(SRC, "skaters.csv"), sits)
    gl = load(os.path.join(H, "goalies_2008_to_2024.csv")) + load(os.path.join(SRC, "goalies.csv"))
    tm = load(os.path.join(H, "teams_2008_to_2024.csv")) + load(os.path.join(SRC, "teams.csv"))
    d = (sk, gl, tm); pickle.dump(d, open(cache, "wb")); return d


def wfit(x, y, w):
    X = np.c_[np.ones(len(x)), x]; sw = np.sqrt(w)
    return np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)[0][1]


def zone_start_effects(tables, seasons):
    """Mechanical effect of one net offensive-zone start on relative xGF / shot attempts, from the same
    player's season-to-season change in deployment (player talent mostly cancels in the difference)."""
    out = {}
    for g in ("F", "D"):
        out[g] = {}
        for c in ("rel_xgf", "rel_cf"):
            dx, dy, w = [], [], []
            for i in range(len(seasons) - 1):
                P1, i1, _ = tables[seasons[i]]; P2, _, _ = tables[seasons[i + 1]]
                for (pid, sit), f in P1.items():
                    if sit != "5on5" or f["h"] < 5 or pid not in i1 or impact.grp(i1[pid][2]) != g:
                        continue
                    f2 = P2.get((pid, "5on5"))
                    if not f2 or f2["h"] < 5:
                        continue
                    dx.append(f2["ozs"] / f2["h"] - f["ozs"] / f["h"]); dy.append(f2[c] / f2["h"] - f[c] / f["h"]); w.append(1 / (1 / f["h"] + 1 / f2["h"]))
            out[g][c] = round(float(wfit(np.array(dx), np.array(dy), np.array(w))), 4)
    return out


def yoy(seasons, imp, g, val):
    xs, ys, hs = [], [], []
    for i in range(len(seasons) - 1):
        a, b = imp[seasons[i]], imp[seasons[i + 1]]
        for pid in set(a) & set(b):
            ra, rb = a[pid], b[pid]
            if ra["grp"] != g or rb["grp"] != g or ra["toi"] < 500 or rb["toi"] < 500:
                continue
            xs.append(val(ra) / ra["toi"] * 60); ys.append(val(rb) / rb["toi"] * 60); hs.append(2 / (1 / ra["toi"] + 1 / rb["toi"]))
    r_ = float(np.corrcoef(xs, ys)[0, 1]); T = float(np.mean(hs))
    return r_, T, float(np.var(xs)), len(xs)


BOX_COLS = ["g", "a1", "a2", "sog", "hits", "blk", "gv", "tk", "pm", "pd", "pt"]


def box_row(al, e):
    n = impact.num
    return {"g": n(al["I_F_goals"]), "a1": n(al["I_F_primaryAssists"]), "a2": n(al["I_F_secondaryAssists"]), "sog": n(al["I_F_shotsOnGoal"]),
            "hits": n(al["I_F_hits"]), "blk": n(al["shotsBlockedByPlayer"]), "gv": n(al["I_F_giveaways"]), "tk": n(al["I_F_takeaways"]),
            "pm": (n(e["OnIce_F_goals"]) - n(e["OnIce_A_goals"])) if e else 0.0, "pd": n(al["penaltiesDrawn"]), "pt": n(al["penalties"])}


def fit_box(bys, byg, imp, seasons, say):
    out = {}
    for g in ("F", "D"):
        X, y, w, means = [], [], [], {}
        rows = []
        for s in seasons:
            d = {}
            for r in bys[s]:
                if r["situation"] in ("all", "5on5"):
                    d.setdefault(r["playerId"], {})[r["situation"]] = r
            for pid, dd in d.items():
                al = dd.get("all")
                if not al or impact.grp(al["position"]) != g or pid not in imp[s]:
                    continue
                h = impact.num(al["icetime"]) / 3600
                if h < 200 / 60:
                    continue
                rows.append((box_row(al, dd.get("5on5")), h, imp[s][pid]["gaa"] / h))
        H = sum(h for _, h, _ in rows)
        means = {c: sum(b[c] for b, _, _ in rows) / H for c in BOX_COLS}
        X = np.array([[b[c] / h - means[c] for c in BOX_COLS] for b, h, _ in rows]); y = np.array([t for _, _, t in rows]); w = np.array([h for _, h, _ in rows])
        coef = impact.wls(X, y, w, lam=1e-4)
        pred = X @ coef
        r2 = float(impact.wcorr(pred, y, w)) ** 2
        out[g] = {"w": dict(zip(BOX_COLS, [round(float(v), 4) for v in coef])), "mean": means, "r2": round(r2, 3)}
        say(f"box-score approximation {g}: R^2 vs. full Impact {r2:.2f}; weights " + ", ".join(f"{c} {v:+.3f}" for c, v in out[g]["w"].items()))
    return out


def main():
    sk, gl, tm = load_all()
    # baseline: keep whatever the current config uses unless overridden (REL_TEAMAVG=0/1) for a comparison run
    cur_cfg = os.path.join(BASE, "params", "impact_params.json")
    default = json.load(open(cur_cfg)).get("rel_teamavg", True) if os.path.exists(cur_cfg) else True
    impact.REL_TEAMAVG = os.environ.get("REL_TEAMAVG", "1" if default else "0") == "1"
    seasons = sorted({r["season"] for r in tm})
    bys, byg = {}, {}
    for r in sk: bys.setdefault(r["season"], []).append(r)
    for r in gl: byg.setdefault(r["season"], []).append(r)
    log = []
    def say(s):
        print(s, flush=True); log.append(s)
    # 1. zone starts
    raw = {s: impact.season_table(bys[s], tm, s) for s in seasons}
    zs = zone_start_effects(raw, seasons)
    impact.ZS.update(zs)
    say(f"zone-start adjustment per net OZ start: {zs}")
    tables = {s: impact.season_table(bys[s], tm, s) for s in seasons}
    # 2. skater weights
    say("skater weights (target: on-ice goal differential relative to team in the season before and after):")
    W, rep = impact.fit_all(tables, seasons, log=say)
    params = {"weights": W, "report": rep, "zs": zs, "rel_teamavg": impact.REL_TEAMAVG, "pen_w": 1.0, "fo_w": 1.0, "goalie_w": 1.0, "scale": {}, "reliability": {}}
    # 3. descriptive scale: undo the noise attenuation the regression builds in (so a season or game total
    #    describes what happened, and the talent step does the regressing explicitly)
    imp = {s: {r["id"]: r for r in impact.compute(bys[s], byg.get(s, []), tm, s, params)} for s in seasons}
    spm = lambda r: r["gaa"] - r["comp"].get("penalties", 0) - r["comp"].get("faceoffs", 0)
    for g in ("F", "D"):
        r_, T, _, n = yoy(seasons, imp, g, spm)
        params["scale"][g] = round(1 / r_, 3)
        say(f"descriptive scale {g}: 1/{r_:.3f} (year-to-year r at ~{T:.0f} min, n={n})")
    # 4. reliability of the final total, by position (sets talent shrinkage and empirical noise)
    imp = {s: {r["id"]: r for r in impact.compute(bys[s], byg.get(s, []), tm, s, params)} for s in seasons}
    for g in ("F", "D", "G"):
        r_, T, vobs, n = yoy(seasons, imp, g, lambda r: r["gaa"])
        k = T * (1 - r_) / r_
        params["reliability"][g] = {"r_yoy": round(r_, 3), "k_min": round(k), "var_true60": vobs * r_, "T": round(T), "n": n}
        say(f"reliability {g}: r={r_:.3f} at ~{T:.0f} min -> half-signal at {k:.0f} min; true spread sd {(vobs * r_) ** .5:.3f} per 60 (n={n})")
    # 5. strict out-of-sample comparison vs old model and points
    tgt = {}
    for s in seasons:
        P, info, means = tables[s]; tgt[s] = {}
        for (pid, sit), f in P.items():
            if sit == "5on5" and f["h"] >= 5 and "t_relGF60" in f and pid in info:
                m = means[("5on5", impact.grp(info[pid][2]))]
                tgt[s][pid] = ((f["t_relGF60"] - m["t_relGF60"]) - (f["t_relGA60"] - m["t_relGA60"]), f["h"])
    def oos(model, grp_=None):
        xs, ys, ws = [], [], []
        for i, s in enumerate(seasons):
            for pid, r in model[s].items():
                if r.get("grp") == "G" or r["toi"] < 500 or (grp_ and r.get("grp") != grp_): continue
                tv = th = 0.0
                for j in (i - 1, i + 1):
                    if 0 <= j < len(seasons) and pid in tgt[seasons[j]]:
                        y2, h2 = tgt[seasons[j]][pid]; tv += y2 * h2; th += h2
                if th: xs.append(r["gaa"] / r["toi"] * 60); ys.append(tv / th); ws.append(th)
        xs, ys, ws = map(np.array, (xs, ys, ws))
        return round(float(impact.wcorr(xs, ys, ws)), 3), len(xs)
    loso = {}
    for i, s in enumerate(seasons):
        keep = [x for x in seasons if x not in {seasons[j] for j in range(i - 2, i + 3) if 0 <= j < len(seasons)}]
        Wl = {}
        for (sit, side), cols in impact.FEATS.items():
            for g in ("F", "D"):
                X, y, w, ss = impact.build_pairs(tables, seasons, sit, side, g)
                m = np.isin(ss, keep)
                Wl[f"{sit}|{side}|{g}"] = dict(zip(cols, [float(v) for v in impact.wls(X[m], y[m], w[m])]))
        pl = dict(params); pl["weights"] = Wl
        loso[s] = {r["id"]: r for r in impact.compute(bys[s], byg.get(s, []), tm, s, pl)}
    old = {s: {r["id"]: r for r in gaa.compute(bys[s], byg.get(s, []), tm, s, play_w=0.4, shoot_s=0.35)} for s in seasons}
    pts = {}
    for s in seasons:
        rows_ = [r for r in bys[s] if r["situation"] == "all" and float(r["icetime"]) > 0]
        pm_ = {}
        for g in ("F", "D"):   # centre points/60 by position so the pooled comparison is fair
            rr = [r for r in rows_ if impact.grp(r["position"]) == g]
            pm_[g] = sum(float(r["I_F_points"]) for r in rr) / (sum(float(r["icetime"]) for r in rr) / 3600)
        pts[s] = {r["playerId"]: {"toi": float(r["icetime"]) / 60, "grp": impact.grp(r["position"]),
                                  "gaa": float(r["I_F_points"]) - pm_[impact.grp(r["position"])] * float(r["icetime"]) / 3600} for r in rows_}
    val = {}
    for nm, mdl in (("impact", loso), ("old_gaa", old), ("points60", pts)):
        val[nm] = {"all": oos(mdl)[0], "F": oos(mdl, "F")[0], "D": oos(mdl, "D")[0]}
    val["n"] = oos(loso)[1]
    say(f"out-of-sample r vs. relative on-ice goal differential in other seasons: {val}")
    # 6. what drives the metric (latest season, 500+ min skaters)
    R = [r for r in imp[seasons[-1]].values() if r["grp"] != "G" and r["toi"] >= 500]
    tot = [r["gaa"] for r in R]; vt = st.pvariance(tot); mt = st.mean(tot)
    drivers = {}
    for k in sorted({k for r in R for k in r["parts"]}):
        x = [r["parts"].get(k, 0) for r in R]; mx = st.mean(x)
        drivers[k] = round(sum((a - mx) * (b - mt) for a, b in zip(x, tot)) / len(x) / vt * 100, 1)
    say(f"share of player-to-player differences by input ({seasons[-1]}): {drivers}")
    # 7. box-score version (fallback for games without an exact MoneyPuck snapshot): best linear
    #    approximation of the full Impact from what the NHL box score records, fitted on 5 recent seasons
    params["box"] = fit_box(bys, byg, imp, seasons[-5:], say)
    params.update({"validation": val, "drivers": drivers, "seasons": seasons, "log": log})
    json.dump(params, open(os.path.join(BASE, "params", os.environ.get("IMPACT_OUT", "impact_params.json")), "w"), indent=1)
    say("wrote config/impact_params.json")


if __name__ == "__main__":
    main()
