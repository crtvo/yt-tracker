"""Command line.

  python -m tracker run                 check channels, analyse new videos, rebuild dashboard
  python -m tracker run --limit 3       same, but analyse at most 3 videos (good for a first test)
  python -m tracker report              rebuild dashboard from saved data only (no API calls)
  python -m tracker digest [--dry-run]  send (or preview) the weekly email
  python -m tracker reprocess --stale   re-analyse videos done with an older prompt version
  python -m tracker reprocess --errors  retry failed videos (resets attempt count)
  python -m tracker reprocess --video ID / --channel "Name"
  python -m tracker status              quick health check
"""

from __future__ import annotations

import argparse
import sys
import time

from . import ANALYSIS_VERSION
from .config import load_config
from .store import Store


def log(*a):
    print(*a, flush=True)


def cmd_run(args) -> int:
    from .gemini import GeminiError, QuotaExhausted, analyze_video
    from .report import write_report
    from .youtube import YouTubeError, backfill_cutoff, list_recent_videos, resolve_channel

    cfg = load_config()
    store = Store()
    if not cfg.channels:
        log("No channels in channels.yaml yet — add one and run again.")
        write_report(store, cfg.report_title)
        return 0

    profiles = {}
    for ch in cfg.channels:
        try:
            info = resolve_channel(ch)
        except YouTubeError as e:
            log(f"!! {ch.key}: {e}")
            continue
        store.channels[info["id"]] = {**store.channels.get(info["id"], {}), **info, "group": ch.group or info["title"]}
        profiles[info["id"]] = ch
        days = ch.backfill_days or cfg.default_backfill_days
        try:
            vids = list_recent_videos(info, backfill_cutoff(days))
        except YouTubeError as e:
            log(f"!! {info['title']}: {e}")
            continue
        for v in vids:
            store.upsert_meta(v)
        store.channels[info["id"]]["videos_listed"] = len(vids)
        log(f"✓ {info['title']}: {len(vids)} uploads in the last {days} days")

    # Build the work queue — newest first across all channels.
    queue = []
    for v in store.videos.values():
        if v["channel_id"] not in profiles or not store.needs_processing(v["id"], cfg.max_attempts):
            continue
        if v.get("live_status") in ("live", "upcoming"):
            continue  # come back once the stream has finished
        if v.get("duration_sec", 0) < cfg.min_duration_seconds:
            store.mark_skipped(v["id"], f"shorter than {cfg.min_duration_seconds}s (Short)")
            continue
        queue.append(v)
    queue.sort(key=lambda v: v["published_at"], reverse=True)
    log(f"{len(queue)} video(s) waiting. Video minutes used today: {store.minutes_used_today():.0f}/{cfg.daily_video_minutes_budget}")

    started, done = time.time(), 0
    for v in queue:
        if args.limit and done >= args.limit:
            break
        if (time.time() - started) / 60 > args.max_runtime:
            log("Runtime limit reached — the rest will be picked up next run.")
            break
        minutes = v["duration_sec"] / 60
        uses_video = minutes <= cfg.max_video_minutes
        if uses_video and store.minutes_used_today() + minutes > cfg.daily_video_minutes_budget:
            log(f"Daily video budget reached — {len(queue) - done} left for tomorrow.")
            break
        log(f"→ [{v['published_at'][:10]}] {v['channel_title']}: {v['title'][:80]} ({minutes:.0f} min)")
        try:
            ch = profiles[v["channel_id"]]
            result = analyze_video(v, ch.profile, cfg.model, cfg.max_video_minutes, ch.notes or "")
            store.mark_ok(v["id"], result, cfg.model)
            if result["method"] == "video":
                store.add_minutes(minutes)
            n = len(result["analysis"]["stock_moves"])
            log(f"   ok via {result['method']} — {n} stock move(s)")
        except QuotaExhausted as e:
            log(f"Gemini daily quota hit — stopping. ({str(e)[:120]})")
            break
        except GeminiError as e:
            store.mark_error(v["id"], str(e))
            log(f"   failed: {str(e)[:200]}")
        done += 1
        store.save()  # save after every video so a crash never loses work
        time.sleep(args.sleep)

    store.save()
    payload = write_report(store, cfg.report_title)
    log(f"Dashboard rebuilt: {len(payload['videos'])} videos, {len(payload['moves'])} stock moves, {len(payload['tickers'])} tickers.")
    return 0


def cmd_report(args) -> int:
    from .report import write_report

    cfg = load_config()
    p = write_report(Store(), cfg.report_title)
    log(f"Dashboard rebuilt: {len(p['videos'])} videos, {len(p['moves'])} moves → docs/index.html")
    return 0


def cmd_digest(args) -> int:
    from .digest import send_digest

    cfg = load_config()
    log(send_digest(Store(), days=args.days, title=cfg.report_title, dry_run=args.dry_run))
    return 0


def cmd_reprocess(args) -> int:
    store = Store()
    n = 0
    for v in store.videos.values():
        hit = (
            (args.video and v["id"] == args.video)
            or (args.channel and args.channel.lower() in v.get("channel_title", "").lower())
            or (args.stale and v.get("status") == "ok" and v.get("analysis_version", 0) < ANALYSIS_VERSION)
            or (args.errors and v.get("status") == "error")
        )
        if hit:
            v["status"], v["attempts"] = "pending", 0
            n += 1
    store.save()
    log(f"{n} video(s) queued for re-analysis. They'll be processed on the next `run` (subject to the daily budget).")
    return 0


def cmd_status(args) -> int:
    cfg = load_config()
    store = Store()
    by = {}
    for v in store.videos.values():
        by[v.get("status", "?")] = by.get(v.get("status", "?"), 0) + 1
    log(f"Channels configured: {len(cfg.channels)} | resolved: {len(store.channels)}")
    log(f"Videos by status: {by}")
    log(f"Video minutes used today: {store.minutes_used_today():.0f}/{cfg.daily_video_minutes_budget}")
    errs = [v for v in store.videos.values() if v.get("status") == "error"][:10]
    for v in errs:
        log(f"  error · {v['title'][:60]} · {v.get('error', '')[:120]}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="tracker")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run")
    r.add_argument("--limit", type=int, default=0, help="max videos to analyse this run")
    r.add_argument("--max-runtime", type=float, default=50, help="minutes before stopping")
    r.add_argument("--sleep", type=float, default=7, help="seconds between Gemini calls (free-tier RPM)")
    r.set_defaults(fn=cmd_run)

    sub.add_parser("report").set_defaults(fn=cmd_report)

    d = sub.add_parser("digest")
    d.add_argument("--days", type=int, default=7)
    d.add_argument("--dry-run", action="store_true")
    d.set_defaults(fn=cmd_digest)

    rp = sub.add_parser("reprocess")
    rp.add_argument("--video")
    rp.add_argument("--channel")
    rp.add_argument("--stale", action="store_true")
    rp.add_argument("--errors", action="store_true")
    rp.set_defaults(fn=cmd_reprocess)

    sub.add_parser("status").set_defaults(fn=cmd_status)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

