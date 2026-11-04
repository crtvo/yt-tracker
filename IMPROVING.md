# Improving the tracker

This file is for you, and for any AI assistant you hand the repo to (Claude Code reads it automatically if you rename or copy it to `CLAUDE.md`).

## Architecture in one screen

| File | Job |
|---|---|
| `channels.yaml` | Channel list + settings (model, daily budget, Shorts cutoff, backfill window) |
| `tracker/youtube.py` | YouTube Data API: resolve a handle/URL → channel → uploads playlist → videos with durations |
| `tracker/gemini.py` | Sends the YouTube URL to Gemini with `prompts/<profile>.md` and the JSON `SCHEMA`. Transcript fallback. Cleans the output (`_normalize`) |
| `tracker/store.py` | `data/videos.json` (log), `data/channels.json`, `data/state.json` (daily minute budget) |
| `tracker/positions.py` | Flattens moves; derives per-ticker status (Holding / Trimmed / Exited / Watching / Mentioned) |
| `tracker/report.py` | Injects the data into `templates/dashboard.html` → `docs/index.html`, plus `docs/data.json` and `docs/stock_moves.csv` |
| `tracker/digest.py` | Weekly HTML email |
| `tracker/__main__.py` | CLI: `run`, `report`, `digest`, `reprocess`, `status` |
| `templates/dashboard.html` | Single-file dashboard, vanilla JS, no build step. Data is embedded as `const DATA` |
| `tests/test_pipeline.py` | End-to-end test with APIs mocked. Run it after every change |
| `scripts/make_demo.py` | Rebuilds `demo/index.html` with fake data, for checking the UI |

**Data contract:** a video record = YouTube metadata + `status` (pending/ok/error/skipped) + `analysis` (matches `SCHEMA`) + `analysis_version`, `model`, `method`.

## The improvement loop
1. Spot a problem in the dashboard (wrong action, missed ticker, summary too vague).
2. Fix the **prompt** first (`prompts/stocks.md`). Most quality issues are prompt issues.
3. Re-run one video to check: `python -m tracker reprocess --video ID && python -m tracker run --limit 1`.
4. When it looks right, bump `ANALYSIS_VERSION` in `tracker/__init__.py`, then run `python -m tracker reprocess --stale`. Older videos re-run gradually within the daily budget.
5. Run `python tests/test_pipeline.py` before committing code changes.

## Ideas backlog (roughly by value)
- **Price on the date of the move:** pull the closing price (Finnhub or Alpha Vantage free tier) for each BUY/SELL date, then show "since he bought: +12%". This turns the log into a scorecard of the creator's calls.
- **Portfolio reconstruction:** when a video shows full holdings (`portfolio_snapshot`), treat it as ground truth and show "estimated current portfolio" with weights.
- **Conviction + price target fields:** add `conviction` (1–5) and `price_target` to `SCHEMA` and the prompt.
- **Cross-channel consensus:** a view of tickers that several channels bought in the same 30 days.
- **Alerts:** an immediate email or phone push when a tracked channel posts a BUY/SELL, instead of waiting for the weekly digest.
- **Ticker validation:** check tickers against a symbol list so a mis-heard "NVIDIA → NVDIA" gets flagged.
- **Ask-the-archive:** a "chat with all summaries" page (send `docs/data.json` to Gemini with a question).
- **Google Sheet sync:** append each move to a sheet for pivots (gspread + service account).
- **Hook into Alpha Engine:** export `stock_moves.csv` into your scanner's watchlist.

## Gotchas
- Gemini model names change often. `gemini-flash-latest` follows Google's current Flash model. Pin an ID in `channels.yaml` if results start drifting.
- Newer Gemini models reject `temperature`/`top_p`, so the code doesn't send them.
- The daily 8-hour YouTube cap is tracked in UTC days, in `data/state.json`.
- `_call()` retries once without `responseSchema`/`mediaResolution` if a model returns HTTP 400 for them.
