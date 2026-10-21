"""Team needs, surplus and fits: a screening tool, not a trade predictor (no contract term, clauses, real cap space,
injuries, prospects or intent in the data).

Needs: each part of the game is summed over the players a team has been dressing (pooled, repeatability-shrunk
component rate x his ice time per game), in goals per 84 games vs. the league's average team; the biggest
deficits are the needs. The weakest lineup slot comes from the top-vs-depth ranks.
Surplus: regulars outside the team's best lineup by talent, and players clearly below market value for their cap hit.
Fits are screened on the page (filters for cap hit, sellers only, sort): players strong (70th percentile+) in one of
the team's need areas and more talented than the weakest player they would replace in the team's best lineup."""
import numpy as np
import lineup as lineup_mod
from player_profile import COMPS

LABEL = {"play_driving": "Driving play (5v5 chances for)", "shot_creation": "Shot creation", "finishing": "Finishing", "playmaking": "Playmaking",
         "defense": "Defense (5v5 chances against)", "puck_battles": "Takeaways vs. giveaways", "penalties": "Penalty differential", "faceoffs": "Faceoffs"}
ONICE = ("play_driving", "defense")      # on/off-ice parts: use team-level 5v5 rates (player values cancel when summed)
H5 = 50 / 60                             # typical 5v5 hours per game
SLOT = {"topF": "Top-six forwards", "topD": "Top-four defense", "depF": "Bottom-six forwards", "depD": "Third pair", "goalie": "Starting goalie"}


def build(players, lineups, power_rows, ppi, season_games=84, team5=None, gp_by_team=None):
    """players: playersLeague rows (need id, t, g, pos, tal, tpg, prof, profV, cap, vs/vsLo/vsHi, ng)."""
    by_team = {}
    for p in players:
        if p.get("g") in ("F", "D") and not p.get("ng") and p.get("profV"):
            by_team.setdefault(p["t"], []).append(p)
    # team totals per component: sum(rate60 x minutes per game / 60) x games -> goals per 84 games, with each team's
    # skater minutes scaled to a real game's 300 (so call-ups and extra bodies don't inflate a total)
    tot = {}
    for t, L in by_team.items():
        mins = sum(p.get("tpg") or 0 for p in L) or 1.0
        sc = 300.0 / mins
        tot[t] = {c: sum(p["profV"][c] * (p.get("tpg") or 0) * sc / 60 for p in L) * season_games for c in COMPS}
    if team5:
        lg = [v for v in team5.values() if v[2] > 0]
        lf = sum(v[0] for v in lg) / sum(v[2] for v in lg); la = sum(v[1] for v in lg) / sum(v[2] for v in lg)
        for t in tot:
            v = team5.get(t)
            if v and v[2] > 0:
                tot[t]["play_driving"] = (v[0] / v[2] - lf) * H5 * season_games
                tot[t]["defense"] = (la - v[1] / v[2]) * H5 * season_games
    mean = {c: float(np.mean([tot[t][c] for t in tot])) for c in COMPS}
    sdv = {c: float(np.std([tot[t][c] for t in tot])) for c in COMPS}
    ranks = {c: {t: i + 1 for i, t in enumerate(sorted(tot, key=lambda t: -tot[t][c]))} for c in COMPS}
    ln = {r["team"]: r for r in lineups or []}
    out = {}
    for t, L in by_team.items():
        # components live on different scales (team-level 5v5 rates vary far more than individual parts), so needs and
        # strengths are picked by z-score across the 32 teams; the gap is shown in standings points for context
        z = {c: (tot[t][c] - mean[c]) / (sdv[c] or 1) for c in COMPS}
        needs = [{"key": c, "label": LABEL[c], "gap": round((tot[t][c] - mean[c]) * ppi, 1), "rank": ranks[c][t]}
                 for c in sorted(COMPS, key=lambda c: z[c]) if z[c] <= -0.7][:3]
        strengths = [{"key": c, "label": LABEL[c], "gap": round((tot[t][c] - mean[c]) * ppi, 1), "rank": ranks[c][t]}
                     for c in sorted(COMPS, key=lambda c: -z[c]) if z[c] >= 0.7][:3]
        lr = ln.get(t)
        slot = None
        if lr:
            k = max(SLOT, key=lambda k: lr.get("rk_" + k, 0))
            slot = {"key": k, "label": SLOT[k], "rank": lr.get("rk_" + k)}
        # best lineup by talent (real positions) -> extras + weakest regular F and D
        best = lineup_mod.best(L)
        in_best = {p["id"] for k in ("topF", "depF", "topD", "depD") for p in best[k]}
        weakest = {"F": min(best["topF"] + best["depF"], key=lambda p: p["tal"], default=None),
                   "D": min(best["topD"] + best["depD"], key=lambda p: p["tal"], default=None)}
        surplus = []
        for p in L:
            why = []
            if p["id"] not in in_best and (p.get("tpg") or 0) >= 10:
                why.append("extra: outside the best lineup by talent")
            if p.get("vs") is not None and p.get("vsHi") is not None:
                hi90 = p["vs"] + (p["vsHi"] - p["vs"]) * 1.645 / 1.96
                if hi90 < 0:
                    why.append("overpaid for output: clearly below market for his cap hit")
            if why:
                surplus.append({"id": p["id"], "n": p["n"], "pos": p["pos"], "cap": p.get("cap"), "tal": p["tal"], "why": why})
        surplus.sort(key=lambda s: s["tal"])
        out[t] = {"needs": needs, "strengths": strengths, "slot": slot, "surplus": surplus[:8],
                  "weakest": {g: ({"id": w["id"], "n": w["n"], "tal": w["tal"]} if w else None) for g, w in weakest.items()}}
    return out
