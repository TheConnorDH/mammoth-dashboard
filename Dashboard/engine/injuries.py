"""Injuries: who is out, for how long, and what it costs each upcoming game (v1.8.0).

Source: config/injuries.json (ESPN's injury feed, fetched each morning). Each listed player is matched to the league
player table by team and name. For each of his team's next games, the chance he is out:
  - a reported return date: out for games before it;
  - Out / Injured Reserve, or Day-To-Day after missing the team's latest game: from how absences have actually run
    (params/injury_params.json surv: P(out one more game | out k so far) = surv[k+1] / surv[k]); long-term IR keeps him
    out for at least 10 team games from his first missed game;
  - Day-To-Day and he played the latest game: no adjustment (not tested; the team decides at game time).
Players who were on yesterday's list and are off it today, and who are not in the recent lineup, come back.

Cost of an absence = the lineup weight of the power model x (his talent per 60 - his replacement's) x his minutes / 60:
the same weight as any other lineup change, which the backtest supports (injury_backtest.py: fitted 1.11 vs 0.98).
That shift is applied only to the games he is expected to miss: single-game odds and the season simulation.
Power rankings are not adjusted (the backtest found no gain for rest-of-season prediction)."""
import re
import unicodedata

ESPN_ABBR = {"NJ": "NJD", "TB": "TBL", "SJ": "SJS", "LA": "LAK", "UTAH": "UTA", "WAS": "WSH", "MON": "MTL", "CLB": "CBJ",
             "NAS": "NSH", "VEG": "VGK", "WIN": "WPG", "CAL": "CGY", "ANH": "ANA", "PHX": "UTA", "ARI": "UTA"}
HORIZON = 30   # team games ahead


def norm(name):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", "", s.replace("-", " ")).strip()


def _team_of(e, by_name, abbrs):
    t = by_name.get(norm(e.get("teamName", "")))
    if t:
        return t
    a = (e.get("team") or "").upper()
    a = ESPN_ABBR.get(a, a)
    return a if a in abbrs else None


