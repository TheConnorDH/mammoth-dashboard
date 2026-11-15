"""Forward lines and defense pairs, league-wide (MoneyPuck's season line file, 5v5): results, how they get them, and how
they compare with what their players' talent predicts. Descriptive: line samples are small and combinations change,
so every rate carries an uncertainty band and the page marks which lines have played enough together ("qualified")."""
import math


def _n(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


QUAL = {"line": 2.5, "pairing": 3.5}     # qualified: 5v5 minutes together per team game (a line that plays together regularly)


def build(rows, season, ep2_5v5, players, team_gp):
    """rows: MoneyPuck lines.csv rows. players: playersLeague rows (id -> talent in goals, name). team_gp: {team: GP}.
    Returns (lines, fit) where fit = how combined talent predicts xG share (weighted least squares over lines)."""
    P = {p["id"]: p for p in players or []}
    out = []
    for r in rows:
        if r.get("season") != season or r.get("situation") != "5on5" or r.get("position") not in ("line", "pairing"):
            continue
        typ = r["position"]; lid = str(r["lineId"]); k = 3 if typ == "line" else 2
        ids = [lid[i * 7:(i + 1) * 7] for i in range(k)] if len(lid) == 7 * k else []
        toi = _n(r["icetime"]) / 60; h = toi / 60
        if toi <= 0:
            continue
        F, A = _n(r["xGoalsFor"]), _n(r["xGoalsAgainst"]); uF, uA = _n(r["unblockedShotAttemptsFor"]), _n(r["unblockedShotAttemptsAgainst"])
        se = math.sqrt(A * A * uF * ep2_5v5 + F * F * uA * ep2_5v5) / (F + A) ** 2 if F + A else None
        mem = [P.get(i) for i in ids]
        tal = [m["tal"] for m in mem if m and m.get("tal") is not None]
        out.append({
            "t": r["team"], "ty": "L" if typ == "line" else "P", "ids": ids,
            # member names in id order when every member is known; otherwise MoneyPuck's own label (surnames, alphabetical)
            "nm": [m["n"] for m in mem] if ids and all(mem) else [r["name"].replace("-", " – ")],
            "toi": round(toi, 1), "gp": int(_n(r["games_played"])),
            "xgf": round(F / (F + A), 3) if F + A else None, "se": round(se, 3) if se else None,
            "gf": int(_n(r["goalsFor"])), "ga": int(_n(r["goalsAgainst"])),
            "xf60": round(F / h, 2), "xa60": round(A / h, 2),
            "sh60": round(uF / h, 1), "sa60": round(uA / h, 1),
            "hd60": round(_n(r["highDangerShotsFor"]) / h, 2), "hda60": round(_n(r["highDangerShotsAgainst"]) / h, 2),
            "q": round(F / uF, 4) if uF else None,                       # expected goals per unblocked shot (shot quality)
            "reb60": round(_n(r["reboundsFor"]) / h, 2),
            "fin60": round((_n(r["goalsFor"]) - F) / h, 2),            # goals above expected per 60 (mostly luck over a season)
            "tal": round(sum(tal), 2) if len(tal) == len(ids) and ids else None,   # combined talent of the members (goals / 84 GP each)
            "qmin": round(QUAL[typ] * (team_gp.get(r["team"], 0) or 0), 1),
        })
    # expected xG share from combined talent (separately for lines and pairs), fit across the league weighted by minutes
    fit = {}
    for ty in ("L", "P"):
        L = [x for x in out if x["ty"] == ty and x["tal"] is not None and x["xgf"] is not None]
        if len(L) >= 20:
            w = [x["toi"] for x in L]; sw = sum(w)
            mx = sum(wi * x["tal"] for wi, x in zip(w, L)) / sw; my = sum(wi * x["xgf"] for wi, x in zip(w, L)) / sw
            vxx = sum(wi * (x["tal"] - mx) ** 2 for wi, x in zip(w, L)); vxy = sum(wi * (x["tal"] - mx) * (x["xgf"] - my) for wi, x in zip(w, L))
            b = vxy / vxx if vxx else 0.0; a = my - b * mx
            fit[ty] = {"a": round(a, 4), "b": round(b, 5), "n": len(L)}
            for x in out:
                if x["ty"] == ty and x["tal"] is not None:
                    x["exp"] = round(a + b * x["tal"], 3)
    return out, fit
