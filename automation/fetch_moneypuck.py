"""Download MoneyPuck's public data files (data.htm lists them; free for non-commercial use with credit).
Current season files every run; last season and 2008-2024 history only when missing (cached between runs)."""
import csv, io, os
from common import P, SRC, SEASON, get, unzip_single_csv, write_text, log

MP = "https://moneypuck.com/moneypuck/playerData"
PT = "https://peter-tanner.com/moneypuck/downloads"


def _check_csv(text, need_cols, what, min_rows=10):
    rdr = csv.reader(io.StringIO(text))
    head = next(rdr, [])
    miss = [c for c in need_cols if c not in head]
    if miss:
        raise RuntimeError(f"{what}: unexpected file (missing columns {miss})")
    n = sum(1 for _ in rdr)
    if n < min_rows:
        raise RuntimeError(f"{what}: only {n} rows")
    return n


def _players(text, col="playerId"):
    return {r[col] for r in csv.DictReader(io.StringIO(text))}


def current(tries=4, wait_s=600):
    """MoneyPuck rewrites its files nightly; a download caught mid-rewrite can be partial but still valid CSV
    (seen 2026-10-23: a season skater file with 71 players). So cross-check the files against each other and
    retry; if they never agree, stop (the live page stays as it was)."""
    import time
    for i in range(tries):
        try:
            return _current_once()
        except RuntimeError as e:
            if i == tries - 1:
                raise
            log(f"MoneyPuck files incomplete ({e}); waiting {wait_s // 60} min and retrying ({i + 1}/{tries - 1})")
            time.sleep(wait_s)


def _current_once():
    out = {}
    texts = {}
    for f in ("skaters", "goalies", "lines", "teams"):
        t = get(f"{MP}/seasonSummary/{SEASON}/regular/{f}.csv")
        out[f] = _check_csv(t, ["season", "situation", "team"], f"season {f}")
        texts[f] = t
    for f in ("skaters", "goalies", "lines"):
        t = unzip_single_csv(get(f"{PT}/seasonPlayersSummary/{f}/{SEASON}.zip", binary=True, timeout=300))
        out[f + "_games"] = _check_csv(t, ["gameId", "situation", "playerTeam"], f"game-by-game {f}")
        texts[f + "_games"] = t
    # consistency: the season files must cover (nearly) everyone in the game-by-game files, and all 32 teams
    for f in ("skaters", "goalies"):
        ps, pg = _players(texts[f]), {r["playerId"] for r in csv.DictReader(io.StringIO(texts[f + "_games"])) if r.get("season") == str(SEASON)}
        if pg and len(ps & pg) < 0.97 * len(pg):
            raise RuntimeError(f"season {f} file has {len(ps & pg)} of the {len(pg)} players in the game-by-game file")
    teams = {r["team"] for r in csv.DictReader(io.StringIO(texts["teams"]))}
    if len(teams) < 32:
        raise RuntimeError(f"season teams file has {len(teams)} teams")
    for f in ("skaters", "goalies", "lines", "teams"):
        write_text(P("inputs", "moneypuck", f"{f}.csv"), texts[f])
    for f in ("skaters", "goalies", "lines"):
        write_text(P("inputs", "moneypuck_games", f"{f}_games.csv"), texts[f + "_games"])
    t = unzip_single_csv(get(f"{PT}/shots_{SEASON}.zip", binary=True, timeout=300))
    out["shots"] = _check_csv(t, ["game_id", "xGoal", "teamCode", "event"], "shots")
    write_text(P("inputs", "moneypuck", f"shots_{SEASON}.csv"), t)
    t = get(f"{MP}/playerBios/allPlayersLookup.csv")
    out["lookup"] = _check_csv(t, ["playerId", "birthDate"], "player lookup", 1000)
    write_text(P("inputs", "allPlayersLookup.csv"), t)
    log("MoneyPuck current season:", out)
    return out


def _distinct(path, col="playerId"):
    with open(path, encoding="utf-8") as fh:
        return len({r.get(col) for r in csv.DictReader(fh)})


# minimum distinct players/teams a COMPLETE file has (full seasons are far above these)
_MIN = {"skaters": 750, "goalies": 75, "lines": 2400, "teams": 32}


def static():
    """Last season (build reads ../Source Data) and 2008-2024 history (build + history cache). Downloaded when
    missing OR incomplete: these are cached between runs, so a partial download must never be kept."""
    redo = False
    for f in ("skaters", "goalies", "lines", "teams"):
        path = os.path.join(SRC, f"{f}.csv")
        col = "team" if f == "teams" else ("lineId" if f == "lines" else "playerId")
        ok = os.path.exists(path) and _distinct(path, col) >= _MIN[f]
        for attempt in range(3):
            if ok:
                break
            t = get(f"{MP}/seasonSummary/{SEASON - 1}/regular/{f}.csv")
            _check_csv(t, ["season", "situation"], f"last season {f}")
            write_text(path, t); redo = True
            ok = _distinct(path, col) >= _MIN[f]
            log(f"downloaded last season {f}: {_distinct(path, col)} distinct {col}")
        if not ok:
            raise RuntimeError(f"last season {f} file incomplete after 3 downloads")
    for f in ("skaters", "goalies", "lines", "teams"):
        path = P("inputs", "history", "moneypuck", f"{f}_2008_to_2024.csv")
        col = "team" if f == "teams" else ("lineId" if f == "lines" else "playerId")
        need = {"skaters": 2600, "goalies": 290, "lines": 100000, "teams": 32}[f]
        if os.path.exists(path) and _distinct(path, col) >= need:
            continue
        t = unzip_single_csv(get(f"{PT}/historicalOneRowPerSeason/{f}_2008_to_2024.zip", binary=True, timeout=600))
        _check_csv(t, ["season", "situation"], f"history {f}", 1000)
        write_text(path, t); redo = True
        log("downloaded history", f)
    if redo:   # the model's history cache is built from these files; rebuild it
        cache = os.path.join(os.environ.get("MAMMOTH_CACHE", os.path.join(os.path.expanduser("~"), ".mammoth_cache")), "hist_cache.pkl")
        if os.path.exists(cache):
            os.remove(cache); log("history cache cleared (rebuilt from fresh files)")


def sizes():
    """Distinct players/teams per input file, for the run summary."""
    out = {}
    for label, path, col in (("2026 skaters", P("inputs", "moneypuck", "skaters.csv"), "playerId"),
                             ("2026 goalies", P("inputs", "moneypuck", "goalies.csv"), "playerId"),
                             ("2026 game-by-game skaters", P("inputs", "moneypuck_games", "skaters_games.csv"), "playerId"),
                             ("2025-26 skaters", os.path.join(SRC, "skaters.csv"), "playerId"),
                             ("2025-26 goalies", os.path.join(SRC, "goalies.csv"), "playerId"),
                             ("2008-24 skaters", P("inputs", "history", "moneypuck", "skaters_2008_to_2024.csv"), "playerId")):
        out[label] = _distinct(path, col) if os.path.exists(path) else None
    return out


def game_ids():
    """Game ids (e.g. 2026020140) present in the game-by-game skater file and the shot file."""
    gg, sh = set(), set()
    with open(P("inputs", "moneypuck_games", "skaters_games.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            gg.add(int(r["gameId"]))
    with open(P("inputs", "moneypuck", f"shots_{SEASON}.csv"), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sh.add(SEASON * 1000000 + int(float(r["game_id"])))
    return gg, sh


if __name__ == "__main__":
    static(); current()
