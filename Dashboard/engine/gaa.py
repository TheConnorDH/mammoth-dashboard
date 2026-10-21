"""Goals Above Average (GAA) player model, built from MoneyPuck season-summary files.

Every skater and goalie is measured in GOALS relative to an average NHL player at the same
position, given the same ice time in each game state. Units are shared across F, D and G, so all
three rank on one axis. Each value carries a standard error from event-level randomness, giving a
95% interval (value +/- 1.96 SE).

Skater components
  EV offense   (on-ice 5v5 xGF/60 - position avg) x 5v5 hours / 5      shared equally by 5 skaters
  EV defense   (position avg - on-ice 5v5 xGA/60) x 5v5 hours / 5
  PP offense   (on-ice 5v4 xGF/60 - position avg) x 5v4 hours / 5
  PK defense   (position avg - on-ice 4v5 xGA/60) x 4v5 hours / 4
  Finishing    individual goals - individual xG (all situations)
  Penalties    0.17 x (penalties drawn - penalties taken)   ~net goal value of one power play
  Faceoffs     0.01 x (wins - losses)                        small, literature-range value
Goalies
  Goals saved above expected (xGA - GA), all situations.

What it does not do: isolate a player from his linemates or opponents (that needs play-by-play
regression, i.e. RAPM). Team totals reconcile to goal differential within the error documented in
validate(); see build output.
"""
import math

PEN_VALUE = 0.17
FO_VALUE = 0.01
PLAY_W = 0.0      # weight on primary assists; secondary assists get half. Set from validate.py (data-chosen).
SHOOT_S = 0.2     # share of a shot's xG credited to the shooter (rest split among on-ice teammates). 0.2 = equal
                  # five-way split. Set from validate.py (data-chosen).
SITS = ("5on5", "5on4", "4on5")


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def grp(pos):
    return "D" if pos == "D" else "F"


def ep2_by_situation(team_rows, season):
    """E[p^2] of shot goal-probabilities per situation, from danger-bucket xG (league-wide).
    Within-bucket spread is ignored, so this is a lower bound; inflate by 1.2 to stay conservative."""
    out = {}
    for sit in SITS + ("all",):
        n = s = 0.0
        for r in team_rows:
            if r["season"] != season or r["position"] != "Team Level" or r["situation"] != sit:
                continue
            for b in ("lowDanger", "mediumDanger", "highDanger"):
                k = num(r[f"{b}ShotsFor"]); xg = num(r[f"{b}xGoalsFor"])
                if k > 0:
                    n += k; s += k * (xg / k) ** 2
        out[sit] = 1.2 * s / n if n else 0.01
    return out


