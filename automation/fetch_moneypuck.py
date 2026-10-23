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


def static():
    """Last season (build reads ../Source Data) and 2008-2024 history (build + history cache). Skipped when present."""
    for f in ("skaters", "goalies", "lines", "teams"):
        path = os.path.join(SRC, f"{f}.csv")
        if not os.path.exists(path):
            t = get(f"{MP}/seasonSummary/{SEASON - 1}/regular/{f}.csv")
            _check_csv(t, ["season", "situation"], f"last season {f}")
            write_text(path, t)
            log("downloaded last season", f)
    for f in ("skaters", "goalies", "lines", "teams"):
        path = P("inputs", "history", "moneypuck", f"{f}_2008_to_2024.csv")
        if not os.path.exists(path):
            t = unzip_single_csv(get(f"{PT}/historicalOneRowPerSeason/{f}_2008_to_2024.zip", binary=True, timeout=600))
            _check_csv(t, ["season", "situation"], f"history {f}", 1000)
            write_text(path, t)
            log("downloaded history", f)


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
