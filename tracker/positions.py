"""Turns per-video stock mentions into a chronological ledger and a 'current status' per ticker."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

# ACCUMULATE counts here so "still adding" shows up in the Last trade column.
TRADE_ACTIONS = {"BUY", "ADD", "ACCUMULATE", "TRIM", "SELL"}

OWNERSHIP_ACTIONS = {"BUY", "ADD", "ACCUMULATE", "TRIM", "SELL", "HOLD"}

def local_date(iso: str, tz: str | None) -> str:
    """YouTube timestamps are UTC; show the date as it was where you live."""
    if not tz:
        return iso[:10]
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return iso[:10]


STATUS_FROM_ACTION = {
    "BUY": "Holding",
    "ADD": "Holding",
    "ACCUMULATE": "Holding (adding)",
    "HOLD": "Holding",
    "TRIM": "Holding (trimmed)",
    "SELL": "Exited",
    "WATCH": "Watching",
    "MENTION": "Mentioned",
}


def flatten_moves(videos: dict, groups: dict | None = None, tz: str | None = None) -> list[dict]:
    """Every stock move from every analysed video, newest first.

    groups maps channel_id → group name, so several channels run by the same
    person share one position per ticker.
    """
    groups = groups or {}
    out = []
    for v in videos.values():
        if not v.get("analysis"):  # includes videos queued for re-analysis (keep old result until replaced)
            continue
        for i, m in enumerate(v["analysis"].get("stock_moves", [])):
            out.append({
                **m,
                "move_id": f"{v['id']}-{i}",
                "video_id": v["id"],
                "video_title": v["title"],
                "video_url": v["url"],
                "channel_id": v["channel_id"],
                "channel_title": v["channel_title"],
                "group": groups.get(v["channel_id"]) or v["channel_title"],
                "date": local_date(v["published_at"], tz),
                "published_at": v["published_at"],
            })
    out.sort(key=lambda m: (m["published_at"], m["move_id"]), reverse=True)
    return out


def ticker_summaries(moves: list[dict]) -> list[dict]:
    """One row per (group, ticker) with current status and history counts."""
    groups: dict[tuple, list] = defaultdict(list)
    for m in moves:
        groups[(m.get("group") or m["channel_title"], m["ticker"])].append(m)

    rows = []
    for (group, ticker), ms in groups.items():
        ms = sorted(ms, key=lambda m: m["published_at"])  # oldest → newest
        latest = ms[-1]

        # Status comes from the latest move that says something about ownership;
        # a later MENTION/WATCH doesn't override an earlier BUY.
        status = "Mentioned"
        last_owned = [m for m in ms if m["action"] in OWNERSHIP_ACTIONS and m.get("is_own_position", True)]
        if last_owned:
            status = STATUS_FROM_ACTION[last_owned[-1]["action"]]
        elif any(m["action"] == "WATCH" for m in ms):
            status = "Watching"

        trades = [m for m in ms if m["action"] in TRADE_ACTIONS and m.get("is_own_position", True)]

        counts = defaultdict(int)
        for m in ms:
            counts[m["action"]] += 1

        rows.append({
            "group": group,
            "channel_id": latest["channel_id"],
            "channel_ids": sorted({m["channel_id"] for m in ms}),
            "channel_title": group,
            "ticker": ticker,
            "company": next((m["company"] for m in reversed(ms) if m.get("company")), ""),
            "status": status,
            "last_action": latest["action"],
            "last_date": latest["date"],
            "last_ownership_action": last_owned[-1]["action"] if last_owned else "",
            "last_ownership_date": last_owned[-1]["date"] if last_owned else "",
            "last_trade_action": trades[-1]["action"] if trades else "",
            "last_trade_date": trades[-1]["date"] if trades else "",
            "first_date": ms[0]["date"],
            "mentions": len(ms),
            "counts": dict(counts),
        })
    rows.sort(key=lambda r: r["last_date"], reverse=True)
    return rows
