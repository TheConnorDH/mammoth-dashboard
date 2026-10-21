"""Power rankings: expected goal differential per game for the REST of the season, from
  (1) the talent of each team's CURRENT lineup (players who dressed in its last 5 games, at the minutes they
      played there; talent from last season, newcomers at the newcomer average),
  (2) goal differential so far, (3) expected-goal differential so far, (4) last season's goal differential.
Weights change with games played and were fitted on 8 seasons of in-season checkpoints (work/pr_*.py);
config/power_params.json. Goals here exclude empty-net goals (they come from goalie records), as in the fit."""
import math
import numpy as np
import impact

LAST_N = 5


def _interp(gp, cps, key):
    xs = [c["gp"] for c in cps]
    if gp <= xs[0]:
        c = list(cps[0][key])
        # below the first checkpoint the evidence in results-to-date grows ~ in proportion to games played,
        # so their weights shrink proportionally (avoids reading a 6-0 opener as a +6 team)
        f = max(gp, 0) / xs[0]
        c[2] *= f; c[3] *= f
        return c
    for i in range(1, len(xs)):
        if gp <= xs[i]:
            f = (gp - xs[i - 1]) / (xs[i] - xs[i - 1])
            a, b = cps[i - 1][key], cps[i][key]
            return [x + f * (y - x) for x, y in zip(a, b)] if isinstance(a, list) else a + f * (b - a)
    return cps[-1][key]


