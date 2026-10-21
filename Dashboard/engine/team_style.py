"""Team style tags (descriptive, not predictive): what stands out about how each team plays, relative to the
rest of the league. Pools this season with last season (last season counted at half weight, so this season
takes over by about midseason), then tags traits in the league's top or bottom ~20%."""

LAST_W = 0.5


def _n(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _pool(cur_rows, last_rows, season_cur, season_last):
    out = {}
    for rows, s, w in ((cur_rows, season_cur, 1.0), (last_rows, season_last, LAST_W)):
        for r in rows:
            if r.get("season") != s or r.get("position", "Team Level") != "Team Level":
                continue
            d = out.setdefault(r["team"], {}).setdefault(r["situation"], {})
            for k, v in r.items():
                if k in ("team", "season", "name", "team.1", "position", "situation"):
                    continue
                d[k] = d.get(k, 0.0) + w * _n(v)
    return out


def _pct(vals, v):
    return sum(1 for x in vals if x < v) / max(1, len(vals) - 1)


def build(cur_rows, last_rows, season_cur="2026", season_last="2025", players=None, cur_gp=None):
    P = _pool(cur_rows, last_rows, season_cur, season_last)
    F = {}
    for t, d in P.items():
        a, e, pp, pk = d.get("all"), d.get("5on5"), d.get("5on4"), d.get("4on5")
        if not a or not e or a.get("iceTime", 0) <= 0 or e.get("iceTime", 0) <= 0:
            continue
        ha, he = a["iceTime"] / 3600, e["iceTime"] / 3600
        f = {
            "pace": (e["shotAttemptsFor"] + e["shotAttemptsAgainst"]) / he,
            "cf": e["shotAttemptsFor"] / max(1, e["shotAttemptsFor"] + e["shotAttemptsAgainst"]),
            "quality": e["xGoalsFor"] / max(1, e["unblockedShotAttemptsFor"]),
            "volume": e["unblockedShotAttemptsFor"] / he,
            "xga": e["xGoalsAgainst"] / he,
            "hdAgainst": e["highDangerShotsAgainst"] / max(1, e["unblockedShotAttemptsAgainst"]),
            "rebounds": a["reboundsFor"] / max(1, a["unblockedShotAttemptsFor"]),
            "hits": a["hitsFor"] / ha,
            "blocks": a["blockedShotAttemptsAgainst"] / ha,
            "takeaways": a["takeawaysFor"] / ha,
            "penTaken": a["penaltiesFor"] / ha,
            "penDrawn": a["penaltiesAgainst"] / ha,
            "fo": a["faceOffsWonFor"] / max(1, a["faceOffsWonFor"] + a["faceOffsWonAgainst"]),
            "finish": (a["goalsFor"] - a["xGoalsFor"]) / max(1, a["xGoalsFor"]),
            "goalie": (a["xGoalsAgainst"] - a["goalsAgainst"]) / max(1, a["xGoalsAgainst"]),
        }
        if pp and pp.get("iceTime", 0) > 0:
            f["pp"] = pp["xGoalsFor"] / (pp["iceTime"] / 3600)
        if pk and pk.get("iceTime", 0) > 0:
            f["pk"] = pk["xGoalsAgainst"] / (pk["iceTime"] / 3600)
        F[t] = f
    # roster age and star concentration (from the league player table)
    if players:
        by = {}
        for p in players:
            if p.get("ng") or p.get("g") == "G":
                continue
            by.setdefault(p["t"], []).append(p)
        for t, L in by.items():
            if t not in F:
                continue
            L = sorted(L, key=lambda p: -(p.get("tpg") or 0))[:18]
            mins = sum(p.get("tpg") or 0 for p in L) or 1
            F[t]["age"] = sum((p.get("age") or 27) * (p.get("tpg") or 0) for p in L) / mins
            pos = sorted([max(p["tal"], 0) for p in L], reverse=True)
            F[t]["star"] = sum(pos[:3]) / max(sum(pos), 1e-9)
            F[t]["depth"] = sum(1 for p in L if (p.get("tpct") or 0) >= 50)
    teams = list(F)
    col = lambda k: [F[t][k] for t in teams if k in F[t]]
    rules = [  # (feature, high or low, threshold, tag, why)
        ("pace", "high", .8, "High-event", "lots of shot attempts both ways"),
        ("pace", "low", .2, "Low-event", "few shot attempts either way"),
        ("cf", "high", .8, "Puck possession", "out-attempts opponents at 5v5"),
        ("quality", "high", .8, "Quality over quantity", "high-danger looks per shot"),
        ("volume", "high", .8, "Shoots from everywhere", "high shot volume"),
        ("xga", "low", .2, "Stingy defense", "allows little shot quality at 5v5"),
        ("xga", "high", .8, "Leaky defense", "allows a lot of shot quality at 5v5"),
        ("hdAgainst", "low", .2, "Protects the slot", "few high-danger shots against"),
        ("rebounds", "high", .8, "Crashes the net", "creates a lot of rebounds"),
        ("hits", "high", .85, "Physical", "high hit rate"),
        ("blocks", "high", .85, "Blocks shots", "blocks a lot of shots"),
        ("takeaways", "high", .85, "Forechecking / takeaways", "high takeaway rate"),
        ("penTaken", "low", .15, "Disciplined", "takes few penalties"),
        ("penTaken", "high", .85, "Undisciplined", "takes a lot of penalties"),
        ("penDrawn", "high", .85, "Draws penalties", "earns a lot of power plays"),
        ("fo", "high", .85, "Wins faceoffs", "strong on the dot"),
        ("pp", "high", .8, "Dangerous power play", "creates a lot of PP chances"),
        ("pk", "low", .2, "Strong penalty kill", "allows little on the PK"),
        ("finish", "high", .85, "Finishing team", "scores more than shot quality predicts (partly luck)"),
        ("goalie", "high", .85, "Goaltending-driven", "goalies save more than expected"),
        ("age", "low", .15, "Young roster", "minutes go to young players"),
        ("age", "high", .85, "Veteran roster", "minutes go to experienced players"),
        ("star", "high", .85, "Star-driven", "talent concentrated in a few players"),
        ("depth", "high", .85, "Deep lineup", "many above-median players"),
    ]
    out = {}
    for t, f in F.items():
        cand = []
        for k, side, thr, tag, why in rules:
            if k not in f:
                continue
            p = _pct(col(k), f[k])
            if (side == "high" and p >= thr) or (side == "low" and p <= thr):
                cand.append((abs(p - 0.5), tag, why))
        cand.sort(reverse=True)
        ranks = {k: sorted(teams, key=lambda x: -F[x].get(k, -1e9)).index(t) + 1 for k in f}
        out[t] = {"tags": [{"tag": n, "why": w} for _, n, w in cand[:4]], "label": cand[0][1] if cand else "Balanced", "ranks": ranks, "n": len(teams),
                  "mostlyLastSeason": bool(cur_gp is not None and cur_gp.get(t, 0) < 15)}
    return out
