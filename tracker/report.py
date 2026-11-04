"""Builds docs/index.html (the dashboard), docs/data.json and docs/stock_moves.csv."""

from __future__ import annotations

import csv
import json

from . import DOCS_DIR, TEMPLATES_DIR
from .positions import flatten_moves, ticker_summaries
from .store import now_iso


def build_payload(store, title: str, tz: str | None = None) -> dict:
    videos = sorted(store.videos.values(), key=lambda v: v.get("published_at", ""), reverse=True)
    groups = {cid: c.get("group") or c.get("title") for cid, c in store.channels.items()}
    moves = flatten_moves(store.videos, groups, tz)
    return {
        "title": title,
        "generated_at": now_iso(),
        "channels": list(store.channels.values()),
        "videos": [
            {k: v.get(k) for k in ("id", "channel_id", "channel_title", "title", "url", "published_at",
                                   "duration_sec", "thumbnail", "status", "error", "analysis", "method")}
            for v in videos if v.get("status") in ("ok", "error", "pending")
        ],
        "moves": moves,
        "tickers": ticker_summaries(moves),
    }


def write_report(store, title: str, tz: str | None = None) -> dict:
    payload = build_payload(store, title, tz)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    data = json.dumps(payload, ensure_ascii=False)
    (DOCS_DIR / "data.json").write_text(data, encoding="utf-8")

    html = (TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8")
    safe = data.replace("</", "<\\/")  # never let data close the <script> tag
    html = html.replace("/*__DATA__*/null", safe).replace("__TITLE__", _esc(title))
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")
    (DOCS_DIR / ".nojekyll").write_text("")

    with open(DOCS_DIR / "stock_moves.csv", "w", newline="", encoding="utf-8") as f:
        cols = ["date", "channel_title", "ticker", "company", "action", "is_own_position", "price",
                "position_note", "timeframe", "rationale", "video_title", "video_url", "timestamp"]
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(payload["moves"])
    return payload


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
