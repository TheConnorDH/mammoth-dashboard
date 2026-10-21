"""Best possible lineup by talent, respecting real positions: each forward line needs a center, so the top six
forwards must include at least two centers and the twelve at least four; centers can play wing and left/right
wingers are interchangeable. Defense: best four, then the third pair. 'Top' = best 6 F + best 4 D;
'depth' = the next 6 F + 2 D; total adds the starting goalie. Uses talent at a standard workload (ice-time independent).
Teams dressing 11 F + 7 D use the 7th defenseman in the 12th forward slot; teams that haven't dressed enough
players yet get replacement-level fill (flagged 'incomplete')."""


def _take(pool, n=6, centers=2):
    C = [p for p in pool if p.get("pos") == "C"][:centers]
    rest = [p for p in pool if p not in C]
    sel = C + rest[:n - len(C)]
    return sel, [p for p in pool if p not in sel]


def best(players):
    F = sorted([p for p in players if p["g"] == "F"], key=lambda p: -p["tal"])
    D = sorted([p for p in players if p["g"] == "D"], key=lambda p: -p["tal"])
    G = sorted([p for p in players if p["g"] == "G"], key=lambda p: -p["tal"])
    top_f, pool = _take(F)
    dep_f, _ = _take(pool)
    return {"topF": top_f, "topD": D[:4], "depF": dep_f, "depD": D[4:6], "G": G[:1]}


def league(players_league, ppi):
    by = {}
    for p in players_league:
        if not p.get("ng"):
            by.setdefault(p["t"], []).append(p)
    # replacement level (league 10th percentile by position) fills slots a team hasn't dressed anyone for yet,
    # so every team appears; such rows are flagged incomplete
    def _p10(g):
        v = sorted(p["tal"] for p in players_league if p.get("g") == g and not p.get("ng"))
        return v[int(0.10 * (len(v) - 1))] if v else 0.0
    repl = {g: {"n": "replacement level", "pos": g if g != "F" else "F", "tal": _p10(g), "g": g, "id": None} for g in "FDG"}
    rows = []
    for t, L in by.items():
        b = best(L)
        # 11 forwards + 7 defensemen is a real configuration: the 7th defenseman takes the 12th forward slot
        extraD = sorted([p for p in L if p["g"] == "D"], key=lambda p: -p["tal"])[6:]
        while len(b["topF"]) + len(b["depF"]) < 12 and extraD:
            b["depF" if len(b["topF"]) >= 6 else "topF"].append(extraD.pop(0))
        miss = 0
        for k, need, g in (("topF", 6, "F"), ("depF", 6, "F"), ("topD", 4, "D"), ("depD", 2, "D"), ("G", 1, "G")):
            while len(b[k]) < need:
                b[k].append(dict(repl[g])); miss += 1
        s = lambda ps: round(sum(p["tal"] for p in ps) * ppi, 1)
        nm = lambda ps: [f'{p["n"]} ({p["pos"]})' for p in ps]
        rows.append({"team": t, "incomplete": miss, "top": round(s(b["topF"]) + s(b["topD"]), 1), "topF": s(b["topF"]), "topD": s(b["topD"]),
                     "depth": round(s(b["depF"]) + s(b["depD"]), 1), "depF": s(b["depF"]), "depD": s(b["depD"]), "goalie": s(b["G"]),
                     "topNames": nm(b["topF"] + b["topD"]), "depNames": nm(b["depF"] + b["depD"]), "gName": nm(b["G"])})
    for k in ("top", "topF", "topD", "depth", "depF", "depD", "goalie"):
        for i, r in enumerate(sorted(rows, key=lambda r: -r[k])):
            r["rk_" + k] = i + 1
    for r in rows:
        r["total"] = round(r["top"] + r["depth"] + r["goalie"], 1)      # 18 skaters + the starting goalie
    for i, r in enumerate(sorted(rows, key=lambda r: -r["total"])):
        r["rk_total"] = i + 1
    return sorted(rows, key=lambda r: r["rk_total"])