def compute(skater_rows, goalie_rows, team_rows, season, team=None, play_w=None, shoot_s=None):
    play_w = PLAY_W if play_w is None else play_w
    s_sh = SHOOT_S if shoot_s is None else shoot_s
    ep2 = ep2_by_situation(team_rows, season)
    # index skaters by player and situation
    P = {}
    for r in skater_rows:
        if r["season"] != season:
            continue
        P.setdefault((r["playerId"], r["name"], r["team"], r["position"]), {})[r["situation"]] = r
    # position baselines per situation (ice-time weighted league averages)
    base = {}
    for sit in SITS:
        for g in ("F", "D"):
            f = a = h = ix = 0.0
            for (pid, nm, tm, pos), d in P.items():
                r = d.get(sit)
                if r is None or grp(pos) != g:
                    continue
                f += num(r["OnIce_F_xGoals"]); a += num(r["OnIce_A_xGoals"]); h += num(r["icetime"]) / 3600; ix += num(r["I_F_xGoals"])
            base[(sit, g)] = (f / h if h else 0, a / h if h else 0, ix / h if h else 0)
    # playmaking baseline: primary / secondary assists per on-ice TEAMMATE goal, by position (all situations)
    pm = {}
    for g in ("F", "D"):
        a1 = a2 = og = 0.0
        for (pid, nm, tm, pos), d in P.items():
            r = d.get("all")
            if r is None or grp(pos) != g:
                continue
            a1 += num(r.get("I_F_primaryAssists")); a2 += num(r.get("I_F_secondaryAssists"))
            og += num(r.get("OnIce_F_goals")) - num(r.get("I_F_goals"))   # teammates' goals only: you can't assist your own
        pm[g] = (a1 / og if og else 0, a2 / og if og else 0)
    out = []
    for (pid, nm, tm, pos), d in P.items():
        if team and tm != team:
            continue
        g = grp(pos)
        al = d.get("all")
        if not al:
            continue
        comp, var = {}, 0.0
        share = {"5on5": 5, "5on4": 5, "4on5": 4}
        for sit, key_off, key_def in (("5on5", "ev_off", "ev_def"), ("5on4", "pp_off", None), ("4on5", None, "pk_def")):
            r = d.get(sit)
            if r is None:
                if key_off: comp[key_off] = 0.0
                if key_def: comp[key_def] = 0.0
                continue
            h = num(r["icetime"]) / 3600
            bf, ba, bix = base[(sit, g)]
            n_sk = share[sit]
            if key_off:
                # shooter keeps share s of his own shots' xG; teammates' shots are split (1-s)/(n-1)
                ix, onf = num(r["I_F_xGoals"]), num(r["OnIce_F_xGoals"])
                own = ix - bix * h
                mates = (onf - ix) - (bf - bix) * h
                comp[key_off] = s_sh * own + (1 - s_sh) / (n_sk - 1) * mates
                ish, ons = num(r["I_F_unblockedShotAttempts"]), num(r["OnIce_F_unblockedShotAttempts"])
                var += (s_sh ** 2 * ish + ((1 - s_sh) / (n_sk - 1)) ** 2 * max(ons - ish, 0)) * ep2[sit]
            if key_def:
                comp[key_def] = (ba * h - num(r["OnIce_A_xGoals"])) / n_sk
                var += num(r["OnIce_A_unblockedShotAttempts"]) * ep2[sit] / n_sk ** 2
        ig, ixg, ish = num(al["I_F_goals"]), num(al["I_F_xGoals"]), num(al["I_F_unblockedShotAttempts"])
        comp["finishing"] = ig - ixg
        var += max(0.0, ixg - ish * ep2["all"])
        pd, pt = num(al["penaltiesDrawn"]), num(al["penalties"])
        comp["penalties"] = PEN_VALUE * (pd - pt)
        var += PEN_VALUE ** 2 * (pd + pt)
        # playmaking: zero-sum within a team (credit for setting up a larger share of on-ice goals than
        # an average player at the position, taken from teammates who set up fewer)
        if play_w:
            og = num(al.get("OnIce_F_goals")) - num(al.get("I_F_goals")); a1 = num(al.get("I_F_primaryAssists")); a2 = num(al.get("I_F_secondaryAssists"))
            comp["playmaking"] = play_w * (a1 - pm[g][0] * og) + 0.5 * play_w * (a2 - pm[g][1] * og)
            var += play_w ** 2 * (a1 + 0.25 * a2)
        fw, fl = num(al["faceoffsWon"]), num(al["faceoffsLost"])
        comp["faceoffs"] = FO_VALUE * (fw - fl)
        var += FO_VALUE ** 2 * (fw + fl)
        total = sum(comp.values())
        se = math.sqrt(var)
        gp = int(num(al["games_played"]))
        toi = num(al["icetime"]) / 60
        out.append({"id": pid, "name": nm, "team": tm, "pos": pos, "grp": g, "gp": gp, "toi": round(toi, 1),
                    "gaa": round(total, 2), "se": round(se, 2), "lo": round(total - 1.96 * se, 2), "hi": round(total + 1.96 * se, 2),
                    "per60": round(total / (toi / 60), 3) if toi else 0, "comp": {k: round(v, 2) for k, v in comp.items()}})
    for r in goalie_rows:
        if r["season"] != season or r["situation"] != "all":
            continue
        if team and r["team"] != team:
            continue
        xga, ga, n = num(r["xGoals"]), num(r["goals"]), num(r["unblocked_shot_attempts"])
        total = xga - ga
        se = math.sqrt(max(0.0, xga - n * ep2["all"]))
        toi = num(r["icetime"]) / 60
        out.append({"id": r["playerId"], "name": r["name"], "team": r["team"], "pos": "G", "grp": "G", "gp": int(num(r["games_played"])),
                    "toi": round(toi, 1), "gaa": round(total, 2), "se": round(se, 2), "lo": round(total - 1.96 * se, 2), "hi": round(total + 1.96 * se, 2),
                    "per60": round(total / (toi / 60), 3) if toi else 0, "comp": {"goaltending": round(total, 2)}})
    return out


def verdict(p):
    if p["lo"] > 0:
        return "above"
    if p["hi"] < 0:
        return "below"
    return "unclear"
