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

## 4. Add the Claude API key (writes the daily brief)
1. At console.anthropic.com: add a payment method, then **API Keys → Create Key**; copy it. (Optional: set a monthly spend limit under Billing; the brief uses a few cents a day at most.)
2. Repository **Settings → Secrets and variables → Actions → New repository secret**. Name: `ANTHROPIC_API_KEY`, value: the key. **Add secret**.
   Without a key the page still updates daily, with a plain template brief.

## 5. First run
**Actions** tab → **Daily dashboard update** → **Run workflow**. The first run takes longer (it downloads MoneyPuck's history files once). When it finishes, the page is at:

`https://<your-github-username>.github.io/mammoth-dashboard/`

Bookmark that. From then on it updates every morning by itself.
