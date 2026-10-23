"""Daily brief. 1) Build a facts packet from the built data (output/data.json + box scores + standings).
2) Ask Claude to write the brief from the packet only. 3) Check every number in the draft against the packet;
one retry with the problems listed; otherwise fall back to a plain template brief built from the same packet.
Writes config/brief.md and output/brief_audit.json."""
import json, os, re, glob, datetime as dt, urllib.request, urllib.error
from common import P, TEAM, log, write_text, write_json

MODEL = os.environ.get("BRIEF_MODEL", "claude-sonnet-5-5")
WD = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _pct(x): return f"{round(100 * x)}%"
def _ord(n): return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"
def _d(s): d = dt.date.fromisoformat(s); return f"{d.strftime('%b')} {d.day}"


def facts():
    d = json.load(open(P("output", "data.json"), encoding="utf-8"))
    st = {s["abbr"]: s for s in d["standings"]}
    raw = open(P("inputs", "nhl", "standings.txt"), encoding="utf-8").read(); raw = json.loads(raw[raw.find("{"):])
    divseq = {t["teamAbbrev"]["default"]: t["divisionSequence"] for t in raw["standings"]}
    name = {s["abbr"]: s["name"] for s in d["standings"]}
    tm, pw = d["team"], {r["team"]: r for r in d["power"]["rows"]}
    me = pw[TEAM]; u = st[TEAM]
    F = {"today": dt.date.today().isoformat(),
         "record": tm["rec"], "games_played": tm["gp"], "points": tm["pts"], "streak": tm.get("streak"),
         "division": u["div"], "division_place": _ord(divseq[TEAM]),
         "power_rank": _ord(me["rank"]), "power_likely_range": f"{_ord(me['r10'])}-{_ord(me['r90'])}", "power_tier": f"Tier {me['tier']}",
         "power_rating": f"{me['rating']:+.1f} standings points per 84 games vs. an average team",
         "projected_points": tm["proj"], "projected_80pct_range": f"{tm['projLo80']}-{tm['projHi80']}",
         "playoff_odds": _pct(tm["pPlayoff"]),
         "season_points_vs_expected_from_shot_quality": f"{tm['pts']} points vs. {tm['deserved']:.1f} expected",
         "season_expected_goals_for_against": f"{tm['xgf']:.1f} for, {tm['xga']:.1f} against"}
    sn = d.get("snaps") or []
    prev = [s for s in sn if s["gp"] < tm["gp"]]
    if prev:
        F["previous_playoff_odds"] = _pct(prev[-1]["pPlayoff"]); F["previous_power_rank"] = _ord(prev[-1]["rank"])
    # latest game
    boxes = sorted((json.load(open(f, encoding="utf-8")) for f in glob.glob(P("inputs", "nhl", "boxscores", "*.json"))), key=lambda b: b["id"])
    if boxes:
        b = boxes[-1]; home = b["home"] == TEAM; opp = b["away"] if home else b["home"]
        res = "won" if b["uta_score"] > b["opp_score"] else "lost"
        ot = {"OT": " in overtime", "SO": " in a shootout"}.get(b.get("last_period"), "")
        sched = json.load(open(P("inputs", "nhl", "league_schedule.json"), encoding="utf-8"))["games"]
        uta = [g for g in sched if TEAM in (g["home"], g["away"]) and g["state"] == 7]
        gnum = next((i for i, g in enumerate(uta, 1) if g["id"] == b["id"]), len(boxes))
        G = {"game_number": gnum, "days_since_game": (dt.date.today() - dt.date.fromisoformat(b["date"])).days, "date": _d(b["date"]), "opponent": name.get(opp, opp), "home_or_away": "home" if home else "away",
             "result": f"Utah {res} {b['uta_score']}-{b['opp_score']}{ot}", "shots_on_goal": f"Utah {b['uta_sog']}, {opp} {b['opp_sog']}",
             "utah_scorers": [f"{s['name']} ({s['g']}G {s['a']}A{', ' + str(s['ppg']) + ' PPG' if s.get('ppg') else ''})" for s in b["skaters"] if s["g"]],
             "utah_assists_only": [f"{s['name']} ({s['a']}A)" for s in b["skaters"] if s["a"] and not s["g"]],
             "utah_goalies": [f"{g['name']}: {g['sv']} saves on {g['sa']} shots{' (started)' if g.get('start') else ''}" for g in b["goalies"]]}
        if len(boxes) > 1:
            a = {s["name"] for s in boxes[-2]["skaters"]}; c = {s["name"] for s in b["skaters"]}
            G["lineup_in_vs_previous_game"] = sorted(c - a); G["lineup_out_vs_previous_game"] = sorted(a - c)
        G["skater_ice_time"] = {s["name"]: s["toi"] for s in b["skaters"]}
        rc = next((r for r in d.get("recaps", []) if r["id"] == b["id"]), None)
        if rc:
            s = rc["stats"]
            G.update({"expected_goals": f"Utah {s['xg'][0]:.1f}, {opp} {s['xg'][1]:.1f}", "expected_goals_5v5": f"Utah {s['xg5'][0]:.1f}, {opp} {s['xg5'][1]:.1f}",
                      "dangerous_shots_10pct_plus": f"Utah {s['danger'][0]}, {opp} {s['danger'][1]}",
                      "power_play_goals": f"Utah {s['ppg'][0]}, {opp} {s['ppg'][1]}",
                      "chance_utah_wins_replaying_every_shot_by_its_quality": _pct(rc["deserve"])})
            G["goalies_vs_expected"] = [f"{g['name']} ({g['team']}): allowed {g['ga']} on {g['sa']} shots worth {g['xga']:.1f} expected goals, "
                                        f"{abs(g['xga'] - g['ga']):.1f} goals {'better' if g['xga'] >= g['ga'] else 'worse'} than expected" for g in rc["goalies"]]
        else:
            G["note"] = "MoneyPuck's shot data for this game isn't out yet: no expected goals, dangerous shots or replay odds."
        pg = next((x for x in d.get("perGame", []) if x["id"] == b["id"] and not x.get("pending")), None)
        if pg:
            G["player_impact_best_goals"] = [f"{x['name']} ({x['score']:+.2f})" for x in pg["best"]]
            G["player_impact_lowest_goals"] = [f"{x['name']} ({x['score']:+.2f})" for x in pg["worst"]]
        F["latest_game"] = G
    nxt = []
    for g in d.get("next10", [])[:3]:
        wd = WD[dt.date.fromisoformat(g["date"]).weekday()]
        nxt.append({"day": wd, "date": _d(g["date"]), "where": "home" if g["ha"] == "vs" else "away", "opponent": name.get(g["opp"], g["opp"]),
                    "opponent_power_rank": _ord(g["oppRank"]), "utah_win_chance": _pct(g["pWin"]),
                    "back_to_back": [name.get(t, t) + " on the second night of a back-to-back" for t in g.get("b2b", [])],
                    "same_division": st.get(g["opp"], {}).get("div") == u["div"]})
    F["next_games"] = nxt
    mp_dates = [r["date"] for r in d.get("recaps", []) if r.get("date")]
    F["data_note"] = {"moneypuck_through": _d(max(mp_dates)) if mp_dates else None, "nhl_results_through": _d(max(g["date"] for g in json.load(open(P("inputs", "nhl", "league_schedule.json")))["games"] if g["state"] == 7))}
    return F


