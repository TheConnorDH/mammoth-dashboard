# Utah Mammoth Season Dashboard

An objective, data-only season dashboard for the Utah Mammoth, rebuilt automatically every morning and published with GitHub Pages.

- **Data:** [MoneyPuck.com](https://moneypuck.com/data.htm) (shot-model and player data, free for non-commercial use with credit) and the NHL's public API (results, standings, schedules, box scores, rosters). MoneyPuck files are downloaded fresh each run and are not stored in this repository.
- **Daily job:** `.github/workflows/daily.yml` runs `automation/daily.py` at about 5:45 am Mountain time and again at about 8:00 am if Utah's latest game wasn't in every source yet. Steps: download → update lineup from last game's ice time → build (`Dashboard/build.py`) → write the brief (Claude API, every number checked against the data; plain template if a check fails) → rebuild → integrity checks → publish.
- **If something fails,** the previous page stays up and GitHub emails the repository owner. Each run's report is under the Actions tab.
- **Model and design notes:** `Dashboard/HANDOFF.md`. Setup steps: `SETUP.md`.
