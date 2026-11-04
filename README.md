# YouTube Channel Tracker

You give it a list of YouTube channels. Every 6 hours it checks them for new uploads, has Gemini watch each new video, and logs a structured summary. For investing channels, the summary includes every stock the creator **bought, added to, trimmed, sold, held or is watching**, with the reasoning and a timestamp link. All of this is published as a searchable dashboard, and a weekly digest goes to your inbox.

```
channels.yaml ──► GitHub Actions (every 6h) ──► YouTube Data API: list new uploads
                                              ──► Gemini: watch video → JSON summary + stock moves
                                              ──► data/videos.json  (the permanent log)
                                              ──► docs/index.html   (dashboard, GitHub Pages)
              GitHub Actions (Mondays) ──────► weekly email digest
```

**Dashboard tabs**
- **Latest moves:** a chronological feed of buys/sells, grouped by day and video. You can filter by action.
- **Stocks:** one row per ticker, showing its current status (Holding, Trimmed, Exited, Watching), the date of the last move, and a colored history strip. Click a ticker to see its full timeline.
- **Videos:** every summary, filterable by category and searchable across titles, summaries, key points and tickers.
- **Channels:** per-channel stats.
- **CSV export:** downloads every stock move, for Excel or Sheets.

To see the layout before setup, open `demo/index.html` (it uses made-up data).

---

## Setup (about 20 minutes, one time)

### 1. Get two free API keys
| Key | Where | Notes |
|---|---|---|
| **YouTube Data API** | [console.cloud.google.com](https://console.cloud.google.com) → New project → *APIs & Services* → *Enable APIs* → "YouTube Data API v3" → *Credentials* → *Create API key* | Free tier is 10,000 units/day. This tool uses about 10. |
| **Gemini API** | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → *Create API key* | Free tier works. Google caps YouTube-URL input at **8 hours of video per day**, and the tool stays under that. |

### 2. Create the GitHub repo
1. Create a new repository on github.com (for example `yt-tracker`) and upload all of these files, keeping the folder structure.
2. **Public or private?** GitHub Pages hosts the dashboard. On a free GitHub account, Pages only works for **public** repos. That means anyone with the link could see the summaries (they're all summaries of public videos). For a private dashboard, GitHub Pro ($4/mo) lets Pages serve from a private repo. You can also skip Pages and download `docs/index.html` from the repo whenever you want to look.

### 3. Add your secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `YOUTUBE_API_KEY` | from step 1 |
| `GEMINI_API_KEY` | from step 1 |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASSWORD` | a Gmail **App Password**: Google Account → Security → 2-Step Verification → App passwords. This is not your normal password. |
| `DIGEST_TO` | where the weekly email goes (comma-separate several addresses) |

Optional, on the **Variables** tab: `DASHBOARD_URL` = your Pages URL, so the email links to the dashboard.

### 4. Turn on the dashboard
Repo → **Settings → Pages** → Source: *Deploy from a branch* → Branch `main`, folder **`/docs`** → Save.
The URL will look like `https://<your-username>.github.io/yt-tracker/`.

### 5. Add your channels
Edit `channels.yaml` on GitHub (the pencil icon), replace the placeholder, and commit:
```yaml
channels:
  - handle: "@TheInvestorChannel"
    profile: stocks          # extracts buys/sells
  - handle: "@SomeOtherChannel"
    profile: general         # summaries only
```

### 6. First run
Repo → **Actions → Update channel report → Run workflow**. Set *limit* to `3` for a quick test. Check the log, then open the dashboard. After that the job runs by itself every 6 hours.

**Backfill timing:** a 6-month backlog for one channel posting about 3×20-minute videos a week is roughly 26 hours of video, so it takes **3–4 days** under the free 8-hour daily limit. Newest videos are processed first, so the latest moves show up on day one.

---

## Day-to-day

| You want to… | Do this |
|---|---|
| Add or remove a channel | Edit `channels.yaml` and commit |
| Force an update now | Actions → *Update channel report* → Run workflow |
| Send the digest now | Actions → *Weekly email digest* → Run workflow |
| See failures | Videos tab (red text), or run `python -m tracker status` |
| Fix a bad summary | `python -m tracker reprocess --video <VIDEO_ID>` and commit |

### Running on your own computer (optional, for tinkering)
```bash
pip install -r requirements.txt
export YOUTUBE_API_KEY=...  GEMINI_API_KEY=...      # Windows PowerShell: $env:YOUTUBE_API_KEY="..."
python -m tracker run --limit 2
python -m tracker report          # rebuild the dashboard only
python -m tracker digest --dry-run   # writes data/last_digest.html
python tests/test_pipeline.py     # tests, no API keys needed
```
If you run locally, commit and push `data/` afterwards so GitHub Actions continues from the same log.

---

## Improving it over time
See **`IMPROVING.md`**. In short:
- **Better summaries:** edit `prompts/stocks.md` or `prompts/general.md`, bump `ANALYSIS_VERSION` in `tracker/__init__.py`, then run `reprocess --stale`.
- **New fields** (price targets, conviction 1–5, etc.): add them to `SCHEMA` in `tracker/gemini.py` and show them in `templates/dashboard.html`.
- **Working with Claude on it:** open the repo in Claude Code, or paste the relevant file here. `IMPROVING.md` explains the architecture.

## Costs
On the free tiers it's $0: GitHub Actions is free for public repos (2,000 min/month on private ones, and each run takes 1–5 min), the YouTube API is free, and the Gemini free tier covers it. If you outgrow the free tier or the 8-hour/day limit, enable billing in AI Studio. Flash models cost cents per video at low media resolution.

## Limits to know
- Gemini only accepts **public** videos, one per request. Members-only and unlisted videos are skipped.
- Videos longer than `max_video_minutes` (default 60) use the transcript instead of the video. YouTube sometimes blocks transcript requests from cloud servers; those videos show as failed and are retried up to 3 times.
- Livestreams are processed after they end. Shorts are skipped.
- **Summaries are AI-generated and can be wrong.** Check the timestamp link before acting on a move. None of this is financial advice.