SYSTEM = """You write the daily brief for an objective, data-only Utah Mammoth dashboard. Rules:
- Use ONLY facts in the JSON packet. Never add anything from memory (injuries, trades, quotes, history, opinions, predictions beyond the packet).
- Every number you write must appear in the packet (you may write small counts as words). Don't compute new numbers (no differences, sums or averages).
- Neutral, plain language. No hype, no fan voice, no "we". Say what the numbers show; don't speculate about causes the packet doesn't show.
- Expected goals = quality of chances; "replaying every shot by its quality" = the chance Utah wins with average finishing and goaltending.
- Format (Markdown), 200-320 words:
## <headline: the result and the one-line story>
<one paragraph: record, the result, how the chances compared>
What the numbers showed:
- 3 to 5 bullets, each starting with a **bold label.** (lineup changes only if listed; goaltending vs expected; special teams; Player Impact best/lowest in goals; season process vs results)
**Where Utah stands:** power rank (likely range), tier, rating, projection with 80% range, playoff odds (and the previous value if given).
**What to watch next:** the next games with Utah's win chance; mention back-to-backs and division games only if flagged.
*Data note: MoneyPuck data through <date>; NHL results through <date>.*
If a fact is missing (e.g. no shot data yet), leave that part out and say the detailed chance data isn't in yet.
If days_since_game is 2 or more, open by saying Utah hasn't played since that date, then recap that game briefly.
Write scores and records with a hyphen exactly as in the packet (e.g. 5-4, 7-3-0). Use plain text only (no HTML)."""


