# Art Research Archive — Automated Pipeline (Research Stage Only)

This repo automates Stages 1–3 of the research pipeline:
**Retriever → Researcher → Slack notification for your approval.**

Content Creator (video generation) is a separate, later phase — not included here.

## One-time setup

### 1. Push this folder to a new GitHub repo
```bash
git init
git add .
git commit -m "Initial pipeline setup"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

### 2. Add two repository secrets
Go to your repo → **Settings → Secrets and variables → Actions → New repository secret**

- `NVIDIA_API_KEY` — your key from https://build.nvidia.com/settings/api-keys
- `SLACK_WEBHOOK_URL` — your Incoming Webhook URL from https://api.slack.com/apps

### 3. Confirm the model name
Open `scripts/researcher.py` and check the `NVIDIA_MODEL` variable matches the
exact model string shown on your NVIDIA `/models` catalog page for the model
you want to use (e.g. `nvidia/nemotron-3-super-120b-a12b`).

### 4. Add artworks to the queue
Edit `queue/queue.csv` — one artwork name per row. The workflow picks the
first row without `done` in the `status` column each time it runs.

## Running it

- **Automatically**: the workflow runs once a day at 09:00 UTC (edit the
  `cron` line in `.github/workflows/research-pipeline.yml` to change this).
- **Manually**: go to the repo's **Actions** tab → **Research Pipeline** →
  **Run workflow**. You can optionally type a specific artwork name to
  research immediately, bypassing the queue.

## What happens each run

1. `retriever.py` pulls facts from Wikidata, Wikipedia, and the Met Open
   Access API → writes `archive/<slug>/raw_sources.json`
2. `researcher.py` sends those sources to your chosen NVIDIA model, which
   writes a cited, structured entry → `archive/<slug>/draft_entry.md`
3. `notify_slack.py` posts the draft to your Slack channel
4. The workflow commits both files back into the repo automatically

## After you review in Slack

There's no automated "approve" button yet — for now, review the draft in
Slack or directly in the repo (`archive/<slug>/draft_entry.md`), edit the
file directly in GitHub if needed, and rename or tag it however you like to
mark it approved. A proper approval mechanism (and the Content Creator
stage) can be added once this Research stage is working the way you want.

## Costs

Everything here is free:
- GitHub Actions: free tier covers this easily (a few minutes per run)
- NVIDIA NIM API: free tier, up to 40 requests/minute
- Wikidata / Wikipedia / Met API: free, no key required
- Slack Incoming Webhooks: free on Slack's free plan
