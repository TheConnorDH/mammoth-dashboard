# Changelog

The version shown on the page comes from the `VERSION` file. Numbering: MAJOR.MINOR.PATCH. MINOR adds features or model changes (each validated on past seasons before shipping); PATCH fixes bugs without changing the model.

## 1.6.1 (2026-10-26)

**Changed**
- **Standouts are judged against teammates that night, and there is no cap.** Raw game values lean with the score (a team's summed skater values track the game's goal differential, r 0.67), so in 1.6.0 a team that won by 3+ averaged 4.8 standouts and one that lost by 3+ averaged 1.7. A skater now needs to be one typical swing (about 0.42 goals for forwards, 0.31 for defensemen) above or below his teammates' average that night; blowouts are now balanced (won by 3+: 3.7 standouts and 3.7 rough nights; lost by 3+: 2.4 and 2.6). A standout must also have a positive game in itself (a rough night a negative one), so the best player on a bad night isn't called a good game; in this season's games that never happened, because a team's average per skater stays small (-0.18 to +0.34 goals). Goalies stay on saves vs. expected (swing about 1.6), since that doesn't depend on teammates' scoring. The cap of 4 is gone (it hid real standouts in about 1 team-game in 5); the most so far is 7.

## 1.6.0 (2026-10-26)

