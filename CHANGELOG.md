# Changelog

The version shown on the page comes from the `VERSION` file. Numbering: MAJOR.MINOR.PATCH. MINOR adds features or model changes (each validated on past seasons before shipping); PATCH fixes bugs without changing the model.

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