NUM = r"[+\-\u2212]?\d+(?:\.\d+)?"
WORDNUM = r"\b(six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|hat trick)\b"


def _clean(text):
    return re.sub(r"\*\*|__|#", " ", text).replace("\u2212", "-").replace("\u2013", "-")


def verify(draft, packet):
    """Every number in the draft must come from the packet: scores/records/ranges as exact strings, times as ice times,
    other numbers by value (signs must match when written), percentages and decimals included. Plus: no spelled-out
    numbers above five, no capitalised names that aren't in the packet, the result string in the headline area, length."""
    P_ = json.loads(json.dumps(packet))
    times = set(((P_.get("latest_game") or {}).get("skater_ice_time") or {}).values())
    (P_.get("latest_game") or {}).pop("skater_ice_time", None)
    for k in ("today",): P_.pop(k, None)
    ptxt = _clean(json.dumps(P_, ensure_ascii=False))
    full = _clean(json.dumps(packet, ensure_ascii=False))
    dates = set(re.findall(r"[A-Z][a-z]{2} \d{1,2}\b", ptxt))
    signed = set(re.findall(NUM, ptxt))
    vals = {abs(float(x.lstrip("+"))) for x in signed} | {5.0, 10.0, 80.0, 84.0}
    dashed = set(re.findall(r"\b\d+(?:st|nd|rd|th)?-\d+(?:st|nd|rd|th)?(?:-\d+)?\b", ptxt))
    t = _clean(draft); probs = []
    for d_ in dates: t = t.replace(d_, " ")            # dates are checked as dates
    for m in re.findall(r"\b\d{1,2}:\d{2}\b", t):
        if m not in times: probs.append(f"time {m} not in the packet")
    t = re.sub(r"\b\d{1,2}:\d{2}\b", " ", t)
    for m in re.findall(r"\b\d+(?:st|nd|rd|th)?-\d+(?:st|nd|rd|th)?(?:-\d+)?\b", t):
        if m not in dashed: probs.append(f"'{m}' not in the packet")
    t = re.sub(r"\b\d+(?:st|nd|rd|th)?-\d+(?:st|nd|rd|th)?(?:-\d+)?\b", " ", t)
    t = re.sub(r"(\d)v(\d)", " ", t)
    for m in re.findall(NUM, t):
        v = abs(float(m.lstrip("+")))
        if v not in vals or (m[0] in "+-" and m not in signed and m.replace("+", "") not in signed):
            probs.append(f"number {m} not in the packet")
    for w in re.findall(WORDNUM, draft, flags=re.I): probs.append(f"spelled-out number '{w}'")
    ok_caps = {"Utah", "Mammoth", "MoneyPuck", "NHL", "Player", "Impact", "Tier", "Game", "Data", "Expected", "PP", "PPG", "SOG"}
    for m in re.finditer(r"(?<![.!?:*#\n] )(?<![.!?:*#\n])\b([A-Z][a-zA-Z'\-]{2,})", _clean(draft)):
        start = m.start(); pre = _clean(draft)[max(0, start - 3):start]
        if re.search(r"[.!?:*#\n(\-]\s*$", pre) or start == 0: continue
        nm = re.sub(r"'s$", "", m.group(1))
        if nm not in full and nm not in ok_caps: probs.append(f"name '{nm}' not in the packet")
        continue
        if m.group(1) not in full and m.group(1) not in ok_caps: probs.append(f"name '{m.group(1)}' not in the packet")
    G = packet.get("latest_game")
    if G and G["result"].split(" ")[2] not in draft[:400]: probs.append("the game score should appear in the opening")
    if "<" in draft: probs.append("no HTML")
    w = len(re.findall(r"\w+", draft))
    if not 190 <= w <= 360: probs.append(f"length {w} words (want 200-320)")
    if not draft.lstrip().startswith("## "): probs.append("must start with a '## ' headline")
    return sorted(set(probs))


