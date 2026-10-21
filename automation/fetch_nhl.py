"""NHL public API (api-web.nhle.com): standings, Utah schedule, full league schedule/results, Utah box scores,
Utah roster, and birth dates for players MoneyPuck's lookup doesn't have yet. Writes the exact files build.py reads."""
import csv, glob, json, os, datetime as dt
from common import P, TEAM, NHL_SEASON, get, get_json, write_text, write_json, log

API = "https://api-web.nhle.com/v1"
FINAL = ("OFF", "FINAL")


def _save_raw(path, url, text):
    # build.py reads these files by searching for the JSON start, so keep the raw compact JSON after a header
    write_text(path, f"{url}\n→ {url}\nContent-Type: application/json\n\n{text}")


def standings():
    url = f"{API}/standings/now"
    t = get(url); j = json.loads(t)
    if len(j.get("standings", [])) != 32:
        raise RuntimeError(f"standings: {len(j.get('standings', []))} teams")
    _save_raw(P("inputs", "nhl", "standings.txt"), url, t)
    return j


def utah_schedule():
    url = f"{API}/club-schedule-season/{TEAM}/{NHL_SEASON}"
    t = get(url); j = json.loads(t)
    if not j.get("games"):
        raise RuntimeError("club schedule empty")
    _save_raw(P("inputs", "nhl", "schedule_season.txt"), url, t)
    # month files were a manual fallback; the season file covers everything, so remove stale ones
    for f in glob.glob(P("inputs", "nhl", "schedule_20*.txt")):
        os.remove(f)
    return j


def league_schedule(start="2026-09-28", end="2027-04-30"):
    """Every regular-season game: {'id','date','home','away','state','hs','as','period'}; state 7 = final, 1 = not final."""
    games, d = {}, start
    while d and d <= end:
        j = get_json(f"{API}/schedule/{d}")
        for day in j.get("gameWeek", []):
            for g in day.get("games", []):
                if g.get("gameType") != 2:
                    continue
                fin = g.get("gameState") in FINAL
                games[g["id"]] = {"id": g["id"], "date": day["date"], "home": g["homeTeam"]["abbrev"], "away": g["awayTeam"]["abbrev"],
                                  "state": 7 if fin else 1, "hs": g["homeTeam"].get("score", 0) if fin else 0,
                                  "as": g["awayTeam"].get("score", 0) if fin else 0,
                                  "period": (g.get("periodDescriptor") or {}).get("number", 3) if fin else 1}
        d = j.get("nextStartDate")
    out = sorted(games.values(), key=lambda g: g["id"])
    if len(out) < 1300:
        raise RuntimeError(f"league schedule: only {len(out)} games")
    write_json(P("inputs", "nhl", "league_schedule.json"), {"fetched": dt.date.today().isoformat(), "games": out}, indent=None)
    log(f"league schedule: {len(out)} games, {sum(g['state'] == 7 for g in out)} final")
    return out


def roster():
    """Utah's current NHL roster -> config/roster.json (same shape as before)."""
    j = get_json(f"{API}/roster/{TEAM}/current")
    players = []
    for grp in ("forwards", "defensemen", "goalies"):
        for p in j.get(grp, []):
            h = p.get("heightInInches")
            players.append({"name": f'{p["firstName"]["default"]} {p["lastName"]["default"]}', "pos": p.get("positionCode"),
                            "number": p.get("sweaterNumber"), "shoots": p.get("shootsCatches"),
                            "height": f"{h // 12}' {h % 12}\"" if h else None, "weight": p.get("weightInPounds"), "playerId": str(p["id"])})
    if len(players) < 18:
        raise RuntimeError(f"roster: only {len(players)} players")
    # keep hand-set extras: a status note on anyone listed, and players listed with a status (e.g. assigned to the AHL)
    old_path = P("config", "roster.json")
    if os.path.exists(old_path):
        old = {p["playerId"]: p for p in json.load(open(old_path, encoding="utf-8"))["players"]}
        ids = {p["playerId"] for p in players}
        for p in players:
            if old.get(p["playerId"], {}).get("status"): p["status"] = old[p["playerId"]]["status"]
        players += [p for i, p in old.items() if i not in ids and p.get("status")]
    write_json(P("config", "roster.json"), {"source": f"NHL API roster, {dt.date.today().isoformat()}", "players": players})
    return players


