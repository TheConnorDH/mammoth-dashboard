# Handoff: Utah Mammoth 2026-27 Season Dashboard

Read this first in any new session. Everything needed lives in this folder; no chat history is required.
The runbook (weekly steps, folder map) is README.md. This file is the model/design record: current state first, then the dated change log.

## Folder layout (reorganized Oct 3 2026)
- `build.py` + `template.html`: the weekly build (run `python3 build.py`; output in `output/`).
- `engine/`: model code used by the build (impact, league, power, seasonsim, shotmap, style, models, gaa).
- `calibration/`: refit scripts, run only when a new history season is added (fit_impact, fit_talent, validate, validate_roster). `calibration/experiments/`: the one-off backtests behind each design decision (records; several need MoneyPuck game-level history files that are not kept here).
- `config/`: hand-edited inputs (brief.md, lineup.json, contracts.json, roster.json).
- `params/`: fitted model parameters written by calibration (never hand-edit).
- `inputs/`, `history/` (snapshots.json + per-GP MoneyPuck archive), `output/`.
- `archive/`: old backups and legacy files, kept for reference only.

## Goal
A season-long, **objective** analysis and tracking board for the Utah Mammoth (Connor's request: no fan opinions or personal "calls" on the board; evaluate strengths and weaknesses purely from data). Branded in Mammoth colors: Rock Black #000000, Mountain Blue #6CACE3, Salt White #FFFFFF. No logos.

## If this session can publish hosted pages
1. `python3 build.py` (rebuilds `output/mammoth_dashboard.html` from the inputs).
2. Publish `output/mammoth_dashboard.html` as a hosted page. The template is a full HTML document; if the publishing tool wants body-only content, strip the outer `<html>/<head>/<body>` tags but keep the Chart.js `<script>` tag, the `<style>` block and all inline `<script>` blocks (theme, data, app).
3. Give Connor the link and reuse the same page on every update.

## Update routine
See README.md. Summary: refresh NHL standings, schedule and box scores into `inputs/nhl/`; Connor drops the four MoneyPuck 2026-27 season-summary CSVs (skaters, goalies, lines, teams) into `inputs/moneypuck/`; edit `config/brief.md` (neutral, data-led weekly write-up) and `config/lineup.json` (current deployment); run `build.py`; republish. `history/snapshots.json` holds the trend history; never delete it.

## What the board contains
Record/projection hero; auto-generated Executive Summary (rule-based insight cards built in build.py: outlook, process vs. results, top strength/weakness, biggest rank movers, top/struggling performer, best/worst value, goaltending, with a confidence level by games played); weekly brief; Strengths & Weaknesses (every directional metric auto-ranked league-wide, plus last season's bottom-eight metrics tracked automatically); standings (NHL, 3-2-1-0, Blueprint seeding); results, next 10, rivals, countdowns; team profile with deserve-to-win and luck meter; players (this season's MoneyPuck shot-model stats beside 2025-26 percentiles, ice-tilt and luck charts); rankings (Game Score converted to position percentiles so F/D/G share one axis; per-game best/worst three; cumulative race; performance vs. cap hit); deployment and line results; goaltending (GSAx); trends; method notes.

## The 95% standard (Connor's requirement)
Every claim on the board must carry a 95% interval or a significance label; nothing is stated as fact unless it clears 95%. Components:
- `impact.py` + `calibration/fit_impact.py`: **Player Impact**, the ranking measure since Oct 3 2026 (replaced Goals Above Average, which turned out to be ~77% driven by goals/assists). Statistical plus-minus: each player's on-ice goal differential relative to his team's average (rel_teamavg=True since Oct 3; originally on vs. off ice) in neighbouring seasons is predicted from relative xG/shot attempts (zone-start adjusted), ixG, finishing, A1/A2, takeaways, giveaways, blocks; separate F/D and 5v5/PP/PK fits; scaled to a descriptive goal scale; goalies = GSAx; penalties 0.17, faceoffs 0.01. Talent = two-season pool x T/(T+k). Intervals from measured year-to-year noise. Box-score approximation (R^2 ~0.7 F / 0.6 D) for per-game stars when no exact MoneyPuck snapshot. Out-of-sample r 0.45 vs points/60 0.35 vs old GAA 0.30. Run `python3 fit_impact.py` (~1 min) after adding a history season; writes params/impact_params.json. `gaa.py` is legacy (kept only for the comparison).
- `calibration/validate.py`: run after adding a new season of history (`inputs/history/moneypuck/`). Re-derives reconciliation, component reliability (shrinkage constants), the playmaking weight (chosen by out-of-sample prediction), team-metric reliability, and the team carry-over prior. Writes `params/model_params.json`. Takes ~5 minutes.
- `models.py`: calibrated team significance (true-score model from 18 seasons), pooled two-season player talent with 95% intervals, Poisson game model with OT calibration, Monte Carlo season simulation, empirical playoff line from `inputs/history/standings_final_*`.
- `history/mp/<gp>/`: raw MoneyPuck files archived per games-played; per-game GAA is recomputed from consecutive snapshots every build (exact single-game values when updates are one game apart).
- Model Integrity section on the page shows automated data checks each build.

- `league.py` + `calibration/validate_roster.py` (added Oct 3 2026): every NHL player valued with the same model; Utah players' league rank by position with simulated 95% rank ranges; league top-10s; roster strength for every team (top-12 F + top-6 D by ice time + goalies normalised to one season of starts). Start-of-season backtest on 486 team-seasons: roster talent r 0.51, last season's goal differential r 0.55, both together r 0.59 (adds information, doesn't replace results). Run `python3 validate_roster.py` after `calibration/fit_impact.py`.
- Linemate adjustment from MoneyPuck lines data was TESTED and REJECTED: subtracting linemate quality worsened out-of-sample prediction at every weight, including for 4,670 team changers.

- Oct 3 2026 (later): game-by-game MoneyPuck files (`inputs/moneypuck_games/`) give EXACT per-game Impact; each game uses the season's off-ice rates so games sum exactly to the season (checked each build). 95% intervals recalibrated from split halves of 2021-22..2024-25 game-level history (noise var per 60 = a/min + c, `params/interval_params.json`); cross-fitted coverage of shipped intervals ~94.5-96.8% (heaviest-minute forwards ~91%). Birth dates in `inputs/allPlayersLookup.csv`; aging curve TESTED and REJECTED (team-level test worse; survivor bias), ages shown only (`params/age_params.json` _decision). Shots files: shot-level, but no on-ice player IDs, so no RAPM from them; candidate use = shot maps. History cache now lives at ~/.mammoth_cache (scratch); the old cache copies were moved to archive/legacy/history/ (stale). The user's drive is nearly full: do not copy the multi-GB history files into this folder.

- Oct 3 2026 (latest): IMPACT vs TALENT separated. Impact = what happened in his actual minutes (goals; ~0.334 standings points per goal: params/points_params.json). Talent = per-60 rate (pooled, regressed) at a STANDARD workload (F 15.3 min, D 19.5 min, G 51.7 games; params/talent_params.json) -> league ranks and value vs contract; 'expected in his role' = talent x his minutes (used for roster strength). Baseline switched to on-ice minus TEAM AVERAGE (team sums now ~1:1 with real goal differential, roster test r .514 -> .526). Tested and rejected: separate 5v5/PP/PK talent components (worse OOS), a harder-minutes role penalty (not identifiable). Talent intervals widened by calibrated multipliers (F 1.25, D 1.18, G 1.15).

- Oct 3 2026 (display): everything shown as STANDINGS POINTS vs. average (D.ppi = 1.036 x 0.3228 = 0.334 pts per goal) plus NHL percentile at position; goals on hover. All tables sortable/filterable via a generic enhancer at the end of template.html (MutationObserver re-applies after re-renders). Talent pools last season at weight prior_w (F/D 0.5, G 0.25; split-half backtest, params/interval_params.json); talent_mult recalibrated (F 1.19, D 1.09, G 1.08; cross-fit coverage 95.0/94.5/94.9). Rank section has a 'this season vs. blended' explainer.

- Oct 3 2026 (power): POWER RANKINGS (power.py, params/power_params.json). Rating = expected rest-of-season goal differential per game -> standings points per 84 vs. average, from (1) talent of each team's current lineup (players in last 5 games, at their minutes there; talent from last season only), (2) GD and (3) xGD so far (goalie rows, empty-net excluded), (4) last season's GD; weights interpolated by games played (GD/xGD weights scaled by gp/4 before ~4 GP). Backtest: calibration/experiments/pr_*.py over 8 seasons x 5 checkpoints; blend r .60/.65/.68/.70/.65 vs GD alone .20/.44/.59/.65/.62; rest-of-season 95% coverage 94.2-95.6% per checkpoint. The scratch validation scripts now live in calibration/experiments/ (they read MoneyPuck game-level history files from the uploads folder, which aren't kept here).

- Oct 3 2026 (odds): WIN PROBABILITY + HOME ICE + LEAGUE SIMULATION. Home ice: league-wide 0.24 regulation goals/game, home win 54.1% (2014-15..2025-26 excl. 2020-21); team-specific home edges not reliable (yoy r 0.06) -> one value for all arenas (params/hia_params.json). Win model (params/winprob_params.json): P(home win) = logistic(0.184 + 0.764*rating diff in goals/game), P(OT) = logistic(-1.208 - 0.113|diff|), P(home win|OT) = logistic(0.111 + 0.317 diff); 9,680 held-out games, calibrated by decile within ~1.5 pts. Power table shows win % vs. an average team on neutral ice = logistic(0.764*rating) plus a matchup calculator. seasonsim.py simulates every remaining game (league schedule in inputs/nhl/league_schedule.json, built from the NHL stats API game endpoint; team id map in build history) with the real playoff format; backtest params/sim_backtest.json: final-points RMSE beats pace and average-rest at every checkpoint; 95% coverage 94.6-96.0% with sd multipliers power_params.sim_sd_mult. Hero projection and playoff odds now come from this league simulation. Utah next-10 shows win odds and expected points. Strength-of-schedule adjustment TESTED and REJECTED (inconsistent). Value vs. contract now uses EXPECTED IMPACT IN HIS ROLE (talent x actual minutes). Shot maps (shotmap.py) from shots_2026.csv. Validation scripts in calibration/experiments/.
- League schedule JSON rebuild snippet: read each saved stats-API page (JSON after the header lines), map homeTeamId/visitingTeamId with {1:'NJD',2:'NYI',3:'NYR',4:'PHI',5:'PIT',6:'BOS',7:'BUF',8:'MTL',9:'OTT',10:'TOR',12:'CAR',13:'FLA',14:'TBL',15:'WSH',16:'CHI',17:'DET',18:'NSH',19:'STL',20:'CGY',21:'COL',22:'EDM',23:'VAN',24:'ANA',25:'DAL',26:'LAK',28:'SJS',29:'CBJ',30:'MIN',52:'WPG',54:'VGK',55:'SEA',68:'UTA'}, write {'games':[{'id','date','home','away','state','hs','as','period'}]} (state 7 = final; period > 3 = OT/SO).

- Oct 3 2026 (weighting): talent pools up to THREE previous seasons at backtested weights (params/talent_weights.json: F .7/.4/.3 shrink x0.5; D .6/.4/.4 x0.4; G .4/.4/.2 x0.4), chosen in two stages on 8 seasons x 5 in-season checkpoints (calibration/experiments/tw_opt2.py: weights by correlation, shrinkage by error so levels are calibrated); LOSO rest-of-season r F .603->.628, D .589->.618, G .210->.218, calibration slopes ~1.0 (old 1.3/1.4/2.2). build.py loads 2024-25 and 2023-24 from the history cache (fit_impact.load_all). Within-season recency weighting: no gain. Aging re-tested: helps player-level (survivor-biased) and power slightly, but roster test drops .571 -> .497 -> NOT used. Power: lineup r up to .48-.51; blend r .623/.662/.685/.696/.647; 2-seasons-ago GD and last-10 form tested, not used. Everything downstream recalibrated (interval talent_mult F 1.52 D 1.42 G 1.15; power true_var; winprob; sim_sd_mult [1.6,1.03,1.0,0.97,1.0]; roster test r .571 vs last-season GD .548, both .622; newcomer = no minutes in 3 prior seasons).

- Oct 3 2026 (priors/aging/goalies): EXPERIENCE PRIOR adopted (talent_weights.json prior_model; F prior = -0.2 + 0.15*ln(1+weighted prior min/1000), D x0.53; goalies keep newcomer prior): roster test r .571 -> .596 (both .634), player test F .630 -> .632. Aging re-tested with a survivor-free team harness (calibration/experiments/team_harness.py, aging_team*.py): every normal curve hurts; data prefers rating older rostered players UP (selection), so no aging. Goalie ceiling r~0.39 for rest-of-season prediction; model 0.22; danger-split GSAx and a 5-season look-back don't help. Power lineup r now .53/.51/.49/.50/.53. CSS wrap fixes at end of <style>.

- Oct 3 2026 (age, split scope): age adjustment ON for INDIVIDUAL talent only (params/age_params.json curve: F +0.0203/60 per yr under 27, -0.0164 over 27; D +0.011/-0.0037), validated in-season (F r .634 -> .645). Team strength (power.compute ages=None; league.rosters uses talent84_team) excludes age because team tests get worse. Player's own multi-season trend tested: no value (calibration/experiments/trend_test.py). Talent table adds P(Utah's best skater), P(better than next), and a head-to-head matrix for the top 8 skaters (20k simulations of talent uncertainty).

- Oct 3 2026 (Utah ranking display): Talent tab = one scale for all positions, Utah rank + position rank (F1, D1...) + TIERS (new tier when the tier's top player beats this one in >=75% of 20k talent draws) + a range chart (estimate, 50% and 95% bars). Head-to-head matrix moved into a collapsible. Age adjustment is applied to every NHL player (league ranks included). CSS: td nowrap by default; prose and .wrap cells wrap; wide tables scroll inside cards.

## Known limitations / next steps
- DONE: Goals Above Average replaces Game Score for rankings (box-score Game Score only for per-game fallback and the production race). Player values are on-ice based (no teammate/opponent separation; that needs play-by-play RAPM).
- Interval coverage has not been directly backtested on in-season splits (no game-level history available); widths reflect event randomness for performance and measured talent spread for talent.
- Not done (data not available here): league-wide contract value (needs every NHL cap hit), age curves (season files have no birth dates).
- Shot maps need MoneyPuck's shots_2026 file (coordinates), dropped into `inputs/moneypuck/`.
- `config/calls.json` is legacy and no longer rendered.
- Browser gotcha: never declare top-level JS variables named `top`, `name`, `status`, `parent`, etc. (window globals). That bug blanked the page once.

## Redesign backlog (Connor's notes, Oct 3 2026) -- BUILT Oct 3 (see below)
1. League + team explorer: Impact, Talent, tiers/league bands and the range-bar chart for ANY team or all players (filters: team, position, age; sortable). League caliber bands by percentile (e.g., elite top 10%, first-line/top-pair, middle, depth, below) separate from Utah's within-roster tiers.
2. Tabs instead of one long page: Overview | Team (power, odds, projections, standings, strengths/weaknesses, shot maps, schedule) | Utah Players (impact, talent tiers + bars, value, game stars, deployment) | League Explorer | Method & Integrity.
3. Cut or merge low-value/redundant parts: old Players section (2025-26 percentiles, tilt and luck-ledger charts), Impact race, Roster-strength table (fold into Power Rankings), deserved-points/luck meter overlap, preseason projection now inconsistent with the league sim, recipe/driver cards (move to Method), rarely used tables; keep only what answers a question.
4. Confidence display rules (95% is a target, not a label for everything): 95% only for verdict words ("clearly above/below"); ranges as a likely (50%) bar + 90% whiskers; rank ranges as likely (80%); projections headline 80% range with 95% on hover; no intervals on probabilities themselves (win %, playoff %); hide verdict pills when the sample is too small instead of showing "not clear" everywhere.

## Redesign built (Oct 3 2026, template.html v8)
- Tabs: Overview | Team | Utah Players | League Explorer | Method (lazy per-tab chart init via inits[]; hash navigation). Dark mode toggle ([data-theme], localStorage, no reload needed). Old single-page template kept as template_v7_tabless_backup.html.
- Full active Utah roster from config/roster.json (incl. players with no games: valued from earlier seasons, flagged noGames; excluded from team roster strength).
- League Explorer: playersLeague in data.json (every player, same model): filters team/conf/div/pos/age/band/search; league bands by talent percentile (Elite >=90, Top of lineup >=67, Middle >=33, Depth >=10, Fringe); single-team talent chart with within-team tiers (75% rule, normal approx).
- Team tab: power rankings with conf/div filter, matchup calculator, conference/division comparison (all or top N), roster vs top-8, season sim, standings, strengths/weaknesses, shot maps.
- Utah Players: roster table (Utah rank, tier, pos rank, Impact with 90% range, talent range bars, band, style tags, role, cap hit), talent chart, Impact breakdown, value vs contract (role and raw talent: rankFitRaw/vsRaw), game stars, deployment, goalies, head-to-head.
- Style tags: style.py (descriptive; pooled 3 seasons; percentile thresholds).
- Confidence display: verdict words at 95% (team "leaning" ~85%), player ranges 50% + 90%, rank ranges 80% (r10/r90), projections 80% (95% on hover), no intervals on probabilities, tiers 75%.
- Removed: old players table, tilt/luck-ledger charts, Impact race, team profile tiles, luck meter/deserved card, rivals, trends chart, roster-strength table (folded into Team tab gap card). Unused keys dropped from data.json.
- Lamoureux has no cap hit in config/contracts.json (add when known).
- Oct 3 2026 (team styles): engine/team_style.py tags each team's style from its numbers relative to the league (pace, possession, shot quality/volume, defense, slot protection, rebounds, hits, blocks, takeaways, discipline, penalties drawn, faceoffs, PP/PK, finishing, goaltending, roster age, star concentration, depth). This season pooled with last season at half weight; flagged "mostly last season" under 15 GP. Shown in the power table, a Utah team-style card (Team tab) and the Explorer team view. Descriptive only.
- Oct 3 2026 (lineups): engine/lineup.py builds each team's best lineup by talent with real positions (>=2 C in the top 6 F, 4 C in the 12; centers can play wing; L/R wingers interchangeable; best 4 D then 3rd pair). Team tab "Lineup Strength: Top vs. Depth" (table + scatter, conf/div filter, Utah best-lineup card). Team style now also returns per-feature league ranks (Utah "Full style profile" in the Team tab). One-off analyses NOT added to the board (by design): young-core peak projection, Edmonton/Doan/Stenlund deep-dives, Cup-style comparison.

### 2026-10-03 — Team tab selectable for any team
- Team tab now opens with a **Team Breakdown** driven by `select#tm-sel` (default UTA); clicking a team in Power Rankings calls `pickTeam()`.
- Per-team sections: header tiles (power row + standings), style tags + full profile (`styleRanks`), roster vs top-8 (`LG.rosters`), best lineup (`D.lineups`), sim histogram (`power.simAll`), points chart/game log/next-10 odds computed client-side from `power.sched` + `power.winprob`, strengths & weaknesses (`swAll`), shot maps (`shotsAll` + league grids in `shots`).
- League-wide sections (Power, Conferences/Divisions, Lineup Strength, Standings) follow below. Old Utah-only cards (roster-gap, ln-uta) folded into the breakdown. Hero/Overview stays Utah.
- Verified: all 32 teams render without undefined/NaN; Utah next-game odds match the build's `next10` exactly.

### 2026-10-04 — Filter-aware ranks
Rule: renumber only when a filter defines a real peer group; otherwise the full-list rank stays with the row. NHL rank always stays visible.
- Power Rankings / Lineup Strength: conference or division filter → `#` = rank within the group, NHL rank (and likely range / move) underneath; lineup metric cells show group ranks with NHL rank on hover.
- League Explorer: team, conference, division, position and age filters define the peer group and renumber; band, name search and show-N only hide rows; header sorting never renumbers. Caliber column labeled "NHL F/D/G rank".
- Unchanged by design: team-page ranks (S&W, style profile, opponent rank, roster vs top-8) are always NHL ranks; standings views carry their own official ranks; Utah roster rank is within-Utah.

### 2026-10-04 — Tab restructure + Roster for any team (v11)
- Tabs: Overview (Utah) · League (power, matchup calc, conferences/divisions, lineup strength, standings) · Team · Roster · Player Finder · How It Works. Hash ids: overview, league, team, roster, finder, method; `#players`/`#explorer` alias; `#team/VGK` and `#roster/VGK` deep-link a team.
- One selected team (`TM`) shared by Team and Roster (`setTeam`, `teamOptions`, `renderers`, `shown`, `refresh`). Panes render only when visible and stale, so no Chart.js in hidden panes.
- Roster is generic: `rosterRows(x)` (Utah from `D.rank`, others from `playersLeague`), client-side team rank / position rank / 75% tiers (goalies never become a tier's reference player because their sd is ~3x skaters'), forest, impact parts (build now exports `pp`, `pp25`, `imp25`, `vd` per league player), head-to-head. Utah-only: value vs contract, game by game, deployment, goalies.
- Player Finder: single-team card removed (Roster replaces it); team codes link to Roster; reset button.
- Team names link to the Team page from power, lineup, standings, conferences, next-10 and results tables.
- Audit fixes: empty-roster teams (pre-first-game), shootout results (period 5 = SO), consistent unit labels ("pts / 84 GP, standard minutes" vs "his minutes"), "NHL caliber" naming, NHL rank wording, 8-color tier palette, theme toggle keeps filter values, duplicate-last-name chart labels, empty parts chart message.
- Verified: client-side Utah ranks/tiers match the build exactly; all 32 teams render cleanly on Team and Roster; independent audit found no remaining critical issues.

### 2026-10-04 — Update after Game 2 (4-1 at CBJ)
- Season files (skaters, goalies, teams, shots) through Oct 3, except three late West games MoneyPuck hadn't posted. MoneyPuck's game-by-game download and season lines file were unchanged (game-by-game stops at game 2026020021, Oct 2): re-downloaded under new names, same checksums.
- Utah Game 2 player Impact computed exactly from consecutive season snapshots (history/mp/1 -> 2).
- NEW: power.compute(season_totals=...) takes GP / GD / xGD from the season teams file when it has more games than the game-by-game file (includes empty-net goals, a small difference). The lineup (last 5 games) still comes from the game files. Rows carry resultsFrom/lineupGames.
- Per-game check now passes when lagging games are covered exactly by snapshot differencing.
- Box score 2026020027 logged (from boxscore + landing; the plain boxscore URL returned a cached in-progress copy, so add ?final=1).
- History file inventory (verified by headers/seasons): season-level 2008-09..2024-25 (skaters/goalies/lines/teams_2008_to_2024.csv); 2025-26 season-level in Source Data/; game-level 2008-09..2024-25 = uploads "2008_to_2024 (4)" goalies, "(5)" lines, "(6)" skaters; 2025-26 game-level in Source Data/Raw Downloads/2025 (1-3).zip; shots 2007-2025 + shots_2025.zip.

### 2026-10-04 — Per-game values frozen (bug fix)
- BUG: game-by-game Impact used the player's SEASON off-ice rates and the team's season averages (to make games sum to the season). So every new game silently changed earlier games' values (Game 1's third star flipped Trocheck -> Stenlund after Game 2).
- FIX (build.py per-game block): (1) consecutive season snapshots one Utah game apart give game k = Impact(through k) - Impact(through k-1): fixed forever (archives never change) and telescopes to the season total exactly; (2) otherwise game-by-game rows, computed once and frozen in history/pergame_frozen.json keyed by gameId + md5 of params/impact_params.json; (3) otherwise box score. Game 1 restored to its original values (Vejmelka, Carcone, Trocheck / Marino, Hayton, But). Check: summed game values vs season totals, gap 0.00.
- Never delete history/mp/<gp>/ archives: they are what keeps past games fixed.

### 2026-10-04 — Per-game method revised (supersedes the entry above)
- Snapshot differencing only works if a season file is captured after every Utah game, so it can't be the primary method with weekly updates.
- Now: (1) game-by-game rows, full Impact model on that game alone, each player vs. his team in that same game (game's own off-ice rates; no season override) and last season's league means as the fixed scale. A pure function of the game, so it never changes and doesn't depend on update timing. (2) Snapshot differencing only as a PROVISIONAL fallback when the game-by-game download lacks the game and snapshots are exactly one Utah game apart; replaced by (1) when MoneyPuck posts the game. (3) Box score, provisional.
- For Game 1 the two methods agree exactly (0.00-0.01 goals per player). Summed game values vs. season totals differ slightly by design (game baseline vs season baseline); check tolerance 0.25 x sqrt(games) goals.
- history/pergame_frozen.json removed (no longer needed). PG_DIAG=1 python3 build.py prints game-vs-snapshot comparisons.

### 2026-10-04 — Rule: game-level outputs only from game-level data (Connor)
- Per-game Impact/stars come ONLY from MoneyPuck game-by-game rows. No snapshot-differencing or box-score fallbacks: a game without game data shows "Waiting for MoneyPuck's game-by-game data" (perGame[].pending = true) on Overview and Roster. Snapshot differencing kept only as a diagnostic (PG_DIAG=1). impact.box_impact is no longer used for display.
- Box scores are still logged (results, goals/assists text, goalie SV%, integrity checks). Season-level outputs (talent, season Impact, power results via season teams file, projections) update from season files as before.
- File identification: game-by-game files are detected by header (lineId -> lines; ",shifts," -> skaters; ",ongoal," -> goalies), never by name; season files are copied to fixed names after checking contents/checksums.

### 2026-10-04 — Data inventory + birth-date supplement
- Verified on hand: season-level skaters/goalies/lines/teams 2008-09..2026-27; game-level skaters/goalies/lines 2008-09..2026-27 (2026-27 through game 21); shots 2007-08..2026-27; bio lookup (MoneyPuck allPlayersLookup.csv, 3,400 players).
- Gap: 28 current-season players (mostly 2025-26 draftees/rookies) had no birth date -> no age adjustment. Filled from the NHL API into inputs/bio_supplement.csv; impact.ages() reads it after the lookup. All current players now have ages. Historical gaps remain (77 skaters 2008-25, 36 in 2025-26, 18 goalies), affecting only past calibration fits, not displayed values.

### 2026-10-04 — Team tiers
- power rows get "tier": walk teams by rating; a new tier starts when the tier's top team beats this team with >= 75% probability, using each team's true-strength sd (sd_pts, ~8.5 pts early season). Same rule as player tiers; league-wide (filters don't change tiers). Shown as a T pill in the power table, colored bars in the power chart, and on the hero / Team page power tile. Note on page: boundaries compare with the tier's top team, so neighbors across a boundary can be nearly even.

### 2026-10-04 (later) — Full MoneyPuck refresh through Oct 3
- All 8 files new (season skaters/goalies/lines/teams with hashed names, game-by-game "2026 (6/7/8)", shots_2026 (2)); identified by headers. Game files saved as inputs/moneypuck_games/{skaters,goalies,lines}_games.csv.
- Game 2 per-game values now from game data (matched the provisional values within 0.01). Utah power 11th, Tier 2 (+7.1): lineup piece now includes Cossa's start (newcomer goalie prior) and other teams' Oct 3 games entered.

### 2026-10-04 — Roster tab extras for every team
- build.py "teamExtra" (all non-Utah teams): perGame (latest 10 games with MoneyPuck game data; full Impact per game per team; stat lines from game rows), lastLines (last game's 4 lines / 3 pairs from 5v5 game-lines ice time, greedy no-repeat; starting goalie by ice time), lines (season 5v5, top 8 lines + 5 pairs), goalies (season file: GP, SV%, GSAx, 2025-26). ~100 KB now.
- Template: only Value vs. Contract is Utah-only (#ro-uta); teamExtras(x) renders Game by Game / Deployment / Goaltending for any team (Utah keeps staff lineup card and box-score starts).
- Utah server tiers (utaTier) now use the page's rule exactly (normal approx, 75%, goalies never lead, ties by name); client and server match 25/25.

### 2026-10-04 — League-wide salaries and market pay line
- inputs/contracts/caphit_2026-27_spotrac.csv (784) and avg_2026-27_spotrac.csv (785; adds Hellebuyck) pasted from Spotrac rankings. engine/contracts.py loads + matches to MoneyPuck ids (name aliases, team, position tie-break, fuzzy same-team spelling; NAMEFIX for Zuccarello). 653/653 players who have played are matched; Utah config contracts fill gaps (Lamoureux, Tanev). Utah cap hits matched Spotrac exactly.
- Cap hit is the value input. Contract average is used only to flag entry-level deals (Spotrac's ELC average includes potential performance bonuses). ELC = bonus pattern, or age <= 24.5 with cap <= $1.0M.
- Market line (replaces Utah-only line): talent84 (and tstd for raw) = a + b x cap + c x ELC, least squares on all skaters who have played. 10-fold CV on 605 skaters chose linear + ELC over log(cap), quadratic and F/D-specific lines. Current: ~0.42 standings points per $1M; ELC deals deliver ~1.3 points more than the same cap hit on the open market; r 0.65 for non-ELC. "Expected for pay" = a + b x cap (open-market price), so ELC players show surplus and are tagged.
- Output: rank rows + playersLeague get aav/cap, elc, vs, vsLo/Hi, exp, vsRaw..., rankFit/rankFitRaw are league fits. Roster tab value section works for every team; Player Finder has a Cap hit column with vs. market. New check: cap hits matched.
- Update each week only when contracts change (trades, signings): re-paste both Spotrac views.

### 2026-10-04 — Scatter quadrants
- quadPlugin(mx, my, labels) draws dotted median lines + corner labels. Lineup Strength (top vs depth): league median team; quadrants Complete / Top-heavy / Deep, no stars / Thin, with team lists and Utah's quadrant. Value vs contract: league-median skater (cap hit and value, all NHL skaters with a cap hit) so every team uses the same lines; quadrants Paid stars / Bargains / Expensive, low output / Cheap depth; the market diagonal still decides value. Medians chosen over means (robust to outlier rosters and $10M+ contracts).

### 2026-10-04 — Player profiles, comparables, team needs & fits
- engine/player_profile.py: skill components = Impact parts pooled (current + 3 prior seasons, talent weights) and shrunk by repeatability (rate x n/(n+k), k = mean minutes x (1-r)/r; r = year-to-year per-60 correlation, 2023-24..2025-26, data profRel). Percentiles within F or D among players with 200+ weighted minutes (mid-rank ties, clipped); faceoffs ranked/shown for centers only. Usage (TOI/GP, PP/PK share of team time, OZ starts, hits/60, blocks/60, high-danger share of own shots) from this + last season (0.7). Size/handedness from bio files.
- Comparables: standardized Euclidean within F/D; skills weighted sqrt(r), usage 0.6; faceoffs only between two centers.
- engine/needs.py: team totals per component (player shrunk rate x TOI scaled to 300 skater-min/game x 84); driving play and defense from team-level 5v5 xGF/xGA rates (this + last season at 0.5) because on/off values cancel when summed. Needs/strengths by z-score (<= -0.7 / >= 0.7), weakest lineup slot, possible moves (extras outside best lineup with 10+ TOI; clearly below market). Fits screened client-side (70th pct+ in a need, more talented than the team's weakest regular F/D; filters: max cap, sellers < 35% playoff odds, ELC toggle; sort value/gain/cap).
- UI: Roster tab Player Profile section (click any name), Player Finder profile card, Team tab "Needs, Possible Moves & Fits". Labels renamed: "Takeaways vs. giveaways", "Penalty differential", "Shot creation".
- Independent audit fixed: on-ice components at team level, D faceoffs, percentile > 100, minutes scaling, need thresholds, low-minute suppression, wording.

### 2026-10-04 — Player type (archetype) + blurb
- player_profile.archetype(g, pos, prof, useP, ht, tpct): rule-based, ordered checks on skill and usage percentiles (e.g. F: play-driving star [needs talent pct 90+], offensive play driver, sniper, power forward [6'2"+] / physical scorer, net-front forward, playmaker, shutdown forward, two-way, energy, checking center, PP specialist, secondary scorer, complementary/depth; D: offensive, two-way, puck-mover, shutdown, stay-at-home, offensive-minded, steady/depth), prefixed with role by ice-time percentile (top-line/middle-six/bottom-six; top/second/third pair). Blurb = top skills (70th+), usage notes, weak spots (25th-). Only for 200+ weighted minutes. Descriptive; checked for plausibility on known players and spread across types.
- Shown: profile header + summary sentence, comparables, roster table under names, Player Finder sub-line + "player type" filter.

### 2026-10-04 — Team data alignment check + Lineup Strength fixes
- Verified: all 32 teams in power, roster (league.rosters) and lineup views; power records match standings; power lineup piece vs roster talent rank r 0.96-0.97 (same inputs: prior-season talent x ice time, no age). Lineup Strength differs by design (equal weight per slot, standard workload, age-adjusted, current + prior data, best possible lineup with C rules). Power GD excludes empty-net goals (as fitted), so DAL/DET/STL GD per game differs from standings by their EN goals.
- Fix: lineup.league no longer drops teams that haven't dressed 12 F / 6 D (COL had 11 F): missing slots filled at replacement level (league 10th percentile), row flagged "incomplete". Total now includes the starting goalie (was skaters only).
- New check "Team views agree" (teams present, records, rank correlation >= 0.8).
- Known design effect: the "at least 2 C in top six / 4 in twelve" rule uses MoneyPuck position labels, so teams with few listed centers (e.g. MIN) get a weaker C promoted into the top six in Lineup Strength.
- 11F/7D: lineup.league uses the 7th D in the 12th F slot (COL dressed 11F + 7D in both games); replacement fill only when a team truly lacks players.
- Power table 'Top impact players (in his role)': top 3 of players dressed in the last 5 games by talent84 (expected impact in his role = talent x actual TOI; goalies by share of starts), shown with values in pts. Replaces 'top skaters by talent (tstd)'. rows gain topV/topPos.

### 2026-10-04 — Goalie handling across the dashboard
- Power table: "Top impact players" = top 3 SKATERS by talent84; goalies on a separate line: likely starter (most starts in last 5 games, from game files) and backup, each rated as if he starts (tstd = talent at a starter's workload), with starts shown (e.g. 2/2).
- power.compute now exports per-team goalies [{id, name, rate60, mpg, starts, dr}], dr = lineup weight b1 x (his rate - team's recent goalie mix) = model-implied change in expected GD per game if he starts. Measured: starter vs backup median 0.5 pts of win probability (max ~1.8, WSH); best vs worst regular goalie ~5. Shown only in the matchup calculator (goalie selectors) + a note under Utah's next 10; not separately backtested.
- Goalie profiles (player_profile.goalie_*): GSAx/60 and saves above expected per 100 shots by danger level, rebound control, freezing; pooled over 4 seasons with G weights and shrunk by year-to-year r (gsax 0.13, danger splits 0.14-0.16, rebounds 0.41, freeze 0.47; profRel.G). Percentiles among goalies with 1000+ weighted minutes; suppressed below that. Archetype: Starter / 1A-1B / Backup (+ best trait), with blurb. Roster "In his role" for goalies shows the share of starts it assumes.
- Unchanged by design: goalies excluded from value vs contract and from fits; never a tier's reference player; Lineup Strength uses the best goalie; exec card lists all goalies with starts.

### 2026-10-04 — Matchup tab
- New tab "matchup" (between Team and Roster). Pick two teams (or an upcoming game from the league schedule; defaults to Utah's next game), venue, and each team's goalie (likely starter default).
- Sections: odds tiles (win %, OT, expected points, power rank/tier, records, form); Where each team can win (10+ rank gaps excluding hits/rebounds, PP vs weak PK, strength-meets-need); Who to watch (top impact skaters + goalie line, links to profiles); Tale of the tape (lineup-slot talent ranks + style ranks flipped so 1st = best); Team styles + player-type mix; Special teams (PP xG/60 vs opponent PK xGA/60, penalties taken/drawn); Lines (Utah staff lineup / others' last-game lines, line value = sum of talent, edge if gap >= 1 pt); Rosters side by side by impact in role; Player vs player (profiles side by side, goalie metrics if goalies); Expected box score (opponent-adjusted per-game rates: shots, xG, high-danger shots, power plays; model goals); Live win probability (independent Poisson goals over time left, rates calibrated so 0-0 at puck drop = pre-game odds; OT at model OT odds; ignores score effects / empty nets; not backtested in-game); History (this season's meetings + remaining; last season's series from inputs/history/games_2025-26.json with xG share).
- Build exports teamRates (per-game rates, this season + last at 0.5) and games25.

### 2026-10-04 — Model vs. public consensus test
- calibration/experiments/consensus_test.py (SIT=5on5): model talent (prior seasons only) vs prior points/60 for predicting next-season on-ice GD relative to team. 5v5: talent wins (F .385 vs .328; D .343 vs .245; top-15% scorers .389 vs .185). All situations: points win (.663 vs .596) because PP deployment persists — usage, not talent. Elite finishers retain ~42% at 5v5, same as everyone (linear). Decision: no model change. Results in params/consensus_test.json, shown on How It Works.

### 2026-10-06 — Weekly update (through Oct 5)
- All 8 MoneyPuck files new (through game 43). NHL standings/results refreshed (43 final). Box score 2026020036 (L 2-4 at NYR) logged. Lineup config: Game 3, Vejmelka started. Brief rewritten. Checks 11/11.

## Oct 7 weekly update (through game 52, Oct 6)
- Installed 8 new MoneyPuck files (season max GP 5; game files and shots through 2026020052) under fixed names.
- Added box score 2026020047 (UTA 5 @ NJD 3); league_schedule games 44-52 final; standings as of Oct 7.
- lineup.json: Game 4, Vejmelka started Games 1, 3, 4. New brief (Utah 3-1-0, 7th, Tier 2, proj 104, 78% playoff).
- Checks 11/11; rt3 32/32 teams. Note: built page now has 4 script blocks; test harness uses sc[2] (data) and sc[3] (main).

## Oct 9 update (MoneyPuck through game 65, Oct 8; NHL results through Oct 9)
- Installed 8 new files; box score 2026020056 (UTA 1 @ BOS 6; Cossa started, pulled 15:51; Vejmelka relief), penalties from landing (drawnBy).
- Schedule games 53-69 final; standings Oct 9. lineup.json Game 5. Brief: 3-2-0, 8th, Tier 2, proj 102, 76%.
- Checks 11/11; rt3 32/32.

## Oct 11 update (MoneyPuck season + game files through game 83, Oct 10; no shots file this upload)
- 7 files installed (shots_2026.csv left at Oct 8). Box score 2026020074 (UTA 4 @ BUF 1). Schedule 70-83 final; standings Oct 10 (83 games).
- lineup.json Game 6: Yamamoto in for Carcone; lines from MoneyPuck 5v5 TOI. Brief: 4-2-0, 7th, Tier 2, proj 105, 81%.
- Oct 10 score page fetch truncated; games 82-83 taken from their box scores.
- Checks 11/11; rt3 32/32.
- Oct 11 (later): shots file through game 83 installed; data note updated.
- Playoff line: seasonsim now returns per-conference cutoff (points of last team in, per sim) as out["_cut"]. team.playoffLine = this season's simulated West median (93) when the league sim runs; playoffLineHist (97, 7 seasons, 84-game scale) and playoffLineNow {median, lo80, hi80} exported; sim note/chart label updated. Reason: page showed historical 97 next to odds computed against the actual simulated format (weak West bottom -> ~93).
- Inflation check (no change): projections average 93.1 pts/team (1.108 pts/game) vs 1.103-1.124 in seven past seasons; playoff probabilities sum to 16.0; sim spread (sd 19 pts) within the historical 13-20 range.

## Oct 13: Matchup share card
- Matchup tab, new card #mu-share under the odds tiles: canvas image (Wide 1200x675 for X, Square 1080x1080 for texts/Instagram; drawn at 2x), download link + long-press image, post text (<= 280 chars; drops power rank, goalies, model score, away edge in that order if long) and a longer group-text version. Copy buttons with select fallback.
- Content = same numbers as the tab: win odds (venue + selected goalies), OT chance, power rank/tier/record, top 2 edges per team (shortEdge() plain-language rewrite), top 2 impact skaters, likely goalie, model score (MU.la/lb), first unplayed meeting date (+ MT start time for Utah games), data-through date from schedule. Team colors from TEAM_COL (no logos). Footer: "not betting advice", data credit MoneyPuck/NHL.
- muShare wrapped in try/catch (no canvas -> message, rest of tab unaffected). Test: rt14.js (stub canvas) renders all 93 Utah matchups x venues, no undefined/NaN, max tweet 280. Visual check of wide image done in preview; square layout adjusted by geometry (two-line footer).
- Backup: archive/backups/template_v18_backup.html.

## Oct 13 (later): Matchup analysis rebuilt (validated "how each team wins") + richer share card
- calibration/experiments/matchup_validation.py -> params/matchup_validation.json (D.muVal): team YoY r 2010-26 (5v5 chances .65/.62, slot shots .68/.66, possession .67, PP .57, PK .43, PP finishing .15, penalties drawn/taken .66/.71, finishing .32, team saves .26, faceoffs .57, hits .67); 2025-26 odd/even split (chances .60/.65, finishing -.07, team saves .12); single-game win rate by xG share (shootouts dropped: no winner in file; xG winner wins .668); GD/game on 5v5 chances, PP/PK and faceoffs (faceoff coef negative -> no extra effect).
- build: teamRates adds f5/a5/h5 (5v5 xG per 60, 5v5 hours/game), hdf5/hda5, cf5, pph/pkh, finNow/savNow (this season, per game). engine/power.py exports partsR (unrounded, r units).
- template: muEngine (waterfall of the odds: home ice, roster talent, last season, chances, results, goalies; exact to the tile odds, small pieces folded into "Other"); paths per team: 5v5 (multiplicative attack x defense / league), special teams (penalties drawn x opp taken / league; value = time per PP x PP rate x opp PK / league), draw penalties, stay out of the box, goalie edge (talent rate60; "usual mix" = minutes-weighted, unnamed), top-line matchup (top six F vs opp top-four D), depth, best lever fallback, upset route (only when behind on 5v5+ST chances and < 50%). Running hot/cold (finNow/savNow >= 0.3 a game) shown as context only. New cards: #mu-why, #mu-edges (rebuilt), #mu-gloss (what stats mean / carry over / watchable). Tape notes updated (finishing, goaltending results, faceoffs).
- Share card: Full 1080x1350 (default) and Wide 1600x900; includes odds bar, verdict, model score, why-the-odds waterfall, how each team wins (3 each with numbers + what to watch), key matchups (5v5 ranks, PP/PK ranks, goalies, best player), stat to watch live, running hot/cold. Text versions follow away-then-home order.
- Independent audit (subagent) found 18 issues; fixed: waterfall rounding (partsR), hidden steps (Other row), defensive-branch wording, 5v5/upset triggers, shootout ties in validation and H2H, watch stat naming, goalie tag ("small, noisy edge"), usual-mix consistency, neutral date, penalty wording ("penalties drawn", "expected PP goals"), weak-goalie "lean on", top-line trigger, faceoff/hits wording, double colons/capitalization, neutral home row, ord(0). Tests: rt3 32/32, rt12 124/0, rt14 93/0, audit_wf exact (2e-16).
- Visual check: Full format verified in preview; Wide checked by layout geometry only (preview panel unavailable).

## Oct 13 (late): preview graphic, player and schedule additions
- Anytime-goal chance: calibration/experiments/scorer_validation.py -> params/scorer_params.json. Backtest on all 2,988 player-games of 2026-27 so far using prior-season data only: mean predicted 14.8% vs actual 14.6%; top decile 32.5% vs 31.8%; Brier 0.1182 vs base 0.1249 (k_fin 20, k_xg 6 chosen on the same games: small grid, mild optimism). build exports playersLeague[].gx60 (shrunk ixG/60 x shrunk finishing, seasons 2026/2025/2024/2023 at 1/1/0.5/0.25). Page: P = 1 - exp(-gx60 x tpg/60 x opp xGA factor), dressed players only (Utah staff lineup; others' last-game lines).
- Back-to-back: calibration/experiments/rest_validation.py -> params/rest_validation.json (2025-26, 1,312 games, 430 B2B team-games): second night vs rested opponent = -0.31 win logit (se 0.13, about -7.6 win-% points at 50/50), -2.2 pts of xG share (se 0.6). Now applied to matchup odds (tab + share), next10 odds (build) and the season sim (seasonsim accepts a per-game shift). D.restVal exported.
- Share graphic: team line = record, division place, power rank (Tier dropped: jargon); "Last game" result line, amber "2nd night of back-to-back" flag; key matchups: "Likely to score" (top 2 each) replaces "Best player"; "Schedule" row when a team is on a B2B. Post text: "To score" line replaces "Watch"; back-to-back line when relevant. Who-to-watch card shows top-3 scoring chances with the backtest numbers.
- Considered and left out: last-game lineup changes (stale for tonight; would mislead as injury news), head-to-head player history (tiny samples), point streaks (noise), projected shots (redundant with model score), team archetype labels (no validated counter effect).
- Checks: rt3 32/32, rt12 124/0, rt14 93/0, rt16 1,984 matchups engine odds == tile odds, waterfall sums within 1 pt (484 with a back-to-back).

## Oct 14 update (MoneyPuck through game 105, Oct 13; NHL results through Oct 13)
- 8 files installed. Box score 2026020102 (TOR 4 @ UTA 5; penalties from landing). Schedule 84-105 final (Oct 13 score page truncated: 100-105 from box scores / MoneyPuck game files; 103-105 boxscores were cached LIVE, scores taken from landing?final=2 and MoneyPuck skater goal sums).
- Cap-hit check now judged by ice time (>= 98%); count-based 97% failed because call-ups missing from the pasted Spotrac list (24 players, 1.1% of ice time).
- Brief: 5-2-0, 1st in Central, 7th power, proj 106, 82%. Checks 11/11; rt3 32/32, rt12 124/0, rt14 93/0.
- Note on MoneyPuck goalie game file: playerTeam = goalie's team and xGoals = chances AGAINST that team.

## Oct 14 (later): matchup paths broadened + game recap graphic
- Paths: added "Win the slot" (high-danger share >= 57% when no 5v5 path; YoY .68), "Shut down X's power play" (own PK top-10 vs their PP top-12), "Fresher legs" (opponent on a back-to-back; validated effect, already in odds), best-lever fallback now fills sides with < 2 paths, 5v5 path names the team's top line. Across all 1,984 team-sides: 12 path types (was 9); sides with 0 paths 54 -> 34, with 1 path 713 -> 367, with 3 paths 405 -> 627. Goalie path doesn't show in the harness (no goalie selected there) but does on the page.
- Recap: engine/recap.py -> D.recaps (every Utah game in the shot file: all shots [t, utah?, xG, goal, strength, shooter, on goal, period], deserve-to-win = each non-empty-net shot simulated as a goal at its xG 20,000x, stats incl. 5v5/PP xG, dangerous shots (xG >= 10%), goalie saves vs expected from the goalie game file, box-score score/last period). D.snaps (gp, playoff odds, proj, power rank) for before/after context. Overview card #rc-card: game picker, Full 1080x1350 / Wide 1600x900 image (score, verdict "Earned it / Stole one / Deserved better / Outplayed / coin-flip", why, deserve bar, cumulative xG race chart with goal markers, by-the-numbers, Utah best/worst by Player Impact, biggest goal by win-probability swing (league-average scoring, no team strength), unlikeliest goal, playoff odds and power rank change, next game), post text <= 280 and group-text version.
- Bug caught: MoneyPuck shot file stores isHomeTeam / shotOnEmptyNet as "1.0", so string compares failed (home strength swapped); now numeric.
- Tests: rt17 (path variety), rt18 (all 7 recaps x 2 formats, no undefined/NaN). Visual check not possible this round (preview panel closed); layout checked by geometry. mammoth-probe artifact was overwritten with a recap render test page.

## Oct 16 update (MoneyPuck through game 118, Oct 15; NHL results through Oct 15)
- 8 files installed. Box score 2026020117 (UTA 4 @ EDM 2). Schedule 106-118 final. Brief: 6-2-0, 1st Central, 5th power (up 2), proj 107, 85%. Recap now includes Game 8 (deserve-to-win 65%).
- Checks 11/11; rt3 32/32, rt12 124/0, rt14 93/0, rt18 recaps 8/0.

## Oct 18 update (MoneyPuck through game 134, Oct 17; NHL results through Oct 17)
- 8 files installed. Game 9 (EDM 6 @ UTA 2): NHL boxscore endpoint stuck on a LIVE cache (final=1 and final=2), so inputs/nhl/boxscores/2026020133.json was built from MoneyPuck's game file (goals, primary/secondary assists, SOG, hits, TOI, faceoffs, blocks, giveaways/takeaways, PIM; +/- from 5on5+other on-ice goals) plus landing (score, penalties drawn/taken). Goalies from MoneyPuck goalie game file (Vejmelka 17 SA/5 GA/33:48, Cossa 4/1/26:12). Field "source" notes this.
- Schedule 119-134 final (134 PIT@VGK from MoneyPuck goal sums, 6-2). Brief: 6-3-0, 1st Central by points, 7th power (down 2), proj 105, 82%.
- Checks 11/11; rt3 32/32, rt12 124/0, rt14 93/0, rt18 recaps 9/0.

## Oct 20 update (MoneyPuck through game 140, Oct 19; NHL results through Oct 19)
- 8 files installed. Box score 2026020140 (PIT 4 @ UTA 5; Cossa start). Schedule 135-140 final. Lineup: Marino out, DeSimone in; staff lines/pairs updated from MoneyPuck 5v5 TOI (Crouse-Schmaltz-Keller, Cooley-Trocheck-Guenther, Lee-Hayton-Yamamoto, But-Stenlund-McBain; Sergachev-Weegar, Schmidt-Peeke, Simashev-DeSimone).
- Brief: 7-3-0, 1st Central, 7th power, proj 106, 86%. Checks 11/11; rt3 32/32, rt12 124/0, rt14 93/0, rt18 recaps 10/0.
- Oct 20: per-game Player Impact now shown in goals everywhere (game-stars list shows goals, points in tooltip; recap graphic labels GOALS, 2 decimals). Season/talent views stay in standings points.
- Oct 20: recap 'Biggest goal' replaced by official Game-winner (winner's goal that put it one past the loser's final total; none for shootouts) plus 'Biggest swing' only when a different goal moved win chance 20+ points (league-average win model makes early 0-0 goals always ~17).

## Oct 20 (later): player-judging review + caliber labels
- Review of the whole player pipeline (Impact, Talent weights/shrinkage/age/experience prior, intervals, tiers, bands, profiles, goalies). Already validated and unchanged. Newly tested and NOT adopted: score/venue (and flurry) adjusted xG. Team level helps a little (next-season GD r .502 -> .525, YoY .593 -> .612). Player level gives nothing (on-ice relative YoY .333 raw vs .323/.330; next GF% .203 vs .197/.201; individual xG/60 -> next G/60 .758 vs .761).
- Caliber bands checked against the 75% tier rule run league-wide: skater percentile bands match the rule's natural breaks (adjacent band tops separate ~80%: F 90v67 .83, 67v33 .82; D .91/.81). Goalies do not (90th vs 67th pct .59, 83rd vs 17th .66; league-wide rule finds 2 tiers).
- Changes (template.html only; backup archive/backups/template_v19_pre_bands.html): (1) Superstar = top 2% at position (98th vs 90th: F .84, D .95; 19 players now), pill .p-star. (2) Goalie caliber = P(talent > average) from tal/tsd: >= .75 "Likely above avg", <= .25 "Likely below avg", else "Avg range" (now 5 / 58 / 2). bandOf(pct, g, tal, tsd). Finder filter options + lede updated.
- Test rt20.js (generates rt20_run.js from rt3): all 32 rosters clean, band counts as above.

## Oct 20 (late): fully automated daily updates (GitHub Actions + Pages)
- This folder now lives in a GitHub repository (repo root = the old Hockey/ level: Dashboard/, automation/, .github/workflows/daily.yml; "Source Data" is downloaded). The repository is the source of truth from here on; the scheduled job commits its state back every morning.
- automation/daily.py: fetch_moneypuck (season 2026 files, game-by-game zips, shots zip, player lookup every run; 2025-26 season files and 2008-2024 history only when missing, kept in the Actions cache) -> fetch_nhl (standings/now, club-schedule-season, weekly /v1/schedule paging -> league_schedule.json, roster/UTA/current -> config/roster.json (keeps hand-set status entries), new Utah box scores from boxscore + landing (only once the NHL marks them final and the score + skater goals reconcile; automated boxes from the last 3 days are refreshed for scoring changes), NHL player landing birth dates for players missing from both bio files) -> lineup_auto (last game's 5v5 lines/pairs from the MoneyPuck lines game file, greedy, ordered by players' 5v5 TOI; goalie starts from box scores; scratches = roster skaters who didn't dress) -> build -> brief_auto -> build -> gate.
- Brief: facts packet from data.json + box scores + standings; Claude Messages API (BRIEF_MODEL env, default claude-sonnet-5-5, temperature 0.2) with rules (packet facts only, no computed numbers); verifier: scores/records/ranges must match packet strings, times must be packet ice times, other numbers by value with sign, no spelled-out numbers above five, capitalised names must be in the packet, score in the opening, 190-360 words, no HTML; one retry with the problems listed; else a plain template brief; output/brief_audit.json keeps the packet and attempts.
- Gate: blocking checks = box-score goals vs final score, league schedule vs standings, the two static backtests. Others are shown on the page but don't block. Early run (11:45 UTC) waits if Utah's newest game isn't in MoneyPuck's game and shot files or its box score isn't final; final run (14:00 UTC) publishes whatever is available. A failed final run leaves the previous page up; GitHub emails the owner.
- build.py fix: "Box-score goals sum to final score" now subtracts the shootout-winning goal (no skater is credited with it).
- Secret: ANTHROPIC_API_KEY (repository secret). Without it the template brief is used.

## Oct 24: v1.1.0 (playoffs, any-team view, all-team rosters)
- Versioning: `VERSION` at repo root (shown in the page header, linked to `CHANGELOG.md`). Bump MINOR for features/model changes, PATCH for fixes; write the changelog entry with every release.
- Playoffs: `engine/seasonsim.py` `_playoffs()` plays the bracket inside the existing 10,000-season simulation (same strength draw, scaled to end-of-season uncertainty). Series model and backtests: `params/playoff_params.json`; experiments in `calibration/experiments/` (`stars_vs_depth_*`, `playoff_predictors_*`, `cup_odds_*`). Output per team: `power.rows[].po`. New check "Playoff simulation adds up".
- Any team: header select (`h-sel`) sets the global selected team `TM`; `renderHero`, `renderOverview`, playoffs, team, roster and matchup re-render for it; league tables highlight it. Other teams' overview data: `execAll` (rule-based), `recapsAll` (latest 5 games, MoneyPuck shots + league schedule).
- All-team rosters: `automation/fetch_nhl.py rosters_all()` -> `config/rosters_all.json` (a failed team keeps yesterday's list). The build moves traded players to their new team and adds rostered players with no games this season (`ng`), rated from past seasons; team-strength views and power rankings still exclude `ng` players.
- Share cards: post-text / group-text boxes removed; "why the odds lean" bars fixed to point toward each team's side.
- Workflow: also runs on push to main (code paths only).

## Oct 24 (later): v1.2.0
- Series model: elite skaters counted up to 2 (`elite_cap` in params/playoff_params.json; b_power 1.609, b_elite 0.561, alpha 0.7). LOSO log-loss 0.6468 vs 0.6595 linear; full Cup backtest equal within noise (`cup_odds_backtest_floor*` in calibration/experiments).
- Goalie labels: starter percentile vs. the 32 likely starters (`goalieStarters` in data; most starts this season, then talent): <20 Below starter floor, 20-40 Borderline starter, 40+ Starter quality. Validated on 12 held-out seasons (`goalie_bands_validation.txt`).
- Goalie floor inside the power rankings tested and not adopted (`pr_goalie_floor_*`).

## Oct 24 (late): v1.3.0
- Series model = average of two logistic models (params/playoff_params.json `blend`: every elite counted; first two only), alpha 0.7. Nested check showed the capped version's edge came partly from choosing it on the same data (`thresh.py` results in calibration/experiments/topend_*).
- Site: methodology moved to the Guide tab (`p-method`, sections `g-*`, opened via goGuide(id)); data tabs keep one-line subtitles. Tabs: Overview, Team, Roster, Matchup, League, Playoffs, Players, Guide (data-t ids unchanged: finder, method). Per-tab team selects removed (header `h-sel` drives TM). renderPlayoffModelNotes() and renderStatGlossary() render into the Guide.

## Oct 26: v1.4.0
- Games tab (`p-games`, JS `GMX`/`gm*`): `engine/games.py` builds `D.games` (every scheduled game: date, start UTC, score, xG, deserve, odds) and per-date detail files `output/games/<date>.json` (both teams' per-game Impact via `impact.compute(... team=t)`, stat lines, goalies, shots with adjusted x/y). `automation/daily.py` copies them to `site/games/`; the page fetches a date's file on demand (`EMBED_GAMES=1` embeds them as `D.gameDays` for offline previews/tests). Hash: `#games/<date>/<id>`.
- Upcoming-game odds computed in the power block (`game_odds_`), same model as next-10 (ratings + home ice + REST_LOGIT). Each build records odds for games dated today or later into `history/pregame_odds.json` (committed by the workflow); finished games show the last recorded value as `pre`. Never back-filled.
- Recaps (`D.recaps`, `D.recapsAll`) carry `pl` (both teams' per-game values); `rcImage(R)` draws the 1080x1350 card and switches to a compact layout with both-team bars when `pl` is present. `rcRender` (Overview) and the Games tab both use it.
- Style tags: `params/style_params.json` (cuts, shrinkage k, precisions) read by `engine/style.py`; tag kinds '' / 'weak' / 'best' (`styK` in playersLeague; chips styled `.tagchip.weak/.best`). Team tags in `engine/team_style.py` (quality/noisy tags removed; "Closest to" fallback). Validation scripts in `calibration/experiments/style_tags_*`, `team_style_validation.*`.
- Workflow: `workflow_dispatch` input `attempt` (manual/early/final) for the outside scheduler (SETUP.md section 6); skip/commit dates in America/Denver; fetch-depth 30.
- New check: "Games tab adds up".
