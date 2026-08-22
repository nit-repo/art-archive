# Art Research Archive — Automated Pipeline

This repo automates the pipeline from artwork name to a reel-ready content brief:
**Retriever → Researcher → Brief Writer → Slack notification for your approval.**

The Researcher produces a fact-checked, fully cited archive entry. The Brief Writer
turns that entry into a production-ready short-form video brief — hook, beat sheet,
voiceover, on-screen captions, visual assets and a do-not-claim list. Slack shows you
the **brief** (that being the thing you'd actually produce), with the cited entry
linked underneath for checking the receipts.

Video rendering itself is still a separate, later phase — not included here.

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
The model is read from the `NVIDIA_MODEL` environment variable, defaulting to the
value in `scripts/researcher.py`. Check it matches the exact model string shown on
your NVIDIA `/models` catalog page.

**Important:** reasoning models on this endpoint default to thinking **on** and emit
their chain-of-thought into the response body — the first live run spent an entire
8192-token budget reasoning and never reached the entry. The pipeline therefore sends
`enable_thinking: false` explicitly, strips any reasoning that still arrives, retries
once at double the budget if the model runs out of tokens, and then *verifies* every
required section is present — failing the run rather than committing a half-finished
draft. Set `ENABLE_THINKING=true` to opt back in (budget roughly 3x the tokens).

Tunable environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `NVIDIA_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` | Model for both AI stages |
| `ENABLE_THINKING` | `false` | Let the model emit chain-of-thought before answering |
| `RESEARCHER_MAX_TOKENS` | `8192` | Token budget for the archive entry |
| `BRIEF_MAX_TOKENS` | `8192` | Token budget for the reel brief |
| `REEL_RUNTIME_SECONDS` | `45` | Target runtime; drives the VO word budget |

### 4. Add artworks to the queue
Edit `queue/queue.csv` — one artwork name per row. The workflow picks the first
row without `done` in the `status` column, and marks it `done` (with a
`completed_at` timestamp) after a successful run, so the queue advances by itself.
When every row is done the scheduled run fails loudly rather than silently
re-researching the last entry.

## Running it

- **Automatically**: the workflow runs once a day at 09:00 UTC (edit the
  `cron` line in `.github/workflows/research-pipeline.yml` to change this).
- **Manually**: go to the repo's **Actions** tab → **Research Pipeline** →
  **Run workflow**. You can optionally type a specific artwork name to
  research immediately, bypassing the queue.

## What happens each run

1. `retriever.py` pulls facts from Wikidata, Wikipedia, and the Met Open Access
   API → writes `archive/<slug>/raw_sources.json`. Met results are matched against
   the artwork title before being trusted, so an unrelated painting can't slip in
   as a source. Image assets from Wikipedia and the Met are preserved here.
2. `researcher.py` sends those sources to your chosen NVIDIA model, which writes a
   cited, structured entry → `archive/<slug>/draft_entry.md`
3. `brief_writer.py` turns that entry into a reel brief →
   `archive/<slug>/content_brief.md`. It may shape the narrative but may not
   introduce a fact the archive entry doesn't already carry.
4. `notify_slack.py` posts the brief — with the artwork image — to your Slack channel
5. The workflow commits the files and the updated queue back into the repo

## Running the tests

The pipeline's parsing, filtering and validation logic is covered by offline
unit tests — no network or API key needed:

```bash
python -m unittest discover -s tests -v
```

They also run in CI on every push (`.github/workflows/tests.yml`).

## After you review in Slack

There's no automated "approve" button yet — for now, review the brief in Slack or
directly in the repo (`archive/<slug>/content_brief.md`), edit it in GitHub if
needed, and rename or tag it however you like to mark it approved. A proper
approval mechanism (and the rendering stage) can be added once this is working
the way you want.

Section 6 of every brief, **Do Not Claim**, is the accuracy guardrail: it lists
what a producer must not say, drawn from the gaps and disputes in the cited entry.
Read it before producing.

## Costs

Everything here is free:
- GitHub Actions: free tier covers this easily (a few minutes per run)
- NVIDIA NIM API: free tier, up to 40 requests/minute
- Wikidata / Wikipedia / Met API: free, no key required
- Slack Incoming Webhooks: free on Slack's free plan