def _names_by_id(players):
    # MoneyPuck's spelling first (the build joins box scores to MoneyPuck rows by name), then the NHL roster
    out = {}
    path = P("inputs", "allPlayersLookup.csv")
    if os.path.exists(path):
        for r in csv.DictReader(open(path, encoding="utf-8")):
            out[r["playerId"]] = r["name"]
    for p in players:
        out.setdefault(p["playerId"], p["name"])
    return out


def box_compact(box, land, names):
    """NHL boxscore + landing -> the compact Utah box score build.py expects."""
    home = box["homeTeam"]["abbrev"]; away = box["awayTeam"]["abbrev"]
    side = "homeTeam" if home == TEAM else "awayTeam"; oside = "awayTeam" if side == "homeTeam" else "homeTeam"
    pst = box["playerByGameStats"][side]
    a1, a2 = {}, {}
    for per in (land.get("summary") or {}).get("scoring", []):
        for g in per.get("goals", []):
            ast = g.get("assists", [])
            if len(ast) > 0: a1[ast[0]["playerId"]] = a1.get(ast[0]["playerId"], 0) + 1
            if len(ast) > 1: a2[ast[1]["playerId"]] = a2.get(ast[1]["playerId"], 0) + 1
    pt, pd = {}, {}
    for per in (land.get("summary") or {}).get("penalties", []):
        for pe in per.get("penalties", []):
            if pe.get("type") not in ("MIN", "MAJ"):
                continue
            mine = (pe.get("teamAbbrev") or {}).get("default") == TEAM
            c = (pe.get("committedByPlayer") or {}).get("sweaterNumber"); dr = (pe.get("drawnBy") or {}).get("sweaterNumber")
            if mine and c is not None: pt[c] = pt.get(c, 0) + 1
            if not mine and dr is not None: pd[dr] = pd.get(dr, 0) + 1
    sk = []
    for p in pst.get("forwards", []) + pst.get("defense", []):
        pid = p["playerId"]; num = p.get("sweaterNumber")
        sk.append({"name": names.get(str(pid), p["name"]["default"]), "pos": p.get("position"), "g": p.get("goals", 0), "a": p.get("assists", 0),
                   "sog": p.get("sog", 0), "hits": p.get("hits", 0), "toi": p.get("toi", "00:00"), "fo": p.get("faceoffWinningPctg", 0),
                   "pim": p.get("pim", 0), "blk": p.get("blockedShots", 0), "gv": p.get("giveaways", 0), "tk": p.get("takeaways", 0),
                   "ppg": p.get("powerPlayGoals", 0), "pm": p.get("plusMinus", 0), "a1": a1.get(pid, 0), "a2": a2.get(pid, 0),
                   "pt": pt.get(num, 0), "pd": pd.get(num, 0)})
    gl = []
    for p in pst.get("goalies", []):
        if p.get("toi", "00:00") in ("00:00", "0:00"):
            continue
        g = {"name": names.get(str(p["playerId"]), p["name"]["default"]), "sa": p.get("shotsAgainst", 0), "sv": p.get("saves", 0),
             "ga": p.get("goalsAgainst", 0), "toi": p.get("toi"), "start": bool(p.get("starter"))}
        if p.get("decision"): g["decision"] = p["decision"]
        gl.append(g)
    return {"id": box["id"], "date": box["gameDate"], "home": home, "away": away,
            "uta_score": box[side]["score"], "opp_score": box[oside]["score"], "uta_sog": box[side].get("sog"), "opp_sog": box[oside].get("sog"),
            "last_period": (box.get("gameOutcome") or {}).get("lastPeriodType", "REG"), "skaters": sk, "goalies": gl, "landing": True,
            "source": "NHL API boxscore + landing (automated)"}


