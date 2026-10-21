"""Player profiles: where a skater ranks within his position group (F or D) on each part of his game, plus how he is
used, his size and where he shoots from; and his most similar players league-wide.

Skill components are the Player Impact parts (goals vs. an average player at his position), pooled over this season
and up to three previous seasons with the talent weights, then shrunk toward average by how repeatable each
component is: shrunk = rate x n / (n + k), with k = typical minutes x (1 - r) / r and r = the component's
year-to-year correlation (per 60, players with 500+ minutes in consecutive seasons, 2023-24 to 2025-26).
Descriptive, not predictive: the profile says how a player has played, the talent number says how good he is."""
import math
import numpy as np

COMPS = ["play_driving", "shot_creation", "finishing", "playmaking", "defense", "puck_battles", "penalties", "faceoffs"]
USAGE = ["toi", "pp", "pk", "oz", "hits", "blocks", "hd"]
USAGE_LABEL = {"toi": "Ice time per game", "pp": "Power-play share", "pk": "Penalty-kill share", "oz": "Offensive-zone starts",
               "hits": "Hits per 60", "blocks": "Blocked shots per 60", "hd": "High-danger share of his shots"}


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def reliability(seasons, min_minutes=500):
    """seasons: list of {pid: player dict with grp, toi (minutes), parts}, oldest first. Returns {grp: {comp: {r, k}}}."""
    out = {}
    for g in ("F", "D"):
        out[g] = {}
        for c in COMPS:
            xs, ys, mins = [], [], []
            for a, b in zip(seasons[:-1], seasons[1:]):
                for pid, p in a.items():
                    q = b.get(pid)
                    if not q or p.get("grp") != g or q.get("grp") != g or p.get("toi", 0) < min_minutes or q.get("toi", 0) < min_minutes:
                        continue
                    xs.append(p["parts"].get(c, 0.0) / p["toi"] * 60); ys.append(q["parts"].get(c, 0.0) / q["toi"] * 60)
                    mins.append((p["toi"] + q["toi"]) / 2)
            if len(xs) < 30 or np.std(xs) == 0 or np.std(ys) == 0:
                out[g][c] = {"r": 0.05, "k": 1e6, "n": len(xs)}
                continue
            r = float(np.clip(np.corrcoef(xs, ys)[0, 1], 0.02, 0.95)); mbar = float(np.mean(mins))
            out[g][c] = {"r": round(r, 3), "k": round(mbar * (1 - r) / r, 1), "n": len(xs)}
    return out


def pooled_components(cur, prevs, w, rel):
    """cur/prevs: Impact dicts (parts in goals, toi in minutes). w: weights of previous seasons (current = 1)."""
    g = cur["grp"]
    num = {c: cur.get("parts", {}).get(c, 0.0) for c in COMPS}; den = cur.get("toi", 0.0)
    for wi, p in zip(w, prevs):
        if p and p.get("grp") == g and p.get("toi", 0) > 0:
            for c in COMPS:
                num[c] += wi * p.get("parts", {}).get(c, 0.0)
            den += wi * p["toi"]
    out = {}
    for c in COMPS:
        rate = num[c] / den * 60 if den > 0 else 0.0
        k = rel[g][c]["k"]
        out[c] = rate * den / (den + k) if den > 0 else 0.0
    return out, den


def usage(rows_by_season, team_time, season_w=(1.0, 0.7)):
    """rows_by_season: [ {(pid, situation): row}, ... ] current first. team_time: [ {(team, situation): hours}, ... ].
    Returns {pid: {toi, pp, pk, oz, hits, blocks, hd}} (rates pooled across the seasons given)."""
    acc = {}
    for wi, rows, tt in zip(season_w, rows_by_season, team_time):
        for (pid, sit), r in rows.items():
            if sit != "all":
                continue
            a = acc.setdefault(pid, {"gp": 0, "min": 0, "pp": 0, "ppT": 0, "pk": 0, "pkT": 0, "oz": 0, "dz": 0, "hits": 0, "blocks": 0, "hd": 0, "ush": 0})
            gp = _f(r["games_played"]); mins = _f(r["icetime"]) / 60
            a["gp"] += wi * gp; a["min"] += wi * mins
            a["hits"] += wi * _f(r.get("I_F_hits")); a["blocks"] += wi * _f(r.get("shotsBlockedByPlayer"))
            a["hd"] += wi * _f(r.get("I_F_highDangerShots")); a["ush"] += wi * _f(r.get("I_F_unblockedShotAttempts"))
            for sit2, key in (("5on4", "pp"), ("4on5", "pk")):
                s = rows.get((pid, sit2))
                if s:
                    a[key] += wi * _f(s["icetime"]) / 3600
                    a[key + "T"] += wi * tt.get((r["team"], sit2), 0.0) * (gp / max(1.0, tt.get((r["team"], "gp"), gp)))
            e = rows.get((pid, "5on5"))
            if e:
                a["oz"] += wi * _f(e.get("I_F_oZoneShiftStarts")); a["dz"] += wi * _f(e.get("I_F_dZoneShiftStarts"))
    out = {}
    for pid, a in acc.items():
        h = a["min"] / 60
        out[pid] = {"toi": a["min"] / a["gp"] if a["gp"] else None,
                    "pp": a["pp"] / a["ppT"] if a["ppT"] > 0 else None, "pk": a["pk"] / a["pkT"] if a["pkT"] > 0 else None,
                    "oz": a["oz"] / (a["oz"] + a["dz"]) if a["oz"] + a["dz"] > 0 else None,
                    "hits": a["hits"] / h if h > 0 else None, "blocks": a["blocks"] / h if h > 0 else None,
                    "hd": a["hd"] / a["ush"] if a["ush"] >= 10 else None, "min": a["min"]}
    return out