def build(inj, prev, players, standings, sched, last_played, params, today, lineup_detail, b_lineup, newcomer60, std_min, wp_slope, data_through=None):
    """inj / prev: injuries.json contents (or None). players: playersLeague rows. sched: league schedule games.
    last_played: {player id: 'YYYY-MM-DD'}; data_through: {team: last game date in the game-by-game file} (games after it
    are not counted as missed, since the file can lag the schedule). lineup_detail: {team: [[pid, grp, rate60, mpg], ...]} from the power model.
    b_lineup: {team: lineup weight}. Returns (rows for the page, per-game shifts {game id: {'h': x, 'a': x}}, status)."""
    if not inj or not inj.get("players"):
        return [], {}, {"ok": False, "n": 0, "matched": 0, "fetched": (inj or {}).get("fetched")}
    surv = params["surv"]
    by_name = {norm(s["name"]): s["abbr"] for s in standings}
    abbrs = {s["abbr"] for s in standings}
    P = {}
    for p in players:
        P.setdefault((p["t"], norm(p["n"])), p)
    by_nm = {}
    for p in players:
        by_nm.setdefault(norm(p["n"]), []).append(p)
    # each team's games: finished (for games missed) and upcoming (for the chance he is out)
    fin, up = {}, {}
    for g in sorted(sched, key=lambda g: (g["date"], g["id"])):
        for t in (g["home"], g["away"]):
            if g["state"] in (6, 7):
                fin.setdefault(t, []).append(g)
            elif g["date"] >= today:        # not final and not in the past (a postponed or lagging game is not "next")
                up.setdefault(t, []).append(g)
    LD = {t: {str(x[0]): x for x in L} for t, L in (lineup_detail or {}).items()}

    def rate_of(p):   # talent per 60 from the player table (goals per 84 games at the standard workload)
        g = p["g"]; m = (std_min.get(g) or {}).get("mall") or 15.0; n = (std_min.get(g) or {}).get("games") or 84
        return p["tal"] * 60 / (n * m) if p.get("tal") is not None else newcomer60.get(g, 0.0)

    listed = set()
    rows = []
    for e in inj["players"]:
        t = _team_of(e, by_name, abbrs)
        if not t:
            continue
        p = P.get((t, norm(e["name"])))
        if not p:      # traded or listed under a slightly different name: same name anywhere in the league, if unique
            c = by_nm.get(norm(e["name"]), [])
            p = c[0] if len(c) == 1 else None
        if not p:      # nickname on one side (Alex / Alexander): same team, same last name and first initial, if unique
            nn = norm(e["name"]).split()
            c = [q for q in players if q["t"] == t and nn and norm(q["n"]).split()[-1:] == nn[-1:] and norm(q["n"])[:1] == nn[0][:1]]
            p = c[0] if len(c) == 1 else None
        rows.append({"e": e, "t": t, "p": p}); listed.add((t, norm(e["name"])))
    # recently activated (dropped off the list within the last 14 days; fetch_nhl keeps the list) who haven't played since
    # and aren't in the recent lineup: he returns for the next game. Fallback: yesterday's list vs. today's.
    back = []
    act = inj.get("activated")
    if act is None and prev and prev.get("players"):
        act = [{**e, "since": today} for e in prev["players"]]
    for e in act or []:
        t = _team_of(e, by_name, abbrs)
        if not t or (t, norm(e["name"])) in listed:
            continue
        p = P.get((t, norm(e["name"])))
        lp = last_played.get(str(p["id"])) if p else None
        if p and str(p["id"]) not in LD.get(t, {}) and not p.get("ng") and (lp is None or lp < (e.get("since") or today)):
            back.append({"t": t, "p": p, "e": e})

    def replacement(t, g, excl):
        ld = LD.get(t, {})
        if g == "G":       # a goalie's starts go to the team's other goalie: the next one in the recent lineup, else the best extra
            gl = sorted([x for x in ld.values() if x[1] == "G" and x[0] not in {str(i) for i in excl}], key=lambda x: -x[3])
            if gl:
                return gl[0][2]
        extras = [q for q in players if q["t"] == t and q["g"] == g and str(q["id"]) not in ld and str(q["id"]) not in {str(i) for i in excl} and q.get("tal") is not None]
        extras.sort(key=lambda q: -q["tal"])
        top = extras[:2]
        return sum(rate_of(q) for q in top) / len(top) if top else newcomer60.get(g, 0.0)

    out_ids = {r["p"]["id"] for r in rows if r["p"]}
    shifts, page = {}, []
    for r in rows:
        e, t, p = r["e"], r["t"], r["p"]
        status = e.get("status") or ""
        F, U = fin.get(t, []), up.get(t, [])[:HORIZON]
        lp = last_played.get(str(p["id"])) if p else None
        thru = (data_through or {}).get(t, "9999")
        k = sum(1 for g in F if (lp is None or g["date"] > lp) and g["date"] <= thru) if p else None       # team games missed so far
        if p and p.get("ng") and lp is None:
            k = sum(1 for g in F if g["date"] <= thru)
        dtd = status.lower().startswith("day")
        rd = e.get("returnDate")
        rd = rd if rd and rd > today else None      # a reported date already passed while he's still listed: use the curve
        pout = []
        for j, g in enumerate(U):
            if rd and rd > today:
                q = 1.0 if g["date"] < rd else 0.0
            elif dtd and not k:
                q = 0.0
            else:
                kk = k or 0
                q = (surv[min(kk + j + 1, len(surv) - 1)] / surv[min(kk, len(surv) - 1)]) if kk else surv[min(j + 1, len(surv) - 1)]
                if e.get("ltir") and kk + j < 10:
                    q = 1.0
            pout.append(round(q, 3))
        exp_missed = round(sum(pout), 1)
        first_below = lambda c: next((g["date"] for g, q in zip(U, pout) if q < c), None)    # None: still likely out at the horizon
        back_at, back_lo, back_hi = first_below(0.5), first_below(0.75), first_below(0.25)
        # cost: only players the model would otherwise count (in the recent lineup, or a regular by season minutes)
        cost = 0.0; mpg = None; inl = False
        if p:
            ld = LD.get(t, {}).get(str(p["id"]))
            if ld:
                rate, mpg, inl = ld[2], ld[3], True
                cost = (b_lineup.get(t) or 0.0) * (rate - replacement(t, p["g"], out_ids)) * mpg / 60
        for g, q in zip(U, pout):
            if q and cost:
                d = shifts.setdefault(str(g["id"]), {"h": 0.0, "a": 0.0})
                d["h" if g["home"] == t else "a"] += q * cost
        page.append({"t": t, "n": p["n"] if p else e["name"], "id": p["id"] if p else None, "pos": (p or {}).get("pos") or e.get("pos"), "g": (p or {}).get("g"),
                     "status": status, "ltir": bool(e.get("ltir")), "injury": e.get("injury"), "returnDate": rd, "note": e.get("note"), "detail": e.get("detail"),
                     "updated": e.get("updated"), "missed": k, "expMissed": exp_missed, "pNext": pout[0] if pout else None, "backBy": rd or back_at, "backLo": None if rd else back_lo, "backHi": None if rd else back_hi,
                     "pg": [[g["date"], q] for g, q in zip(U, pout) if q >= 0.05], "horizon": U[-1]["date"] if U else None,
                     "cost": round(cost, 4), "winCost": round(cost * wp_slope * 0.25, 4), "inLineup": inl, "mpg": round(mpg, 1) if mpg else None,
                     "tal": (p or {}).get("tal"), "tpct": (p or {}).get("tpct")})
    for b in back:      # back from the list: he returns for the next game, in place of his team's replacement-level player
        t, p = b["t"], b["p"]
        if p["g"] == "G" or not up.get(t):     # a returning goalie's share of starts is unknown: no adjustment
            continue
        rate = rate_of(p); mpg = p.get("tpg") or 0.0
        gain = (b_lineup.get(t) or 0.0) * (rate - replacement(t, p["g"], out_ids | {p["id"]})) * mpg / 60
        for g in up[t][:HORIZON]:
            d = shifts.setdefault(str(g["id"]), {"h": 0.0, "a": 0.0})
            d["h" if g["home"] == t else "a"] += -gain       # shifts are costs; a return is a negative cost
        page.append({"t": t, "n": p["n"], "id": p["id"], "pos": p.get("pos"), "g": p["g"], "status": "Activated", "ltir": False, "injury": b["e"].get("injury"),
                     "returnDate": None, "note": "Off the injury list since yesterday; expected back in the lineup.", "detail": None, "updated": None,
                     "missed": None, "expMissed": 0.0, "pNext": 0.0, "backBy": today, "backLo": None, "backHi": None, "pg": [], "horizon": None, "cost": round(-gain, 4), "winCost": round(-gain * wp_slope * 0.25, 4),
                     "inLineup": False, "mpg": round(mpg, 1), "tal": p.get("tal"), "tpct": p.get("tpct")})
    status = {"ok": bool(inj.get("ok", True)), "fetched": inj.get("fetched"), "error": inj.get("error"), "n": len(inj["players"]),
              "matched": sum(1 for r in rows if r["p"]), "unmatched": [r["e"]["name"] for r in rows if not r["p"]][:20], "activated": len(back)}
    return page, shifts, status
