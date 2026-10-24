# Utah Mammoth Season Dashboard

**Live page: https://theconnordh.github.io/mammoth-dashboard/**

An objective, data-only view of the Utah Mammoth's season, with every other NHL team one click away (pick a team at the top of the page). It updates automatically every morning. Current version and changes: [CHANGELOG.md](CHANGELOG.md).

## What's on it
- **Overview:** the daily brief, which is a short write-up of the latest game. Every number in it is checked against the data before it is published.
- **League:** standings, playoff odds and power rankings.
- **Playoffs:** each team's odds round by round, playoff strength (chance of beating an average playoff team in a series), seeding and likely first-round opponents, and what has predicted past playoff series.
- **Team and Roster:** any team's style, lines and roster, with Player Impact (per game, in goals) and Talent (percentile at his position).
- **Matchup:** any two teams, with goalies and venue, compared head to head.
- **Player Finder:** every NHL player rated the same way, filtered by team, division, position or age.
- **How It Works:** the method, and the integrity checks run on every build.

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
