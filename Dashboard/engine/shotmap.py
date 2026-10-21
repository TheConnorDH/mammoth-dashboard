"""Shot maps from MoneyPuck shot-level data: where Utah creates and allows unblocked shot attempts, as expected
goals per game in each zone of the offensive end, compared with the league-average team."""
import csv

XS = list(range(25, 90, 8))      # blue line (25 ft) to goal line (89 ft), 8-ft columns
YS = list(range(-42, 43, 12))    # boards to boards, 12-ft rows


def cell(x, y):
    if x < 25 or x > 89 or abs(y) > 42:      # behind-the-net attempts are left out of the map
        return None
    i = min(int((x - 25) // 8), len(XS) - 2)
    j = min(int((y + 42) // 12), len(YS) - 2)
    return i, j


def build(path, team, season_games_played=None):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    games = {}
    for r in rows:
        games.setdefault(r["game_id"], set()).update([r["homeTeamCode"], r["awayTeamCode"]])
    team_games = sum(len(v) for v in games.values())
    ugames = sum(1 for v in games.values() if team in v)
    nx, ny = len(XS) - 1, len(YS) - 1
    def grid():
        return [[0.0] * ny for _ in range(nx)]
    out = {k: {"uta": grid(), "lg": grid(), "goals": []} for k in ("ev_for", "ev_against", "pp_for")}
    for r in rows:
        if r["event"] not in ("SHOT", "MISS", "GOAL") or float(r.get("shotOnEmptyNet") or 0) == 1:
            continue
        try:
            x, y, xg = float(r["xCordAdjusted"]), float(r["yCordAdjusted"]), float(r["xGoal"])
        except ValueError:
            continue
        c = cell(x, y)
        if not c:
            continue
        home = r["isHomeTeam"] in ("1", "1.0")
        shooter = r["homeTeamCode"] if home else r["awayTeamCode"]
        defender = r["awayTeamCode"] if home else r["homeTeamCode"]
        sk_for = int(float(r["homeSkatersOnIce"] if home else r["awaySkatersOnIce"])); sk_ag = int(float(r["awaySkatersOnIce"] if home else r["homeSkatersOnIce"]))
        kinds = []
        if sk_for == 5 and sk_ag == 5:
            kinds = [("ev_for", shooter == team), ("ev_against", defender == team)]
        elif sk_for == 5 and sk_ag == 4:
            kinds = [("pp_for", shooter == team)]
        for k, mine in kinds:
            out[k]["lg"][c[0]][c[1]] += xg
            if mine:
                out[k]["uta"][c[0]][c[1]] += xg
                if r["event"] == "GOAL":
                    out[k]["goals"].append([round(x, 1), round(y, 1)])
    res = {"xs": XS, "ys": YS, "games": ugames, "teamGames": team_games, "maps": {}}
    for k, d in out.items():
        u = [[round(v / max(ugames, 1), 4) for v in col] for col in d["uta"]]
        l = [[round(v / max(team_games, 1), 4) for v in col] for col in d["lg"]]
        tot_u = sum(map(sum, u)); tot_l = sum(map(sum, l))
        # slot = 65-89 ft (three columns nearest the net) x the middle 36 ft between the faceoff dots (y -18..18)
        slot = lambda g: sum(g[i][j] for i in (nx - 3, nx - 2, nx - 1) for j in (ny // 2 - 1, ny // 2, ny // 2 + 1))
        res["maps"][k] = {"uta": u, "lg": l, "goals": d["goals"], "total": round(tot_u, 3), "lgTotal": round(tot_l, 3),
                          "slotShare": round(slot(u) / tot_u, 3) if tot_u else None, "lgSlotShare": round(slot(l) / tot_l, 3) if tot_l else None}
    return res
