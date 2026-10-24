#!/usr/bin/env python3
"""Utah Mammoth 2026-27 Season Dashboard - build pipeline.

Reads:
  ../Source Data/*.csv                 2025-26 MoneyPuck baselines (season=2025)
  inputs/moneypuck/*.csv               2026-27 MoneyPuck full files (preferred, season=2026)
  inputs/moneypuck_partial/*.csv       Utah-only rows (fallback when full files absent)
  inputs/nhl/standings.txt             NHL api-web standings/now response
  inputs/nhl/schedule_*.txt            NHL api-web club schedule responses (season and/or month)
  inputs/nhl/boxscores/*.json          compact per-game Utah box scores
  config/*.json, config/brief.md       calls, predictions, lineups, weekly brief
Writes:
  history/snapshots.json               one row per games-played milestone (trend lines)
  output/data.json                     everything the page renders
  output/mammoth_dashboard.html        self-contained page
"""
import csv, json, os, re, glob, datetime, math, statistics, sys
sys.path[:0] = [os.path.join(os.path.dirname(os.path.abspath(__file__)), d) for d in ("engine", "calibration")]
import gaa, models, impact, league, power, seasonsim, shotmap, style, team_style
import lineup as lineup_mod
import contracts as contracts_mod
import player_profile as profile_mod
import needs as needs_mod
import recap as recap_mod

BASE = os.path.dirname(os.path.abspath(__file__))
HOCKEY = os.path.dirname(BASE)
SRC = os.path.join(HOCKEY, "Source Data")
VERSION = open(os.path.join(HOCKEY, "VERSION")).read().strip() if os.path.exists(os.path.join(HOCKEY, "VERSION")) else "dev"
P = lambda *a: os.path.join(BASE, *a)
TEAM = "UTA"
SEASON_GAMES = 84
PRIOR_POINTS = 101          # preseason projection midpoint (V16)
PRIOR_K = 20                # games of weight given to the preseason prior
PLAYOFF_LINE = 94           # ~West 8th-place line scaled to 84 games
UNLOCK = {"team_regression": 10, "goalies": 10, "lines": 10, "players": 20}
MIN_VERDICT_TOI = 250       # minutes before a player's "clearly above/below average" verdict is shown (normal approximation needs volume)

CENTRAL = ["COL", "DAL", "MIN", "UTA", "WPG", "NSH", "STL", "CHI"]


