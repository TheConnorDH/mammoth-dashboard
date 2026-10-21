"""League-wide cap hits (Spotrac paste, 2026-27) matched to MoneyPuck player ids, plus the market pay line.
Cap hit is the value input (what the team carries against the cap). Spotrac's 'contract average' is only used to
flag entry-level deals: for ELCs it includes potential performance bonuses, so contract average > cap hit."""
import csv, os, re, unicodedata, difflib

ALIAS = {"zachary": "zach", "mitchell": "mitch", "joshua": "josh", "matthew": "matt", "thomas": "tom", "alexander": "alex",
         "nicholas": "nick", "jacob": "jake", "samuel": "sam", "christopher": "chris", "michael": "mike", "william": "will",
         "jonathan": "jon", "daniel": "dan", "cameron": "cam", "timothy": "tim", "anthony": "tony", "benjamin": "ben",
         "maxim": "max", "evgenii": "evgeni", "jt": "jt"}
TEAMFIX = {"WAS": "WSH"}
NAMEFIX = {"Mats Zuccarello-Aasen": "Mats Zuccarello"}   # Spotrac name -> MoneyPuck name


def grp_of(pos):
    return "G" if pos == "G" else ("D" if pos == "D" else "F")


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", "", s.replace("-", " ").replace(".", "")).strip()


def keyname(s):
    p = norm(s).split()
    if not p:
        return ""
    p[0] = ALIAS.get(p[0], p[0])
    return "".join(p)


def load(base):
    d = os.path.join(base, "inputs", "contracts")
    cap_p, avg_p = os.path.join(d, "caphit_2026-27_spotrac.csv"), os.path.join(d, "avg_2026-27_spotrac.csv")
    if not os.path.exists(cap_p):
        return []
    avg = {}
    if os.path.exists(avg_p):
        for r in csv.DictReader(open(avg_p, encoding="utf-8")):
            avg[(r["name"], r["team"])] = float(r["contract_avg"])
    out = []
    for r in csv.DictReader(open(cap_p, encoding="utf-8")):
        cap = float(r["cap_hit"]); a = avg.get((r["name"], r["team"]))
        out.append({"name": r["name"], "team": TEAMFIX.get(r["team"], r["team"]), "pos": r["pos"], "cap": cap / 1e6,
                    "avg": a / 1e6 if a else None, "bonusELC": bool(a and a - cap >= 50000 and cap <= 1.0e6)})
    return out


def match(rows, players):
    """players: dicts with id, name, team (and grp if known). Returns {player id: contract row} and the unmatched rows.
    Position breaks ties (Vancouver has two Elias Petterssons: a center and a defenseman)."""
    by_full, by_team_last = {}, {}
    for p in players:
        by_full.setdefault(keyname(p["name"]), []).append(p)
        by_team_last.setdefault((p["team"], norm(p["name"]).split()[-1] if norm(p["name"]) else ""), []).append(p)
    got, miss = {}, []
    for r in rows:
        k = keyname(NAMEFIX.get(r["name"], r["name"])); c = by_full.get(k, [])
        if len(c) > 1:
            c = [p for p in c if p["team"] == r["team"]]
        if len(c) > 1:
            c = [p for p in c if p.get("grp") == grp_of(r["pos"])]
        if len(c) != 1:   # same team + same last name, unique
            last = norm(r["name"]).split()[-1] if norm(r["name"]) else ""
            c = by_team_last.get((r["team"], last), [])
            if len(c) > 1:
                c = [p for p in c if p.get("grp") == grp_of(r["pos"])]
        if len(c) != 1:   # same team, close spelling (accents mangled in some files)
            cand = [p for p in players if p["team"] == r["team"]]
            best = max(cand, key=lambda p: difflib.SequenceMatcher(None, keyname(p["name"]), k).ratio(), default=None)
            c = [best] if best and difflib.SequenceMatcher(None, keyname(best["name"]), k).ratio() >= 0.85 else []
        if len(c) == 1 and c[0]["id"] not in got:
            got[c[0]["id"]] = r
        else:
            miss.append(r)
    return got, miss
