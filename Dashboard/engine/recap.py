"""Game recaps for the share graphic: every shot of a team's games (MoneyPuck shot file), chance-based
"deserve to win" (each non-empty-net shot simulated as a goal with its own xG probability, 20,000 times;
the MoneyPuck method), goalie saves vs. expected (MoneyPuck game-by-game goalie file) and box-score extras."""
import csv, json, os, glob
import numpy as np

def _num(x):
    try: return float(x)
    except (TypeError, ValueError): return 0.0

def build(shots_path, goalie_games_path, box_dir, team, sims=20000, seed=5):
    if not os.path.exists(shots_path):
        return []
    games = {}
    with open(shots_path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if team not in (r["homeTeamCode"], r["awayTeamCode"]):
                continue
            g = games.setdefault(r["game_id"], {"home": r["homeTeamCode"], "away": r["awayTeamCode"], "shots": []})
            us = r["teamCode"] == team; hs, as_ = int(_num(r["homeSkatersOnIce"])), int(_num(r["awaySkatersOnIce"]))
            mine, theirs = (hs, as_) if _num(r["isHomeTeam"]) == 1 else (as_, hs)
            en = _num(r["shotOnEmptyNet"]) == 1
            st = "EN" if en else ("6v5" if mine > theirs and theirs >= 5 else "PP" if mine > theirs else "SH" if mine < theirs and mine < 5 else ("5v5" if mine == 5 and theirs == 5 else "EV"))
            name = r.get("shooterName") or ""
            g["shots"].append([int(_num(r["time"])), 1 if us else 0, round(_num(r["xGoal"]), 3), 1 if r["event"] == "GOAL" else 0, st,
                               name.split(" ")[-1] if name else "", 1 if r["event"] in ("SHOT", "GOAL") else 0, int(_num(r["period"]))])
    gl = {}
    if os.path.exists(goalie_games_path):
        with open(goalie_games_path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["situation"] != "all": continue
                k = str(int(r["gameId"]) - 2026000000) if r["gameId"].startswith("2026") else r["gameId"]
                gl.setdefault(k, []).append({"name": r["name"], "team": r["playerTeam"], "sa": int(_num(r["ongoal"])), "ga": int(_num(r["goals"])),
                                             "xga": round(_num(r["xGoals"]), 2), "toi": round(_num(r["icetime"]) / 60, 1)})
    rng = np.random.default_rng(seed)
    out = []
    for gid, g in games.items():
        S = sorted(g["shots"], key=lambda s: s[0])
        box_path = os.path.join(box_dir, f"2026{int(gid):06d}.json")
        box = json.load(open(box_path)) if os.path.exists(box_path) else None
        live = [s for s in S if s[4] != "EN"]
        pu = np.array([s[2] for s in live if s[1] == 1]); po = np.array([s[2] for s in live if s[1] == 0])
        gu = (rng.random((sims, len(pu))) < pu).sum(axis=1) if len(pu) else np.zeros(sims)
        go = (rng.random((sims, len(po))) < po).sum(axis=1) if len(po) else np.zeros(sims)
        deserve = float(np.mean(gu > go) + 0.5 * np.mean(gu == go))
        agg = lambda us, f: round(sum(s[2] for s in S if s[1] == us and f(s)), 2)
        cnt = lambda us, f: sum(1 for s in S if s[1] == us and f(s))
        stats = {k: [f(1), f(0)] for k, f in {
            "sog": lambda u: cnt(u, lambda s: s[6] == 1), "xg": lambda u: agg(u, lambda s: s[4] != "EN"), "xg5": lambda u: agg(u, lambda s: s[4] == "5v5"),
            "danger": lambda u: cnt(u, lambda s: s[2] >= 0.1 and s[4] != "EN"), "ppg": lambda u: cnt(u, lambda s: s[4] == "PP" and s[3] == 1),
            "ppxg": lambda u: agg(u, lambda s: s[4] == "PP"), "goals": lambda u: cnt(u, lambda s: s[3] == 1), "g5": lambda u: cnt(u, lambda s: s[4] == "5v5" and s[3] == 1)}.items()}
        rec = {"gid": int(gid), "id": 2026000000 + int(gid), "home": g["home"], "away": g["away"], "deserve": round(deserve, 3), "stats": stats,
               "shots": S, "goalies": gl.get(gid, [])}
        if box:
            rec.update({"date": box["date"], "us": box["uta_score"], "them": box["opp_score"], "lp": box.get("last_period", "REG"),
                        "sogBox": [box.get("uta_sog"), box.get("opp_sog")]})
        out.append(rec)
    return sorted(out, key=lambda r: r["gid"])
