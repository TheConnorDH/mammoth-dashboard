"""Utah's current lines/pairs from the last game's 5v5 ice time (MoneyPuck game-by-game lines file), greedy with no
player twice (same rule the board uses for every other team); goalie starts from the box scores. Keeps Connor's own lineup."""
import csv, glob, json, os, datetime as dt
from common import P, TEAM, write_json, log


def _ranges(nums):
    out, s = [], None
    for i, n in enumerate(nums):
        if s is None: s = n
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            out.append(str(s) if s == n else f"{s}, {n}" if n == s + 1 else f"{s}-{n}"); s = None
    return ", ".join(out)


def build():
    path = P("config", "lineup.json")
    cfg = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    rows = [r for r in csv.DictReader(open(P("inputs", "moneypuck_games", "lines_games.csv"), encoding="utf-8"))
            if r["playerTeam"] == TEAM and r["situation"] == "5on5" and r["season"] == "2026"]
    if not rows:
        log("lineup: no Utah game rows yet; unchanged"); return cfg
    last = max(r["gameId"] for r in rows)
    L = sorted([r for r in rows if r["gameId"] == last], key=lambda r: -float(r["icetime"]))
    known = {p["name"].split(" ")[-1].lower() for p in json.load(open(P("config", "roster.json"), encoding="utf-8"))["players"]}

    def split(name):
        # MoneyPuck joins last names with "-": rejoin pieces that form a hyphenated roster name (e.g. Ekman-Larsson)
        parts, out, i = name.split("-"), [], 0
        while i < len(parts):
            if i + 1 < len(parts) and f"{parts[i]}-{parts[i + 1]}".lower() in known:
                out.append(f"{parts[i]}-{parts[i + 1]}"); i += 2
            else:
                out.append(parts[i]); i += 1
        return out
    used, fw, df = set(), [], []
    for r in L:
        ps = split(r["name"])
        if used & set(ps): continue
        if r["position"] == "line" and len(fw) < 4 and len(ps) == 3: fw.append(ps); used |= set(ps)
        elif r["position"] == "pairing" and len(df) < 3 and len(ps) == 2: df.append(ps); used |= set(ps)
    # order units by their players' own 5v5 ice time in that game (top line/pair first); fix MoneyPuck's name casing
    toi = {}
    for r in csv.DictReader(open(P("inputs", "moneypuck_games", "skaters_games.csv"), encoding="utf-8")):
        if r["gameId"] == last and r["playerTeam"] == TEAM and r["situation"] == "5on5":
            toi[r["name"].split(" ")[-1].lower()] = float(r["icetime"])
    fw.sort(key=lambda u: -sum(toi.get(x.lower(), 0) for x in u)); df.sort(key=lambda u: -sum(toi.get(x.lower(), 0) for x in u))
    roster_last = {p["name"].split(" ")[-1].lower(): p["name"].split(" ")[-1] for p in json.load(open(P("config", "roster.json"), encoding="utf-8"))["players"]}
    fw = [[roster_last.get(x.lower(), x) for x in u] for u in fw]; df = [[roster_last.get(x.lower(), x) for x in u] for u in df]
    if len(fw) < 4 or len(df) < 3:
        log(f"lineup: only {len(fw)} lines / {len(df)} pairs found for game {last}; unchanged"); return cfg
    # box scores (in game order) -> who dressed and who started in goal
    boxes = sorted((json.load(open(f, encoding="utf-8")) for f in glob.glob(P("inputs", "nhl", "boxscores", "*.json"))), key=lambda b: b["id"])
    starts = {}
    for i, b in enumerate(boxes, 1):
        for g in b.get("goalies", []):
            if g.get("start"): starts.setdefault(g["name"].split(" ")[-1], []).append(i)
    gtxt = "; ".join(f"{k} (Game{'s' if len(v) > 1 else ''} {_ranges(v)})" for k, v in sorted(starts.items(), key=lambda kv: kv[1][0]))
    dressed = {s["name"].split(" ")[-1] for s in boxes[-1]["skaters"]} if boxes and boxes[-1]["id"] == int(last) else set()
    roster = json.load(open(P("config", "roster.json"), encoding="utf-8"))["players"]
    scratches = [p["name"].split(" ")[-1] for p in roster if p["pos"] != "G" and dressed and p["name"].split(" ")[-1] not in dressed]
    b = next((x for x in boxes if x["id"] == int(last)), None)
    when = ""
    if b:
        d = dt.date.fromisoformat(b["date"]); opp = b["away"] if b["home"] == TEAM else b["home"]
        when = f"Game {boxes.index(b) + 1} ({d.strftime('%b')} {d.day} {'vs' if b['home'] == TEAM else '@'} {opp})"
    cfg["as_of"] = when or f"game {last}"
    cfg["source"] = "Automated: lines and pairs from MoneyPuck 5v5 ice time in the last game; goalie starts from NHL box scores; scratches = roster skaters who didn't dress."
    cfg["staff"] = {"forwards": fw, "defense": df, "goalie": gtxt, "scratches": scratches}
    write_json(path, cfg, indent=2)
    log("lineup:", cfg["as_of"], fw, df, "scratches", scratches)
    return cfg


if __name__ == "__main__":
    build()
