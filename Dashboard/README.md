# Utah Mammoth Season Dashboard: runbook

The page is rebuilt from scratch every update by `build.py`. Nothing in `output/` is edited by hand.
Model/design details and the change log are in HANDOFF.md.

## Folder map
| Folder / file | What it is | Touch it? |
|---|---|---|
| `build.py`, `template.html` | The weekly build and the page layout | Run `python3 build.py` |
| `config/` | Hand-edited: `brief.md` (weekly write-up), `lineup.json`, `contracts.json` (Utah cap hits, fallback), `roster.json` (active roster) | Yes, weekly as needed |
| `inputs/contracts/` | League cap hits + contract averages pasted from Spotrac (2026-27) | After trades/signings |
| `inputs/moneypuck/` | MoneyPuck season files (skaters, goalies, lines, teams, shots_2026.csv) | Replace weekly |
| `inputs/moneypuck_games/` | MoneyPuck game-by-game files (skaters, goalies, lines; names don't matter) | Replace weekly |
| `inputs/nhl/` | NHL API: standings, schedules, league schedule, box scores | Refreshed by Claude |
| `inputs/history/`, `inputs/allPlayersLookup.csv` | MoneyPuck 2008-2024 history, birth dates | One-time |
| `inputs/bio_supplement.csv` | NHL API birth dates for players missing from MoneyPuck's lookup (add rows when new players debut) | As needed |
| `engine/` | Model code used by the build | No |
| `params/` | Fitted model parameters | No (written by calibration) |
| `calibration/` | Refit scripts; `experiments/` = backtests behind each design decision | Only after a new history season |
| `history/` | `snapshots.json` (trend history: never delete) + per-games-played MoneyPuck archive | No |
| `output/` | The built page and data.json | No |
| `archive/` | Old backups and legacy files | No |
| `../Source Data/` | 2025-26 MoneyPuck season files (used as last season) | One-time |

## Each update (Claude does this)
1. **Standings:** web_fetch `https://api-web.nhle.com/v1/standings/now` (saved to a tool-results file) -> `inputs/nhl/standings.txt`.
2. **Utah schedule:** for games beyond the season file, fetch `https://api-web.nhle.com/v1/club-schedule/UTA/month/YYYY-MM` -> `inputs/nhl/schedule_YYYY-MM.txt`.
3. **League schedule + results:** fetch `https://api.nhle.com/stats/rest/en/game?cayenneExp=season=20262027%20and%20gameType=2&start=N&limit=250` for N = 0, 250, 500, 750, 1000, 1100; rebuild `inputs/nhl/league_schedule.json` (snippet in HANDOFF.md). The build checks completed games against the standings.
4. **Box scores:** each new Utah game: `https://api-web.nhle.com/v1/gamecenter/<gameId>/boxscore` -> compact JSON in `inputs/nhl/boxscores/<gameId>.json` (same shape as 2026020013.json).
5. **MoneyPuck (weekly from Connor, same day):** season files -> `inputs/moneypuck/`; game-by-game files -> `inputs/moneypuck_games/`; `shots_2026.csv` -> `inputs/moneypuck/`.
6. **Config:** write `config/brief.md`; update `config/lineup.json`, `config/roster.json` (moves/call-ups) and `config/contracts.json` (new cap hits).
7. `python3 build.py` (checks print at the end; all should pass).
8. Publish `output/mammoth_dashboard.html` to the `mammoth-season-dashboard` artifact.

## After the season ends (once a year)
Add the 2026-27 season files to history, then run, in order: `python3 calibration/validate.py`, `python3 calibration/fit_impact.py`, `python3 calibration/fit_talent.py`, `python3 calibration/validate_roster.py`. The history cache rebuilds itself (it lives in `~/.mammoth_cache`). The interval/weighting/power backtests in `calibration/experiments/` need MoneyPuck's game-by-game history files (multi-GB, not kept here).
