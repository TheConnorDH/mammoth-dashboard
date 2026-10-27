"""Player style tags, derived from his own numbers (descriptive, not predictive): what stands out about how he
plays relative to other NHL players at his position. Pools this season with the previous two (weights 1/.7/.4 on
counts), per-60 rates shrunk toward the position mean by ice time, league percentiles among position peers with
enough ice time. Only traits that repeat from season to season are tagged (params/style_params.json); one weak
spot at most; a player with no tag gets his strongest trait, labeled as such."""
import bisect, json, math, os

W = [1.0, 0.7, 0.4]


def _ord(n):
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _pool(seasons_rows):
    """seasons_rows: list of skater-row lists [current, last, two ago] -> {pid: {sit: {col: weighted sum}}}"""
    out, info = {}, {}
    for w, rows in zip(W, seasons_rows):
        for r in rows or []:
            sit = r.get("situation")
            if sit not in ("all", "5on5", "5on4", "4on5"):
                continue
            pid = r["playerId"]
            info.setdefault(pid, r.get("position"))
            d = out.setdefault(pid, {}).setdefault(sit, {})
            d["rawmin"] = d.get("rawmin", 0.0) + num(r.get("icetime")) / 60 if sit == "all" else d.get("rawmin", 0.0)
            for c in ("icetime", "games_played", "I_F_xGoals", "I_F_goals", "I_F_primaryAssists", "I_F_hits", "shotsBlockedByPlayer",
                      "I_F_takeaways", "penaltiesDrawn", "penalties", "faceoffsWon", "faceoffsLost", "OnIce_F_xGoals", "OnIce_A_xGoals",
                      "OffIce_F_xGoals", "OffIce_A_xGoals", "timeOnBench", "I_F_unblockedShotAttempts"):
                d[c] = d.get(c, 0.0) + w * num(r.get(c))
    return out, info


def _pct(vals, v, higher=True):
    if not vals:
        return 0.0
    below = sum(1 for x in vals if (x < v if higher else x > v))
    return below / len(vals)


