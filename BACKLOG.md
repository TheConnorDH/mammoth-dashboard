# Backlog

Requests and planned changes, in rough priority order. Each item is validated on history before it ships, and gets a version bump and changelog entry.

## Shipped
- 1.4.0 (2026-10-26): Games tab (every game by date, both teams' player values, upcoming odds, saved pregame odds), both-team bars on the recap graphic, validated style tags, outside scheduler for on-time updates.
- 1.3.0 (2026-10-24): blended series model, Guide tab, decluttered data tabs, tab reorder.
- 1.2.0 (2026-10-24): elite-skater floor in the playoff series model, goalie floor labels, elite indicator.
- 1.1.0 (2026-10-24): versioning + changelog, all-team rosters, playoff tab, team selector across the site, odds-lean bar fix, push-to-rebuild. See CHANGELOG.md.

## Next
1. **Pull-request build check.** A GitHub Action that builds the site from a branch (no publish), so a broken change shows a red X before merge.
2. **CLAUDE.md** project rules file for working in Claude Code (VS Code).

## Playoff tab (shipped in 1.1.0; notes kept for follow-ups)
Goal: the site shows how likely a team is to *make* the playoffs; add how likely it is to *succeed* once there.

Evidence (`Dashboard/calibration/experiments/playoff_predictors_*`, `stars_vs_depth_*`, 165 series 2013-14 to 2024-25, leave-one-season-out):
- The favorite by the end-of-season power ranking won 61.8% of series. By elite count (top-10% players) it also won 61.8%. Power + elite was the best combination (63.0%).
- Total roster talent (54.5%), the bottom six (47.9%) and goalie talent (49.7%) were near coin flips.
- Every Cup winner in the sample had 2+ elite players; 7 of 11 had 0-1 superstars.

Prototype (`cup_odds_sim.py`, results in `cup_odds_results.txt`):
- Series model A: power ranking only. Series model B: power ranking + elite count.
- Monte Carlo of the rest of the season (projected points) → NHL bracket (top 3 per division + 2 wild cards) → series by series.
- Outputs per team: make playoffs, series win % vs an average playoff team ("playoff strength"), reach Final, win Cup, Cup % if in.
- Adds early-season uncertainty in team strength (current true-strength variance minus end-of-season variance).

Backtest of the full simulation (2026-10-24, `cup_odds_backtest_*`, 8 seasons, from ~4 and ~14 games played):
- Real skill for making the playoffs (+22-36% Brier skill) and winning round 1 (+18-25%); small for the conference final (+7-12%); none for the Final or Cup (0-7% and 0-1%).
- Favorites were given ~15-17% and won 1 of 8 (Oct) / 0 of 8 (Nov). The prototype's playoff qualification was overconfident (80-100% group: predicted 94%, actual 85-87%).
- Conclusion: do NOT publish Cup % as a sharp number. Show round-1 and playoff-strength odds; shrink Cup odds heavily toward equal-among-playoff-teams, or omit.

Calibration (`cup_odds_backtest_calibration.py`): keeping 70% of the fitted series edge (alpha 0.7) scored best across rounds; favorites then average ~13% Cup. Live calibrated list: `cup_B_cal.json`.

Before shipping:
- Confirm alpha with more seasons / more sims (8 champions is a tiny sample); re-check calibration at every round.
- Decide on A vs B (B is slightly better on series but rests on a moderate effect).
- Use the same elite definition historically and live (prior-only talent, regulars only). Same for the goalie floor (live uses current talent vs. this season's likely starters).
- Done in 1.1.0: each simulated team's standings and playoff strength come from the same draw.
- Home ice, and reseeding rules if the NHL changes format.
- Done in 1.2.0: elite term counts the first two only (validated leave-one-season-out).
- Test recent goalie form going into the playoffs (e.g. last month's GSAx) as a series factor. Pre-season goalie talent added nothing (49.7% alone; made combined models worse).
- Page design: playoff tab with Cup odds, playoff strength, round-by-round odds, and Utah's path / likely opponents.

## Model ideas tested and not adopted
- Style tags at the old fixed cuts (2026-10-26, `style_tags_*`, `team_style_validation.*`): Finisher, Shutdown and five team tags didn't repeat next season often enough; Play driver needed a stricter cut. Shrinking rates by ice time helped slightly (adopted). Using 5-on-5 rates for Shooter/Playmaker repeated less than all-situations rates (not adopted; the Power-play weapon tag covers the power play).
- Power-ranking lineup window/weighting (2026-10-24, `pr_lineup_window_*`): last 3/10/20 games, season to date, last 5+20 combined, and weighting heavy-minute skaters more (minutes^1.5, ^2). All within 0.5% of the current last-5-games, minutes-as-played lineup; the best (minutes^1.5, 0.2% less error) won 20 of 40 season-checkpoints, a coin flip. Not adopted.
- Smoother top-end measures for the playoff series model (2026-10-24, `topend_*`): 18 alternatives (best/2nd-best player percentile, top-2/3 talent, soft counts, other thresholds, minutes-weighted talent up to minutes^4 as a stand-in for playoff ice time). None beat 'first two elite skaters'. Real playoff ice time isn't in our data (MoneyPuck game files are regular season only); worth retesting if we collect it.
- Goalie floor in the power rankings (2026-10-24, `pr_goalie_floor_*`): a bottom-20% goalie costs ~6 points/82 in a full-season check, but in the power-ranking backtest neither a floor (20th-50th pct) nor a separate goalie term beat the current model; results and last season already carry it. Not adopted.
- Last-season roster continuity / replayed last season / team-residual split for power rankings (no gain; `pr_continuity_*`, 2026-10-24).
- Score/venue-adjusted xG (small team-level gain, none at player level).

## Later
- Games tab: score the saved pregame odds once a few hundred games have them (calibration table in the Guide).
- Games tab: live scores during the evening (needs a lighter, more frequent job).
- Design polish pass with screenshots (desktop + mobile): spacing, table density, chart styling. Matchup calculator on League duplicates the Matchup tab; consider removing.
- Playoffs tab: optional 'Win round 1 if they make it' column.
- Site polish: landing view, mobile, About page, plain labels.
- Nightly collection of NHL play-by-play, shifts and EDGE data toward our own xG model.
- Live game updates.
