"""Daily pipeline: fetch -> freshness check -> lineup -> build -> brief -> rebuild -> integrity gate -> site/.
Sets GitHub output status=published (site/ ready) or status=waiting (early run, Utah's latest game not in every
source yet; the later run publishes). Exit 1 = failure: the live page stays as it was and GitHub emails the repo owner.
Run: python automation/daily.py [--final-attempt] [--offline]   (--offline skips downloads, for local tests)."""
import json, os, shutil, subprocess, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import P, REPO, DASH, TEAM, log, write_text
import fetch_moneypuck, fetch_nhl, lineup_auto, brief_auto

# A failed check in this list blocks publishing; others are shown on the page (Model Integrity) but don't block.
HARD = ("Box-score goals sum to final score", "League schedule matches standings",
        "Impact model at least matches the alternatives out of sample", "Power rankings backtested")


def summary(md):
    p = os.environ.get("GITHUB_STEP_SUMMARY")
    if p:
        with open(p, "a", encoding="utf-8") as f: f.write(md + "\n")
    log(md)


def build():
    for d_ in ("output", os.path.join("history", "mp")): os.makedirs(P(d_), exist_ok=True)
    r = subprocess.run([sys.executable, "build.py"], cwd=DASH, capture_output=True, text=True, timeout=1800)
    tail = (r.stdout or "")[-1500:] + (r.stderr or "")[-3000:]
    if r.returncode != 0:
        raise RuntimeError("build.py failed:\n" + tail)
    log(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "built")
    return json.load(open(P("output", "data.json"), encoding="utf-8"))


def selftest_box(players):
    """Compare the automated box-score converter against the newest hand-built box score (log only)."""
    hand = []
    for f in sorted(glob.glob(P("inputs", "nhl", "boxscores", "*.json"))):
        src = json.load(open(f, encoding="utf-8")).get("source", "")
        if "automated" not in src and "MoneyPuck" not in src:
            hand.append(f)
    if not hand:
        return
    old = json.load(open(hand[-1], encoding="utf-8")); gid = old["id"]
    try:
        box = fetch_nhl.get_json(f"{fetch_nhl.API}/gamecenter/{gid}/boxscore"); land = fetch_nhl.get_json(f"{fetch_nhl.API}/gamecenter/{gid}/landing")
        new = fetch_nhl.box_compact(box, land, fetch_nhl._names_by_id(players))
    except Exception as e:
        summary(f"- Box-score self-test skipped: {e}"); return
    o = {s["name"]: s for s in old["skaters"]}; diffs = []
    for s in new["skaters"]:
        q = o.get(s["name"])
        if not q: diffs.append(f"{s['name']} not in hand-built file"); continue
        for k in ("g", "a", "sog", "a1", "a2", "pt", "pd", "pm", "toi"):
            if q.get(k) != s.get(k): diffs.append(f"{s['name']} {k}: {q.get(k)} vs {s.get(k)}")
    summary(f"- Box-score self-test vs hand-built {gid}: " + ("identical on goals, assists, A1/A2, penalties, +/-, TOI" if not diffs else "; ".join(diffs[:12])))


def main():
    final = "--final-attempt" in sys.argv; offline = "--offline" in sys.argv
    summary(f"### Mammoth dashboard daily run ({'final attempt' if final else 'early attempt'})")
    if not offline:
        fetch_moneypuck.static()
        fetch_nhl.standings(); fetch_nhl.utah_schedule(); sched = fetch_nhl.league_schedule()
        players = fetch_nhl.roster()
        fetch_moneypuck.current()
        added, waiting = fetch_nhl.boxscores(sched, players)
        fetch_nhl.bios()
        summary("- Input sizes (distinct players): " + ", ".join(f"{k} {v}" for k, v in fetch_moneypuck.sizes().items()))
        selftest_box(players)
        # freshness: every finished league game should be in MoneyPuck's game file and shot file
        done = {g["id"] for g in sched if g["state"] == 7}
        gg, sh = fetch_moneypuck.game_ids()
        miss_g, miss_s = sorted(done - gg), sorted(done - sh)
        uta_done = [g["id"] for g in sched if g["state"] == 7 and TEAM in (g["home"], g["away"])]
        newest = uta_done[-1] if uta_done else None
        summary(f"- Finished games: {len(done)}; missing from MoneyPuck game file: {len(miss_g)}, shot file: {len(miss_s)}; Utah box scores waiting: {waiting}")
        if newest and (newest not in gg or newest not in sh or newest in waiting) and not final:
            summary("- Utah's latest game isn't in every source yet; waiting for the later run."); return "waiting"
    lineup_auto.build()
    d = build()
    a = brief_auto.run()
    summary(f"- Brief: {a['used']}" + (f" (checks: {a['attempts']})" if a.get("attempts") else "") + (f" error: {a['error']}" if a.get("error") else ""))
    if a["used"] != "claude" and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_FEDERATION_RULE_ID")):
        summary("- **Warning:** the Claude-written brief wasn't used today (see above); the page has the template brief.")
    d = build()
    bad = [c for c in d["checks"] if not c["ok"]]
    for c in bad: summary(f"- Check not passed: **{c['check']}**: {c['detail'][:200]}")
    hard = [c for c in bad if c["check"] in HARD]
    if hard:
        if not final:
            summary("- Blocking check failed on the early run; the later run will try again."); return "waiting"
        summary("- Blocking check failed: not publishing (yesterday's page stays up)."); return "failed"
    site = os.path.join(REPO, "site"); shutil.rmtree(site, ignore_errors=True); os.makedirs(site)
    shutil.copy(P("output", "mammoth_dashboard.html"), os.path.join(site, "index.html"))
    write_text(os.path.join(site, ".nojekyll"), "")
    import datetime as _dt
    write_text(P("history", "last_run.json"), json.dumps({"published_utc": _dt.datetime.utcnow().isoformat(timespec="seconds"), "record": d["team"]["rec"],
                                                          "checks_passed": sum(c["ok"] for c in d["checks"]), "checks": len(d["checks"]), "brief": a["used"]}))
    pl = d.get("playersLeague") or []
    summary(f"- Data size: {len(pl)} NHL players rated ({sum(1 for p in pl if p.get('g') == 'G')} goalies), "
            f"{len(d.get('standings') or [])} teams in standings, {len((d.get('power') or {}).get('rows') or [])} in power rankings")
    if len(pl) < 500:
        summary("- **Warning:** fewer than 500 players rated; MoneyPuck's files look incomplete.")
    summary(f"- Published: {d['team']['rec']}, {sum(c['ok'] for c in d['checks'])}/{len(d['checks'])} checks passed.")
    return "published"


if __name__ == "__main__":
    try:
        st = main()
        o = os.environ.get("GITHUB_OUTPUT")
        if o:
            with open(o, "a") as f: f.write(f"status={st}\n")
        sys.exit(1 if st == "failed" else 0)
    except Exception as e:
        summary(f"- **Run failed:** {str(e)[:1500]}")
        raise