def pct_rank(vals, v):
    """Percentile 0-100 of v within vals: (below + half of ties) / n, clipped. Ties share a middle percentile."""
    if v is None:
        return None
    vv = [x for x in vals if x is not None]
    if len(vv) < 2:
        return None
    below = sum(1 for x in vv if x < v); eq = sum(1 for x in vv if x == v)
    return int(max(0, min(100, round(100 * (below + 0.5 * eq) / len(vv)))))


def height_in(h):
    if not h:
        return None
    try:
        ft, inch = h.replace('"', "").split("'")
        return int(ft) * 12 + int(inch.strip() or 0)
    except ValueError:
        return None


def comparables(profiles, rel=None, n=6, w_usage=0.6):
    """profiles: {pid: {grp, isC, comps, use}}. Similarity within position group on standardized skill components,
    each weighted by sqrt(year-to-year r) so noisy skills count less, plus usage (weight w_usage). Faceoffs only count
    when comparing centers (wingers and defensemen take too few draws for the number to mean anything).
    Returns {pid: [(other pid, distance), ...]}."""
    out = {}
    for g in ("F", "D"):
        ids = [pid for pid, p in profiles.items() if p["grp"] == g]
        if len(ids) < n + 1:
            continue
        comps = [c for c in COMPS if not (g == "D" and c == "faceoffs")]
        feats = comps + ["toi", "pp", "pk", "hits", "hd"]
        M = np.array([[(profiles[i]["comps"].get(c) if c in COMPS else profiles[i]["use"].get(c)) for c in feats] for i in ids], dtype=float)
        for j in range(M.shape[1]):     # missing usage -> column median
            col = M[:, j]; med = np.nanmedian(col) if np.isfinite(col).any() else 0.0
            col[~np.isfinite(col)] = med
            sd = col.std() or 1.0
            M[:, j] = (col - col.mean()) / sd
        wc = [math.sqrt(max(0.02, (rel or {}).get(g, {}).get(c, {}).get("r", 0.5))) for c in comps]
        W = np.array(wc + [w_usage] * 5)
        isC = np.array([1.0 if profiles[i].get("isC") else 0.0 for i in ids])
        Z = M * np.sqrt(W)
        if "faceoffs" in comps:          # faceoff difference only between two centers
            fo = comps.index("faceoffs")
            both = isC[:, None] * isC[None, :]
        D = ((Z[:, None, :] - Z[None, :, :]) ** 2)
        if "faceoffs" in comps:
            D[:, :, fo] *= both
        D = np.sqrt(D.sum(-1))
        for a, pid in enumerate(ids):
            order = np.argsort(D[a])
            out[pid] = [(ids[b], round(float(D[a, b]), 2)) for b in order[1:n + 1]]
    return out


# ---------------- archetype: one label + a short blurb, from the profile percentiles (descriptive, rule-based)
def _role(g, toi_p):
    if toi_p is None:
        return ""
    if g == "F":
        return "Top-line" if toi_p >= 80 else ("Middle-six" if toi_p >= 45 else "Bottom-six")
    return "Top-pair" if toi_p >= 75 else ("Second-pair" if toi_p >= 40 else "Third-pair")


PHRASE = {"play_driving": "tilts the ice at 5v5", "shot_creation": "creates his own looks", "finishing": "finishes above expectation",
          "playmaking": "sets up teammates", "defense": "suppresses chances against", "puck_battles": "wins the puck back more than he gives it away",
          "penalties": "draws more penalties than he takes", "faceoffs": "wins faceoffs"}