def boxscores(sched_games, players):
    """Add box scores for Utah's finished games that don't have one yet. A box still cached as live is skipped (tried again next run)."""
    names = _names_by_id(players)
    have = {}
    for f in glob.glob(P("inputs", "nhl", "boxscores", "*.json")):
        have[os.path.basename(f)[:-5]] = json.load(open(f, encoding="utf-8"))
    recent = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    added, waiting = [], []
    for g in sched_games:
        if TEAM not in (g["home"], g["away"]) or g["state"] != 7:
            continue
        old = have.get(str(g["id"]))
        # new games, plus automated boxes from the last 3 days (the NHL sometimes changes goal/assist credit the next day)
        if old and not ("automated" in old.get("source", "") and g["date"] >= recent):
            continue
        box = land = None
        for q in ("", "?final=1", "?final=2"):
            b = get_json(f"{API}/gamecenter/{g['id']}/boxscore{q}")
            if b.get("gameState") in FINAL:
                box = b; break
        for q in ("", "?final=1", "?final=2"):
            l_ = get_json(f"{API}/gamecenter/{g['id']}/landing{q}")
            if l_.get("gameState") in FINAL:
                land = l_; break
        if not box or not land:
            waiting.append(g["id"]); continue
        c = box_compact(box, land, names)
        so = 1 if c["last_period"] == "SO" and c["uta_score"] > c["opp_score"] else 0
        if c["uta_score"] + c["opp_score"] != g["hs"] + g["as"] or sum(s["g"] for s in c["skaters"]) != c["uta_score"] - so:
            if not old: waiting.append(g["id"])
            continue
        for s in c["skaters"] + c["goalies"]:
            if ". " in s["name"][:3]: log(f"  name not found by id, using NHL short name: {s['name']}")
        if old and {k: v for k, v in old.items() if k != "source"} == {k: v for k, v in c.items() if k != "source"}:
            continue
        write_json(P("inputs", "nhl", "boxscores", f"{g['id']}.json"), c)
        added.append(g["id"])
    log("box scores added:", added, "still waiting:", waiting)
    return added, waiting


def bios(min_needed_from=("skaters", "goalies")):
    """Birth dates for players in this season's MoneyPuck files that neither the lookup nor the supplement covers."""
    known = set()
    for name in ("allPlayersLookup.csv", "bio_supplement.csv"):
        path = P("inputs", name)
        if os.path.exists(path):
            for r in csv.DictReader(open(path, encoding="utf-8")):
                if r.get("birthDate"): known.add(r["playerId"])
    need = {}
    for f in min_needed_from:
        for r in csv.DictReader(open(P("inputs", "moneypuck", f"{f}.csv"), encoding="utf-8")):
            if r["playerId"] not in known: need[r["playerId"]] = r
    path = P("inputs", "bio_supplement.csv")
    rows = list(csv.DictReader(open(path, encoding="utf-8"))) if os.path.exists(path) else []
    n0 = len(rows)
    cols = ["playerId", "name", "position", "team", "birthDate", "weight", "height", "nationality", "shootsCatches", "primaryNumber", "primaryPosition", "source"]
    for pid, r in list(need.items())[:60]:
        try:
            j = get_json(f"{API}/player/{pid}/landing", tries=2)
        except RuntimeError:
            continue
        if not j.get("birthDate"):
            continue
        h = j.get("heightInInches")
        rows.append({"playerId": pid, "name": r.get("name"), "position": j.get("position"), "team": j.get("currentTeamAbbrev") or r.get("team"),
                     "birthDate": j.get("birthDate"), "weight": j.get("weightInPounds"), "height": f"{h // 12}' {h % 12}\"" if h else "",
                     "nationality": j.get("birthCountry"), "shootsCatches": j.get("shootsCatches"), "primaryNumber": j.get("sweaterNumber"),
                     "primaryPosition": j.get("position"), "source": f"NHL API player landing {dt.date.today().isoformat()}"})
    if len(rows) > n0:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
    log(f"birth dates: {len(need)} missing, {len(rows) - n0} added")


if __name__ == "__main__":
    standings(); utah_schedule(); s = league_schedule(); pl = roster(); boxscores(s, pl)