def compute(sk_games, gl_games, prev_by_id, prev_team_gd, ip, newcomer60, pp, pts_per_goal, season="2026", season_games=84, sims=4000, ages=None, season_totals=None):
    # team games from goalie rows (all situations)
    games, gname = {}, {}
    for r in gl_games:
        if r.get("situation") != "all" or r.get("season") != season:
            continue
        gname[r["playerId"]] = r["name"]
        e = games.setdefault(r["gameId"], {"d": int(r["gameDate"]), "t": {}})
        te = e["t"].setdefault(r["playerTeam"], {"ga": 0.0, "xga": 0.0, "g": {}})
        te["ga"] += float(r["goals"]); te["xga"] += float(r["xGoals"]); te["g"][r["playerId"]] = te["g"].get(r["playerId"], 0) + float(r["icetime"])
    tg = {}
    for gid, e in games.items():
        if len(e["t"]) != 2:
            continue
        (a, ea), (b, eb) = e["t"].items()
        tg.setdefault(a, []).append((e["d"], gid, eb["ga"] - ea["ga"], eb["xga"] - ea["xga"], ea["g"]))
        tg.setdefault(b, []).append((e["d"], gid, ea["ga"] - eb["ga"], ea["xga"] - eb["xga"], eb["g"]))
    lineup = {}
    for r in sk_games:
        if r.get("situation") == "all" and r.get("season") == season:
            lineup.setdefault(r["playerTeam"], []).append((r["gameId"], r["playerId"], "D" if r["position"] == "D" else "F", float(r["icetime"]), r["name"]))
    teams = sorted(set(prev_team_gd) | set(tg))
    rows = []
    for t in teams:
        G = sorted(tg.get(t, []))
        gp = len(G)
        last = G[-LAST_N:]; lg = {x[1] for x in last}
        toi, grp, names = {}, {}, {}
        for gid, pid, g, ice, nm in lineup.get(t, []):
            if gid in lg:
                toi[pid] = toi.get(pid, 0) + ice; grp[pid] = g; names[pid] = nm
        for x in last:
            for pid, ice in x[4].items():
                toi[pid] = toi.get(pid, 0) + ice; grp[pid] = "G"
        # goalie starts in the last games (the goalie with the most ice time in each game)
        gstarts = {}
        for x in last:
            if x[4]:
                st = max(x[4], key=x[4].get); gstarts[st] = gstarts.get(st, 0) + 1
        roster, contrib, gl_ = 0.0, [], []
        for pid, secs in toi.items():
            pvs = prev_by_id.get(pid)
            pvs = pvs if isinstance(pvs, list) else [pvs]
            g = grp[pid]
            valid = [q for q in pvs if q and q.get("grp") == g]
            pv = valid[0] if valid else None
            tl = impact.talent({"grp": g, "toi": 0.0, "gaa": 0.0}, pvs, ip, age=(ages or {}).get(pid)) if valid else None
            rate = tl["rate60"] if tl else newcomer60[g]
            mpg = secs / 60 / max(1, len(last))
            roster += rate * mpg / 60
            contrib.append((rate * mpg / 60, pv["name"] if pv else names.get(pid, pid)))
            if g == "G":
                gl_.append({"id": pid, "name": gname.get(pid, pv["name"] if pv else pid), "rate60": round(rate, 4), "mpg": round(mpg, 2), "starts": gstarts.get(pid, 0)})
        gd_ = float(np.mean([x[2] for x in G])) if G else 0.0; xgd_ = float(np.mean([x[3] for x in G])) if G else 0.0; src_ = "games"
        # MoneyPuck's game-by-game files can lag its season files; if the season file has more games, take results from it
        # (season totals include empty-net goals, which the fit excluded: a small difference, ~0.1 goals/game at most)
        st_ = (season_totals or {}).get(t)
        if st_ and st_[0] > gp:
            gp, gd_, xgd_, src_ = st_[0], st_[1], st_[2], "season"
        rows.append({"team": t, "gp": gp, "gd": gd_, "xgd": xgd_, "resultsFrom": src_, "lineupGames": len(last),
                     "roster": roster if toi else None, "prevgd": prev_team_gd.get(t, 0.0), "lineupN": len(toi),
                     "top": [n for _, n in sorted(contrib, reverse=True)[:3]], "lineupIds": list(toi.keys()),
                     "goalies": sorted(gl_, key=lambda q: (-q["starts"], -q["mpg"]))})
    known = [r["roster"] for r in rows if r["roster"] is not None]
    for r in rows:   # a team with no games yet: lineup unknown, use the league-average lineup
        if r["roster"] is None:
            r["roster"] = float(np.mean(known)) if known else 0.0; r["noLineup"] = True
    cps = pp["checkpoints"]
    gps = [c["gp"] for c in cps]; tv = pp["true_var"]
    for r in rows:
        b = _interp(r["gp"], cps, "coef")
        x = [1.0, r["roster"], r["gd"], r["xgd"], r["prevgd"]]
        r["pred"] = sum(bi * xi for bi, xi in zip(b, x))
        r["parts_raw"] = {"lineup": b[1] * r["roster"], "results": b[2] * r["gd"], "shots": b[3] * r["xgd"], "lastseason": b[4] * r["prevgd"]}
        r["weights"] = b
        gmix = sum(q["rate60"] * q["mpg"] / 60 for q in r.get("goalies", []))
        for q in r.get("goalies", []):
            q["dr"] = round(b[1] * (q["rate60"] - gmix), 4)    # change in expected goal differential per game if he starts
        r["true_sd"] = math.sqrt(float(np.interp(r["gp"], gps, tv)))
    mean_pred = float(np.mean([r["pred"] for r in rows]))
    pm = {k: float(np.mean([r["parts_raw"][k] for r in rows])) for k in rows[0]["parts_raw"]}
    scale = season_games * pts_per_goal
    for r in rows:
        r["rating"] = round((r["pred"] - mean_pred) * scale, 1)                       # standings points per 84 games vs. an average team
        r["parts"] = {k: round((v - pm[k]) * scale, 1) for k, v in r["parts_raw"].items()}
        r["partsR"] = {k: round(v - pm[k], 5) for k, v in r["parts_raw"].items()}   # unrounded, same units as r (matchup odds breakdown)
        r["sd_pts"] = r["true_sd"] * scale
    rng = np.random.default_rng(3)
    mu = np.array([r["rating"] for r in rows]); sd = np.array([r["sd_pts"] for r in rows])
    ranks = (-rng.normal(mu[None, :], sd[None, :], size=(sims, len(rows)))).argsort(axis=1).argsort(axis=1) + 1
    order = (-mu).argsort().argsort() + 1
    for i, r in enumerate(rows):
        r["rank"] = int(order[i]); r["rlo"] = int(np.percentile(ranks[:, i], 2.5, method="lower")); r["rhi"] = int(np.percentile(ranks[:, i], 97.5, method="higher"))
        r["r10"] = int(np.percentile(ranks[:, i], 10, method="lower")); r["r90"] = int(np.percentile(ranks[:, i], 90, method="higher"))
        r["lo"] = round(r["rating"] - 1.96 * r["sd_pts"], 1); r["hi"] = round(r["rating"] + 1.96 * r["sd_pts"], 1)
        for k in ("gd", "xgd", "roster", "prevgd", "pred", "true_sd", "sd_pts"):
            r[k] = round(r[k], 3)
        r.pop("parts_raw", None)
        r["weights"] = [round(w, 3) for w in r["weights"]]
    return sorted(rows, key=lambda r: r["rank"])