WEAK = {"play_driving": "gets out-chanced", "shot_creation": "creates few looks of his own", "finishing": "finishes below expectation",
        "playmaking": "sets up few chances", "defense": "gives up chances against", "puck_battles": "turns the puck over",
        "penalties": "takes more penalties than he draws", "faceoffs": "loses faceoffs"}


def archetype(g, pos, prof, useP, ht=None, tpct=None):
    """g: F/D; pos: C/L/R/D; prof: skill percentiles; useP: usage percentiles. Returns (label, blurb) or (None, None)."""
    if not prof or all(v is None for v in prof.values()):
        return None, None
    P = lambda k: prof.get(k) if prof.get(k) is not None else 50
    U = lambda k: (useP or {}).get(k) if (useP or {}).get(k) is not None else 50
    off = max(P("shot_creation"), P("playmaking")); big = ht is not None and ht >= 74
    if g == "F":
        if P("play_driving") >= 80 and off >= 80 and U("toi") >= 70:
            a = "Play-driving star" if min(P("play_driving"), off) >= 90 and (tpct or 0) >= 90 else "Offensive play driver"
        elif P("finishing") >= 75 and P("shot_creation") >= 65:
            a = "Sniper"
        elif U("hits") >= 75 and P("shot_creation") >= 55:
            a = "Power forward" if big else "Physical scorer"
        elif U("hd") >= 80 and P("shot_creation") >= 55:
            a = "Net-front forward"
        elif P("playmaking") >= 75 and P("playmaking") >= P("shot_creation") + 10:
            a = "Playmaker"
        elif P("defense") >= 65 and U("pk") >= 65 and U("oz") <= 45:
            a = "Shutdown forward"
        elif P("play_driving") >= 60 and P("defense") >= 60:
            a = "Two-way forward"
        elif U("hits") >= 75:
            a = "Energy forward"
        elif pos == "C" and P("faceoffs") >= 75 and U("pk") >= 55:
            a = "Checking center"
        elif U("pp") >= 75 and P("play_driving") < 50:
            a = "Power-play specialist"
        elif off >= 65:
            a = "Secondary scorer"
        else:
            a = "Depth forward" if U("toi") < 45 else "Complementary forward"
    else:
        if (P("shot_creation") >= 75 or P("playmaking") >= 75) and U("pp") >= 60:
            a = "Offensive defenseman"
        elif P("play_driving") >= 65 and P("defense") >= 60:
            a = "Two-way defenseman"
        elif P("playmaking") >= 65 and P("play_driving") >= 55:
            a = "Puck-mover"
        elif P("defense") >= 65 and (U("pk") >= 60 or U("blocks") >= 65):
            a = "Shutdown defenseman"
        elif U("hits") >= 70 or U("blocks") >= 70:
            a = "Stay-at-home defenseman"
        elif off >= 60:
            a = "Offensive-minded defenseman"
        else:
            a = "Depth defenseman" if U("toi") < 40 else "Steady defenseman"
    role = _role(g, (useP or {}).get("toi"))
    label = (role + " " + a[0].lower() + a[1:]) if role and not a.startswith(("Depth", "Play-driving star")) else a
    keys = [k for k in PHRASE if prof.get(k) is not None]
    top = [k for k in sorted(keys, key=lambda k: -prof[k]) if prof[k] >= 70][:2]
    low = [k for k in sorted(keys, key=lambda k: prof[k]) if prof[k] <= 25][:2]
    use = []
    if U("pp") >= 75: use.append("power play")
    if U("pk") >= 75: use.append("penalty kill")
    if U("oz") <= 25: use.append("mostly defensive-zone starts")
    elif U("oz") >= 80: use.append("sheltered offensive-zone starts")
    if U("hits") >= 85: use.append("one of the league's heavier hitters")
    s1 = ("He " + " and ".join(PHRASE[k] for k in top) + ".") if top else "No standout skill."
    s2 = (" Usage: " + ", ".join(use) + ".") if use else ""
    s3 = (" Weak spot: " + "; ".join(WEAK[k] for k in low) + ".") if low else ""
    return label, s1 + s2 + s3


# ---------------- goalies: a separate profile (skater components don't apply)
GCOMPS = ["gsax", "ld", "md", "hd", "reb", "frz"]
GLABEL = {"gsax": "Goals saved above expected (per 60)", "ld": "Low-danger shots (saves above expected per 100)",
          "md": "Medium-danger shots", "hd": "High-danger shots", "reb": "Rebound control", "frz": "Freezing the puck"}


