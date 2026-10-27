"""Every NHL game of the season for the Games tab: a light index of all games (played and upcoming) and, for each
played game, a detail record: both teams' Player Impact in that game (the full model run on that game alone, the
same values as each team's game-by-game stars), stat lines, goalies, every shot (time, xG, location) and
"deserve to win" (each non-empty-net shot replayed at its xG, the recap method).

Upcoming games carry the model's win odds (power ratings + home ice + rest). Odds recorded on the morning of a
game are kept after it is played (history/pregame_odds.json), so a finished game shows what the model expected
beforehand. Odds are never back-filled for games played before recording started (that would use hindsight)."""
import csv
import json
import os
import numpy as np


PARTS = ["play_driving", "shot_creation", "finishing", "playmaking", "puck_battles", "defense", "penalties", "faceoffs"]


def _n(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _shots(shots_path):
    """game number (e.g. '20013') -> list of shots from the HOME team's point of view:
    [time s, 1 = home shot, xG, goal, strength, shooter last name, on goal, period, x, y]
    x, y: MoneyPuck's adjusted coordinates (every shot toward the net at x = +89); home shots are drawn on the
    right half of the rink, away shots mirrored to the left."""
    out = {}
    if not os.path.exists(shots_path):
        return out
    with open(shots_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["event"] not in ("SHOT", "MISS", "GOAL"):
                continue
            home = _n(r["isHomeTeam"]) == 1
            hs, as_ = int(_n(r["homeSkatersOnIce"])), int(_n(r["awaySkatersOnIce"]))
            mine, theirs = (hs, as_) if home else (as_, hs)
            en = _n(r["shotOnEmptyNet"]) == 1
            st = "EN" if en else ("6v5" if mine > theirs and theirs >= 5 else "PP" if mine > theirs else "SH" if mine < theirs and mine < 5 else ("5v5" if mine == 5 and theirs == 5 else "EV"))
            nm = r.get("shooterName") or ""
            x, y = _n(r.get("xCordAdjusted")), _n(r.get("yCordAdjusted"))
            out.setdefault(r["game_id"], []).append([int(_n(r["time"])), 1 if home else 0, round(_n(r["xGoal"]), 3), 1 if r["event"] == "GOAL" else 0, st,
                                                     nm.split(" ")[-1] if nm else "", 1 if r["event"] in ("SHOT", "GOAL") else 0, int(_n(r["period"])),
                                                     round(x if home else -x), round(y if home else -y)])
    for v in out.values():
        v.sort(key=lambda s: s[0])
    return out


def _deserve(S, seed, sims=20000):
    rng = np.random.default_rng(seed)
    live = [s for s in S if s[4] != "EN"]
    ph = np.array([s[2] for s in live if s[1] == 1]); pa = np.array([s[2] for s in live if s[1] == 0])
    gh = (rng.random((sims, len(ph))) < ph).sum(axis=1) if len(ph) else np.zeros(sims)
    ga = (rng.random((sims, len(pa))) < pa).sum(axis=1) if len(pa) else np.zeros(sims)
    return round(float(np.mean(gh > ga) + 0.5 * np.mean(gh == ga)), 3)


def _stats(S):
    agg = lambda u, f: round(sum(s[2] for s in S if s[1] == u and f(s)), 2)
    cnt = lambda u, f: sum(1 for s in S if s[1] == u and f(s))
    F = {"sog": lambda u: cnt(u, lambda s: s[6] == 1), "xg": lambda u: agg(u, lambda s: s[4] != "EN"), "xg5": lambda u: agg(u, lambda s: s[4] == "5v5"),
         "danger": lambda u: cnt(u, lambda s: s[2] >= 0.1 and s[4] != "EN"), "ppg": lambda u: cnt(u, lambda s: s[4] == "PP" and s[3] == 1),
         "ppxg": lambda u: agg(u, lambda s: s[4] == "PP"), "goals": lambda u: cnt(u, lambda s: s[3] == 1), "g5": lambda u: cnt(u, lambda s: s[4] == "5v5" and s[3] == 1)}
    return {k: [f(1), f(0)] for k, f in F.items()}     # [home, away]


def build(sched, games_files, shots_path, team_rows, season, ip, means, impact, odds=None, pregame=None, today=None):
    """sched: league schedule games. games_files: {'skaters','goalies'} MoneyPuck game-by-game paths.
    odds: {game id: {'pH','pOT','b2b'}} for games not yet played (current model). pregame: stored odds by game id.
    Returns (index, details_by_date, pregame_updated)."""
    odds = odds or {}; pregame = dict(pregame or {})
    sk, gl = {}, {}
    if games_files.get("skaters"):
        with open(games_files["skaters"], newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["season"] == season:
                    r["team"] = r["playerTeam"]; r["games_played"] = "1"; sk.setdefault(r["gameId"], []).append(r)
    if games_files.get("goalies"):
        with open(games_files["goalies"], newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["season"] == season:
                    r["team"] = r["playerTeam"]; r["games_played"] = "1"; gl.setdefault(r["gameId"], []).append(r)
    shots = _shots(shots_path)
    index, details = [], {}
    for g in sorted(sched, key=lambda g: (g["date"], g.get("start") or "", g["id"])):
        gid = str(g["id"]); short = str(int(gid) - int(season) * 1000000) if gid.startswith(season) else gid
        fin = g["state"] in (6, 7)
        row = {"id": g["id"], "d": g["date"], "t": g.get("start"), "h": g["home"], "a": g["away"], "f": 1 if fin else 0}
        if not fin and g.get("sched") in ("PPD", "SUSP", "CNCL"):
            row["ppd"] = 1
        if fin:
            row.update({"hs": g["hs"], "as": g["as"], "lp": "SO" if g["period"] >= 5 else ("OT" if g["period"] == 4 else "REG")})
        if not fin and gid in odds and not row.get("ppd"):
            o = odds[gid]; row.update({"pH": o["pH"], "pOT": o["pOT"]})
            if o.get("b2b"): row["b2b"] = o["b2b"]
            if today is None or g["date"] >= today:      # recorded until the game is played; the last record is the pregame line
                pregame[gid] = {"pH": o["pH"], "pOT": o["pOT"], "asOf": today}
        if fin and gid in pregame:
            row["pre"] = pregame[gid]["pH"]
        if fin and gid in sk:
            S = shots.get(short, [])
            det = {"players": {}, "goalies": [], "stats": _stats(S) if S else None, "deserve": _deserve(S, int(gid) % 2 ** 31) if S else None, "shots": S}
            for side, t in (("h", g["home"]), ("a", g["away"])):
                rows_ = [r for r in sk[gid] if r["playerTeam"] == t]
                grows_ = [r for r in gl.get(gid, []) if r["playerTeam"] == t]
                res = impact.compute(rows_, grows_, team_rows, season, ip, team=t, means_override=means)
                line = {}
                for r in rows_:
                    if r["situation"] == "all":
                        line[r["playerId"]] = [int(_n(r["I_F_goals"])), int(_n(r["I_F_primaryAssists"]) + _n(r["I_F_secondaryAssists"])), int(_n(r["I_F_shotsOnGoal"])), round(_n(r["icetime"]) / 60, 1)]
                for r in grows_:
                    if r["situation"] == "all":
                        sa, ga = int(_n(r["ongoal"])), int(_n(r["goals"]))
                        line[r["playerId"]] = [sa - ga, sa, round(_n(r["xGoals"]) - ga, 2), round(_n(r["icetime"]) / 60, 1)]
                        det["goalies"].append({"name": r["name"], "team": t, "sa": sa, "ga": ga, "xga": round(_n(r["xGoals"]), 2), "toi": round(_n(r["icetime"]) / 60, 1)})
                # [name, position group, Impact in goals, stat line, parts]  skaters: G, A, SOG, TOI; goalies: saves, shots, saves vs
                # expected, TOI. parts: where the Impact came from, in PARTS order (goals; each vs. the position average)
                det["players"][side] = sorted([[v["name"], v["grp"], round(v["gaa"], 2), line.get(v["id"]),
                                                [round((v.get("parts") or {}).get(k, 0.0), 2) for k in PARTS] if v["grp"] != "G" else None]
                                               for v in res if v["toi"] > 0], key=lambda x: -x[2])
            if det["stats"]:
                row.update({"xgH": det["stats"]["xg"][0], "xgA": det["stats"]["xg"][1], "dz": det["deserve"]})
            row["det"] = 1
            details.setdefault(g["date"], {})[gid] = det
        index.append(row)
    return index, details, pregame