def build(skater_seasons, goalie_seasons=None):
    P, info = _pool(skater_seasons)
    feats = {}
    for pid, d in P.items():
        a = d.get("all"); e = d.get("5on5"); pp = d.get("5on4"); pk = d.get("4on5")
        if not a or a["icetime"] <= 0:
            continue
        h = a["icetime"] / 3600; gp = max(a["games_played"], 1e-9)
        f = {"min": a["icetime"] / 60, "rawmin": a.get("rawmin", a["icetime"] / 60), "grp": "D" if info[pid] == "D" else "F",
             "ixg60": a["I_F_xGoals"] / h, "fin60": (a["I_F_goals"] - a["I_F_xGoals"]) / h, "a160": a["I_F_primaryAssists"] / h,
             "hits60": a["I_F_hits"] / h, "blk60": a["shotsBlockedByPlayer"] / h, "tk60": a["I_F_takeaways"] / h,
             "pd60": a["penaltiesDrawn"] / h, "pt60": a["penalties"] / h, "tpg": a["icetime"] / 60 / gp,
             "fo": (a["faceoffsWon"], a["faceoffsLost"]), "shots": a["I_F_unblockedShotAttempts"]}
        if e and e["icetime"] > 0 and e["timeOnBench"] > 0:
            he, hb = e["icetime"] / 3600, e["timeOnBench"] / 3600
            f["relF"] = e["OnIce_F_xGoals"] / he - e["OffIce_F_xGoals"] / hb
            f["relA"] = e["OnIce_A_xGoals"] / he - e["OffIce_A_xGoals"] / hb
        f["pp_pg"] = (pp["icetime"] / 60 / gp) if pp else 0.0
        f["pp_ixg60"] = (pp["I_F_xGoals"] / (pp["icetime"] / 3600)) if pp and pp["icetime"] > 600 else None
        f["pk_pg"] = (pk["icetime"] / 60 / gp) if pk else 0.0
        feats[pid] = f
    # validated rules (params/style_params.json): shrink each rate toward the position mean by pooled minutes, then
    # percentile among position peers with 500+ pooled minutes; each tag's cut is set so that most tagged players
    # still show the trait next season
    SP = json.load(open(os.path.join(os.path.dirname(__file__), "..", "params", "style_params.json")))
    elig = {g: [f for f in feats.values() if f["grp"] == g and f["rawmin"] >= 150] for g in ("F", "D")}
    peers = {g: [f for f in elig[g] if f["min"] >= 500] for g in ("F", "D")}
    keys = {r["feat"]: r["k"] for r in list(SP["tags"].values()) + list(SP["weak"].values())}
    for g in ("F", "D"):
        for c, k in keys.items():
            vals = [f[c] for f in elig[g] if f.get(c) is not None]
            mu = sum(vals) / len(vals) if vals else 0.0
            for f in elig[g]:
                if f.get(c) is not None:
                    f["s_" + c] = mu + (f[c] - mu) * (f["min"] / (f["min"] + k) if k else 1.0)
    pv = {(g, c): sorted(f["s_" + c] for f in peers[g] if "s_" + c in f) for g in ("F", "D") for c in keys}
    def pct(g, c, f):
        v = f.get("s_" + c); L = pv[(g, c)]
        return None if v is None or not L else bisect.bisect_left(L, v) / len(L)
    out = {}
    for pid, f in feats.items():
        g = f["grp"]
        if f["rawmin"] < 150:
            out[pid] = {"tags": [], "label": "Not enough NHL ice time yet"}
            continue
        cand, weak = [], []
        for name, r in SP["tags"].items():
            p = pct(g, r["feat"], f)
            if p is not None and p >= r["thr"]:
                cand.append((p, name, r["why"]))
        fw, fl = f["fo"]
        if fw + fl >= 300 and fw / (fw + fl) >= 0.55: cand.append((0.5 + fw / (fw + fl) - 0.5, "Faceoff ace", f"{100 * fw / (fw + fl):.0f}% on faceoffs"))
        if f["pp_ixg60"] is not None and f["pp_pg"] >= (1.5 if g == "F" else 1.2):
            pr = [x for x in peers[g] if x["pp_ixg60"] is not None]
            p = sum(1 for x in pr if x["pp_ixg60"] < f["pp_ixg60"]) / len(pr) if pr else 0
            if p >= 0.7: cand.append((p, "Power-play weapon", "big power-play shot threat"))
        if f["pk_pg"] >= (1.5 if g == "F" else 2.0): cand.append((0.75, "Penalty killer", f"{f['pk_pg']:.1f} PK min/game"))
        for name, r in SP["weak"].items():
            p = pct(g, r["feat"], f)
            if p is None:
                continue
            if (r["side"] == "high" and p >= r["thr"]) or (r["side"] == "low" and p <= 1 - r["thr"]):
                weak.append((abs(p - 0.5), name, r["why"]))
        cand.sort(reverse=True); weak.sort(reverse=True)
        tags = [{"tag": n, "why": w} for _, n, w in cand[:3]]
        if weak:
            tags.append({"tag": weak[0][1], "why": weak[0][2], "kind": "weak"})
        if not cand:   # no trait clears the bar: name his strongest one, clearly as a relative strength
            best = max(((pct(g, r["feat"], f), r["feat"]) for r in SP["tags"].values() if pct(g, r["feat"], f) is not None), default=None)
            if best:
                tags.insert(0, {"tag": f"Best trait: {SP['best_label'][best[1]]}", "why": f"{_ord(round(best[0] * 100))} percentile among {'forwards' if g == 'F' else 'defensemen'}; no trait clears the tag bar", "kind": "best"})
        role = ("Top-line minutes" if f["tpg"] >= 18.5 else "Middle-six minutes" if f["tpg"] >= 15 else "Depth minutes") if g == "F" else \
               ("Top-pair minutes" if f["tpg"] >= 22 else "Second-pair minutes" if f["tpg"] >= 19 else "Third-pair minutes")
        out[pid] = {"tags": tags, "label": cand[0][1] if cand else "No standout trait", "role": role}
    # goalies
    for gw, rows in zip(W, goalie_seasons or []):
        pass
    if goalie_seasons:
        G = {}
        for w, rows in zip(W, goalie_seasons):
            for r in rows or []:
                if r.get("situation") != "all":
                    continue
                d = G.setdefault(r["playerId"], {"gp": 0.0, "min": 0.0, "hdx": 0.0, "hdg": 0.0, "x": 0.0, "g": 0.0, "reb": 0.0, "sog": 0.0, "gpLast": 0.0})
                d["gp"] += w * num(r["games_played"]); d["min"] += w * num(r["icetime"]) / 60
                if w == W[1]: d["gpLast"] = num(r["games_played"])
                d["hdx"] += w * num(r.get("highDangerxGoals")); d["hdg"] += w * num(r.get("highDangerGoals"))
                d["x"] += w * num(r["xGoals"]); d["g"] += w * num(r["goals"]); d["reb"] += w * num(r.get("rebounds")); d["sog"] += w * num(r.get("ongoal"))
        pool = [d for d in G.values() if d["min"] >= 1500]
        for pid, d in G.items():
            if d["min"] < 300:
                out[pid] = {"tags": [], "label": "Not enough NHL ice time yet"}; continue
            hd = (d["hdx"] - d["hdg"]) / (d["min"] / 60); reb = d["reb"] / max(d["sog"], 1)
            cand = []
            p = _pct([(x["hdx"] - x["hdg"]) / (x["min"] / 60) for x in pool], hd)
            if p >= 0.75: cand.append((p, "High-danger stopper", "saves more of the dangerous chances than expected"))
            p = _pct([x["reb"] / max(x["sog"], 1) for x in pool], reb, higher=False)
            if p >= 0.75: cand.append((p, "Rebound control", "allows few rebounds"))
            ov = (d["x"] - d["g"]) / (d["min"] / 60)
            p = _pct([(x["x"] - x["g"]) / (x["min"] / 60) for x in pool], ov)
            if p >= 0.8: cand.append((p, "Above-expected goalie", "saves more than expected overall"))
            cand.sort(reverse=True)
            out[pid] = {"tags": [{"tag": n, "why": w} for _, n, w in cand[:2]], "label": cand[0][1] if cand else "No standout trait",
                        "role": "Starter workload" if d["gpLast"] >= 45 else "Backup / split workload"}
    return out