def goalie_season(rows, season):
    """{pid: {min, comp: {k: (numerator, denominator)}, gp, team}} from one season's goalie rows (situation all)."""
    out = {}
    for r in rows:
        if r.get("season") != season or r.get("situation") != "all":
            continue
        h = _f(r["icetime"]) / 3600; sog = _f(r["ongoal"])
        out[r["playerId"]] = {"min": h * 60, "gp": _f(r["games_played"]), "team": r["team"], "comp": {
            "gsax": (_f(r["xGoals"]) - _f(r["goals"]), h),
            "ld": (_f(r["lowDangerxGoals"]) - _f(r["lowDangerGoals"]), _f(r["lowDangerShots"]) / 100),
            "md": (_f(r["mediumDangerxGoals"]) - _f(r["mediumDangerGoals"]), _f(r["mediumDangerShots"]) / 100),
            "hd": (_f(r["highDangerxGoals"]) - _f(r["highDangerGoals"]), _f(r["highDangerShots"]) / 100),
            "reb": (_f(r["xRebounds"]) - _f(r["rebounds"]), sog / 100),
            "frz": (_f(r["freeze"]) - _f(r["xFreeze"]), sog / 100)}, "sog": sog}
    return out


def goalie_reliability(seasons, min_minutes=1500):
    """seasons: list of goalie_season dicts, oldest first. Year-to-year r per metric and k (in minutes)."""
    out = {}
    for k in GCOMPS:
        xs, ys, mins = [], [], []
        for a, b in zip(seasons[:-1], seasons[1:]):
            for pid, p in a.items():
                q = b.get(pid)
                if not q or p["min"] < min_minutes or q["min"] < min_minutes:
                    continue
                na, da = p["comp"][k]; nb, db = q["comp"][k]
                if da > 0 and db > 0:
                    xs.append(na / da); ys.append(nb / db); mins.append((p["min"] + q["min"]) / 2)
        if len(xs) < 20 or np.std(xs) == 0:
            out[k] = {"r": 0.05, "k": 1e6, "n": len(xs)}; continue
        r = float(np.clip(np.corrcoef(xs, ys)[0, 1], 0.02, 0.95)); mbar = float(np.mean(mins))
        out[k] = {"r": round(r, 3), "k": round(mbar * (1 - r) / r, 1), "n": len(xs)}
    return out


def goalie_pooled(pid, seasons, w, rel):
    """seasons: [current, last, two ago, three ago] goalie_season dicts; w: weights for prior seasons (current = 1)."""
    ws = [1.0] + list(w)
    num = {k: 0.0 for k in GCOMPS}; den = {k: 0.0 for k in GCOMPS}; mins = 0.0; sog = 0.0
    for wi, S in zip(ws, seasons):
        p = S.get(pid)
        if not p:
            continue
        mins += wi * p["min"]; sog += wi * p["sog"]
        for k in GCOMPS:
            n, d = p["comp"][k]; num[k] += wi * n; den[k] += wi * d
    out = {}
    for k in GCOMPS:
        rate = num[k] / den[k] if den[k] > 0 else 0.0
        out[k] = rate * mins / (mins + rel[k]["k"]) if mins > 0 else 0.0
    return out, mins, (sog / (mins / 60) if mins > 0 else None)


def goalie_archetype(share_now, prof):
    role = "Starter" if share_now >= 0.55 else ("1A/1B goalie" if share_now >= 0.35 else "Backup")
    best = [k for k in ("hd", "reb", "md", "ld", "frz") if (prof.get(k) or 0) >= 75]
    trait = {"hd": "strong on high-danger shots", "reb": "controls rebounds", "md": "strong on medium-danger shots",
             "ld": "rarely beaten from distance", "frz": "freezes the puck"}
    weak = [k for k in ("hd", "reb", "md", "ld") if prof.get(k) is not None and prof[k] <= 25]
    wtxt = {"hd": "high-danger shots", "reb": "rebound control", "md": "medium-danger shots", "ld": "low-danger shots"}
    label = role + (", " + trait[best[0]] if best else "")
    g = prof.get("gsax")
    ordn = lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
    txt = (f"Overall {('above' if g >= 60 else 'below' if g <= 40 else 'around')} expected for the shots he faces ({ordn(g)} percentile)." if g is not None else "")
    if best: txt += " Best at: " + ", ".join(trait[k] for k in best[:2]) + "."
    if weak: txt += " Weak spot: " + ", ".join(wtxt[k] for k in weak[:2]) + "."
    return label, txt.strip()