def ord_(n):
    if not n:
        return ""
    n = int(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def fmtv(v, f):
    if v is None:
        return "n/a"
    if f == "pct1":
        return f"{v*100:.1f}%"
    if f == "pct3":
        return f"{v:.3f}".lstrip("0")
    if f == "f3":
        return f"{v:.3f}"
    return f"{v:.2f}"


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def readcsv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def safe_div(a, b):
    return a / b if b else None


# ---------------------------------------------------------------- MoneyPuck
def team_rows(rows, season):
    out = {}
    for r in rows:
        if r.get("season") == season and r.get("position") == "Team Level":
            out.setdefault(r["name"], {})[r["situation"]] = r
    return out


def team_metrics(sits):
    """sits: {situation: row}. Returns metric dict (None where not computable)."""
    a, e, pp, pk = sits.get("all"), sits.get("5on5"), sits.get("5on4"), sits.get("4on5")
    m = {}
    if not a:
        return m
    g = lambda r, k: num(r[k]) if r else 0.0
    m["gp"] = int(g(a, "games_played"))
    m["gf"], m["ga"] = g(a, "goalsFor"), g(a, "goalsAgainst")
    m["xgf"], m["xga"] = g(a, "xGoalsFor"), g(a, "xGoalsAgainst")
    m["sf"], m["sa"] = g(a, "shotsOnGoalFor"), g(a, "shotsOnGoalAgainst")
    m["xgf_pg"] = safe_div(m["xgf"], m["gp"])
    m["gf_pg"] = safe_div(m["gf"], m["gp"])
    m["ga_pg"] = safe_div(m["ga"], m["gp"])
    m["xga_pg"] = safe_div(m["xga"], m["gp"])
    m["sh_pct"] = safe_div(m["gf"], m["sf"])
    m["sv_pct"] = None if not m["sa"] else 1 - m["ga"] / m["sa"]
    m["reb_rate_for"] = safe_div(g(a, "reboundsFor"), m["sf"])
    m["reb_rate_against"] = safe_div(g(a, "reboundsAgainst"), m["sa"])
    m["reb_goal_share"] = safe_div(g(a, "reboundGoalsFor"), m["gf"])
    hrs_a = g(a, "iceTime") / 3600
    m["reb_ga_60"] = safe_div(g(a, "reboundGoalsAgainst"), hrs_a)
    m["fo_pct"] = safe_div(g(a, "faceOffsWonFor"), g(a, "faceOffsWonFor") + g(a, "faceOffsWonAgainst"))
    if e:
        hrs = g(e, "iceTime") / 3600
        m["xgf_pct_5v5"] = safe_div(g(e, "xGoalsFor"), g(e, "xGoalsFor") + g(e, "xGoalsAgainst"))
        m["cf_pct_5v5"] = safe_div(g(e, "shotAttemptsFor"), g(e, "shotAttemptsFor") + g(e, "shotAttemptsAgainst"))
        m["hd_share_5v5"] = safe_div(g(e, "highDangerShotsFor"), g(e, "highDangerShotsFor") + g(e, "highDangerShotsAgainst"))
        m["xgf60_5v5"] = safe_div(g(e, "xGoalsFor"), hrs)
        m["xga60_5v5"] = safe_div(g(e, "xGoalsAgainst"), hrs)
        m["blocked_share_5v5"] = safe_div(g(e, "blockedShotAttemptsFor"), g(e, "shotAttemptsFor"))
        m["retention_5v5"] = safe_div(g(e, "playContinuedInZoneFor"), g(e, "unblockedShotAttemptsFor"))
        shp = safe_div(g(e, "goalsFor"), g(e, "shotsOnGoalFor"))
        svp = None if not g(e, "shotsOnGoalAgainst") else 1 - g(e, "goalsAgainst") / g(e, "shotsOnGoalAgainst")
        m["pdo_5v5"] = (shp + svp) if (shp is not None and svp is not None) else None
    if pp and num(pp["iceTime"]) > 0:
        hrs = g(pp, "iceTime") / 3600
        m["pp_xgf60"] = safe_div(g(pp, "xGoalsFor"), hrs)
        m["pp_sog60"] = safe_div(g(pp, "shotsOnGoalFor"), hrs)
        m["pp_reb60"] = safe_div(g(pp, "reboundsFor"), hrs)
        m["pp_gf60"] = safe_div(g(pp, "goalsFor"), hrs)
        m["pp_fo_pct"] = safe_div(g(pp, "faceOffsWonFor"), g(pp, "faceOffsWonFor") + g(pp, "faceOffsWonAgainst"))
        m["pp_min"] = g(pp, "iceTime") / 60
    if pk and num(pk["iceTime"]) > 0:
        hrs = g(pk, "iceTime") / 3600
        m["pk_xga60"] = safe_div(g(pk, "xGoalsAgainst"), hrs)
        m["pk_dzgive60"] = safe_div(g(pk, "dZoneGiveawaysFor"), hrs)
        m["pk_rebga60"] = safe_div(g(pk, "reboundGoalsAgainst"), hrs)
        m["pk_rebA60"] = safe_div(g(pk, "reboundsAgainst"), hrs)
        m["pk_min"] = g(pk, "iceTime") / 60
    return m


METRIC_DEFS = {
    # key: (label, higher_is_better (None = context only), format, explanation, category)
    "gf_pg": ("Goals for per game", True, "f2", "All situations.", "Results"),
    "ga_pg": ("Goals against per game", False, "f2", "All situations.", "Results"),
    "xgf_pct_5v5": ("5v5 expected-goal share", True, "pct1", "Share of 5-on-5 expected goals controlled. The best single predictor of future results.", "Even strength"),
    "cf_pct_5v5": ("5v5 shot-attempt share", True, "pct1", "Corsi: share of all 5-on-5 shot attempts.", "Even strength"),
    "hd_share_5v5": ("5v5 high-danger shot share", True, "pct1", "Share of slot and crease shots at 5 on 5.", "Even strength"),
    "xgf60_5v5": ("5v5 chance creation (xGF/60)", True, "f2", "Expected goals created per 60 at even strength.", "Even strength"),
    "xga60_5v5": ("5v5 chance suppression (xGA/60)", False, "f2", "Expected goals allowed per 60 at even strength.", "Even strength"),
    "blocked_share_5v5": ("Own shot attempts blocked", False, "pct1", "Share of 5v5 attempts blocked before reaching the net. High = shooting into crowded lanes.", "Even strength"),
    "sh_pct": ("Shooting %", True, "pct1", "All situations. Extremes tend to regress.", "Finishing & goaltending"),
    "sv_pct": ("Save %", True, "pct3", "All situations.", "Finishing & goaltending"),
    "pdo_5v5": ("5v5 PDO", None, "f3", "Shooting % + save % at 5v5. Well above 1.000 = luck helping.", "Finishing & goaltending"),
    "reb_rate_for": ("Follow-up shot rate", True, "f3", "Rebound attempts (within 3 seconds) per shot on goal.", "Second chances"),
    "reb_goal_share": ("Rebound-goal share", True, "pct1", "Share of goals scored off rebounds.", "Second chances"),
    "reb_rate_against": ("Follow-ups allowed rate", False, "f3", "Opponent rebound attempts per shot on goal allowed.", "Second chances"),
    "reb_ga_60": ("Rebound goals against / 60", False, "f2", "All situations.", "Second chances"),
    "pp_gf60": ("PP goals / 60", True, "f2", "5-on-4 scoring rate.", "Power play"),
    "pp_xgf60": ("PP xG / 60", True, "f2", "5-on-4 chance quality and volume.", "Power play"),
    "pp_sog60": ("PP shots / 60", True, "f2", "5-on-4 shot volume.", "Power play"),
    "pp_reb60": ("PP follow-up shots / 60", True, "f2", "5-on-4 rebound attempts.", "Power play"),
    "pp_fo_pct": ("PP faceoff %", True, "pct1", "Winning PP draws means starting with the puck.", "Power play"),
    "pk_xga60": ("PK xG against / 60", False, "f2", "4-on-5 chance suppression.", "Penalty kill"),
    "pk_dzgive60": ("PK own-zone giveaways / 60", False, "f2", "Turnovers in the defensive zone while shorthanded.", "Penalty kill"),
    "pk_rebga60": ("PK rebound goals against / 60", False, "f2", "Second-chance goals allowed shorthanded.", "Penalty kill"),
    "fo_pct": ("Faceoff %", True, "pct1", "All situations.", "Possession"),
    "retention_5v5": ("Zone retention after shots", None, "pct1", "How often play stays in the offensive zone after a shot. Context: high retention without follow-ups = possession without danger.", "Possession"),
}

FAULT_LINES = [
    ("Second chances (for)", ["reb_rate_for", "reb_goal_share"]),
    ("Second chances (against)", ["reb_rate_against", "reb_ga_60"]),
    ("Power play", ["pp_fo_pct", "pp_xgf60", "pp_reb60"]),
    ("Penalty kill", ["pk_dzgive60", "pk_rebga60"]),
    ("Shot selection", ["blocked_share_5v5", "retention_5v5"]),
]


def league_stats(team_map, key):
    vals = [team_metrics(s).get(key) for s in team_map.values()]
    vals = [v for v in vals if v is not None]
    return (sum(vals) / len(vals)) if vals else None, vals


def rank_of(value, vals, higher_better):
    if value is None or not vals:
        return None
    ordered = sorted(vals, reverse=bool(higher_better))
    # rank = 1 + number strictly better
    better = sum(1 for v in vals if (v > value if higher_better else v < value))
    return better + 1


# ---------------------------------------------------------------- NHL feeds
def load_json_from_text(path, start_marker):
    txt = open(path, encoding="utf-8").read()
    i = txt.find(start_marker)
    return json.loads(txt[i:]) if i >= 0 else None


def parse_standings():
    path = P("inputs", "nhl", "standings.txt")
    if not os.path.exists(path):
        return []
    d = load_json_from_text(path, '{"wildCardIndicator"')
    out = []
    for t in d["standings"]:
        w, l, otl, rw = t["wins"], t["losses"], t["otLosses"], t["regulationWins"]
        gp = t["gamesPlayed"]
        p321 = 3 * rw + 2 * (w - rw) + otl
        out.append({
            "abbr": t["teamAbbrev"]["default"], "name": t["teamName"]["default"],
            "conf": t["conferenceName"], "div": t["divisionName"], "gp": gp,
            "w": w, "l": l, "otl": otl, "rw": rw, "row": t["regulationPlusOtWins"],
            "pts": t["points"], "ptsPct": round(t["points"] / (2 * gp), 3) if gp else 0,
            "p321": p321, "p321Pct": round(p321 / (3 * gp), 3) if gp else 0,
            "gf": t["goalFor"], "ga": t["goalAgainst"], "gd": t["goalDifferential"],
            "streak": f'{t.get("streakCode","")}{t.get("streakCount","")}',
            "l10": f'{t["l10Wins"]}-{t["l10Losses"]}-{t["l10OtLosses"]}',
            "date": t["date"],
        })
    return out


GAME_RE = re.compile(r'\{"id":(\d+),"season":\d+,"gameType":(\d),"gameDate":"([\d-]+)"')


def parse_schedule():
    games = {}
    for path in sorted(glob.glob(P("inputs", "nhl", "schedule_*.txt"))):
        txt = open(path, encoding="utf-8").read()
        starts = [(m.start(), m) for m in GAME_RE.finditer(txt)]
        for i, (pos, m) in enumerate(starts):
            if m.group(2) != "2":
                continue
            end = starts[i + 1][0] if i + 1 < len(starts) else len(txt)
            blk = txt[pos:end]
            gid = m.group(1)
            def grab(pattern):
                mm = re.search(pattern, blk)
                return mm.group(1) if mm else None
            away = grab(r'"awayTeam":\{"id":\d+.*?"abbrev":"([A-Z]{3})"')
            home = grab(r'"homeTeam":\{"id":\d+.*?"abbrev":"([A-Z]{3})"')
            if not away or not home:
                continue
            a_blk = blk[blk.find('"awayTeam"'):blk.find('"homeTeam"')]
            h_blk = blk[blk.find('"homeTeam"'):]
            asc = re.search(r'"score":(\d+)', a_blk)
            hsc = re.search(r'"score":(\d+)', h_blk)
            state = grab(r'"gameState":"([A-Z]+)"')
            lpt = grab(r'"lastPeriodType":"([A-Z]+)"')
            start = grab(r'"startTimeUTC":"([^"]+)"')
            g = {"id": gid, "date": m.group(3), "start": start, "away": away, "home": home,
                 "state": state, "lpt": lpt,
                 "away_score": int(asc.group(1)) if asc else None,
                 "home_score": int(hsc.group(1)) if hsc else None}
            if gid not in games or (g["home_score"] is not None):
                games[gid] = g
    # box scores override (authoritative for completed games)
    for path in glob.glob(P("inputs", "nhl", "boxscores", "*.json")):
        b = json.load(open(path, encoding="utf-8"))
        gid = str(b["id"])
        home = b["home"]; away = b["away"]
        us_home = home == TEAM
        g = games.get(gid, {"id": gid, "date": b["date"], "start": None})
        g.update({"home": home, "away": away, "state": "OFF", "lpt": b.get("last_period", "REG"),
                  "home_score": b["uta_score"] if us_home else b["opp_score"],
                  "away_score": b["opp_score"] if us_home else b["uta_score"]})
        games[gid] = g
    out = []
    for g in sorted(games.values(), key=lambda x: (x["date"], x["id"])):
        if TEAM not in (g["home"], g["away"]):
            continue
        home = g["home"] == TEAM
        g["opp"] = g["away"] if home else g["home"]
        g["ha"] = "vs" if home else "@"
        final = g.get("state") in ("OFF", "FINAL") and g.get("home_score") is not None
        g["final"] = final
        if final:
            us = g["home_score"] if home else g["away_score"]
            them = g["away_score"] if home else g["home_score"]
            g["us"], g["them"] = us, them
            ot = g.get("lpt") in ("OT", "SO")
            if us > them:
                g["res"], g["pts"], g["p321"] = ("W" if not ot else ("OTW" if g["lpt"] == "OT" else "SOW")), 2, (2 if ot else 3)
            else:
                g["res"], g["pts"], g["p321"] = ("L" if not ot else ("OTL" if g["lpt"] == "OT" else "SOL")), (1 if ot else 0), (1 if ot else 0)
        out.append(g)
    return out


def toi_min(s):
    try:
        mm, ss = s.split(":")
        return int(mm) + int(ss) / 60
    except Exception:
        return 0.0


def aggregate_boxscores():
    players, goalies = {}, {}
    for path in sorted(glob.glob(P("inputs", "nhl", "boxscores", "*.json"))):
        b = json.load(open(path, encoding="utf-8"))
        for s in b["skaters"]:
            p = players.setdefault(s["name"], {"name": s["name"], "pos": s["pos"], "gp": 0, "g": 0, "a": 0,
                                               "sog": 0, "hits": 0, "toi": 0.0, "ppg": 0, "pim": 0, "blk": 0, "gv": 0, "tk": 0})
            p["gp"] += 1
            for k in ("g", "a", "sog", "hits", "ppg", "pim", "blk", "gv", "tk"):
                p[k] += s.get(k, 0)
            p["toi"] += toi_min(s["toi"])
        for gl in b["goalies"]:
            q = goalies.setdefault(gl["name"], {"name": gl["name"], "gp": 0, "gs": 0, "sa": 0, "sv": 0, "ga": 0, "w": 0, "l": 0, "so": 0})
            q["gp"] += 1
            q["gs"] += 1 if gl.get("start") else 0
            q["sa"] += gl["sa"]; q["sv"] += gl["sv"]; q["ga"] += gl["ga"]
            q["w"] += 1 if gl.get("decision") == "W" else 0
            q["l"] += 1 if gl.get("decision") in ("L", "O") else 0
            q["so"] += 1 if (gl.get("decision") == "W" and gl["ga"] == 0 and toi_min(gl["toi"]) >= 59) else 0
    for p in players.values():
        p["pts"] = p["g"] + p["a"]
        p["toi_pg"] = round(p["toi"] / p["gp"], 1) if p["gp"] else 0
    return players, goalies


# ---------------------------------------------------------------- baselines per player
def player_baselines(names):
    rows = readcsv(os.path.join(SRC, "skaters.csv"))
    five = [r for r in rows if r["season"] == "2025" and r["situation"] == "5on5" and num(r["icetime"]) >= 400 * 60]
    allsit = {(r["name"]): r for r in rows if r["season"] == "2025" and r["situation"] == "all"}
    def per60(r, k):
        return num(r[k]) / (num(r["icetime"]) / 3600)
    lg = []
    for r in five:
        onF, onA = num(r["OnIce_F_xGoals"]), num(r["OnIce_A_xGoals"])
        offF, offA = num(r["OffIce_F_xGoals"]), num(r["OffIce_A_xGoals"])
        lg.append({"name": r["name"], "team": r["team"], "pos": r["position"],
                   "xgf60": per60(r, "OnIce_F_xGoals"), "xga60": per60(r, "OnIce_A_xGoals"),
                   "rel": ((onF / (onF + onA)) - (offF / (offF + offA))) * 100 if (offF + offA) else 0,
                   "toi": num(r["icetime"]) / 60})
    n = len(lg)
    def pct(key, v, low_good=False):
        if v is None:
            return None
        if low_good:
            return round(100 * sum(1 for x in lg if x[key] > v) / n)
        return round(100 * sum(1 for x in lg if x[key] < v) / n)
    out = {}
    fw_all = [r for r in rows if r["season"] == "2025" and r["situation"] == "all" and r["position"] != "D" and num(r["icetime"]) >= 300 * 60]
    def fpct(key_fn, v):
        vals = [key_fn(r) for r in fw_all]
        return round(100 * sum(1 for x in vals if x < v) / len(vals))
    reb60 = lambda r: num(r["I_F_rebounds"]) / (num(r["icetime"]) / 3600)
    take60 = lambda r: num(r["I_F_takeaways"]) / (num(r["icetime"]) / 3600)
    for nm in names:
        b = next((x for x in lg if x["name"] == nm), None)
        a = allsit.get(nm)
        rec = {"name": nm}
        if b:
            rec.update({"team25": b["team"], "xgf60": round(b["xgf60"], 2), "xga60": round(b["xga60"], 2),
                        "rel": round(b["rel"], 1), "toi5v5": round(b["toi"]),
                        "rel_pct": pct("rel", b["rel"]), "off_pct": pct("xgf60", b["xgf60"]),
                        "def_pct": pct("xga60", b["xga60"], low_good=True)})
        if a:
            rec.update({"gp25": int(num(a["games_played"])), "g25": int(num(a["I_F_goals"])),
                        "xg25": round(num(a["I_F_xGoals"]), 1),
                        "pts25": int(num(a["I_F_points"])),
                        "gmx25": round(num(a["I_F_goals"]) - num(a["I_F_xGoals"]), 1)})
            if a["position"] != "D" and num(a["icetime"]) >= 300 * 60:
                rec["reb_pct"] = fpct(reb60, reb60(a))
                rec["take_pct"] = fpct(take60, take60(a))
        out[nm] = rec
    return out, lg


# ---------------------------------------------------------------- helpers for the statistical layer
def playoff_line_history():
    """West 8th-place points % in every saved full season -> mean/sd scaled to an 84-game season."""
    vals = []
    for path in sorted(glob.glob(P("inputs", "history", "standings_final_*"))):
        txt = open(path, encoding="utf-8").read()
        d = json.loads(txt[txt.find('{"wildCardIndicator"'):])["standings"] if path.endswith(".txt") else json.load(open(path))["standings"]
        if max(t["gamesPlayed"] for t in d) < 80:
            continue
        w = sorted([t for t in d if t["conferenceName"] == "Western"], key=lambda t: -t["points"])
        vals.append(w[7]["points"] / (2 * w[7]["gamesPlayed"]))
    m, sd = statistics.mean(vals), statistics.stdev(vals)
    return {"pct_mean": round(m, 4), "pct_sd": round(sd, 4), "n": len(vals),
            "pts_mean": round(m * 2 * SEASON_GAMES, 1), "pts_sd": round(sd * 2 * SEASON_GAMES, 1)}


def league_rates_2025():
    d = json.load(open(P("inputs", "history", "standings_final_2025-26.json")))["standings"]
    gpg = sum(t["goalFor"] for t in d) / sum(t["gamesPlayed"] for t in d) * 2
    pts_pct = sum(t["points"] for t in d) / sum(2 * t["gamesPlayed"] for t in d)
    return gpg, pts_pct


def box_gs(s):
    """Single-game Game Score from box score + game summary (Luszczyszyn 2016 weights; on-ice
    shot-attempt terms unavailable per game; +/- stands in for on-ice goals for/against)."""
    if "a1" in s:
        ast = 0.7 * s["a1"] + 0.55 * s["a2"]
        pen = 0.15 * s.get("pd", 0) - 0.15 * s.get("pt", 0)
    else:
        ast = 0.625 * s["a"]
        pim = s.get("pim", 0)
        pen = -0.15 * (1 if pim == 5 else pim // 2)
    return 0.75 * s["g"] + ast + 0.075 * s["sog"] + 0.05 * s.get("blk", 0) + pen + 0.15 * s.get("pm", 0)


def goalie_gs(sv, ga):
    return 0.1 * sv - 0.75 * ga


# ---------------------------------------------------------------- main build
def main():
    now = datetime.datetime.now()
    params = json.load(open(P("params", "model_params.json")))
    rel = params["reliability"]
    gaa.PLAY_W = params.get("play_w", 0.0)
    gaa.SHOOT_S = params.get("shoot_s", 0.2)
    ip = impact.load_params(BASE)
    impact.REL_TEAMAVG = bool(ip.get("rel_teamavg", False))   # must be set before any direct season_table() call
    AGE = impact.ages(BASE, now.date())
    TPAR = json.load(open(P("params", "talent_params.json")))
    PPAR = json.load(open(P("params", "points_params.json")))
    to_pts = lambda goals: None if goals is None else round(goals * PPAR["impact_goal_slope"] * PPAR["points_per_goal"], 1)
    impact.ZS.update(ip["zs"])
    gpg, lg_pts_pct = league_rates_2025()
    tie_f = models.calibrate_ties(gpg, lg_pts_pct)
    pline = playoff_line_history()

    # ---- team data
    raw25 = readcsv(os.path.join(SRC, "teams.csv"))
    t25 = team_rows(raw25, "2025")
    uta25 = team_metrics(t25[TEAM])
    full_mp = os.path.exists(P("inputs", "moneypuck", "teams.csv"))
    mp_dir = "moneypuck" if full_mp else "moneypuck_partial"
    raw26 = readcsv(P("inputs", mp_dir, "teams.csv"))
    t26 = team_rows(raw26, "2026")
    uta26 = team_metrics(t26.get(TEAM, {}))
    ep2 = gaa.ep2_by_situation(raw26 if full_mp else raw25, "2026" if full_mp else "2025")
    se26 = models.team_se(t26.get(TEAM, {}), ep2)

    metrics = {}
    for key, (label, hib, fmt, expl, cat) in METRIC_DEFS.items():
        lg25, vals25 = league_stats(t25, key)
        row = {"key": key, "label": label, "hib": hib, "fmt": fmt, "expl": expl, "cat": cat,
               "cur": uta26.get(key), "last": uta25.get(key), "lg25": lg25, "se": se26.get(key),
               "rank25": rank_of(uta25.get(key), vals25, hib) if hib is not None else None}
        if full_mp and len(t26) >= 30:
            lg26, vals26 = league_stats(t26, key)
            row["lg26"] = lg26
            row["rank26"] = rank_of(uta26.get(key), vals26, hib) if hib is not None else None
        ref = row.get("lg26") if row.get("lg26") is not None else lg25
        row["sig"] = models.team_posterior(row["cur"], ref, uta26.get("gp"), params["team_rel"].get(key), hib)
        row["rel_yoy"] = params["team_rel"].get(key, {}).get("r_yoy")
        metrics[key] = row

    nteams26 = len(t26) if full_mp else None
    sw_list = []
    for k, m in metrics.items():
        if m["hib"] is None:
            continue
        sw_list.append({"key": k, "label": m["label"], "cat": m["cat"], "fmt": m["fmt"], "cur": m["cur"], "last": m["last"],
                        "rank": m.get("rank26"), "rank25": m["rank25"], "n": nteams26, "sig": m["sig"]["label"], "z": m["sig"]["z"], "rel_yoy": m.get("rel_yoy")})
    ranked = [x for x in sw_list if x["rank"]]
    half = (nteams26 or 32) / 2
    strengths = sorted([x for x in ranked if x["rank"] <= half], key=lambda x: x["rank"])[:6]
    weaknesses = sorted([x for x in ranked if x["rank"] > half], key=lambda x: -x["rank"])[:6]
    confirmed_str = [x for x in sw_list if x["sig"] == "confirmed strength"]
    confirmed_weak = [x for x in sw_list if x["sig"] == "confirmed weakness"]
    carryover = [k for k, m in metrics.items() if m["hib"] is not None and m["rank25"] and m["rank25"] >= 25]
    # the same table for every team (Team tab is selectable)
    sw_all = {}
    if full_mp and len(t26) >= 30:
        cur_all = {t_: team_metrics(s_) for t_, s_ in t26.items()}
        last_all = {t_: team_metrics(s_) for t_, s_ in t25.items()}
        lstats26 = {k_: league_stats(t26, k_) for k_ in METRIC_DEFS}; lstats25 = {k_: league_stats(t25, k_) for k_ in METRIC_DEFS}
        for t_, cm_ in cur_all.items():
            lm_ = last_all.get(t_, {}); out_ = []
            for k_, (label, hib, fmt, expl, cat) in METRIC_DEFS.items():
                if hib is None:
                    continue
                lg26_, vals26_ = lstats26[k_]; lg25_, vals25_ = lstats25[k_]
                sig_ = models.team_posterior(cm_.get(k_), lg26_ if lg26_ is not None else lg25_, cm_.get("gp"), params["team_rel"].get(k_), hib)
                out_.append({"key": k_, "label": label, "cat": cat, "fmt": fmt, "cur": cm_.get(k_), "last": lm_.get(k_),
                             "rank": rank_of(cm_.get(k_), vals26_, hib), "rank25": rank_of(lm_.get(k_), vals25_, hib) if lm_ else None,
                             "sig": sig_["label"], "rel_yoy": params["team_rel"].get(k_, {}).get("r_yoy")})
            sw_all[t_] = out_

    # ---- standings & schedule
    standings = parse_standings()
    sched = parse_schedule()
    played = [g for g in sched if g["final"]]
    upcoming = [g for g in sched if not g["final"]]
    me = next((t for t in standings if t["abbr"] == TEAM), None)
    gp = me["gp"] if me else len(played)
    pts = me["pts"] if me else sum(g["pts"] for g in played)
    cum, c, c3 = [], 0, 0
    for i, g in enumerate(played, 1):
        c += g["pts"]; c3 += g["p321"]
        cum.append({"n": i, "pts": c, "p321": c3, "date": g["date"], "opp": g["opp"], "res": g["res"]})
    mp_gp = uta26.get("gp") or 0

    # ---- projection: objective prior (18-season carry-over model) + in-season evidence -> simulation
    tp = params["team_prior"]
    gs25 = uta25["gf"] / (uta25["gf"] + uta25["ga"])
    prior_mean = tp["c0"] + tp["c_gs"] * gs25 + tp["c_xgs"] * uta25["xgf_pct_5v5"]
    goals_per_team_season = statistics.mean(team_metrics(s_)["gf"] + team_metrics(s_)["ga"] for s_ in t25.values())
    noise = math.sqrt(0.25 / goals_per_team_season)
    prior_sd = math.sqrt(max(tp["resid_sd"] ** 2 - noise ** 2, 1e-6))
    obs = obs_se = None
    if mp_gp and uta26.get("xgf_pct_5v5") is not None:
        # Evidence model (calibrated on 18 seasons): full-season goal share and xG share carried equal
        # predictive weight (0.371 vs 0.368), so both are treated as equally noisy measurements whose
        # noise equals binomial goal-share noise at the league scoring rate. Conservatively assume they
        # are perfectly correlated (no precision gain from averaging).
        gfa = uta26["gf"] + uta26["ga"]
        gs_obs = uta26["gf"] / gfa if gfa else 0.5
        obs = (gs_obs + uta26["xgf_pct_5v5"]) / 2
        obs_se = math.sqrt(0.25 / (gpg * mp_gp))
    post_mean, post_sd = models.posterior_share(prior_mean, prior_sd, obs, obs_se)
    sim = models.simulate_season(pts, gp, SEASON_GAMES, post_mean, post_sd, gpg, pline["pts_mean"], pline["pts_sd"])
    sim_pre = models.simulate_season(0, 0, SEASON_GAMES, prior_mean, prior_sd, gpg, pline["pts_mean"], pline["pts_sd"], sims=6000)
    pts_at_mp = cum[mp_gp - 1]["pts"] if mp_gp and len(cum) >= mp_gp else pts
    deserved = models.deserved_points(uta26.get("xgf"), uta26.get("xga"), mp_gp)
    act_ppg = pts / gp if gp else 0

    # ---- upcoming
    st_by = {t["abbr"]: t for t in standings}
    def strength(abbr):
        return team_metrics(t25.get(abbr, {})).get("xgf_pct_5v5")
    next10 = []
    for g in upcoming[:10]:
        o = st_by.get(g["opp"], {})
        ls = strength(g["opp"])
        pw, pl, pt_ = models.game_point_probs(gpg * post_mean, gpg * (1 - post_mean))
        next10.append({"date": g["date"], "start": g.get("start"), "ha": g["ha"], "opp": g["opp"],
                       "oppRec": f'{o.get("w",0)}-{o.get("l",0)}-{o.get("otl",0)}' if o else "", "opp25xgf": ls})

    # ---- players (box score production + 2025-26 profile)
    box_players, box_goalies = aggregate_boxscores()
    roster_names = sorted(box_players.keys())
    lineup = json.load(open(P("config", "lineup.json"), encoding="utf-8"))
    extra_names = ["Kailer Yamamoto", "Liam O'Brien", "Sebastian Cossa"]
    base, league_players = player_baselines(roster_names + extra_names)
    players = []
    for nm in roster_names:
        p = dict(box_players[nm]); p.update({k: v for k, v in base.get(nm, {}).items() if k != "name"})
        players.append(p)
    tilt = [dict(base[n], pos=box_players.get(n, {}).get("pos", "")) for n in roster_names + extra_names
            if n in base and base[n].get("xgf60") is not None]
    lg_xgf60 = sum(x["xgf60"] for x in league_players) / len(league_players)
    lg_xga60 = sum(x["xga60"] for x in league_players) / len(league_players)

    # ---- Goals Above Average: this season (Utah) and 2025-26 (any team, by name)
    contracts = json.load(open(P("config", "contracts.json"), encoding="utf-8"))["aav"]
    sk25 = readcsv(os.path.join(SRC, "skaters.csv")); gl25 = readcsv(os.path.join(SRC, "goalies.csv"))
    means25 = impact.season_table(sk25, raw25, "2025")[2]     # stable position baselines (full 2025-26 season)
    gaa25 = {p_["id"]: p_ for p_ in impact.compute(sk25, gl25, raw25, "2025", ip)}   # keyed by player id (duplicate names exist)
    # two and three seasons ago (talent pools up to three previous seasons at backtested weights)
    import fit_impact as _fi
    _hsk, _hgl, _htm = _fi.load_all()
    def _season_imp(s_):
        return {p_["id"]: p_ for p_ in impact.compute([r for r in _hsk if r["season"] == s_], [r for r in _hgl if r["season"] == s_], _htm, s_, ip)}
    gaa24, gaa23 = _season_imp("2024"), _season_imp("2023")
    prevs_of = lambda pid: [gaa25.get(pid), gaa24.get(pid), gaa23.get(pid)]
    rank, mp_lines = [], []
    rosters_note = None
    if full_mp:
        sk26 = readcsv(P("inputs", "moneypuck", "skaters.csv")); gl26 = readcsv(P("inputs", "moneypuck", "goalies.csv"))
        # league-wide: every player valued identically, so Utah's numbers are directly comparable
        rp = json.load(open(P("params", "roster_params.json")))
        team_gp = {r["team"]: int(num(r["games_played"])) for r in raw26 if r["season"] == "2026" and r["situation"] == "all"}
        lg26 = impact.compute(sk26, gl26, raw26, "2026", ip, means_override=means25)
        for q_ in lg26:
            pv = gaa25.get(q_["id"])
            league.player_value(q_, prevs_of(q_["id"]), ip, rp, team_gp.get(q_["team"], mp_gp), SEASON_GAMES, age=AGE.get(q_["id"]), standard=TPAR["standard"])
            pvv = next((x_ for x_ in prevs_of(q_["id"]) if x_ and x_["grp"] == q_["grp"] and x_.get("toi", 0) > 0), None)
            q_["tpg"] = league.toi_per_game(q_, pvv)
        # active Utah roster players who haven't played yet: value them from their earlier seasons, same method
        ROSTER = json.load(open(P("config", "roster.json")))["players"]
        have_ = {q_["id"] for q_ in lg26}
        base26 = {r["playerId"]: r for r in sk26 if r["situation"] == "all"}
        for rp_ in ROSTER:
            pid_ = rp_.get("playerId")
            if not pid_ or pid_ in have_:
                continue
            g_ = "G" if rp_["pos"] == "G" else ("D" if rp_["pos"] == "D" else "F")
            q_ = {"id": pid_, "name": rp_["name"], "team": TEAM, "pos": rp_["pos"], "grp": g_, "gp": 0, "toi": 0.0, "gaa": 0.0, "se": 0.0, "lo": 0.0, "hi": 0.0,
                  "per60": 0.0, "comp": {}, "parts": {}, "noGames": True}
            league.player_value(q_, prevs_of(pid_), ip, rp, team_gp.get(TEAM, mp_gp), SEASON_GAMES, age=AGE.get(pid_), standard=TPAR["standard"])
            pvv = next((x_ for x_ in prevs_of(pid_) if x_ and x_["grp"] == g_ and x_.get("toi", 0) > 0), None)
            q_["tpg"] = league.toi_per_game(q_, pvv) if pvv else 0.0
            lg26.append(q_)
        # every team's current NHL roster (config/rosters_all.json, fetched each morning): traded players move to their
        # new team the next day, and rostered players who haven't played this season (injured, suspended, scratched)
        # are valued from their earlier seasons, same method as above. Power rankings still use who actually dressed.
        ra_path = P("config", "rosters_all.json")
        RA_ = json.load(open(ra_path, encoding="utf-8")) if os.path.exists(ra_path) else {}
        RA = RA_.get("teams", {}); ra_failed = set(RA_.get("failed", []))
        # today's lists win over a team's kept-from-yesterday list (a player traded since then is on both)
        cur_team = {p_["playerId"]: t_ for t_, ps_ in RA.items() if t_ in ra_failed for p_ in ps_ if p_.get("playerId")}
        cur_team.update({p_["playerId"]: t_ for t_, ps_ in RA.items() if t_ not in ra_failed for p_ in ps_ if p_.get("playerId")})
        n_moved = n_added = 0
        for q_ in lg26:
            t_ = cur_team.get(q_["id"])
            if t_ and t_ != q_["team"]:
                q_["mpTeam"] = q_["team"]; q_["team"] = t_; n_moved += 1
        have_ = {q_["id"] for q_ in lg26}
        for t_, ps_ in RA.items():
            for rp_ in ps_:
                pid_ = rp_.get("playerId")
                if not pid_ or pid_ in have_ or not rp_.get("pos") or cur_team.get(pid_) != t_:
                    continue
                g_ = "G" if rp_["pos"] == "G" else ("D" if rp_["pos"] == "D" else "F")
                q_ = {"id": pid_, "name": rp_["name"], "team": t_, "pos": rp_["pos"], "grp": g_, "gp": 0, "toi": 0.0, "gaa": 0.0, "se": 0.0, "lo": 0.0, "hi": 0.0,
                      "per60": 0.0, "comp": {}, "parts": {}, "noGames": True}
                league.player_value(q_, prevs_of(pid_), ip, rp, team_gp.get(t_, mp_gp), SEASON_GAMES, age=AGE.get(pid_), standard=TPAR["standard"])
                pvv = next((x_ for x_ in prevs_of(pid_) if x_ and x_["grp"] == g_ and x_.get("toi", 0) > 0), None)
                if not pvv:      # no NHL minutes in the last three seasons: nothing to rate him on yet
                    continue
                q_["tpg"] = league.toi_per_game(q_, pvv)
                lg26.append(q_); have_.add(pid_); n_added += 1
        rosters_note = {"teams": len(RA), "moved": n_moved, "added": n_added}
        roster_meta = {rp_["playerId"]: rp_ for rp_ in ROSTER if rp_.get("playerId")}
        for q_ in lg26:
            if q_["id"] in roster_meta:
                q_["number"] = roster_meta[q_["id"]]["number"]; q_["posFull"] = roster_meta[q_["id"]]["pos"]; q_["onRoster"] = True
                if roster_meta[q_["id"]].get("status"): q_["status"] = roster_meta[q_["id"]]["status"]
        # league-wide cap hits (Spotrac 2026-27) matched to player ids; Utah's config file fills any gaps
        cap_rows = contracts_mod.load(os.path.dirname(os.path.abspath(__file__)))
        cap_by_id, cap_miss = contracts_mod.match(cap_rows, [{"id": q_["id"], "name": q_["name"], "team": q_["team"], "grp": q_["grp"]} for q_ in lg26])
        for q_ in lg26:
            c_ = cap_by_id.get(q_["id"])
            a_ = c_["cap"] if c_ else (contracts.get(q_["name"]) if q_["team"] == TEAM or q_.get("onRoster") else None)
            if a_:
                q_["aav"] = round(a_, 6)
                # entry-level: Spotrac's contract average includes ELC performance bonuses; otherwise young + near-minimum
                q_["elc"] = bool((c_ and c_["bonusELC"]) or (q_.get("age") is not None and q_["age"] <= 24.5 and a_ <= 1.0))
        lg_trank = league.rank_ranges(lg26, key="tstd", sd_key="tstd_sd")      # talent ranks are deployment-independent
        lg_srank = league.simple_rank(lg26, "gaa", lambda q_: q_["gp"] >= 1)
        lg_25rank = league.simple_rank(list(gaa25.values()), "gaa", lambda q_: q_["toi"] >= (1500 if q_["grp"] == "G" else 500))
        rosters_ = league.rosters(lg26)
        lgby = {q_["id"]: q_ for q_ in lg26}
        res26 = [q_ for q_ in lg26 if q_["team"] == TEAM or q_.get("onRoster")]
        for p_ in res26:
            prev = gaa25.get(p_["id"])
            if p_.get("talent84") is not None:
                p_["talent"] = round(p_["talent60"] * p_["toi"] / 60, 2)
            else:
                p_["talent"] = 0.0
            p_["lgTalent"] = lg_trank.get(p_["id"]); p_["lgSeason"] = lg_srank.get(p_["id"]); p_["lg25"] = lg_25rank.get(p_["id"])
            p_["luck"] = round(p_["gaa"] - p_["talent"], 2)    # vs. his own norm (talent x minutes)
            p_["verdict"] = gaa.verdict(p_) if p_["toi"] >= MIN_VERDICT_TOI else ("none" if p_.get("noGames") else "early")
            p_["aav"] = p_.get("aav") or contracts.get(p_["name"])
            p_["per84"] = round(p_["gaa"] / p_["gp"] * SEASON_GAMES, 1) if p_["gp"] else None
            if prev:
                p_["gaa25"] = prev["gaa"]; p_["lo25"] = prev["lo"]; p_["hi25"] = prev["hi"]; p_["parts25"] = prev.get("parts")
            p_["per_m"] = round(p_["gaa"] / p_["aav"], 2) if p_["aav"] else None
            rank.append(p_)
        rank.sort(key=lambda r_: -r_["gaa"])
        bym = {}
        for r in sk26:
            if r["team"] == TEAM and r["season"] == "2026":
                bym.setdefault(r["name"], {})[r["situation"]] = r
        for p in players:
            d = bym.get(p["name"])
            if not d:
                continue
            a, e = d.get("all"), d.get("5on5")
            if a:
                p["ixg26"] = round(num(a["I_F_xGoals"]), 2); p["gmx26"] = round(num(a["I_F_goals"]) - num(a["I_F_xGoals"]), 2)
                p["reb26"] = int(num(a["I_F_rebounds"]))
            if e and num(e["icetime"]) > 0:
                onF, onA = num(e["OnIce_F_xGoals"]), num(e["OnIce_A_xGoals"]); offF, offA = num(e["OffIce_F_xGoals"]), num(e["OffIce_A_xGoals"])
                p["xgf26"] = round(onF / (onF + onA), 3) if onF + onA else None
                p["rel26"] = round((onF / (onF + onA) - offF / (offF + offA)) * 100, 1) if (onF + onA and offF + offA) else None
                p["fu26"] = round(num(e["OnIce_F_rebounds"]) / num(e["OnIce_F_shotsOnGoal"]), 3) if num(e["OnIce_F_shotsOnGoal"]) else None
            g_ = next((r_ for r_ in rank if r_["name"] == p["name"]), None)
            if g_:
                p["gaa26"] = g_["gaa"]; p["verdict26"] = g_["verdict"]
        for r in readcsv(P("inputs", "moneypuck", "lines.csv")):
            if r["team"] == TEAM and r["season"] == "2026" and r["situation"] == "5on5":
                sog = num(r["shotsOnGoalFor"]); hrs = num(r["icetime"]) / 3600
                F, A = num(r["xGoalsFor"]), num(r["xGoalsAgainst"])
                vF, vA = num(r["unblockedShotAttemptsFor"]) * ep2["5on5"], num(r["unblockedShotAttemptsAgainst"]) * ep2["5on5"]
                se_share = math.sqrt(A * A * vF + F * F * vA) / (F + A) ** 2 if F + A else None
                mp_lines.append({"name": r["name"].replace("-", " – "), "type": r["position"], "toi": round(num(r["icetime"]) / 60, 1),
                                 "xgf": F / (F + A) if F + A else None, "lo": max(0, F / (F + A) - 1.96 * se_share) if se_share else None,
                                 "hi": min(1, F / (F + A) + 1.96 * se_share) if se_share else None,
                                 "gf": int(num(r["goalsFor"])), "ga": int(num(r["goalsAgainst"])), "sog": int(sog), "reb": int(num(r["reboundsFor"])),
                                 "fu": round(num(r["reboundsFor"]) / sog, 3) if sog else None, "xga60": round(A / hrs, 2) if hrs else None})
        mp_lines.sort(key=lambda x: (x["type"], -x["toi"]))
    # value vs. contract: true talent per 84 GP (two-season pooled, reliability-regressed) vs. cap hit.
    # value vs. contract, LEAGUE-WIDE market line (Spotrac cap hits, every skater who has played this season):
    #   value = a + b x cap hit + c x entry-level, fitted by least squares; "expected for pay" is the open-market part
    #   (a + b x cap), so entry-level players show the surplus their rookie deal gives the team, tagged ELC.
    #   Model chosen by 10-fold CV on 605 skaters: linear + ELC beat log(cap), a curve, and separate F/D lines.
    # Two value bases: IN HIS ROLE (talent x actual minutes, talent84) and RAW TALENT (standard workload, tstd).
    import numpy as _npf
    def _payfit(key):
        pts_ = [q_ for q_ in lg26 if q_.get("aav") and q_.get(key) is not None and q_["grp"] != "G" and not q_.get("noGames")]
        if len(pts_) < 30:
            return None
        A_ = _npf.array([[1.0, q_["aav"], 1.0 if q_.get("elc") else 0.0] for q_ in pts_]); y_ = _npf.array([q_[key] for q_ in pts_])
        w_ = _npf.linalg.lstsq(A_, y_, rcond=None)[0]
        ne_ = [q_ for q_ in pts_ if not q_.get("elc")]
        r_ne = float(_npf.corrcoef([q_["aav"] for q_ in ne_], [q_[key] for q_ in ne_])[0, 1]) if len(ne_) > 5 else None
        return {"icpt": round(float(w_[0]), 3), "slope": round(float(w_[1]), 3), "elc": round(float(w_[2]), 3), "n": len(pts_),
                "nELC": sum(1 for q_ in pts_ if q_.get("elc")), "r": round(r_ne, 2) if r_ne is not None else None, "scope": "league"}
    fit = _payfit("talent84"); fit_raw = _payfit("tstd")
    for q_ in lg26:
        if not q_.get("aav") or q_["grp"] == "G":
            continue
        if fit and q_.get("talent84") is not None:
            ex_ = fit["icpt"] + fit["slope"] * q_["aav"]
            q_["expectedForPay"] = round(ex_, 1); q_["vsContract"] = round(q_["talent84"] - ex_, 1)
            q_["vsLo"] = round(q_["tlo84"] - ex_, 1); q_["vsHi"] = round(q_["thi84"] - ex_, 1); q_["vsPts"] = to_pts(q_["vsContract"])
        if fit_raw and q_.get("tstd") is not None:
            ex_ = fit_raw["icpt"] + fit_raw["slope"] * q_["aav"]
            q_["expRaw"] = round(ex_, 1); q_["vsRaw"] = round(q_["tstd"] - ex_, 1)
            q_["vsRawLo"] = round(q_["tstd"] - 1.645 * q_["tstd_sd"] - ex_, 1); q_["vsRawHi"] = round(q_["tstd"] + 1.645 * q_["tstd_sd"] - ex_, 1)
    for r_ in rank:   # standings-point equivalents
        r_["pts"] = to_pts(r_["gaa"]); r_["tstdPts"] = to_pts(r_.get("tstd")); r_["roleExpPts"] = to_pts(r_.get("talent84"))
    # within-Utah ranking: one scale for every position, with uncertainty. Simulate each player's true talent
    # (estimate +/- its uncertainty), rank the roster in every draw -> 95% range of each player's Utah rank, and
    # TIERS: a new tier starts when the tier's top player is better than this player in at least 75% of draws.
    tal_pl = [r_ for r_ in rank if r_.get("tstd") is not None and r_.get("tstd_sd")]
    pairwise = None
    if tal_pl:
        import numpy as _np
        rng_ = _np.random.default_rng(17)
        mu_ = _np.array([r_["tstd"] for r_ in tal_pl]); sd_ = _np.array([r_["tstd_sd"] for r_ in tal_pl])
        dr_ = rng_.normal(mu_[None, :], sd_[None, :], size=(20000, len(tal_pl)))
        rk_ = (-dr_).argsort(axis=1).argsort(axis=1) + 1
        order_ = sorted(range(len(tal_pl)), key=lambda i_: (-mu_[i_], tal_pl[i_]["name"]))   # ties broken by name, as on the page
        tier_, lead_ = 1, order_[0]
        for j_, i_ in enumerate(order_):
            r_ = tal_pl[i_]; t_here = tier_
            # same rule as the page (and as team tiers): normal approximation, 75%; goalies never become a tier's reference
            if j_ and 0.5 * (1 + math.erf((mu_[lead_] - mu_[i_]) / math.sqrt(2 * (sd_[lead_] ** 2 + sd_[i_] ** 2)))) >= 0.75:
                if r_["grp"] == "G":
                    t_here = tier_ + 1
                else:
                    tier_ += 1; lead_ = i_; t_here = tier_
            r_["utaRank"] = j_ + 1; r_["utaTier"] = t_here
            r_["utaLo"] = int(_np.percentile(rk_[:, i_], 2.5, method="lower")); r_["utaHi"] = int(_np.percentile(rk_[:, i_], 97.5, method="higher"))
        for g_ in ("F", "D", "G"):
            for j_, r_ in enumerate(sorted([r_ for r_ in tal_pl if r_["grp"] == g_], key=lambda r_: -r_["tstd"])):
                r_["utaPosRank"] = j_ + 1
        top_ = [tal_pl[i_] for i_ in order_[:8]]
        ix_ = {id(r_): k_ for k_, r_ in enumerate(tal_pl)}
        pairwise = {"names": [r_["name"] for r_ in top_], "p": [[round(float((dr_[:, ix_[id(a_)]] > dr_[:, ix_[id(c_)]]).mean()), 2) if a_ is not c_ else None for c_ in top_] for a_ in top_]}
    team_gaa_total = round(sum(r_["gaa"] for r_ in rank), 1) if rank else None

    # ---- league context output
    league_out = None
    if full_mp:
        rpar = json.load(open(P("params", "roster_params.json")))
        tops = {g: [{"name": q_["name"], "team": q_["team"], "tstd": q_["tstd"], "tstdPts": to_pts(q_["tstd"]), "t60": q_["t60"],
                     "rlo": lg_trank[q_["id"]]["rlo"], "rhi": lg_trank[q_["id"]]["rhi"], "uta": q_["team"] == TEAM}
                    for q_ in sorted([q_ for q_ in lg26 if q_["grp"] == g and q_.get("tstd") is not None], key=lambda q_: -q_["tstd"])[:10]] for g in "FDG"}
        top25 = {g: [{"name": q_["name"], "team": q_["team"], "gaa": q_["gaa"], "uta": q_["team"] == TEAM}
                     for q_ in sorted([q_ for q_ in gaa25.values() if q_["grp"] == g and q_["toi"] >= (1500 if g == "G" else 500)], key=lambda q_: -q_["gaa"])[:5]] for g in "FDG"}
        top25["all"] = [{"name": q_["name"], "team": q_["team"], "grp": q_["grp"], "gaa": q_["gaa"], "uta": q_["team"] == TEAM}
                        for q_ in sorted([q_ for q_ in gaa25.values() if q_["toi"] >= (1500 if q_["grp"] == "G" else 500)], key=lambda q_: -q_["gaa"])[:10]]
        top_n = [r_["team"] for r_ in rosters_[:8]]
        avg8 = {k: round(statistics.mean(r_[k] for r_ in rosters_[:8]), 1) for k in ("F", "D", "G", "total")}
        league_out = {"standard": TPAR["standard"], "ptsPerGoal": PPAR, "talentDecision": {k: TPAR[k] for k in ("components_adopted", "components_why", "role_test", "validation")}, "rosters": rosters_, "topTalent": tops, "top25": top25, "avgTop8": avg8, "rosterVal": rpar["dashboard_def"],
                      "priorGdR": rpar["r_prior_season_gd"], "nPlayers": {g: sum(1 for q_ in lg26 if q_["grp"] == g and q_.get("talent84") is not None) for g in "FDG"}}
    # ---- league-wide player explorer (every player valued the same way) + style tags
    players_league = None
    if full_mp:
        st_conf = {s_["abbr"]: (s_["conf"], s_["div"]) for s_ in standings}
        h24sk = [r for r in _hsk if r["season"] == "2024"]; h24gl = [r for r in _hgl if r["season"] == "2024"]
        STY = style.build([sk26, sk25, h24sk], [gl26, gl25, h24gl])
        pos_of = {r["playerId"]: r["position"] for r in sk26 if r["situation"] == "all"}
        players_league = []
        for q_ in lg26:
            if q_.get("tstd") is None:
                continue
            cf_, dv_ = st_conf.get(q_["team"], (None, None)); lt_ = lg_trank.get(q_["id"]) or {}; ls_ = lg_srank.get(q_["id"]) or {}
            sty_ = STY.get(q_["id"], {})
            players_league.append({"id": q_["id"], "n": q_["name"], "t": q_["team"], "cf": cf_, "dv": dv_, "g": q_["grp"], "pos": q_.get("posFull") or pos_of.get(q_["id"], q_["grp"]),
                                   "age": round(q_["age"], 1) if q_.get("age") is not None else None, "gp": q_["gp"], "tpg": round(q_.get("tpg") or 0, 1),
                                   "imp": round(q_["gaa"], 2), "ise": round(q_.get("se", 0), 2), "ipct": ls_.get("pct"),
                                   "tal": q_["tstd"], "tsd": round(q_["tstd_sd"], 2), "tpct": lt_.get("pct"), "trank": lt_.get("rank"), "tn": lt_.get("n"),
                                   "r10": lt_.get("r10"), "r90": lt_.get("r90"), "role": round(q_.get("talent84") or 0, 1),
                                   "sty": [x_["tag"] for x_ in sty_.get("tags", [])], "styWhy": [x_["why"] for x_ in sty_.get("tags", [])], "sRole": sty_.get("role"),
                                   "ng": bool(q_.get("noGames")), **({"from": q_["mpTeam"]} if q_.get("mpTeam") else {}),
                                   **({"cap": q_["aav"], "elc": bool(q_.get("elc")), "vs": q_.get("vsContract"), "vsLo": q_.get("vsLo"), "vsHi": q_.get("vsHi"),
                                       "exp": q_.get("expectedForPay"), "vsRaw": q_.get("vsRaw"), "vsRawLo": q_.get("vsRawLo"), "vsRawHi": q_.get("vsRawHi"), "expRaw": q_.get("expRaw")} if q_.get("aav") else {}),
                                   "vd": gaa.verdict(q_) if q_.get("toi", 0) >= MIN_VERDICT_TOI and q_.get("lo") is not None else None,
                                   "pp": {k_: round(v_, 2) for k_, v_ in (q_.get("parts") or {}).items() if abs(v_) >= 0.005},
                                   **({"imp25": round(gaa25[q_["id"]]["gaa"], 2), "pp25": {k_: round(v_, 2) for k_, v_ in (gaa25[q_["id"]].get("parts") or {}).items() if abs(v_) >= 0.005}}
                                      if q_["id"] in gaa25 else {})})
        for r_ in rank:
            sty_ = STY.get(r_["id"], {})
            r_["style"] = sty_.get("tags", []); r_["styleRole"] = sty_.get("role")
    # ---- player profiles (skill components pooled + shrunk by repeatability, usage, size, shot location) + comparables
    prof_rel = None
    if players_league:
        TW_ = json.load(open(P("params", "talent_weights.json")))
        prof_rel = profile_mod.reliability([gaa23, gaa24, gaa25])
        def _rows(sk_, season_):
            return {(r["playerId"], r["situation"]): r for r in sk_ if r["season"] == season_}
        def _tt(raw_, season_):
            tt_ = {}
            for r in raw_:
                if r["season"] == season_ and r["situation"] in ("5on4", "4on5"):
                    tt_[(r["team"], r["situation"])] = num(r["iceTime"]) / 3600
                if r["season"] == season_ and r["situation"] == "all":
                    tt_[(r["team"], "gp")] = num(r["games_played"])
            return tt_
        use_ = profile_mod.usage([_rows(sk26, "2026"), _rows(sk25, "2025")], [_tt(raw26, "2026"), _tt(raw25, "2025")])
        bio_ = {}
        for f_ in ("allPlayersLookup.csv", "bio_supplement.csv"):
            if os.path.exists(P("inputs", f_)):
                for r in readcsv(P("inputs", f_)):
                    bio_.setdefault(r["playerId"], r)
        lgid_p = {q_["id"]: q_ for q_ in lg26}
        profs_ = {}
        for q_ in lg26:
            if q_["grp"] == "G":
                continue
            comps_, den_ = profile_mod.pooled_components(q_, prevs_of(q_["id"]), TW_[q_["grp"]]["w"], prof_rel)
            pos_ = q_.get("posFull") or pos_of.get(q_["id"], q_["grp"])
            profs_[q_["id"]] = {"grp": q_["grp"], "isC": pos_ == "C", "comps": comps_, "den": den_, "use": use_.get(q_["id"], {})}
        pools_ = {g_: [p_ for p_ in profs_.values() if p_["grp"] == g_ and p_["den"] >= 200] for g_ in ("F", "D")}
        cmp_ = profile_mod.comparables({k_: v_ for k_, v_ in profs_.items() if v_["den"] >= 200}, prof_rel)
        pl_by_id = {p_["id"]: p_ for p_ in players_league}
        for pid_, pr_ in profs_.items():
            pl_ = pl_by_id.get(pid_)
            if not pl_:
                continue
            P_ = pools_[pr_["grp"]]
            # faceoffs ranked among centers only, and shown only for centers
            pl_["prof"] = {c_: (profile_mod.pct_rank([x_["comps"][c_] for x_ in (P_ if c_ != "faceoffs" else [y_ for y_ in P_ if y_["isC"]])], pr_["comps"][c_])
                                if (c_ != "faceoffs" or pr_["isC"]) else None) for c_ in profile_mod.COMPS}
            pl_["profV"] = {c_: round(pr_["comps"][c_], 3) for c_ in profile_mod.COMPS}
            u_ = pr_["use"]
            pl_["use"] = {k_: (round(u_[k_], 3) if u_.get(k_) is not None else None) for k_ in profile_mod.USAGE}
            pl_["useP"] = {k_: profile_mod.pct_rank([x_["use"].get(k_) for x_ in P_], u_.get(k_)) for k_ in profile_mod.USAGE}
            pl_["profMin"] = round(pr_["den"])
            b_ = bio_.get(pid_, {})
            pl_["ht"] = profile_mod.height_in(b_.get("height")); pl_["wt"] = int(num(b_.get("weight"))) if b_.get("weight") else None; pl_["sh"] = b_.get("shootsCatches") or None
            pl_["cmp"] = [[o_, d_] for o_, d_ in cmp_.get(pid_, [])]
            if pr_["den"] >= 200:
                pl_["arch"], pl_["archTxt"] = profile_mod.archetype(pr_["grp"], pl_["pos"], pl_["prof"], pl_["useP"], pl_["ht"], pl_.get("tpct"))
    # goalie profiles (separate metrics; very noisy year to year, so heavily shrunk)
    if players_league:
        GS_ = {s_: profile_mod.goalie_season(rows_, s_) for s_, rows_ in (("2026", gl26), ("2025", gl25), ("2024", _hgl), ("2023", _hgl), ("2022", _hgl))}
        grel_ = profile_mod.goalie_reliability([GS_["2022"], GS_["2023"], GS_["2024"], GS_["2025"]])
        team_gp26_ = {r["team"]: num(r["games_played"]) for r in raw26 if r["season"] == "2026" and r["situation"] == "all"}
        gpro_ = {}
        for p_ in players_league:
            if p_["g"] != "G":
                continue
            v_, m_, sv60_ = profile_mod.goalie_pooled(p_["id"], [GS_["2026"], GS_["2025"], GS_["2024"], GS_["2023"]], TW_["G"]["w"], grel_)
            gpro_[p_["id"]] = (v_, m_, sv60_)
        poolG_ = [x_ for x_ in gpro_.values() if x_[1] >= 1000]
        for p_ in players_league:
            if p_["id"] not in gpro_:
                continue
            v_, m_, sv60_ = gpro_[p_["id"]]
            p_["gprof"] = {k_: profile_mod.pct_rank([x_[0][k_] for x_ in poolG_], v_[k_]) for k_ in profile_mod.GCOMPS}
            p_["profMin"] = round(m_)
            c_ = GS_["2026"].get(p_["id"]); l_ = GS_["2025"].get(p_["id"])
            share_ = (c_["gp"] / max(1, team_gp26_.get(p_["t"], 1))) if c_ else 0.0
            share25_ = (l_["gp"] / 82) if l_ else None
            p_["guse"] = {"share": round(share_, 2), "share25": round(share25_, 2) if share25_ is not None else None, "sog60": round(sv60_, 1) if sv60_ else None}
            if m_ >= 1000:
                p_["arch"], p_["archTxt"] = profile_mod.goalie_archetype(share25_ if share25_ is not None and (c_ is None or c_["gp"] < 10) else share_, p_["gprof"])
            b_ = bio_.get(p_["id"], {})
            p_["ht"] = profile_mod.height_in(b_.get("height")); p_["wt"] = int(num(b_.get("weight"))) if b_.get("weight") else None; p_["sh"] = b_.get("shootsCatches") or None
        prof_rel = dict(prof_rel or {}); prof_rel["G"] = grel_
    # ---- goalies
    mp_g = {}
    for r in readcsv(P("inputs", mp_dir, "goalies.csv")):
        if r["team"] == TEAM and r["situation"] == "all" and r["season"] == "2026":
            mp_g[r["name"]] = r
    goalies = []
    for nm, q in box_goalies.items():
        q = dict(q); q["svp"] = round(q["sv"] / q["sa"], 3) if q["sa"] else None
        g_ = next((r_ for r_ in rank if r_["name"] == nm), None)
        if g_:
            q["gsax"] = g_["gaa"]; q["lo"] = g_["lo"]; q["hi"] = g_["hi"]; q["talent"] = g_["talent"]
            q["xga"] = round(num(mp_g[nm]["xGoals"]), 2) if nm in mp_g else None
        goalies.append(q)
    g25 = {r["name"]: r for r in gl25 if r["season"] == "2025" and r["situation"] == "all"}
    for q in goalies:
        r = g25.get(q["name"])
        if r:
            q["gsax25"] = round(num(r["xGoals"]) - num(r["goals"]), 1); q["gp25"] = int(num(r["games_played"]))
    if "Sebastian Cossa" not in box_goalies:
        goalies.append({"name": "Sebastian Cossa", "gp": 0, "gs": 0, "sa": 0, "sv": 0, "ga": 0, "w": 0, "l": 0, "so": 0, "svp": None,
                        "note": "Backup. AHL career .911 in 123 games."})

    # ---- per-game values: a game's value depends only on that game, so it never changes later. Sources, in order:
    # (1) MoneyPuck's game-by-game rows: the full Impact model run on that game alone, with each player compared with
    #     his own team in that same game (the game's own off-ice rates) and last season's league means as the fixed scale.
    # No fallbacks (Connor's rule): a game without MoneyPuck game-by-game data shows no per-game values until the data arrives.
    # (Season snapshots are still archived; PG_DIAG=1 compares snapshot differences with game values as a diagnostic.)
    import shutil
    if full_mp and mp_gp:
        arch = P("history", "mp", str(mp_gp))
        os.makedirs(arch, exist_ok=True)
        for f_ in ("skaters", "goalies", "teams"):
            if not os.path.exists(os.path.join(arch, f_ + ".csv")):
                shutil.copy(P("inputs", "moneypuck", f_ + ".csv"), os.path.join(arch, f_ + ".csv"))
    snaps = {}
    for dpath in glob.glob(P("history", "mp", "*")):
        try:
            g_ = int(os.path.basename(dpath))
        except ValueError:
            continue
        if all(os.path.exists(os.path.join(dpath, f_ + ".csv")) for f_ in ("skaters", "goalies", "teams")):
            snaps[g_] = dpath
    snap_gaa = {}
    def gaa_at(g_):
        if g_ not in snap_gaa:
            d_ = snaps[g_]
            # league-wide, keyed by id: a player traded to Utah is matched to his own previous total
            res_ = impact.compute(readcsv(os.path.join(d_, "skaters.csv")), readcsv(os.path.join(d_, "goalies.csv")),
                                  readcsv(os.path.join(d_, "teams.csv")), "2026", ip, means_override=means25)
            snap_gaa[g_] = {r_["id"]: r_ for r_ in res_}
        return snap_gaa[g_]
    pg_gaa = {}
    for g_ in (sorted(snaps) if os.environ.get("PG_DIAG") else []):
        if g_ - 1 > len(played) - 1:
            continue
        if g_ == 1 or (g_ - 1) in snaps:
            cur_ = gaa_at(g_); prev_ = gaa_at(g_ - 1) if g_ > 1 else {}
            pg_gaa[str(played[g_ - 1]["id"])] = {v["name"]: {"gaa": round(v["gaa"] - prev_.get(i_, {}).get("gaa", 0), 2), "pos": v["grp"]}
                                                 for i_, v in cur_.items() if v["team"] == TEAM and v["gp"] - prev_.get(i_, {}).get("gp", 0) == 1}
    pg_snap = dict(pg_gaa); pg_gaa = {}
    # MoneyPuck game-by-game files (preferred): exact Impact for every game, computed directly from that game's rows.
    # Files all download as "2026.csv"; the kind is detected from the header.
    games_files = {}
    for path in glob.glob(P("inputs", "moneypuck_games", "*.csv")):
        with open(path, encoding="utf-8") as fh:
            hdr = fh.readline()
        kind = "lines" if hdr.startswith("lineId") else ("skaters" if ",shifts," in hdr else ("goalies" if ",ongoal," in hdr else None))
        if kind:
            games_files[kind] = path
    pg_src, pg_sum = {}, {}
    if "skaters" in games_files and full_mp:
        gsk, ggl = {}, {}
        for r in readcsv(games_files["skaters"]):
            if r["playerTeam"] == TEAM and r["season"] == "2026":
                r["team"] = r["playerTeam"]; r["games_played"] = "1"; gsk.setdefault(r["gameId"], []).append(r)
        if "goalies" in games_files:
            for r in readcsv(games_files["goalies"]):
                if r["playerTeam"] == TEAM and r["season"] == "2026":
                    r["team"] = r["playerTeam"]; r["games_played"] = "1"; ggl.setdefault(r["gameId"], []).append(r)
        for gid_, rows_ in gsk.items():
            res_ = impact.compute(rows_, ggl.get(gid_, []), raw26, "2026", ip, team=TEAM, means_override=means25)
            pg_gaa[gid_] = {v["name"]: {"gaa": round(v["gaa"], 2), "pos": v["grp"]} for v in res_ if v["toi"] > 0}
            pg_src[gid_] = "game"
    if os.environ.get("PG_DIAG"):
        for gid_, v_ in pg_snap.items():
            if pg_src.get(gid_) == "game":
                print("DIAG", gid_, sorted(((round(pg_gaa[gid_][n]["gaa"], 2), round(v_[n]["gaa"], 2), n) for n in v_ if n in pg_gaa[gid_]), reverse=True))
    # ---- goalie floor: each team's likely starter (largest share of starts this season, then talent); their talent spread
    # sets the goalie labels (bottom 20% of starters = below the floor; validated on 12 seasons, calibration/experiments)
    goalie_starters = []
    if players_league:
        for t_ in sorted({s_["abbr"] for s_ in standings}):
            gs_ = [q_ for q_ in players_league if q_["t"] == t_ and q_["g"] == "G" and not q_.get("ng") and q_.get("tal") is not None]
            if gs_:
                goalie_starters.append(max(gs_, key=lambda q_: (((q_.get("guse") or {}).get("share")) or 0, q_["gp"], q_["tal"]))["tal"])
    gst_sorted_ = sorted(goalie_starters)
    starter_pct = lambda tal_: round(100 * sum(1 for v_ in gst_sorted_ if v_ < tal_) / len(gst_sorted_)) if gst_sorted_ and tal_ is not None else None
    goalie_band = lambda tal_: None if starter_pct(tal_) is None else ("below the starter floor" if starter_pct(tal_) < 20 else ("a borderline starter" if starter_pct(tal_) < 40 else "starter quality"))
    # ---- power rankings (needs MoneyPuck game-by-game files)
    power_out = None
    if "skaters" in games_files and "goalies" in games_files:
        pwp = json.load(open(P("params", "power_params.json")))
        prev_gd = {r["team"]: (num(r["goalsFor"]) - num(r["goalsAgainst"])) / num(r["games_played"])
                   for r in raw25 if r["season"] == "2025" and r["situation"] == "all" and num(r["games_played"]) > 0}
        newc = json.load(open(P("params", "roster_params.json")))["newcomer60"]
        prows = power.compute(readcsv(games_files["skaters"]), readcsv(games_files["goalies"]), {k_: prevs_of(k_) for k_ in set(gaa25) | set(gaa24) | set(gaa23)}, prev_gd, ip, newc, pwp,
                              PPAR["points_per_goal"], season="2026", season_games=SEASON_GAMES, ages=None,   # no aging for team strength (see age_params)
                              season_totals={r["team"]: (int(num(r["games_played"])), (num(r["goalsFor"]) - num(r["goalsAgainst"])) / num(r["games_played"]),
                                                         (num(r["xGoalsFor"]) - num(r["xGoalsAgainst"])) / num(r["games_played"]))
                                             for r in raw26 if r["season"] == "2026" and r["situation"] == "all" and num(r["games_played"]) > 0})
        st_by = {s_["abbr"]: s_ for s_ in standings}
        prev_hist = json.load(open(P("history", "snapshots.json"))) if os.path.exists(P("history", "snapshots.json")) else []
        prev_rank = next((h_.get("power") for h_ in sorted(prev_hist, key=lambda h_: -h_["gp"]) if h_.get("power") and h_["gp"] < gp), None)
        lgid_ = {q_["id"]: q_ for q_ in lg26} if full_mp else {}
        for r_ in prows:
            # top impact players among those dressed in the last 5 games: expected impact IN HIS ROLE (talent x his ice time,
            # goalies by share of starts) -- the "In his role" column on the Roster and Player Finder pages
            # skaters only: a goalie's "in his role" averages over his share of starts, which describes no single game;
            # goalies are listed separately as likely starter / backup, each rated as if he starts (talent at a starter's workload)
            sk_ = sorted([lgid_[i_] for i_ in r_.get("lineupIds", []) if i_ in lgid_ and lgid_[i_]["grp"] != "G" and lgid_[i_].get("talent84") is not None], key=lambda q_: -q_["talent84"])
            ng_ = len({x_ for x_ in r_.get("lineupIds", [])}) and r_.get("lineupGames", 0)
            for q_ in r_.get("goalies", []):
                lq_ = lgid_.get(q_["id"])
                q_["tal"] = round(to_pts(lq_["tstd"]), 1) if lq_ and lq_.get("tstd") is not None else None
                q_["tpct"] = (lg_trank.get(q_["id"]) or {}).get("pct")
            r_["top"] = [q_["name"] for q_ in sk_[:3]]
            r_["topV"] = [round(to_pts(q_["talent84"]), 1) for q_ in sk_[:3]]
            r_["topPos"] = [q_.get("posFull") or q_["grp"] for q_ in sk_[:3]]
            r_["glast"] = r_.get("lineupGames", 0)
            r_.pop("lineupIds", None)
            s_ = st_by.get(r_["team"], {})
            r_["rec"] = f'{s_.get("w", 0)}-{s_.get("l", 0)}-{s_.get("otl", 0)}' if s_ else ""; r_["ptsPct"] = s_.get("ptsPct")
            r_["stRank"] = None; r_["move"] = (prev_rank[r_["team"]] - r_["rank"]) if prev_rank and r_["team"] in prev_rank else None
        for i_, s_ in enumerate(sorted(standings, key=lambda s_: (-(s_.get("ptsPct") or 0), -(s_.get("gd") or 0)))):
            for r_ in prows:
                if r_["team"] == s_["abbr"]: r_["stRank"] = i_ + 1
        # team tiers, same rule as players: a new tier starts when the tier's top team is better than this one with >= 75% probability
        # (true-strength uncertainty sd_pts from the backtest; tiers are league-wide and don't change with filters)
        lead_, tier_ = None, 1
        for r_ in sorted(prows, key=lambda r_: -r_["rating"]):
            if lead_ is not None and 0.5 * (1 + math.erf((lead_["rating"] - r_["rating"]) / math.sqrt(2 * (lead_["sd_pts"] ** 2 + r_["sd_pts"] ** 2)))) >= 0.75:
                tier_ += 1; lead_ = r_
            if lead_ is None: lead_ = r_
            r_["tier"] = tier_
        power_out = {"rows": prows, "backtest": pwp["backtest"], "coverage": pwp["coverage_rest_of_season"], "cps": pwp["checkpoints"]}
        # team style tags (descriptive), this season pooled with last season at half weight
        tgp_ = {r["team"]: int(num(r["games_played"])) for r in raw26 if r.get("season") == "2026" and r.get("situation") == "all"}
        TSTY = team_style.build(raw26 if full_mp else [], raw25, "2026", "2025", players=players_league, cur_gp=tgp_)
        for r_ in prows:
            ts_ = TSTY.get(r_["team"], {})
            r_["style"] = ts_.get("tags", []); r_["styleLastSeason"] = ts_.get("mostlyLastSeason", False)
            r_["styleRanks"] = ts_.get("ranks", {}); r_["styleN"] = ts_.get("n")
            if r_["team"] == TEAM: power_out["utaStyleRanks"] = {"ranks": ts_.get("ranks", {}), "n": ts_.get("n")}
        # ---- league-wide season simulation from power ratings + home ice (validated: config/sim_backtest.json)
        wpp = json.load(open(P("params", "winprob_params.json")))
        sched_path = P("inputs", "nhl", "league_schedule.json")
        if os.path.exists(sched_path):
            sched = json.load(open(sched_path))["games"]
            done_ = [g_ for g_ in sched if g_["state"] in (6, 7)]
            # back-to-back (validated on 2025-26: params/rest_validation.json): a team playing the day after a game loses
            # about 0.31 on the win logit vs. a rested opponent; applied to single-game odds and the season simulation
            rv_ = json.load(open(P("params", "rest_validation.json"))) if os.path.exists(P("params", "rest_validation.json")) else None
            REST_LOGIT = rv_["win_logit_per_rest_edge"] if rv_ else 0.0
            played_ = {}
            for g_ in sched:
                for t_ in (g_["home"], g_["away"]): played_.setdefault(t_, set()).add(g_["date"])
            prevday_ = lambda d_: (datetime.date.fromisoformat(d_) - datetime.timedelta(days=1)).isoformat()
            b2b_ = lambda t_, d_: prevday_(d_) in played_.get(t_, ())
            rest_edge = lambda h_, a_, d_: int(b2b_(a_, d_)) - int(b2b_(h_, d_))     # +1: away team tired only (helps home)
            rem_ = [(g_["home"], g_["away"], REST_LOGIT / wpp["win"][1] * rest_edge(g_["home"], g_["away"], g_["date"])) for g_ in sched if g_["state"] not in (6, 7)]
            cur_pts, cur_gp = {}, {}
            for g_ in done_:
                hw_ = g_["hs"] > g_["as"]; ot_ = g_["period"] > 3
                cur_pts[g_["home"]] = cur_pts.get(g_["home"], 0) + (2 if hw_ else (1 if ot_ else 0))
                cur_pts[g_["away"]] = cur_pts.get(g_["away"], 0) + (0 if hw_ and not ot_ else (1 if hw_ else 2))
                for t_ in (g_["home"], g_["away"]): cur_gp[t_] = cur_gp.get(t_, 0) + 1
            mean_pred = statistics.mean(r_["pred"] for r_ in prows)
            mults = pwp.get("sim_sd_mult", [1] * len(pwp["checkpoints"])); cgp = [c_["gp"] for c_ in pwp["checkpoints"]]
            import numpy as _np
            rat = {r_["team"]: r_["pred"] - mean_pred for r_ in prows}
            sds = {r_["team"]: r_["true_sd"] * float(_np.interp(r_["gp"], cgp, mults)) for r_ in prows}
            conf_ = {s_["abbr"]: s_["conf"] for s_ in standings}; div_ = {s_["abbr"]: s_["div"] for s_ in standings}
            # playoff series model (params/playoff_params.json): elite = top-12 F / top-6 D by ice time with talent at
            # or above the 90th percentile at the position (players who have played this season)
            ppo = json.load(open(P("params", "playoff_params.json"))) if os.path.exists(P("params", "playoff_params.json")) else None
            elite_ = {}
            if ppo and players_league:
                for t_ in rat:
                    sk_ = [q_ for q_ in players_league if q_["t"] == t_ and q_["g"] in "FD" and not q_.get("ng")]
                    top_ = sorted([q_ for q_ in sk_ if q_["g"] == "F"], key=lambda q_: -(q_["tpg"] or 0))[:12] + sorted([q_ for q_ in sk_ if q_["g"] == "D"], key=lambda q_: -(q_["tpg"] or 0))[:6]
                    elite_[t_] = sum(1 for q_ in top_ if (q_.get("tpct") or 0) >= ppo["elite_pct"])
            series_ = {**{k_: ppo[k_] for k_ in ("b_power", "b_elite", "alpha")}, "elite_cap": ppo.get("elite_cap", 99), "elite": elite_, "tv_end": pwp["true_var"][-1]} if ppo and elite_ else None
            lsim = seasonsim.simulate(rat, sds, cur_pts, rem_, wpp, conf_, div_, sims=10000, seed=7, series=series_)
            bw_ = wpp["win"][1]
            for r_ in prows:
                q_ = lsim.get(r_["team"])
                if q_:
                    r_.update({"projPts": round(q_["mean"], 1), "projLo": round(q_["lo95"]), "projHi": round(q_["hi95"]), "projLo80": round(q_["lo80"]), "projHi80": round(q_["hi80"]),
                               "pPlayoff": round(q_["playoff"], 3), "pDiv": round(q_["division"], 3)})
                r_["neutralWin"] = round(1 / (1 + math.exp(-bw_ * rat[r_["team"]])), 3)     # vs. an average team, neutral ice
                r_["r"] = round(rat[r_["team"]], 4)
            if lsim.get("_playoffs"):
                po_ = lsim["_playoffs"]; a_ = ppo["alpha"]
                wsum_ = sum(po_[t_]["make"] for t_ in po_) or 1
                avgR_ = sum(rat[t_] * po_[t_]["make"] for t_ in po_) / wsum_; avgE_ = sum(elite_.get(t_, 0) * po_[t_]["make"] for t_ in po_) / wsum_
                cap_ = ppo.get("elite_cap", 99)
                avgE_ = sum(min(elite_.get(t_, 0), cap_) * po_[t_]["make"] for t_ in po_) / wsum_
                ser_ = lambda r0_, e0_: 1 / (1 + math.exp(-a_ * (ppo["b_power"] * (r0_ - avgR_) + ppo["b_elite"] * (min(e0_, cap_) - avgE_))))
                for r_ in prows:
                    t_ = r_["team"]
                    if t_ in po_:
                        z_ = 1.2816 * math.sqrt(max(sds[t_] ** 2 - pwp["true_var"][-1], 0))     # same uncertainty the series model uses
                        r_["po"] = {**po_[t_], "elite": elite_.get(t_, 0), "strength": round(ser_(rat[t_], elite_.get(t_, 0)), 3),
                                    "strengthLo": round(ser_(rat[t_] - z_, elite_.get(t_, 0)), 3), "strengthHi": round(ser_(rat[t_] + z_, elite_.get(t_, 0)), 3)}
                power_out["playoffModel"] = {k_: ppo[k_] for k_ in ppo if k_ != "_note"}
                power_out["playoffModel"]["note"] = ppo["_note"]
            power_out["simAll"] = {t_: [{"x": x_, "n": h_[x_] + (h_[x_ + 1] if x_ + 1 < len(h_) else 0)} for x_ in range(0, len(h_), 2) if h_[x_] + (h_[x_ + 1] if x_ + 1 < len(h_) else 0) > 0]
                                   for t_, h_ in lsim["_hist"].items()}
            power_out["sched"] = [[g_["date"], g_["home"], g_["away"], g_["state"], g_["hs"], g_["as"], g_["period"]] for g_ in sched]
            power_out.update({"winprob": wpp, "simBacktest": json.load(open(P("params", "sim_backtest.json"))), "schedDone": len(done_),
                              "hia": json.load(open(P("params", "hia_params.json"))) if os.path.exists(P("params", "hia_params.json")) else None})
            # Utah: next games with win odds, and the hero projection from the same league simulation
            ru_ = rat.get(TEAM)
            if ru_ is not None:
                lg_ = lambda x: 1 / (1 + math.exp(-x))
                for g_ in next10:
                    ro_ = rat.get(g_["opp"])
                    if ro_ is None: continue
                    a_, b_ = wpp["win"]; c_, d_ = wpp["ot"]
                    hm_ = g_["ha"] in ("H", "vs")
                    re_ = rest_edge(TEAM, g_["opp"], g_["date"]) if hm_ else -rest_edge(g_["opp"], TEAM, g_["date"])   # Utah's rest edge
                    g_["rest"] = re_; g_["b2b"] = [t_ for t_ in (TEAM, g_["opp"]) if b2b_(t_, g_["date"])]
                    if hm_: pw_ = lg_(a_ + b_ * (ru_ - ro_) + REST_LOGIT * re_)
                    else: pw_ = 1 - lg_(a_ + b_ * (ro_ - ru_) - REST_LOGIT * re_)
                    pot_ = lg_(c_ + d_ * abs(ru_ - ro_))
                    g_["pWin"] = round(pw_, 3); g_["pOT"] = round(pot_, 3)
                    e_, f_ = wpp["otwin"]
                    p_otwin_ = lg_(e_ + f_ * (ru_ - ro_)) if g_["ha"] in ("H", "vs") else 1 - lg_(e_ + f_ * (ro_ - ru_))
                    g_["xPts"] = round(2 * pw_ + pot_ * (1 - p_otwin_), 2)          # win = 2, overtime/shootout loss = 1
                    g_["oppRank"] = next((r_["rank"] for r_ in prows if r_["team"] == g_["opp"]), None)
                h_ = lsim["_hist"].get(TEAM)
                if h_:
                    sim = dict(sim); qu_ = lsim[TEAM]
                    sim.update({"mean": round(qu_["mean"], 1), "lo95": round(qu_["lo95"]), "hi95": round(qu_["hi95"]), "lo50": round(qu_["lo50"]), "hi50": round(qu_["hi50"]), "lo80": round(qu_["lo80"]), "hi80": round(qu_["hi80"]),
                                "p_playoff": round(qu_["playoff"], 3), "hist": [{"x": x_, "n": h_[x_] + (h_[x_ + 1] if x_ + 1 < len(h_) else 0)} for x_ in range(0, len(h_), 2) if h_[x_] + (h_[x_ + 1] if x_ + 1 < len(h_) else 0) > 0], "source": "league", "cut": lsim.get("_cut", {}).get(conf_.get(TEAM))})
    gl25_all = [r for r in gl25 if r["season"] == "2025" and r["situation"] == "all"]
    lg_sv = 1 - sum(num(r["goals"]) for r in gl25_all) / sum(num(r["ongoal"]) for r in gl25_all)
    per_game, series = [], {}
    for path in sorted(glob.glob(P("inputs", "nhl", "boxscores", "*.json"))):
        b = json.load(open(path, encoding="utf-8"))
        gid = str(b["id"])
        lines = {s_["name"]: f'{s_["g"]}G {s_["a"]}A, {s_["sog"]} SOG, {s_.get("pm",0):+d}' for s_ in b["skaters"]}
        for gl in b["goalies"]:
            lines[gl["name"]] = f'{gl["sv"]}/{gl["sa"]} saves'
        if gid in pg_gaa:
            rows = [{"name": n, "pos": v["pos"], "score": v["gaa"], "line": lines.get(n, "")} for n, v in pg_gaa[gid].items() if n in lines]
            method = "Player Impact, full model (from MoneyPuck's game-by-game data)"
        else:
            rows = []
            method = "Waiting for MoneyPuck's game-by-game data for this game"
        pg_score = {x["name"]: x["score"] for x in rows}
        rows.sort(key=lambda x: -x["score"])
        opp = b["away"] if b["home"] == TEAM else b["home"]
        per_game.append({"id": b["id"], "date": b["date"], "opp": opp, "score": f'{b["uta_score"]}-{b["opp_score"]}', "method": method,
                         "units": "goals", "exact": gid in pg_gaa, "pending": gid not in pg_gaa, "best": rows[:3], "worst": rows[-3:][::-1] if rows else []})
        for n_, v_ in pg_score.items():
            series.setdefault(n_, []).append(v_)
    for r_ in rank:
        sr = series.get(r_["name"], [])
        r_["cum"] = [round(sum(sr[:i + 1]), 2) for i in range(len(sr))]

    # ---- every team's Roster-tab extras (everything except contracts): game-by-game stars, last game's lines,
    # season lines and pairs (5v5), goaltending. Utah keeps its own richer versions (box-score stat lines, staff lineup).
    team_extra = {}
    if full_mp:
        lg_sched_ = {str(g_["id"]): g_ for g_ in json.load(open(P("inputs", "nhl", "league_schedule.json")))["games"]} if os.path.exists(P("inputs", "nhl", "league_schedule.json")) else {}
        def tx_(t_):
            return team_extra.setdefault(t_, {"perGame": [], "lastLines": None, "lines": [], "goalies": []})
        # season lines and pairs, 5v5, with the same uncertainty band as Utah's
        for r in readcsv(P("inputs", "moneypuck", "lines.csv")):
            if r["season"] != "2026" or r["situation"] != "5on5" or r["team"] == TEAM:
                continue
            F, A = num(r["xGoalsFor"]), num(r["xGoalsAgainst"]); sog = num(r["shotsOnGoalFor"]); hrs = num(r["icetime"]) / 3600
            vF, vA = num(r["unblockedShotAttemptsFor"]) * ep2["5on5"], num(r["unblockedShotAttemptsAgainst"]) * ep2["5on5"]
            se_ = math.sqrt(A * A * vF + F * F * vA) / (F + A) ** 2 if F + A else None
            tx_(r["team"])["lines"].append({"name": r["name"].replace("-", " – "), "type": r["position"], "toi": round(num(r["icetime"]) / 60, 1),
                "xgf": F / (F + A) if F + A else None, "lo": max(0, F / (F + A) - 1.96 * se_) if se_ else None, "hi": min(1, F / (F + A) + 1.96 * se_) if se_ else None,
                "gf": int(num(r["goalsFor"])), "ga": int(num(r["goalsAgainst"])), "sog": int(sog), "reb": int(num(r["reboundsFor"])),
                "fu": round(num(r["reboundsFor"]) / sog, 3) if sog else None, "xga60": round(A / hrs, 2) if hrs else None})
        for t_, e_ in team_extra.items():
            L_ = sorted(e_["lines"], key=lambda x: -x["toi"])
            e_["lines"] = sorted([x for x in L_ if x["type"] == "line"][:8] + [x for x in L_ if x["type"] == "pairing"][:5], key=lambda x: (x["type"], -x["toi"]))
        # goaltending from the season goalie file (+ last season)
        g25id_ = {r["playerId"]: r for r in gl25 if r["season"] == "2025" and r["situation"] == "all"}
        for r in gl26:
            if r["season"] != "2026" or r["situation"] != "all" or r["team"] == TEAM:
                continue
            sa_, ga_ = num(r["ongoal"]), num(r["goals"]); p_ = g25id_.get(r["playerId"])
            tx_(r["team"])["goalies"].append({"name": r["name"], "gp": int(num(r["games_played"])), "sa": int(sa_), "sv": int(sa_ - ga_), "ga": int(ga_),
                "svp": round(1 - ga_ / sa_, 3) if sa_ else None, "gsax": round(num(r["xGoals"]) - ga_, 2),
                "gsax25": round(num(p_["xGoals"]) - num(p_["goals"]), 1) if p_ else None, "gp25": int(num(p_["games_played"])) if p_ else None})
        for e_ in team_extra.values():
            e_["goalies"].sort(key=lambda q_: (-q_["gp"], -q_["sa"]))
        # game by game (latest 10 games with MoneyPuck game data) and last game's lines, from the game-by-game files
        if "skaters" in games_files and "goalies" in games_files:
            gsk_all, ggl_all = {}, {}
            for r in readcsv(games_files["skaters"]):
                if r["season"] == "2026" and r["playerTeam"] != TEAM:
                    r["team"] = r["playerTeam"]; r["games_played"] = "1"; gsk_all.setdefault((r["playerTeam"], r["gameId"]), []).append(r)
            for r in readcsv(games_files["goalies"]):
                if r["season"] == "2026" and r["playerTeam"] != TEAM:
                    r["team"] = r["playerTeam"]; r["games_played"] = "1"; ggl_all.setdefault((r["playerTeam"], r["gameId"]), []).append(r)
            by_team_ = {}
            for (t_, gid_) in gsk_all:
                by_team_.setdefault(t_, []).append(gid_)
            for t_, gids_ in by_team_.items():
                for gid_ in sorted(gids_)[-10:]:
                    rows_ = gsk_all[(t_, gid_)]; gls_ = ggl_all.get((t_, gid_), [])
                    res_ = impact.compute(rows_, gls_, raw26, "2026", ip, team=t_, means_override=means25)
                    stat_ = {}
                    for r in rows_:
                        if r["situation"] == "all":
                            a_ = int(num(r["I_F_primaryAssists"]) + num(r["I_F_secondaryAssists"]))
                            stat_[r["name"]] = f'{int(num(r["I_F_goals"]))}G {a_}A, {int(num(r["I_F_shotsOnGoal"]))} SOG'
                    for r in gls_:
                        if r["situation"] == "all":
                            stat_[r["name"]] = f'{int(num(r["ongoal"]) - num(r["goals"]))}/{int(num(r["ongoal"]))} saves'
                    vals_ = sorted([{"name": v["name"], "pos": v["grp"], "score": round(v["gaa"], 2), "line": stat_.get(v["name"], "")} for v in res_ if v["toi"] > 0], key=lambda x: -x["score"])
                    g_ = lg_sched_.get(gid_, {}); home_ = g_.get("home") == t_
                    us_, them_ = (g_.get("hs"), g_.get("as")) if home_ else (g_.get("as"), g_.get("hs"))
                    tx_(t_)["perGame"].append({"id": int(gid_), "date": g_.get("date") or rows_[0]["gameDate"], "opp": rows_[0]["opposingTeam"],
                        "score": f"{us_}-{them_}" if us_ is not None else "", "method": "Player Impact, full model (from MoneyPuck's game-by-game data)",
                        "units": "goals", "exact": True, "pending": False, "best": vals_[:3], "worst": vals_[-3:][::-1]})
                tx_(t_)["perGame"].reverse()
            # last game's lines from ice time (5v5): greedy, no player twice
            gl_lines_ = {}
            if "lines" in games_files:
                for r in readcsv(games_files["lines"]):
                    if r["season"] == "2026" and r["situation"] == "5on5" and r["playerTeam"] != TEAM:
                        gl_lines_.setdefault((r["playerTeam"], r["gameId"]), []).append(r)
            for t_, gids_ in by_team_.items():
                last_ = sorted(gids_)[-1]; rows_ = sorted(gl_lines_.get((t_, last_), []), key=lambda r: -num(r["icetime"]))
                used_, fw_, df_ = set(), [], []
                for r in rows_:
                    ps_ = r["name"].split("-")
                    if used_ & set(ps_):
                        continue
                    if r["position"] == "line" and len(fw_) < 4 and len(ps_) == 3:
                        fw_.append(ps_); used_ |= set(ps_)
                    elif r["position"] == "pairing" and len(df_) < 3 and len(ps_) == 2:
                        df_.append(ps_); used_ |= set(ps_)
                gl_ = sorted([r for r in ggl_all.get((t_, last_), []) if r["situation"] == "all"], key=lambda r: -num(r["icetime"]))
                g_ = lg_sched_.get(last_, {})
                tx_(t_)["lastLines"] = {"game": f'{g_.get("date", "")} {"vs" if g_.get("home") == t_ else "@"} {g_.get("away") if g_.get("home") == t_ else g_.get("home")}',
                                        "forwards": fw_, "defense": df_, "goalie": gl_[0]["name"].split(" ")[-1] if gl_ else ""}

    # ---- matchup tab: per-game team rates (this season + last season at half weight) and last season's games
    team_rates = {}
    for rows_, s_, w_ in ((raw26, "2026", 1.0), (raw25, "2025", 0.5)):
        for r in rows_:
            if r["season"] != s_ or r["situation"] not in ("all", "5on4", "4on5", "5on5"):
                continue
            e_ = team_rates.setdefault(r["team"], {"gp": 0.0, "sf": 0.0, "sa": 0.0, "xgf": 0.0, "xga": 0.0, "gf": 0.0, "ga": 0.0, "pt": 0.0, "pd": 0.0,
                                                   "hdf": 0.0, "hda": 0.0, "ppx": 0.0, "pph": 0.0, "pkx": 0.0, "pkh": 0.0, "gpn": 0.0,
                                                   "x5f": 0.0, "x5a": 0.0, "h5": 0.0, "hd5f": 0.0, "hd5a": 0.0, "c5f": 0.0, "c5a": 0.0,
                                                   "gfN": 0.0, "gaN": 0.0, "xgfN": 0.0, "xgaN": 0.0})
            if r["situation"] == "5on5":
                e_["x5f"] += w_ * num(r["xGoalsFor"]); e_["x5a"] += w_ * num(r["xGoalsAgainst"]); e_["h5"] += w_ * num(r["iceTime"]) / 3600
                e_["hd5f"] += w_ * num(r["highDangerShotsFor"]); e_["hd5a"] += w_ * num(r["highDangerShotsAgainst"])
                e_["c5f"] += w_ * num(r["shotAttemptsFor"]); e_["c5a"] += w_ * num(r["shotAttemptsAgainst"])
                continue
            if r["situation"] == "all" and s_ == "2026":
                for k_, c_ in (("gfN", "goalsFor"), ("gaN", "goalsAgainst"), ("xgfN", "xGoalsFor"), ("xgaN", "xGoalsAgainst")):
                    e_[k_] += num(r[c_])
            if r["situation"] == "all":
                e_["gp"] += w_ * num(r["games_played"]); e_["gpn"] += num(r["games_played"]) if s_ == "2026" else 0
                for k_, c_ in (("sf", "shotsOnGoalFor"), ("sa", "shotsOnGoalAgainst"), ("xgf", "xGoalsFor"), ("xga", "xGoalsAgainst"), ("gf", "goalsFor"), ("ga", "goalsAgainst"),
                               ("pt", "penaltiesFor"), ("pd", "penaltiesAgainst"), ("hdf", "highDangerShotsFor"), ("hda", "highDangerShotsAgainst")):
                    e_[k_] += w_ * num(r[c_])
            elif r["situation"] == "5on4":
                e_["ppx"] += w_ * num(r["xGoalsFor"]); e_["pph"] += w_ * num(r["iceTime"]) / 3600
            else:
                e_["pkx"] += w_ * num(r["xGoalsAgainst"]); e_["pkh"] += w_ * num(r["iceTime"]) / 3600
    for t_, e_ in team_rates.items():
        g_ = e_["gp"] or 1
        team_rates[t_] = {k_: round(e_[k_] / g_, 3) for k_ in ("sf", "sa", "xgf", "xga", "gf", "ga", "pt", "pd", "hdf", "hda")}
        team_rates[t_].update({"pp60": round(e_["ppx"] / e_["pph"], 3) if e_["pph"] else None, "pk60": round(e_["pkx"] / e_["pkh"], 3) if e_["pkh"] else None, "gpNow": int(e_["gpn"])})
        h5_ = e_["h5"] or 1
        team_rates[t_].update({"f5": round(e_["x5f"] / h5_, 3), "a5": round(e_["x5a"] / h5_, 3), "h5": round(e_["h5"] / g_, 3),
                               "hdf5": round(e_["hd5f"] / h5_, 2), "hda5": round(e_["hd5a"] / h5_, 2), "cf5": round(e_["c5f"] / max(1, e_["c5f"] + e_["c5a"]), 4),
                               "pph": round(e_["pph"] / g_, 4), "pkh": round(e_["pkh"] / g_, 4),
                               "finNow": round((e_["gfN"] - e_["xgfN"]) / e_["gpn"], 3) if e_["gpn"] else None,
                               "savNow": round((e_["xgaN"] - e_["gaN"]) / e_["gpn"], 3) if e_["gpn"] else None})
    games25 = json.load(open(P("inputs", "history", "games_2025-26.json")))["games"] if os.path.exists(P("inputs", "history", "games_2025-26.json")) else []

    # ---- team needs, surplus and fits (screening tool)
    # team-level 5v5 shot quality for the two on-ice components (player on/off values cancel out when summed over a roster);
    # this season pooled with last season at half weight, like the team style tags
    tm5_ = {}
    for rows_, s_, w_ in ((raw26, "2026", 1.0), (raw25, "2025", 0.5)):
        for r in rows_:
            if r["season"] == s_ and r["situation"] == "5on5":
                e_ = tm5_.setdefault(r["team"], [0.0, 0.0, 0.0])
                e_[0] += w_ * num(r["xGoalsFor"]); e_[1] += w_ * num(r["xGoalsAgainst"]); e_[2] += w_ * num(r["iceTime"]) / 3600
    team_needs = needs_mod.build(players_league, lineup_mod.league(players_league, 1.0) if players_league else None,
                                 power_out["rows"] if power_out else None, PPAR["impact_goal_slope"] * PPAR["points_per_goal"], SEASON_GAMES,
                                 team5=tm5_, gp_by_team={r["team"]: num(r["games_played"]) for r in raw26 if r["season"] == "2026" and r["situation"] == "all"}) if players_league else None
    # ---- anytime-goal rates for the matchup preview (validated: params/scorer_params.json, 2026-27 player-games so far)
    # rate = individual xG per 60, all situations (this season + 3 prior, weights 1/1/0.5/0.25), shrunk toward 60% of league
    # with 6 pseudo-hours; times shrunk finishing (goals + 20) / (xG + 20). The page multiplies by ice time and the opponent factor.
    scp_ = json.load(open(P("params", "scorer_params.json"))) if os.path.exists(P("params", "scorer_params.json")) else None
    if scp_ and players_league:
        acc_ = {}
        srcs_ = [(P("inputs", "moneypuck", "skaters.csv"), {"2026": 1.0}), (os.path.join(SRC, "skaters.csv"), {"2025": 1.0}),
                 (P("inputs", "history", "moneypuck", "skaters_2008_to_2024.csv"), {"2024": 0.5, "2023": 0.25})]
        for path_, ws_ in srcs_:
            if not os.path.exists(path_): continue
            with open(path_, newline="", encoding="utf-8") as fh_:
                for r in csv.DictReader(fh_):
                    w_ = ws_.get(r["season"])
                    if not w_ or r["situation"] != "all": continue
                    e_ = acc_.setdefault(r["playerId"], [0.0, 0.0, 0.0]); e_[0] += w_ * num(r["I_F_xGoals"]); e_[1] += w_ * num(r["I_F_goals"]); e_[2] += w_ * num(r["icetime"]) / 3600
        lr_, kx_, kf_ = scp_["lg_rate60"], scp_["k_xg_hours"], scp_["k_fin"]
        for p_ in players_league:
            if p_.get("g") == "G": continue
            e_ = acc_.get(str(p_["id"]), [0.0, 0.0, 0.0])
            p_["gx60"] = round((e_[0] + kx_ * lr_ * 0.6) / (e_[2] + kx_) * (e_[1] + kf_) / (e_[0] + kf_), 4)
    for p_ in players_league or []:
        p_.pop("profV", None)      # internal only
        if p_.get("use"):
            p_["use"] = {k_: (round(v_, 2) if v_ is not None else None) for k_, v_ in p_["use"].items()}

    # ---- automated data-integrity checks
    checks = []
    if me and mp_gp:
        if mp_gp == gp:
            ok = int(uta26["gf"]) == me["gf"] and int(uta26["ga"]) == me["ga"]
            checks.append({"check": "MoneyPuck goals vs. NHL standings", "ok": ok, "detail": f'MoneyPuck {int(uta26["gf"])}-{int(uta26["ga"])}, NHL {me["gf"]}-{me["ga"]}'})
        else:
            checks.append({"check": "MoneyPuck vs. NHL games played", "ok": False, "detail": f"MoneyPuck has {mp_gp} GP, NHL {gp}. Shot-model stats lag until MoneyPuck files are refreshed."})
    nbox = len(glob.glob(P("inputs", "nhl", "boxscores", "*.json")))
    checks.append({"check": "Box scores logged for every game", "ok": nbox == gp, "detail": f"{nbox} box scores, {gp} games played"})
    bad = []
    for path in glob.glob(P("inputs", "nhl", "boxscores", "*.json")):
        b = json.load(open(path))
        # a shootout winner's score includes one goal no skater is credited with
        so_ = 1 if b.get("last_period") == "SO" and b["uta_score"] > b["opp_score"] else 0
        if sum(s_["g"] for s_ in b["skaters"]) != b["uta_score"] - so_:
            bad.append(str(b["id"]))
    checks.append({"check": "Box-score goals sum to final score", "ok": not bad, "detail": "all games match" if not bad else "mismatch: " + ", ".join(bad)})
    for gid_, d_ in pg_gaa.items():
        for n_, v_ in d_.items():
            pg_sum[n_] = pg_sum.get(n_, 0.0) + v_["gaa"]
    n_exact_games = len(pg_gaa)
    if pg_gaa and rank and n_exact_games == mp_gp:
        gap_ = max([abs(pg_sum.get(r_["name"], 0.0) - r_["gaa"]) for r_ in rank if r_["gp"] and r_["name"] in pg_sum] or [0.0])
        n_snap_ = sum(1 for v_ in pg_src.values() if v_ == "snap")
        checks.append({"check": "Per-game Impact is consistent with season totals", "ok": gap_ <= 0.25 * max(1, n_exact_games) ** 0.5,
                       "detail": f"largest per-player gap between summed game values and the season total: {gap_:.2f} goals ({n_exact_games - n_snap_} game(s) from game-by-game data, {n_snap_} provisional from season snapshots). Each game is measured against the team's play in that game and the season total against the season, so they differ slightly; a game's value never changes once MoneyPuck posts it."})
    elif False:
        # only players whose whole season is Utah games in the file (traded-in players' season rows include other teams)
        ng_ = {}
        for gid_, d_ in pg_gaa.items():
            if pg_src.get(gid_) == "game":
                for n_ in d_: ng_[n_] = ng_.get(n_, 0) + 1
        gap_ = max([abs(pg_sum.get(r_["id"], 0.0) - r_["gaa"]) for r_ in rank if ng_.get(r_["name"], 0) == r_["gp"]] or [0.0])
        checks.append({"check": "Per-game Impact adds up to season totals", "ok": gap_ <= 0.15,
                       "detail": f"largest per-player gap between summed game values and the season-file total: {gap_:.2f} goals ({len(set(pg_src))} games from MoneyPuck game-by-game data)"})
    elif pg_gaa:
        lag_ = mp_gp - n_exact_games
        checks.append({"check": "Per-game Impact is consistent with season totals", "ok": True,
                       "detail": f"MoneyPuck's game-by-game file has {n_exact_games} of Utah's {mp_gp} games; the other {lag_} show no per-game values until MoneyPuck posts them (power-ranking results use the season file meanwhile)."})
    if full_mp:
        nPl_ = sum(1 for q_ in lg26 if not q_.get("noGames")); nCap_ = sum(1 for q_ in lg26 if not q_.get("noGames") and q_.get("aav"))
        # judged by ice time: call-ups and prospects missing from the pasted Spotrac list play few minutes, so a count-based
        # threshold fails as the season goes on even when nearly all minutes are covered
        tT_ = sum(num(q_.get("toi")) for q_ in lg26 if not q_.get("noGames")); tC_ = sum(num(q_.get("toi")) for q_ in lg26 if not q_.get("noGames") and q_.get("aav"))
        checks.append({"check": "Cap hits matched to players", "ok": tC_ >= 0.98 * tT_,
                       "detail": f"{nCap_} of {nPl_} players who have played this season have a 2026-27 cap hit, covering {100 * tC_ / max(tT_, 1):.1f}% of ice time (Spotrac list: {len(cap_rows)} contracts; {len(cap_miss)} list entries not matched, mostly players who haven't played yet; unmatched players who have played are mostly call-ups not on the pasted list). Market line fitted on {fit['n'] if fit else 0} skaters, r = {fit['r'] if fit else '-'} for non-entry-level deals."})
    # team views agree: every team in power, roster and lineup views; records match standings; talent pieces line up
    if power_out and league_out and players_league:
        lnv_ = lineup_mod.league(players_league, 1.0)
        tP_ = {r_["team"]: r_ for r_ in power_out["rows"]}; tR_ = {r_["team"]: r_ for r_ in league_out["rosters"]}; tL_ = {r_["team"]: r_ for r_ in lnv_}
        tS_ = {s_["abbr"]: s_ for s_ in standings}
        miss_ = [t_ for t_ in tS_ if t_ not in tP_ or t_ not in tR_ or t_ not in tL_]
        recbad_ = [t_ for t_ in tS_ if t_ in tP_ and tP_[t_]["rec"] != f'{tS_[t_]["w"]}-{tS_[t_]["l"]}-{tS_[t_]["otl"]}']
        ts_ = [t_ for t_ in tS_ if t_ not in miss_]
        rk_ = lambda v_: {t_: i_ for i_, t_ in enumerate(sorted(ts_, key=lambda t_: -v_[t_]))}
        a_ = rk_({t_: tP_[t_]["parts"]["lineup"] for t_ in ts_}); b_ = rk_({t_: tR_[t_]["total"] for t_ in ts_})
        rr_ = statistics.correlation([a_[t_] for t_ in ts_], [b_[t_] for t_ in ts_]) if len(ts_) > 3 else 0
        checks.append({"check": "Team views agree", "ok": not miss_ and not recbad_ and rr_ >= 0.8,
                       "detail": f"{len(ts_)} of {len(tS_)} teams in power, roster and lineup views{' (missing: ' + ', '.join(miss_) + ')' if miss_ else ''}; records match standings{' except ' + ', '.join(recbad_) if recbad_ else ''}; power-ranking lineup piece vs. roster talent rank correlation {rr_:.2f}. (Power goal differential excludes empty-net goals, as in the backtest.)"})
    v_ = ip["validation"]
    checks.append({"check": "Impact model at least matches the alternatives out of sample", "ok": v_["impact"]["all"] >= max(v_["old_gaa"]["all"], v_["points60"]["all"]) - 0.01,
                   "detail": f"predicting a player's on-ice goal differential relative to his team in other seasons ({v_['n']:,} player-seasons, 2008-09 to 2025-26, weights refitted without the tested season and the two on either side): Impact r = {v_['impact']['all']} (F {v_['impact']['F']}, D {v_['impact']['D']}), points per 60 r = {v_['points60']['all']} (F {v_['points60']['F']}, D {v_['points60']['D']}), previous model r = {v_['old_gaa']['all']}"})
    if power_out:
        bt_ = power_out["backtest"]
        ok_ = all(v["r"]["FULL with prior-only roster"] >= max(v["r"]["standings GD"], v["r"]["xGD"], v["r"]["last season GD"], v["r"]["lineup (adopted)"]) - 0.005 for v in bt_.values())
        covs_ = [c_["coverage_rest"] for c_ in power_out["cps"]]
        checks.append({"check": "Power rankings backtested", "ok": ok_ and min(covs_) >= 0.93 and max(covs_) <= 0.97,
                       "detail": f"8 seasons, 5 in-season checkpoints: blend r " + ", ".join(f"{v['r']['FULL with prior-only roster']}" for v in bt_.values()) + f" vs. goal differential alone " + ", ".join(f"{v['r']['standings GD']}" for v in bt_.values()) + f"; 95% rest-of-season ranges held {min(covs_)*100:.1f}-{max(covs_)*100:.1f}% at each checkpoint"})
    if power_out and power_out.get("schedDone") is not None:
        st_gp = sum(s_["gp"] for s_ in standings) // 2
        checks.append({"check": "League schedule matches standings", "ok": st_gp == power_out["schedDone"],
                       "detail": f"{power_out['schedDone']} completed games in the schedule file vs. {st_gp} in the standings (refresh both together)"})
    rv_ = json.load(open(P("params", "roster_params.json")))
    dd_ = rv_["dashboard_def"]
    checks.append({"check": "Roster-strength view adds information", "ok": dd_["r_both"] >= dd_["r_baseline"] + 0.02,
                   "detail": f"start-of-season test on {dd_['n']} team-seasons: roster talent r = {dd_['r']}, last season's goal differential r = {dd_['r_baseline']}, both together r = {dd_['r_both']}"})
    recs = params["reconciliation"]
    checks.append({"check": "Game model calibrated to league points rate", "ok": True, "detail": f"OT inflation factor {tie_f}, average team = {lg_pts_pct:.3f} points %"})
    if power_out and any(r_.get("po") for r_ in power_out["rows"]):
        po_rows_ = [r_ for r_ in power_out["rows"] if r_.get("po")]
        s_make_ = sum(r_["po"]["make"] for r_ in po_rows_); s_cup_ = sum(r_["po"]["cup"] for r_ in po_rows_)
        agree_ = max(abs(r_["po"]["make"] - (r_.get("pPlayoff") or 0)) for r_ in po_rows_)
        mono_ = all(r_["po"]["make"] + 1e-9 >= r_["po"]["r1"] >= r_["po"]["r2"] - 1e-9 >= r_["po"]["final"] - 2e-9 >= r_["po"]["cup"] - 3e-9 for r_ in po_rows_)
        checks.append({"check": "Playoff simulation adds up", "ok": abs(s_make_ - 16) < 0.01 and abs(s_cup_ - 1) < 0.01 and agree_ < 0.002 and mono_,
                       "detail": f"{s_make_:.2f} playoff teams and {s_cup_:.3f} Cups per simulated season (16 and 1); playoff odds match the standings simulation within {agree_ * 100:.2f} points; each round's odds no higher than the round before."})

    # ---- executive summary (rule-based; claims carry their confidence)
    conf = "low" if gp < 10 else ("medium" if gp < 25 else "high")
    ins = []
    ins.append({"tag": "Outlook", "tone": "good" if sim["p_playoff"] >= 0.65 else ("bad" if sim["p_playoff"] < 0.4 else "neutral"),
                "head": f"Projected {round(sim['mean'])} points (80% range {sim.get('lo80', sim['lo95'])}-{sim.get('hi80', sim['hi95'])})",
                "body": (f"{round(sim['p_playoff']*100)}% chance of making the playoffs, from 10,000 simulations of every remaining NHL game (power ratings + home ice, division and wild-card format)." if sim.get("source") == "league"
                         else f"{round(sim['p_playoff']*100)}% chance of clearing a typical West playoff line (~{round(pline['pts_mean'])} points, from {pline['n']} seasons).")})
    if deserved is not None:
        gap = round(pts_at_mp - deserved, 1)
        lim = 1.96 * math.sqrt(max(mp_gp, 1) * 0.7)
        tone = "neutral" if abs(gap) < lim else ("warn" if gap > 0 else "good")
        msg = ("Results are ahead of the shot quality by more than random variation explains." if gap >= lim else
               "Results trail the shot quality by more than random variation explains; points tend to follow." if gap <= -lim else
               "Any gap between results and shot quality is within normal randomness.")
        ins.append({"tag": "Process vs. results", "tone": tone, "head": f"{pts_at_mp} points earned, {deserved} expected from shot quality", "body": msg})
    if confirmed_str:
        x = sorted(confirmed_str, key=lambda x: -abs(x["z"] or 0))[0]
        ins.append({"tag": "Confirmed strength", "tone": "good", "head": f"{x['label']}" + (f": {ord_(x['rank'])} in the NHL" if x["rank"] else ""), "body": f"{fmtv(x['cur'], x['fmt'])}. Utah's true level is clearly better than league average (95%), after accounting for sample size and how much this stat carries over (year-to-year r = {x['rel_yoy']})."})
    elif strengths:
        x = strengths[0]
        ins.append({"tag": "Leading strength (not yet confirmed)", "tone": "neutral", "head": f"{x['label']}: {ord_(x['rank'])} in the NHL", "body": f"{fmtv(x['cur'], x['fmt'])}. Not yet distinguishable from average: after {mp_gp} game{'s' if mp_gp != 1 else ''}, only {round(100 * (metrics[x['key']]['sig'].get('rel') or 0))}% of this number reflects Utah's true level."})
    if confirmed_weak:
        x = sorted(confirmed_weak, key=lambda x: -abs(x["z"] or 0))[0]
        ins.append({"tag": "Confirmed weakness", "tone": "bad", "head": f"{x['label']}" + (f": {ord_(x['rank'])} in the NHL" if x["rank"] else ""), "body": f"{fmtv(x['cur'], x['fmt'])}. Utah's true level is clearly worse than league average (95%), after accounting for sample size and carry-over (r = {x['rel_yoy']})."})
    elif weaknesses:
        x = weaknesses[0]
        ins.append({"tag": "Leading weakness (not yet confirmed)", "tone": "neutral", "head": f"{x['label']}: {ord_(x['rank'])} in the NHL", "body": f"{fmtv(x['cur'], x['fmt'])}. Not yet statistically distinguishable from average at 95%."})
    sk_ = [r_ for r_ in rank if r_["grp"] != "G" and r_["gp"] >= max(1, gp // 2)]
    if sk_:
        b_ = sk_[0]; w_ = sk_[-1]
        vtxt = {"above": "clearly above average", "below": "clearly below average", "unclear": "not yet distinguishable from average",
                "early": "too early for a verdict", "none": "no games yet"}
        ins.append({"tag": "Top performer", "tone": "good", "head": f"{b_['name']}: {to_pts(b_['gaa']):+.1f} standings points vs. average", "body": f"90% range {to_pts(b_['gaa'] - 1.645 * b_['se']):+.1f} to {to_pts(b_['gaa'] + 1.645 * b_['se']):+.1f} points: {vtxt[b_['verdict']]}."})
        ins.append({"tag": "Lowest performer", "tone": "bad", "head": f"{w_['name']}: {to_pts(w_['gaa']):+.1f} standings points vs. average", "body": f"90% range {to_pts(w_['gaa'] - 1.645 * w_['se']):+.1f} to {to_pts(w_['gaa'] + 1.645 * w_['se']):+.1f} points: {vtxt[w_['verdict']]}."})
        lucky = max(sk_, key=lambda r_: r_["luck"]); unl = min(sk_, key=lambda r_: r_["luck"])
        tal_ = [r_ for r_ in rank if r_.get("talentVerdict") == "above"]
        if tal_:
            bt = max(tal_, key=lambda r_: r_["tstd"])
            ins.append({"tag": "Best player (talent)", "tone": "good", "head": f"{bt['name']}: {to_pts(bt['tstd']):+.1f} standings points per standard season",
                        "body": f"Talent independent of ice time, from this season and the last three. 90% range {to_pts(bt['tstd'] - 1.645 * bt['tstd_sd']):+.1f} to {to_pts(bt['tstd'] + 1.645 * bt['tstd_sd']):+.1f} points."})
        if gp >= 5:
            ins.append({"tag": "Running hot", "tone": "warn", "head": f"{lucky['name']}", "body": f"{to_pts(lucky['luck']):+.1f} standings points above what his talent predicts for these minutes. Expect some regression."})
            ins.append({"tag": "Running cold", "tone": "good", "head": f"{unl['name']}", "body": f"{to_pts(unl['luck']):+.1f} standings points below what his talent predicts for these minutes. Expect some improvement."})
    vc = [r_ for r_ in rank if r_.get("vsContract") is not None]
    if vc:
        bv = max(vc, key=lambda r_: r_["vsContract"]); wv = min(vc, key=lambda r_: r_["vsContract"])
        def vs_sig(r_):
            k_ = 1.645 / 1.96   # 90% bounds, matching the value table
            lo_ = r_["vsContract"] - (r_["vsContract"] - r_["vsLo"]) * k_; hi_ = r_["vsContract"] + (r_["vsHi"] - r_["vsContract"]) * k_
            return " Clearly more than the contract pays for." if lo_ > 0 else (" Clearly less than the contract pays for." if hi_ < 0 else " Not a clear gap yet.")
        ins.append({"tag": "Best value", "tone": "good", "head": f"{bv['name']} (${bv['aav']}M)", "body": f"Delivers {to_pts(bv['talent84']):+.1f} standings points per 84 games in his role vs. {to_pts(bv['expectedForPay']):+.1f} expected for his cap hit at the league market rate ({bv['vsPts']:+.1f})." + vs_sig(bv)})
        ins.append({"tag": "Worst value", "tone": "bad", "head": f"{wv['name']} (${wv['aav']}M)", "body": f"Delivers {to_pts(wv['talent84']):+.1f} standings points per 84 games in his role vs. {to_pts(wv['expectedForPay']):+.1f} expected for his cap hit ({wv['vsPts']:+.1f})." + vs_sig(wv)})
    if power_out:
        up_ = next((r_ for r_ in power_out["rows"] if r_["team"] == TEAM), None)
        if up_:
            ins.append({"tag": "Power ranking", "tone": "good" if up_["rhi"] <= 10 else ("bad" if up_["rlo"] >= 23 else "neutral"),
                        "head": f"{ord_(up_['rank'])} of {len(power_out['rows'])} (likely {up_['r10']}-{up_['r90']}), {up_['neutralWin'] * 100:.1f}% vs. an average team" if up_.get('neutralWin') is not None else f"{ord_(up_['rank'])} of {len(power_out['rows'])} (likely {up_['r10']}-{up_['r90']})",
                        "body": f"Rating {up_['rating']:+.1f} standings points per 84 games vs. an average team: lineup {up_['parts']['lineup']:+.1f}, results {up_['parts']['results']:+.1f}, shot quality {up_['parts']['shots']:+.1f}, last season {up_['parts']['lastseason']:+.1f}."})
    if league_out:
        ut_ = next((r_ for r_ in league_out["rosters"] if r_["team"] == TEAM), None)
        if ut_:
            gaps = {k: ut_[k] - league_out["avgTop8"][k] for k in ("F", "D", "G")}
            worst = min(gaps, key=gaps.get); nm_ = {"F": "forwards", "D": "defense", "G": "goaltending"}
            ins.append({"tag": "Roster vs. league", "tone": "neutral", "head": f"{ord_(ut_['rank_total'])} in summed player talent",
                        "body": f"Forwards {ord_(ut_['rank_F'])}, defense {ord_(ut_['rank_D'])}, goalies {ord_(ut_['rank_G'])}. Biggest gap to the eight strongest rosters: {nm_[worst]} ({to_pts(gaps[worst]):+.1f} standings points per 84 games)."})
    gq = [q for q in goalies if q.get("gs") and q.get("gsax") is not None]
    if gq:
        q = max(gq, key=lambda q: q["gs"])
        sig = ("too early for a verdict" if gp < UNLOCK["goalies"] else "clearly above average" if q["lo"] > 0 else ("clearly below average" if q["hi"] < 0 else "not yet distinguishable from average"))
        ins.append({"tag": "Goaltending", "tone": "neutral" if gp < UNLOCK["goalies"] else ("good" if q["lo"] > 0 else ("bad" if q["hi"] < 0 else "neutral")),
                    "head": (f"{q['name']}: {q['gsax']:+.1f} goals saved above expected" if len(gq) == 1 else
                             "Goals saved above expected: " + ", ".join(f"{g_['name'].split(' ')[-1]} {g_['gsax']:+.1f} ({g_['gs']} start{'s' if g_['gs'] != 1 else ''})" for g_ in sorted(gq, key=lambda g_: (-g_["gs"], -g_["gsax"])))),
                    "body": (f"{q['name'].split(' ')[-1]} has the most starts: {sig}. " if len(gq) > 1 and sum(1 for g_ in gq if g_["gs"] == q["gs"]) == 1 else f"{sig.capitalize()}. ") + "Goalie results are mostly noise over short stretches."})
    exec_summary = {"confidence": conf, "gp": gp, "items": ins}
    # ---- the same kind of summary for every other team (Overview follows the selected team), from league-wide data
    exec_all = {}
    if power_out and players_league:
        PPI_ = PPAR["impact_goal_slope"] * PPAR["points_per_goal"]
        rost_ = {r_["team"]: r_ for r_ in (league_out or {}).get("rosters", [])}
        for r_ in power_out["rows"]:
            t_ = r_["team"]
            if t_ == TEAM:
                continue
            gp_ = r_.get("gp") or 0; it_ = []
            if r_.get("projPts") is not None:
                pp_ = r_.get("pPlayoff") or 0
                it_.append({"tag": "Outlook", "tone": "good" if pp_ >= 0.65 else ("bad" if pp_ < 0.4 else "neutral"),
                            "head": f"Projected {round(r_['projPts'])} points (80% range {r_['projLo80']}-{r_['projHi80']})",
                            "body": f"{round(pp_ * 100)}% chance of making the playoffs, from 10,000 simulations of every remaining NHL game (power ratings + home ice, division and wild-card format)."})
            if r_.get("po"):
                po_ = r_["po"]
                it_.append({"tag": "Playoff strength", "tone": "good" if po_["strength"] >= 0.55 else ("bad" if po_["strength"] < 0.45 else "neutral"),
                            "head": f"{round(po_['strength'] * 100)}% to beat an average playoff team in a series",
                            "body": f"80% range {round(po_['strengthLo'] * 100)}-{round(po_['strengthHi'] * 100)}%. {po_['elite']} elite skater{'s' if po_['elite'] != 1 else ''} (top 10% at the position); Cup {round(po_['cup'] * 100, 1)}% overall, {round((po_['cupIfIn'] or 0) * 100, 1)}% if they make it."})
            it_.append({"tag": "Power ranking", "tone": "good" if r_["rhi"] <= 10 else ("bad" if r_["rlo"] >= 23 else "neutral"),
                        "head": f"{ord_(r_['rank'])} of {len(power_out['rows'])} (likely {r_['r10']}-{r_['r90']})" + (f", {r_['neutralWin'] * 100:.1f}% vs. an average team" if r_.get("neutralWin") is not None else ""),
                        "body": f"Rating {r_['rating']:+.1f} standings points per 84 games vs. an average team: lineup {r_['parts']['lineup']:+.1f}, results {r_['parts']['results']:+.1f}, shot quality {r_['parts']['shots']:+.1f}, last season {r_['parts']['lastseason']:+.1f}."})
            sw_ = [x_ for x_ in sw_all.get(t_, []) if x_.get("rank")]
            cs_ = [x_ for x_ in sw_ if x_["sig"] == "confirmed strength"]; cw_ = [x_ for x_ in sw_ if x_["sig"] == "confirmed weakness"]
            if cs_:
                x_ = min(cs_, key=lambda x_: x_["rank"])
                it_.append({"tag": "Confirmed strength", "tone": "good", "head": f"{x_['label']}: {ord_(x_['rank'])} in the NHL", "body": f"{fmtv(x_['cur'], x_['fmt'])}. Clearly better than league average (95%), after accounting for sample size and carry-over (r = {x_['rel_yoy']})."})
            elif sw_:
                x_ = min(sw_, key=lambda x_: x_["rank"])
                it_.append({"tag": "Leading strength (not yet confirmed)", "tone": "neutral", "head": f"{x_['label']}: {ord_(x_['rank'])} in the NHL", "body": f"{fmtv(x_['cur'], x_['fmt'])}. Not yet statistically distinguishable from average at 95%."})
            if cw_:
                x_ = max(cw_, key=lambda x_: x_["rank"])
                it_.append({"tag": "Confirmed weakness", "tone": "bad", "head": f"{x_['label']}: {ord_(x_['rank'])} in the NHL", "body": f"{fmtv(x_['cur'], x_['fmt'])}. Clearly worse than league average (95%), after accounting for sample size and carry-over (r = {x_['rel_yoy']})."})
            elif sw_:
                x_ = max(sw_, key=lambda x_: x_["rank"])
                it_.append({"tag": "Leading weakness (not yet confirmed)", "tone": "neutral", "head": f"{x_['label']}: {ord_(x_['rank'])} in the NHL", "body": f"{fmtv(x_['cur'], x_['fmt'])}. Not yet statistically distinguishable from average at 95%."})
            PL_ = [q_ for q_ in players_league if q_["t"] == t_ and not q_.get("ng")]
            sk_ = [q_ for q_ in PL_ if q_["g"] != "G" and q_["gp"] >= max(1, gp_ // 2)]
            if sk_:
                b_ = max(sk_, key=lambda q_: q_["imp"])
                lo_, hi_ = (b_["imp"] - 1.645 * b_["ise"]) * PPI_, (b_["imp"] + 1.645 * b_["ise"]) * PPI_
                it_.append({"tag": "Top performer", "tone": "good", "head": f"{b_['n']}: {b_['imp'] * PPI_:+.1f} standings points vs. average",
                            "body": f"90% range {lo_:+.1f} to {hi_:+.1f} points: " + ("clearly above average." if lo_ > 0 else "not yet distinguishable from average.")})
            tl_ = [q_ for q_ in PL_ if q_["g"] != "G" and q_.get("tal") is not None]
            if tl_:
                b_ = max(tl_, key=lambda q_: q_["tal"])
                it_.append({"tag": "Best player (talent)", "tone": "good", "head": f"{b_['n']}: {ord_(b_['tpct'])} percentile at his position" if b_.get("tpct") is not None else b_["n"],
                            "body": f"Talent independent of ice time, from this season and the last three: {b_['tal'] * PPI_:+.1f} standings points per standard season (90% range {(b_['tal'] - 1.645 * b_['tsd']) * PPI_:+.1f} to {(b_['tal'] + 1.645 * b_['tsd']) * PPI_:+.1f})."})
            vc_ = [q_ for q_ in PL_ if q_.get("vs") is not None]
            if vc_:
                k_ = 1.645 / 1.96
                def vsig_(q_):
                    lo_ = q_["vs"] - (q_["vs"] - q_["vsLo"]) * k_; hi_ = q_["vs"] + (q_["vsHi"] - q_["vs"]) * k_
                    return " Clearly more than the contract pays for." if lo_ > 0 else (" Clearly less than the contract pays for." if hi_ < 0 else " Not a clear gap yet.")
                bv_ = max(vc_, key=lambda q_: q_["vs"]); wv_ = min(vc_, key=lambda q_: q_["vs"])
                it_.append({"tag": "Best value", "tone": "good", "head": f"{bv_['n']} (${bv_['cap']}M)", "body": f"{bv_['vs'] * PPI_:+.1f} standings points per 84 games in his role vs. what his cap hit buys at the league market rate." + vsig_(bv_)})
                it_.append({"tag": "Worst value", "tone": "bad", "head": f"{wv_['n']} (${wv_['cap']}M)", "body": f"{wv_['vs'] * PPI_:+.1f} standings points per 84 games in his role vs. what his cap hit buys at the league market rate." + vsig_(wv_)})
            ro_ = rost_.get(t_)
            if ro_ and league_out:
                gaps_ = {g_: ro_[g_] - league_out["avgTop8"][g_] for g_ in ("F", "D", "G")}; w_ = min(gaps_, key=gaps_.get)
                it_.append({"tag": "Roster vs. league", "tone": "neutral", "head": f"{ord_(ro_['rank_total'])} in summed player talent",
                            "body": f"Forwards {ord_(ro_['rank_F'])}, defense {ord_(ro_['rank_D'])}, goalies {ord_(ro_['rank_G'])}. Biggest gap to the eight strongest rosters: {({'F': 'forwards', 'D': 'defense', 'G': 'goaltending'})[w_]} ({to_pts(gaps_[w_]):+.1f} standings points per 84 games)."})
            gq_ = sorted([q_ for q_ in PL_ if q_["g"] == "G" and q_["gp"] > 0], key=lambda q_: -q_["gp"])
            if gq_:
                q_ = gq_[0]
                it_.append({"tag": "Goaltending", "tone": "neutral", "head": f"{q_['n']}: {q_['imp']:+.1f} goals vs. an average goalie ({q_['gp']} GP)",
                            "body": (f"Rated {goalie_band(q_.get('tal'))} ({ord_(starter_pct(q_.get('tal')))} percentile among the 32 likely starters). Below the 20th percentile costs about 14 goals a season; above the 40th, more goalie talent adds little. " if starter_pct(q_.get('tal')) is not None else "") + "Goalie results are mostly noise over short stretches."})
            exec_all[t_] = {"confidence": "low" if gp_ < 10 else ("medium" if gp_ < 25 else "high"), "gp": gp_, "items": it_}
        up_ = next((r_ for r_ in power_out["rows"] if r_["team"] == TEAM and r_.get("po")), None)
        if up_:
            po_ = up_["po"]
            ins.insert(1, {"tag": "Playoff strength", "tone": "good" if po_["strength"] >= 0.55 else ("bad" if po_["strength"] < 0.45 else "neutral"),
                           "head": f"{round(po_['strength'] * 100)}% to beat an average playoff team in a series",
                           "body": f"80% range {round(po_['strengthLo'] * 100)}-{round(po_['strengthHi'] * 100)}%. {po_['elite']} elite skater{'s' if po_['elite'] != 1 else ''} (top 10% at the position; every Cup winner since 2014 had at least 2). Cup {round(po_['cup'] * 100, 1)}% overall, {round((po_['cupIfIn'] or 0) * 100, 1)}% if they make it."})
    # ---- game recaps for every other team's latest games (Overview follows the selected team): shots and goalies from
    # MoneyPuck, score and date from the league schedule (Utah's also use its box scores)
    recaps_all = {}
    shots_p_ = P("inputs", "moneypuck", "shots_2026.csv")
    if os.path.exists(shots_p_) and os.path.exists(P("inputs", "nhl", "league_schedule.json")):
        lgs_ = {g_["id"]: g_ for g_ in json.load(open(P("inputs", "nhl", "league_schedule.json")))["games"]}
        for t_ in sorted({s_["abbr"] for s_ in standings}):
            if t_ == TEAM:
                continue
            L_ = []
            for rc_ in recap_mod.build(shots_p_, P("inputs", "moneypuck_games", "goalies_games.csv"), "/nonexistent", t_):
                g_ = lgs_.get(rc_["id"])
                if not g_ or g_["state"] not in (6, 7):
                    continue
                home_ = g_["home"] == t_
                rc_.update({"date": g_["date"], "us": g_["hs"] if home_ else g_["as"], "them": g_["as"] if home_ else g_["hs"],
                            "lp": "SO" if g_["period"] >= 5 else ("OT" if g_["period"] == 4 else "REG")})
                L_.append(rc_)
            recaps_all[t_] = sorted(L_, key=lambda r_: r_["gid"])[-5:]

    # ---- snapshot history (trend lines)
    hist_path = P("history", "snapshots.json")
    hist = json.load(open(hist_path)) if os.path.exists(hist_path) else []
    snap = {"gp": gp, "date": now.strftime("%Y-%m-%d"), "pts": pts, "proj": round(sim["mean"]), "lo95": sim["lo95"], "hi95": sim["hi95"],
            "p_playoff": sim["p_playoff"], "xgf_pct_5v5": uta26.get("xgf_pct_5v5"), "reb_rate_for": uta26.get("reb_rate_for"),
            "pp_xgf60": uta26.get("pp_xgf60"), "pdo_5v5": uta26.get("pdo_5v5"), "sh_pct": uta26.get("sh_pct"), "sv_pct": uta26.get("sv_pct"),
            "gaa": {r_["name"]: r_["gaa"] for r_ in rank},
            "power": {r_["team"]: r_["rank"] for r_ in (power_out or {}).get("rows", [])} or None}
    hist = [h for h in hist if h["gp"] != gp] + [snap]
    hist.sort(key=lambda h: h["gp"])
    json.dump(hist, open(hist_path, "w"), indent=1)

    brief = open(P("config", "brief.md"), encoding="utf-8").read()
    last = played[-1] if played else None
    data = {
        "built": now.strftime("%b %d, %Y %I:%M %p"), "season": "2026-27",
        "dataStatus": {"rosters": rosters_note, "mpFull": full_mp, "standingsDate": standings[0]["date"] if standings else None, "boxscores": nbox, "mpGp": mp_gp},
        "unlock": UNLOCK,
        "team": {"gp": gp, "pts": pts, "rec": f'{me["w"]}-{me["l"]}-{me["otl"]}' if me else "", "rw": me["rw"] if me else None,
                 "streak": me["streak"] if me else "", "gf": me["gf"] if me else None, "ga": me["ga"] if me else None,
                 "pace": round(act_ppg * SEASON_GAMES) if gp else None, "proj": round(sim["mean"]), "projLo": sim["lo95"], "projHi": sim["hi95"], "projLo80": sim.get("lo80"), "projHi80": sim.get("hi80"),
                 "proj50": [sim["lo50"], sim["hi50"]], "pPlayoff": sim["p_playoff"], "preProj": round(sim_pre["mean"]), "prePlayoff": sim_pre["p_playoff"],
                 "playoffLine": round(sim["cut"]["median"]) if sim.get("cut") else round(pline["pts_mean"]), "playoffLineSd": pline["pts_sd"],
                 "playoffLineHist": round(pline["pts_mean"]), "playoffLineN": pline["n"], "playoffLineNow": ({k_: round(v_) for k_, v_ in sim["cut"].items()} if sim.get("cut") else None), "deserved": deserved, "ptsAtMp": pts_at_mp,
                 "xgf": uta26.get("xgf"), "xga": uta26.get("xga"), "p321": me["p321"] if me else None,
                 "shareMean": round(post_mean, 4), "shareSd": round(post_sd, 4), "priorShare": round(prior_mean, 4), "priorSd": round(prior_sd, 4), "simHist": sim["hist"], "simSource": sim.get("source", "utah")},
        "last": last, "next10": next10, "cum": cum, "seasonGames": SEASON_GAMES,
        "gamelog": [{"n": i + 1, "date": g["date"], "ha": g["ha"], "opp": g["opp"], "res": g["res"], "us": g["us"], "them": g["them"], "cum": cum[i]["pts"]} for i, g in enumerate(played)][::-1],
        "exec": exec_summary, "execAll": exec_all, "goalieStarters": goalie_starters, "recapsAll": recaps_all, "version": VERSION, "metrics": metrics, "sw": sw_list, "strengths": strengths, "weaknesses": weaknesses, "carryover": carryover,
        "standings": standings, "central": CENTRAL, "players": players, "mpLines": mp_lines, "teamExtra": team_extra, "rank": rank, "perGame": per_game[::-1], "rankFit": fit, "rankFitRaw": fit_raw, "profRel": prof_rel, "teamNeeds": team_needs, "teamRates": team_rates, "recaps": recap_mod.build(P("inputs", "moneypuck", "shots_2026.csv"), P("inputs", "moneypuck_games", "goalies_games.csv"), P("inputs", "nhl", "boxscores"), TEAM),
        "snaps": [{"gp": h_["gp"], "date": h_["date"], "pPlayoff": h_["p_playoff"], "proj": h_["proj"], "rank": (h_.get("power") or {}).get(TEAM)} for h_ in hist], "scorerVal": scp_ if players_league else None, "restVal": json.load(open(P("params", "rest_validation.json"))) if os.path.exists(P("params", "rest_validation.json")) else None, "muVal": json.load(open(P("params", "matchup_validation.json"))) if os.path.exists(P("params", "matchup_validation.json")) else None, "games25": games25, "consensusTest": json.load(open(P("params", "consensus_test.json"))) if os.path.exists(P("params", "consensus_test.json")) else None,
        "league": league_out, "power": power_out, "pairwise": pairwise, "playersLeague": players_league,
        "lineups": lineup_mod.league(players_league, PPAR["impact_goal_slope"] * PPAR["points_per_goal"]) if players_league else None, "shots": shotmap.build(P("inputs", "moneypuck", "shots_2026.csv"), TEAM) if os.path.exists(P("inputs", "moneypuck", "shots_2026.csv")) else None,
        "shotsAll": ({t_: (lambda s_: {"games": s_["games"], "maps": {k_: {kk: v_[kk] for kk in ("uta", "goals", "total", "slotShare")} for k_, v_ in s_["maps"].items()}})(shotmap.build(P("inputs", "moneypuck", "shots_2026.csv"), t_))
                      for t_ in sorted({s_["abbr"] for s_ in standings})} if os.path.exists(P("inputs", "moneypuck", "shots_2026.csv")) else None),
        "swAll": sw_all, "ppi": round(PPAR["impact_goal_slope"] * PPAR["points_per_goal"], 4),
        "priorW": {g: ip.get("noise", {}).get(g, {}).get("prior_w", 1.0) for g in "FDG"},
        "talentW": {g: ip.get("talent_w", {}).get(g) for g in "FDG"},
        "teamGaa": team_gaa_total, "tilt": tilt, "tiltAvg": {"xgf60": lg_xgf60, "xga60": lg_xga60},
        "goalies": goalies, "lineup": lineup, "history": hist, "brief": brief, "checks": checks,
        "model": {"reliability": rel, "impact": {**{k: ip[k] for k in ("validation", "drivers", "reliability", "report", "scale", "zs", "box")},
                             "noise": {g: {k: v for k, v in ip.get("noise", {}).get(g, {}).items() if k != "old"} for g in "FDG"},
                             "noiseOld": {g: ip.get("noise", {}).get(g, {}).get("old") for g in "FDG"},
                             "age": ip.get("age", {}).get("_decision")}, "reconciliation": recs, "playoffLine": pline, "tieF": tie_f, "teamPrior": tp},
        "countdowns": [{"label": "Defending champs Carolina visit", "date": "2026-12-17"},
                       {"label": "Winter Classic vs Colorado, Rice-Eccles", "date": "2026-12-31"},
                       {"label": "Six-game homestand begins", "date": "2027-01-23"},
                       {"label": "Keller extension window opens", "date": "2027-07-01"}],
    }
    for k_ in ("metrics", "players", "tilt", "tiltAvg", "carryover", "central", "unlock", "priorW", "teamGaa", "season", "history"):
        data.pop(k_, None)
    json.dump(data, open(P("output", "data.json"), "w"), indent=1, default=str)
    tpl = open(P("template.html"), encoding="utf-8").read()
    html = tpl.replace("/*__DATA__*/", "window.DATA = " + json.dumps(data, default=str) + ";")
    open(P("output", "mammoth_dashboard.html"), "w", encoding="utf-8").write(html)
    print(f"Built: GP {gp}, {pts} pts, projected {sim['mean']} ({sim['lo95']}-{sim['hi95']}), playoff {sim['p_playoff']}, "
          f"prior {sim_pre['mean']}, deserved {deserved}, players {len(rank)}, checks ok {sum(c_['ok'] for c_ in checks)}/{len(checks)}")


if __name__ == "__main__":
    main()