**Changed**
- **Game standouts replace the fixed three best and worst.** A standout (&#9650;) or rough night (&#9660;) is a player at least one typical single-game swing above or below his team's level that night at his position (the spread of this season's game values: early on about 0.44 goals for forwards, 0.31 for defensemen, 1.6 for goalies), at most 4 a side (changed in 1.6.1); quiet nights name the closest player instead. In this season's 280 team-games, the old top three included a player under +0.5 goals in 22% of games. Shown on the Overview's last game, the Roster tab's game by game, the Games tab (marked in the bars, with a one-line summary for each team) and the recap graphic (marked in the bars).

## 1.5.0 (2026-10-26)

**New**
- **Impact per 60 and Impact windows.** The Players tab can show Impact for the season or the player's team's last 20, 10 or 5 games, plus Impact per 60 minutes with a percentile among qualified players at his position, and can rank by either. **Qualified** = at least half a regular's minutes over the team's games in the window (7.5 min per team game for forwards, 9.5 for defensemen, 30 for goalies), so the floor scales with the window and the season. The note above the table says how much of the per-60 spread is real at the median qualified sample (early in the season, not much). The Roster tab adds a season per-60 column.

## 1.4.0 (2026-10-26)

**New**
- **Games tab.** Every NHL game of the season, browsable by date (arrows, a date picker, a strip of nearby game days, and an optional team filter). Each game opens on the same page:
  - **Finished games:** score, deserve-to-win, the numbers (shots, expected goals, dangerous shots, power play, goalies), the chance race, every shot on a rink, the season series, and **Player Impact in this game for both teams** as bars on one scale, best to worst, with each player's stat line. These are the same per-game values as each team's game-by-game stars. Bars show **where each player's Impact came from** (driving play, shot creation, finishing, playmaking, takeaways vs. giveaways, defense, penalties, faceoffs; each vs. the position average) or the total only. Skaters set the scale, so a big goalie night runs off the end instead of shrinking everyone else.
  - Teams with near-identical colors (e.g. DET-NJD, BOS-NSH) get a grey home color in that game's bars, charts and graphic.
  - Postponed games are marked; finished games still waiting on MoneyPuck data say so.
  - **Upcoming games:** win odds (power ratings + home ice + rest), overtime chance, back-to-backs, how the two teams compare (record, power rank, projection, playoff odds, goal and shot-quality differential, elite skaters, last 5, likely goalie, top players), the season series, and a link to the full matchup preview.
  - **Odds before the game:** each morning's odds are now saved, so finished games show what the model expected beforehand, with an "upset" tag when the winner had under 40%. Games before 1.4.0 have none (back-filling would use hindsight).
  - Links into the Games tab from the recap card, the Overview's last game, and the Roster tab's game by game.
- **Recap graphic shows every player's Impact for both teams** (bars, away left, home right) in place of the best/worst lists. The Games tab draws it for any finished game, from either team's point of view.
- **Integrity check:** "Games tab adds up" (every played game with MoneyPuck data has both teams' values; Utah's match its own game stars).

**Fixed**
- After switching light/dark mode, links into the Games and Matchup tabs could open the previous selection.

**Changed (style tags, validated)**
- Tested every style tag on 14 past seasons: does a player tagged from seasons t-2..t still show the trait in season t+1? Each player tag's cut is now the loosest at which at least 55% of tagged players are still top-20% at it next season (chance is 20%); rates are pulled toward the position average by ice time (chosen leave-one-season-out).
  - Kept: Shooter and Playmaker (top 20%), Physical, Shot blocker, Puck thief, Draws penalties (top 15%), Play driver (now top 10%, 5-on-5; it repeated 45% of the time at the old top-20% cut, 55% at top 10%).
  - **Dropped:** Finisher (scoring above shot quality repeated at most 49% even for the top 5%) and Shutdown (at most 42%).
  - **New: one weak spot** per player when it repeats at least half the time: Penalty-prone, Low shot threat, Gets out-chanced (red chip).
  - **New: best trait** when no tag clears the bar (dashed chip), e.g. "Best trait: takeaways", so a player isn't left blank or oversold.
- **Team style tags now describe how a team plays, not how good it is.** Dropped the quality tags (Stingy defense, Leaky defense, Dangerous power play; Strengths and Weaknesses covers those) and the ones that didn't repeat (Quality over quantity 40%, Protects the slot 41%, Finishing team 37%, Goaltending-driven 40%, Strong penalty kill 28%). The rest repeat 45-67% of the time. A team with no tag shows its closest trait.

**Changed (updates)**
- **On-time morning updates.** GitHub's own schedule was starting runs 6-7 hours late. The workflow now accepts an outside scheduler (cron-job.org, setup in SETUP.md section 6) that starts the morning attempts at 2:17, 3:47, 5:17 and 6:47 am Mountain; GitHub's schedule stays as a backup, and any attempt after the day is published stops in seconds. "Already published today" now uses the Mountain date and checks the latest commit (a queued attempt no longer republishes). GitHub's backup final attempt moved to 13:47 UTC. Deserve-to-win now uses one value per game everywhere (seeded by the game). The **Run workflow** button still rebuilds right away (attempt: manual).

## 1.3.0 (2026-10-24)

**Changed (model)**
- **Playoff series odds now average two versions of the elite-skater term:** counting every elite skater (1.1) and counting only the first two (1.2). When the threshold and count were chosen fairly (each season held out from the choice), "first two only" was no better than counting every elite skater; the two disagree most for teams with zero elite skaters, where history is thinnest (14 series). The average sits between them (leave-one-season-out log-loss 0.6509; every elite 0.6595; first two 0.6468 before the fair check). Correction: the 1.2.0 note overstated "first two only" as clearly the most accurate. Effect for Utah (0 elite): playoff strength about 42% (1.2: 37%, 1.1: 47%).

**Changed (site)**
- **Cleaner data tabs; new Guide tab.** Methodology notes moved off the data tabs into a Guide (key terms, calibers and goalie labels, and how each tab's numbers are built). Each section has a "How this works" link to its Guide entry. The "What predicts playoff success" tables and the matchup stat glossary live in the Guide.
- **Tabs reordered and renamed:** Overview, Team, Roster, Matchup, League, Playoffs, Players (was Player Finder), Guide (was How It Works).
- The per-tab team pickers are gone; the team picker at the top of the page drives every tab.
- Players tab shows a compact caliber legend.
- Elite-skater wording fixed (it read "6 of 2" for teams above the floor).

## 1.2.1 (2026-10-24)

**Fixed**
- Goalie percentiles now use the same scale as the goalie labels: percentile among the 32 likely starters (shown as "Nth of starters"). Before, the number was the percentile among all goalies, backups included, so a goalie could read 47th yet be labeled *Borderline starter*.

## 1.2.0 (2026-10-24)

**Changed (model)**
- **Playoff series model counts only a team's first two elite skaters.** In 165 past series, each of the first two top-10% skaters moved a team's odds a lot and a third or more added nothing measurable. Counting only two gave more accurate series probabilities than counting every elite player (leave-one-season-out log-loss 0.6468 vs. 0.6595; coin flip 0.6931). The full Cup simulation backtest scored the same as before within simulation noise, so the 70% series-edge setting is unchanged. Effect: teams with 0-1 elite skaters (Utah has 0) drop in playoff strength; teams with many elite skaters no longer get extra credit beyond two.
- **Goalie labels now mark a floor instead of a ladder.** Goalies are compared with the league's 32 likely starters (not all goalies, which mixed in backups): *Below starter floor* (bottom 20%), *Borderline starter* (20th-40th), *Starter quality* (above 40th). Tested on 12 seasons, one held out at a time: teams with a bottom-20% starter lost about 14 goals a season beyond what their skaters predicted (10 of 12 seasons); above the 40th percentile, more goalie talent added nothing measurable. Replaces "Likely above avg / Avg range / Likely below avg", which put almost every goalie in the middle.

**New**
- **Elite skaters indicator** on the Team tab header and the Playoffs tab: "X of 2", the playoff floor.
- Playoffs tab: the "what predicts playoff success" table adds a probability-accuracy column (the measure used to choose the model).
- Other teams' Overview goaltending card says where the starter sits relative to the floor.

**Tested and not adopted**
- A goalie floor inside the power rankings: no better than the current model (results and last season already carry it).

## 1.1.0 (2026-10-24)

**New**
- **Playoffs tab.** Every simulated season now plays out the playoffs under the NHL format: make playoffs, win round 1, playoff strength (chance of beating an average playoff team in a series, with an 80% range), reach the conference final, reach the Final, win the Cup, and Cup odds if a team makes it. Also each team's seeding odds and most likely first-round opponents, and a backtest summary of what predicts playoff success.
  - The series model is power rating + elite skaters (top-10% talent at the position, counted among each team's top 12 forwards and top 6 defensemen by ice time). It was the best of nine measures at picking 165 past series winners (63.0%; power rating alone 61.8%; total roster talent 54.5%; bottom-six talent and goalie talent no better than a coin flip).
  - The full simulation was backtested from early-season points in 8 seasons. Odds after round one carry only modest skill, so the series edge is cut to 70% of its fitted size (the setting that scored best). The page labels how much to trust each column.
- **Pick any team at the top of the page.** The header, Overview, Playoffs, Team, Matchup and Roster tabs all follow the selected team, and the League tables highlight it. The URL remembers the team (e.g. `#overview/NJD`).
  - Overview for other teams: executive summary built from league-wide data, next 10 games with win odds, last game's best and worst players, and the game recap graphic for the team's latest 5 games. The written brief and countdowns stay Utah-only.
- **Every team's NHL roster is pulled each morning.** Traded players move to their new team the next day, and rostered players who haven't played this season (injured, suspended, scratched) appear in the Player Finder, rated from past seasons and marked "no games". Power rankings still use who actually dressed in the last 5 games (backtested).
- **Version number** on the page, linking to this changelog.
- **Integrity check:** the playoff simulation must add up (16 playoff teams and 1 Cup per simulated season, playoff odds identical to the standings simulation, each round no likelier than the one before).
- The site rebuilds right away when code is pushed to `main`, instead of waiting for the next morning.
- **Team colors:** the page's accent colors (header, headings, highlights, chart markers) follow the selected team, adjusted for contrast in light and dark mode. Utah keeps its Mountain Blue palette.

**Changed**
- Game recap and matchup preview cards show one image format (1080x1350, which fits X, Instagram and texts) and nothing else: no format switch, no download button (right-click or long-press to save), and no post-text or group-text boxes.
- Utah's executive summary adds a playoff-strength card.

**Fixed**
- "Why the odds lean" bars now point toward the team they help, on that team's side (the preview graphic puts the away team left and home team right; the Matchup tab puts the first team left). They were drawn on the opposite side before.
- The daily brief's checker no longer flags division and conference names as unsupported names.
- Light mode: the dark stat boxes on the Team and Matchup tabs kept dark text, so it was unreadable; their text now stays light.

## 1.0.0 (2026-10-23)
- Baseline: the dashboard as first published on GitHub Pages with the automated daily update (MoneyPuck + NHL API, Claude-written brief with every number checked, integrity checks before publishing).
