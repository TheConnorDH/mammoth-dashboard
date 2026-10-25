# Utah Mammoth Season Dashboard

**Live page: https://theconnordh.github.io/mammoth-dashboard/**

An objective, data-only view of the Utah Mammoth's season, with every other NHL team one click away (pick a team at the top of the page). It updates automatically every morning. Current version and changes: [CHANGELOG.md](CHANGELOG.md).

## What's on it
Pick any team at the top of the page; every tab follows it.
- **Overview:** the daily brief (Utah), executive summary, game recap graphic, next 10 games, last game's best and worst players.
- **Team:** how the team is built and plays, needs and possible moves, season outlook, strengths and weaknesses, shot maps.
- **Roster:** every player's Impact and Talent, player profiles, value vs. contract, game by game, lines and goaltending.
- **Matchup:** any two teams head to head, with a shareable preview graphic.
- **League:** power rankings, conference and division comparisons, lineup strength, standings.
- **Playoffs:** each team's odds round by round and playoff strength.
- **Players:** every NHL player rated the same way, with filters.
- **Guide:** what every number means and how it's built, plus the integrity checks run on every build.

## Data and credit
- [MoneyPuck.com](https://moneypuck.com/data.htm): shot-model and player data, free for non-commercial use with credit. Files are downloaded fresh on each run and are not stored in this repository.
- The NHL's public API: results, standings, schedules, box scores and rosters.

This is an independent fan project. It is not affiliated with the NHL, the Utah Mammoth or MoneyPuck.

## How it updates
- `.github/workflows/daily.yml` runs `automation/daily.py` up to four times each morning, between about 2:15 and 6:45 am Mountain time. An early run publishes only once Utah's latest game is in every data source; the last run publishes with whatever is available.
- Pipeline: download and check the inputs (including every team's NHL roster) → set the lineup from the last game's ice time → build (`Dashboard/build.py`) → write the brief (Claude API; a plain template if a check fails) → rebuild → integrity checks → publish.
- A push of code to `main` also rebuilds the site right away.
- If something fails, the previous page stays up and GitHub emails the repository owner. Each run's report is under the **Actions** tab.

## In this repository
| Path | What it is |
|---|---|
| `Dashboard/` | Model and page build (`build.py`, `template.html`), config and saved state |
| `automation/` | Daily job: downloads, data checks, lineup, brief |
| `Dashboard/HANDOFF.md` | Model and design notes |
| `SETUP.md` | How to set up your own copy |
| `CHANGELOG.md`, `VERSION` | What changed in each version |
| `BACKLOG.md` | Planned and proposed changes |