def _auth_headers():
    """Workload Identity Federation (preferred: no stored key; GitHub's short-lived OIDC token is exchanged for a
    short-lived Anthropic token) when ANTHROPIC_FEDERATION_RULE_ID is set; otherwise an ANTHROPIC_API_KEY."""
    rule = os.environ.get("ANTHROPIC_FEDERATION_RULE_ID")
    if rule:
        req_url, req_tok = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
        if not req_url or not req_tok:
            raise RuntimeError("federation set up but no GitHub OIDC token (workflow needs permissions: id-token: write)")
        r = urllib.request.Request(req_url + "&audience=https://api.anthropic.com", headers={"Authorization": "Bearer " + req_tok})
        with urllib.request.urlopen(r, timeout=30) as f:
            jwt = json.loads(f.read())["value"]
        body = {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": jwt, "federation_rule_id": rule,
                "organization_id": os.environ.get("ANTHROPIC_ORGANIZATION_ID"), "service_account_id": os.environ.get("ANTHROPIC_SERVICE_ACCOUNT_ID")}
        if os.environ.get("ANTHROPIC_WORKSPACE_ID"): body["workspace_id"] = os.environ["ANTHROPIC_WORKSPACE_ID"]
        r = urllib.request.Request("https://api.anthropic.com/v1/oauth/token", data=json.dumps(body).encode(), method="POST",
                                   headers={"content-type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=30) as f:
                tok = json.loads(f.read())["access_token"]
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"federation token exchange failed ({e.code}); see Console > Workload identity > history")
        return {"authorization": "Bearer " + tok}
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("no Claude credentials (federation variables or ANTHROPIC_API_KEY)")
    return {"x-api-key": key}


_AUTH = {}


def _post(payload):
    if not _AUTH:
        _AUTH.update(_auth_headers())          # one token exchange per run (token lasts 10 minutes)
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode(), method="POST",
                                 headers={**_AUTH, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"Messages API {e.code}: {body[:400]}")


def call_claude(packet, feedback=None):
    msgs = [{"role": "user", "content": "Facts packet:\n```json\n" + json.dumps(packet, indent=1, ensure_ascii=False) + "\n```\nWrite today's brief."}]
    if feedback:
        msgs += [{"role": "assistant", "content": feedback[0]}, {"role": "user", "content": "Fix these problems and rewrite the whole brief: " + "; ".join(feedback[1])}]
    payload = {"model": MODEL, "max_tokens": 1500, "temperature": 0.2, "system": SYSTEM, "messages": msgs}
    try:
        j = _post(payload)
    except RuntimeError as e:
        # some models don't accept sampling settings; retry once without them
        if " 400:" in str(e) and "temperature" in str(e):
            payload.pop("temperature"); j = _post(payload)
        else:
            raise
    return "".join(c.get("text", "") for c in j.get("content", []) if c.get("type") == "text").strip()


def template(F):
    G = F.get("latest_game", {})
    out = [f"## {G['result']} {'vs.' if G['home_or_away'] == 'home' else 'at'} {G['opponent']}" if G else "## Utah update", ""]
    line = f"Utah is {F['record']}, {F['division_place']} in the {F['division']}."
    if G:
        line += f" Game {G['game_number']} ({G['date']}, {G['home_or_away']}): {G['result']}; shots on goal {G['shots_on_goal']}."
        if "expected_goals" in G:
            line += f" Expected goals {G['expected_goals']} (5v5: {G['expected_goals_5v5']}); replaying every shot by its quality, Utah wins {G['chance_utah_wins_replaying_every_shot_by_its_quality']} of the time."
    out += [line, "", "What the numbers showed:", ""]
    if G.get("utah_scorers"): out.append("- **Scoring.** " + ", ".join(G["utah_scorers"]) + ".")
    for g in G.get("goalies_vs_expected", []): out.append(f"- **In net.** {g}.")
    if G.get("player_impact_best_goals"):
        out.append("- **Player Impact (goals).** Best: " + ", ".join(G["player_impact_best_goals"]) + ". Lowest: " + ", ".join(G["player_impact_lowest_goals"]) + ".")
    out.append(f"- **Process vs. results.** {F['season_points_vs_expected_from_shot_quality']} from shot quality; expected goals {F['season_expected_goals_for_against']}.")
    prev = f", previously {F['previous_playoff_odds']}" if F.get("previous_playoff_odds") else ""
    out += ["", f"**Where Utah stands:** {F['power_rank']} in the power rankings (likely {F['power_likely_range']}), {F['power_tier']}, rated {F['power_rating']}. "
                f"Projected {F['projected_points']} points (80% range {F['projected_80pct_range']}), {F['playoff_odds']} playoff odds{prev}.", ""]
    if F["next_games"]:
        out.append("**What to watch next:** " + "; ".join(f"{g['day']} {'vs.' if g['where'] == 'home' else 'at'} {g['opponent']} (Utah {g['utah_win_chance']})" for g in F["next_games"]) + ".")
    dn = F["data_note"]
    out += ["", f"*Data note: MoneyPuck data through {dn['moneypuck_through']}; NHL results through {dn['nhl_results_through']}. Brief generated automatically from the numbers on this page.*"]
    return "\n".join(out) + "\n"


def run():
    try:
        F = facts()
    except Exception as e:                       # keep yesterday's brief rather than fail the update
        log("brief: facts failed, keeping previous brief:", e)
        return {"used": "previous", "error": f"facts: {e}"[:300], "attempts": []}
    audit = {"date": F["today"], "model": MODEL, "attempts": [], "used": None}
    text = None
    try:
        draft = call_claude(F); pr = verify(draft, F); audit["attempts"].append(pr)
        if pr:
            draft = call_claude(F, (draft, pr)); pr = verify(draft, F); audit["attempts"].append(pr)
        if not pr:
            text = draft.rstrip() + "\n"; audit["used"] = "claude"
    except Exception as e:
        audit["error"] = str(e)[:300]
    if text is None:
        try:
            text = template(F); audit["used"] = "template"
        except Exception as e:
            audit["error"] = (audit.get("error", "") + f" template: {e}")[:300]; audit["used"] = "previous"
            write_json(P("output", "brief_audit.json"), {**audit, "packet": F}); return audit
    write_text(P("config", "brief.md"), text)
    write_json(P("output", "brief_audit.json"), {**audit, "packet": F})
    log("brief:", audit["used"], audit.get("attempts"), audit.get("error", ""))
    return audit


if __name__ == "__main__":
    run()
