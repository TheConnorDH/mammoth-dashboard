"""League-wide context: every NHL player's Impact and true talent on the same basis as Utah's, ranks by
position (with 95% rank ranges from the talent uncertainty), and roster strength by team."""
import math
import numpy as np
import impact

W_PREV_GAMES = 10   # minutes per game blends in last season as if it were 10 extra games (stable early, adapts fast)


def toi_per_game(p, prev):
    if prev and prev["gp"] and prev["grp"] == p["grp"]:
        return (p["toi"] + prev["toi"] / prev["gp"] * W_PREV_GAMES) / (p["gp"] + W_PREV_GAMES)
    return p["toi"] / p["gp"] if p["gp"] else 0.0


def player_value(p, prev, ip, rp, team_gp, season_games=84, newcomer_tpg=None, age=None, standard=None):
    """Adds talent60 / talent84 (+ 95% interval) to p, identically for every player in the league.
    Newcomers (no 2025-26 row at this position) shrink toward the measured newcomer average, not 0."""
    prevs = [q for q in (prev if isinstance(prev, (list, tuple)) else [prev])]
    valid = [q for q in prevs if q and q.get("grp") == p["grp"] and q.get("toi", 0) > 0]
    newcomer = not valid
    prev = valid[0] if valid else None      # most recent prior season with minutes (for minutes / starts)
    prior = rp["newcomer60"][p["grp"]] if newcomer else 0.0
    tal = impact.talent(p, prevs, ip, prior_mean=prior, age=age)
    if not tal:   # no minutes at all yet: the prior itself, with the full spread of true talent
        sd = math.sqrt(ip["reliability"][p["grp"]]["var_true60"] + ip.get("noise", {}).get(p["grp"], {}).get("c", 0.0))
        tal = {"rate60": prior, "lo60": prior - 1.96 * sd, "hi60": prior + 1.96 * sd}
    share = 1.0
    if p["grp"] == "G":   # goalies: share of starts (this season + last); normalised per team in rosters()
        g_prev = prev["gp"] if prev and not newcomer else 0
        share = min(1.0, (p["gp"] + g_prev) / max(1, team_gp + (82 if g_prev else 0))) if (p["gp"] + g_prev) else 0.25
    tpg = toi_per_game(p, None if newcomer else prev) or (newcomer_tpg or {}).get(p["grp"], 0.0)
    scale = tpg / 60 * season_games * share
    sd60 = (tal["hi60"] - tal["rate60"]) / 1.96
    # deployment-independent: the same rate at a STANDARD workload for the position (average regular's minutes;
    # goalies: average starter's games), so ice time, PP time and coaching choices don't move it
    std = (standard or {}).get(p["grp"])
    if std:
        sscale = (std["mall"] / 60) * (std.get("games", season_games))
        p.update({"tstd": round(tal["rate60"] * sscale, 1), "tstd_lo": round(tal["lo60"] * sscale, 1), "tstd_hi": round(tal["hi60"] * sscale, 1),
                  "tstd_sd": sd60 * sscale, "t60": round(tal["rate60"], 3), "t60_lo": round(tal["lo60"], 3), "t60_hi": round(tal["hi60"], 3)})
    prev_min = tal.get("prevMinutes", 0.0)
    cur_share = p["toi"] / (p["toi"] + prev_min) if (p["toi"] + prev_min) > 0 else 0.0
    # team strength uses talent WITHOUT the age adjustment (aging helps individual predictions but hurts team ones)
    tal_team = impact.talent(p, prevs, ip, prior_mean=prior, age=None) if age is not None else tal
    p["talent84_team"] = round((tal_team or tal)["rate60"] * scale, 1)
    p.update({"curShare": round(cur_share, 3), "age": round(age, 1) if age is not None else None, "talent60": tal["rate60"], "talent84": round(tal["rate60"] * scale, 1), "tlo84": round(tal["lo60"] * scale, 1),
              "thi84": round(tal["hi60"] * scale, 1), "tsd84": sd60 * scale, "newcomer": newcomer, "gshare": share,
              "talentVerdict": "above" if tal["lo60"] > 0 else ("below" if tal["hi60"] < 0 else "unclear")})
    return p


