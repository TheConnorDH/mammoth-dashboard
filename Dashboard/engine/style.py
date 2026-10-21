"""Player style tags, derived from his own numbers (descriptive, not predictive): what stands out about how he
plays relative to other NHL players at his position. Pools this season with the previous two (weights 1/.7/.4 on
counts), per-60 rates, league percentiles among position peers with enough ice time."""
import math

W = [1.0, 0.7, 0.4]


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
    peers = {g: [f for f in feats.values() if f["grp"] == g and f["min"] >= 500] for g in ("F", "D")}
    out = {}
    for pid, f in feats.items():
        g = f["grp"]; pr = peers[g]
        if f["rawmin"] < 150:
            out[pid] = {"tags": [], "label": "Not enough NHL ice time yet"}
            continue
        cand = []
        def add(name, p, thr, why):
            if p >= thr:
                cand.append((p, name, why))
        if "relF" in f: add("Play driver", _pct([x["relF"] for x in pr if "relF" in x], f["relF"]), 0.8, "team creates more chances with him on")
        if "relA" in f: add("Shutdown", _pct([x["relA"] for x in pr if "relA" in x], f["relA"], higher=False), 0.8, "team allows fewer chances with him on")
        add("Shooter", _pct([x["ixg60"] for x in pr], f["ixg60"]), 0.8, "generates a lot of shot quality himself")
        if f["shots"] >= 150: add("Finisher", _pct([x["fin60"] for x in pr if x["shots"] >= 150], f["fin60"]), 0.85, "scores more than his shot quality predicts")
        add("Playmaker", _pct([x["a160"] for x in pr], f["a160"]), 0.8, "lots of primary assists")
        add("Physical", _pct([x["hits60"] for x in pr], f["hits60"]), 0.85, "high hit rate")
        add("Shot blocker", _pct([x["blk60"] for x in pr], f["blk60"]), 0.85, "blocks a lot of shots")
        add("Puck thief", _pct([x["tk60"] for x in pr], f["tk60"]), 0.85, "high takeaway rate")
        add("Draws penalties", _pct([x["pd60"] for x in pr], f["pd60"]), 0.85, "draws penalties often")
        add("Penalty-prone", _pct([x["pt60"] for x in pr], f["pt60"]), 0.88, "takes penalties often")
        fw, fl = f["fo"]
        if fw + fl >= 300 and fw / (fw + fl) >= 0.55: cand.append((0.5 + fw / (fw + fl) - 0.5, "Faceoff ace", f"{100 * fw / (fw + fl):.0f}% on faceoffs"))
        if f["pp_ixg60"] is not None and f["pp_pg"] >= (1.5 if g == "F" else 1.2):
            add("Power-play weapon", _pct([x["pp_ixg60"] for x in pr if x["pp_ixg60"] is not None], f["pp_ixg60"]), 0.7, "big power-play shot threat")
        if f["pk_pg"] >= (1.5 if g == "F" else 2.0): cand.append((0.75, "Penalty killer", f"{f['pk_pg']:.1f} PK min/game"))
        cand.sort(reverse=True)
        tags = [{"tag": n, "why": w} for _, n, w in cand[:3]]
        role = ("Top-line minutes" if f["tpg"] >= 18.5 else "Middle-six minutes" if f["tpg"] >= 15 else "Depth minutes") if g == "F" else \
               ("Top-pair minutes" if f["tpg"] >= 22 else "Second-pair minutes" if f["tpg"] >= 19 else "Third-pair minutes")
        out[pid] = {"tags": tags, "label": tags[0]["tag"] if tags else "No standout trait", "role": role}
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
