# One-time setup (about 20 minutes)

## 1. Create the repository
1. On github.com: **+** (top right) → **New repository**. Name it e.g. `mammoth-dashboard`. Choose **Public** (free GitHub Pages needs a public repository). Don't add a README. **Create repository**.
2. On the empty repository page, click **uploading an existing file**.
3. Open the `github-repo` folder from Claude in Finder/Explorer and drag **everything inside it** onto the upload area.
   - Mac: press **Cmd + Shift + .** in Finder first so the hidden `.github` folder shows, and include it.
   - Windows: hidden items are shown with View → Show → Hidden items.
4. **Commit changes**.
5. Check that the file `.github/workflows/daily.yml` exists in the repository. If it didn't upload: **Add file → Create new file**, type the name `.github/workflows/daily.yml`, paste the contents of `workflow-daily.yml` from the folder, and commit.

## 2. Turn on the website
Repository **Settings → Pages → Build and deployment → Source: GitHub Actions**.

## 3. Let the daily job save its progress
**Settings → Actions → General → Workflow permissions → Read and write permissions → Save.**

## 4. Connect Claude (writes the daily brief) — no stored key
Uses Workload Identity Federation: each run, GitHub proves which repository and branch it is, and Anthropic hands back a token that expires in minutes. Nothing long-lived is stored.
1. At platform.claude.com, make sure billing has a payment method (the brief costs a few cents a day at most; a monthly spend limit is optional under Billing).
2. **Settings → Workload identity → Connect workload → GitHub Actions.** In the wizard:
   - Restrict it to this repository's main branch: subject prefix `repo:<your-username>/mammoth-dashboard:ref:refs/heads/main`, and the claim `repository_owner` = `<your-username>`.
   - Audience: `https://api.anthropic.com`.
   - Keep the short token lifetime (600 seconds is plenty).
3. The wizard shows a federation rule ID (`fdrl_...`), a service account ID (`svac_...`) and a workspace ID (`wrkspc_...`). Your organization ID is on Settings → Organization.
4. In the GitHub repository: **Settings → Secrets and variables → Actions → Variables tab → New repository variable**, four times:
   - `ANTHROPIC_FEDERATION_RULE_ID`
   - `ANTHROPIC_ORGANIZATION_ID`
   - `ANTHROPIC_SERVICE_ACCOUNT_ID`
   - `ANTHROPIC_WORKSPACE_ID`
   (These are identifiers, not passwords; only runs of this repo's main branch can use them.)

If you'd rather use an API key instead: create one with a 1-year expiry, save it as the repository **secret** `ANTHROPIC_API_KEY`, and set a calendar reminder to replace it. When a key expires the page keeps updating with the plain template brief, and the run summary shows a warning.

Without either, the page still updates daily with the template brief.

## 5. First run
**Actions** tab → **Daily dashboard update** → **Run workflow**. The first run takes longer (it downloads MoneyPuck's history files once). When it finishes, the page is at:

`https://<your-github-username>.github.io/mammoth-dashboard/`

Bookmark that. From then on it updates every morning by itself.

## 6. On-time morning updates (outside scheduler, about 10 minutes)
GitHub's own schedule is best-effort and often starts runs hours late. A free outside scheduler presses **Run workflow** at the right times instead; GitHub's schedule stays as a backup.

**A. A token that can only start this repository's workflow**
1. github.com → your profile picture → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. Name: `mammoth-scheduler`. Expiration: the longest offered (set a calendar reminder to renew it). Repository access: **Only select repositories** → `mammoth-dashboard`.
3. Permissions → Repository permissions → **Actions: Read and write** (nothing else).
4. **Generate token** and copy it (it starts with `github_pat_`).

**B. Four jobs at cron-job.org** (free account). For each: **Create cronjob**, then
- URL: `https://api.github.com/repos/<your-username>/mammoth-dashboard/actions/workflows/daily.yml/dispatches`
- Schedule: custom, every day, at the time below; time zone **America/Denver** (handles daylight saving)
- Advanced: request method **POST**; headers
  - `Authorization`: `Bearer <the token>`
  - `Accept`: `application/vnd.github+json`
  - `X-GitHub-Api-Version`: `2022-11-28`
- Request body:

| Time (Mountain) | Body |
|---|---|
| 2:17 am | `{"ref":"main","inputs":{"attempt":"early"}}` |
| 3:47 am | `{"ref":"main","inputs":{"attempt":"early"}}` |
| 5:17 am | `{"ref":"main","inputs":{"attempt":"early"}}` |
| 6:47 am | `{"ref":"main","inputs":{"attempt":"final"}}` |

A successful call returns status **204** (cron-job.org shows it in the job history) and a run appears under **Actions** within seconds. Early attempts publish only once Utah's last game is in every data source; the final one publishes with whatever is available; once the day is published, later attempts (including GitHub's own late ones) stop after about 20 seconds.

The **Run workflow** button still works as before: leave "attempt" on **manual** to rebuild and publish right away.