def rank_ranges(players, key="talent84", sd_key="tsd84", sims=4000, seed=11):
    """Rank within position, plus the 95% range of that rank when every player's talent is uncertain."""
    rng = np.random.default_rng(seed)
    out = {}
    for g in ("F", "D", "G"):
        L = [p for p in players if p["grp"] == g and p.get(key) is not None]
        if not L:
            continue
        mu = np.array([p[key] for p in L]); sd = np.array([max(p[sd_key], 1e-6) for p in L])
        draws = rng.normal(mu[None, :], sd[None, :], size=(sims, len(L)))
        ranks = (-draws).argsort(axis=1).argsort(axis=1) + 1
        point = (-mu).argsort().argsort() + 1
        lo, hi = np.percentile(ranks, 2.5, axis=0, method="lower"), np.percentile(ranks, 97.5, axis=0, method="higher")
        lo80, hi80 = np.percentile(ranks, 10, axis=0, method="lower"), np.percentile(ranks, 90, axis=0, method="higher")
        for i, p in enumerate(L):
            out[p["id"]] = {"rank": int(point[i]), "rlo": int(lo[i]), "rhi": int(hi[i]), "r10": int(lo80[i]), "r90": int(hi80[i]), "n": len(L),
                            "pct": round(100 * (1 - (point[i] - 1) / max(1, len(L) - 1)))}
    return out


def simple_rank(players, key, qualify):
    out = {}
    for g in ("F", "D", "G"):
        L = sorted([p for p in players if p["grp"] == g and qualify(p)], key=lambda p: -p[key])
        for i, p in enumerate(L):
            out[p["id"]] = {"rank": i + 1, "n": len(L), "pct": round(100 * (1 - i / max(1, len(L) - 1)))}
    return out


def rosters(players, n_f=12, n_d=6, tiers=None):
    """Team strength = summed talent per 84 of each team's top-12 forwards and top-6 defensemen by
    ice time per game, plus its goalies (already weighted by share of starts)."""
    tiers = tiers or {"F": 32, "D": 32, "G": 16}
    ranked = {g: sorted([p for p in players if p["grp"] == g and p.get("talent84") is not None], key=lambda p: -p["talent84"]) for g in "FDG"}
    elite = {g: {p["id"] for p in ranked[g][:tiers[g]]} for g in "FDG"}
    second = {g: {p["id"] for p in ranked[g][tiers[g]:tiers[g] * 3]} for g in "FD"}
    teams = {}
    for p in players:
        if p.get("talent84") is None or p.get("noGames"):
            continue
        teams.setdefault(p["team"], {"F": [], "D": [], "G": []})[p["grp"]].append(p)
    out = []
    for t, d in teams.items():
        F = sorted(d["F"], key=lambda p: -p.get("tpg", 0))[:n_f]; D = sorted(d["D"], key=lambda p: -p.get("tpg", 0))[:n_d]
        gs = sum(p.get("gshare", 1.0) for p in d["G"]) or 1.0
        gnorm = {p["id"]: 1.0 / gs for p in d["G"]}          # a team's goalies share exactly one season of starts
        tv = lambda p: p.get("talent84_team", p["talent84"])
        row = {"team": t, "F": sum(tv(p) for p in F), "D": sum(tv(p) for p in D), "G": sum(tv(p) * gnorm[p["id"]] for p in d["G"]),
               "eliteF": sum(p["id"] in elite["F"] for p in F), "eliteD": sum(p["id"] in elite["D"] for p in D),
               "eliteG": sum(p["id"] in elite["G"] for p in d["G"]),
               "secondF": sum(p["id"] in second["F"] for p in F), "secondD": sum(p["id"] in second["D"] for p in D),
               "best": max(F + D + d["G"], key=lambda p: p["talent84"])["name"] if F + D + d["G"] else None}
        row["total"] = row["F"] + row["D"] + row["G"]
        row["sd"] = math.sqrt(sum(p.get("tsd84", 0) ** 2 for p in F + D) + sum((p.get("tsd84", 0) * gnorm[p["id"]]) ** 2 for p in d["G"]))
        row["n"] = len(F) + len(D) + len(d["G"])
        out.append(row)
    for k in ("F", "D", "G", "total"):
        for i, r in enumerate(sorted(out, key=lambda r: -r[k])):
            r["rank_" + k] = i + 1
    # 95% range of each team's rank, from every player's talent uncertainty
    rng = np.random.default_rng(5)
    mu = np.array([r["total"] for r in out]); sd = np.array([max(r["sd"], 1e-6) for r in out])
    ranks = (-rng.normal(mu[None, :], sd[None, :], size=(4000, len(out)))).argsort(axis=1).argsort(axis=1) + 1
    for i, r in enumerate(out):
        r["rlo"], r["rhi"] = int(np.percentile(ranks[:, i], 2.5, method="lower")), int(np.percentile(ranks[:, i], 97.5, method="higher"))
    for r in out:
        for k in ("F", "D", "G", "total", "sd"):
            r[k] = round(r[k], 1)
    return sorted(out, key=lambda r: -r["total"])
