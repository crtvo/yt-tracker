"""End-to-end test with the YouTube and Gemini APIs mocked out.

    python -m pytest tests/ -q        (or)   python tests/test_pipeline.py
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tracker  # noqa: E402
from tracker import store as store_mod, report as report_mod, digest as digest_mod  # noqa: E402

CHANNEL = {"items": [{"id": "UCtest", "snippet": {"title": "Test Investor", "customUrl": "@testinv", "thumbnails": {}},
                      "contentDetails": {"relatedPlaylists": {"uploads": "UUtest"}}, "statistics": {"subscriberCount": "1000"}}]}


def fake_get(endpoint, **p):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    if endpoint == "channels":
        return CHANNEL
    if endpoint == "playlistItems":
        return {"items": [
            {"contentDetails": {"videoId": f"v{i}", "videoPublishedAt": (now - timedelta(days=d)).isoformat().replace("+00:00", "Z")}}
            for i, d in enumerate([1, 3, 10, 400])  # last one is outside the backfill window
        ]}
    if endpoint == "videos":
        durs = {"v0": "PT15M2S", "v1": "PT45S", "v2": "PT1H30M"}  # normal, Short, too long
        return {"items": [
            {"id": vid, "snippet": {"title": f"Video {vid}", "publishedAt": (now - timedelta(days=int(vid[1]) * 3 + 1)).isoformat().replace("+00:00", "Z"),
                                    "thumbnails": {}, "liveBroadcastContent": "none"},
             "contentDetails": {"duration": durs[vid]}}
            for vid in p["id"].split(",")
        ]}
    raise AssertionError(endpoint)


ANALYSIS = {"summary": "He sold TSLA and bought more NVDA.", "key_points": ["Sold TSLA"], "category": "Portfolio Update",
            "topics": ["AI"], "sentiment": "bullish", "market_view": "",
            "stock_moves": [{"ticker": "$tsla", "company": "Tesla", "action": "SELL", "is_own_position": True, "rationale": "Too pricey"},
                            {"ticker": "NVDA", "company": "NVIDIA", "action": "add", "is_own_position": True, "rationale": "Demand"},
                            {"ticker": "", "company": "?", "action": "BUY", "is_own_position": True, "rationale": "x"}]}


def fake_call(model, parts, use_schema=True, low_res=True):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(ANALYSIS)}]}}], "usageMetadata": {"totalTokenCount": 1234}}


def test_full_run():
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "data").mkdir()
        cfg = tmp / "channels.yaml"
        cfg.write_text("settings:\n  min_duration_seconds: 180\n  max_video_minutes: 60\nchannels:\n  - handle: '@testinv'\n    profile: stocks\n")
        with mock.patch.object(store_mod, "DATA_DIR", tmp / "data"), \
             mock.patch.object(report_mod, "DOCS_DIR", tmp / "docs"), \
             mock.patch.object(digest_mod, "DATA_DIR", tmp / "data"), \
             mock.patch("tracker.config.CONFIG_PATH", cfg), \
             mock.patch("tracker.config.load_config.__defaults__", (cfg,)), \
             mock.patch("tracker.youtube._get", side_effect=fake_get), \
             mock.patch("tracker.gemini._call", side_effect=fake_call), \
             mock.patch("tracker.gemini.get_transcript", return_value="transcript text"):
            from tracker.__main__ import main
            assert main(["run", "--sleep", "0"]) == 0

            vids = json.loads((tmp / "data" / "videos.json").read_text())
            assert set(vids) == {"v0", "v1", "v2"}, vids.keys()
            assert vids["v1"]["status"] == "skipped"            # Short
            assert vids["v0"]["status"] == "ok" and vids["v0"]["method"] == "video"
            assert vids["v2"]["status"] == "ok" and vids["v2"]["method"] == "transcript"  # too long → transcript
            moves = vids["v0"]["analysis"]["stock_moves"]
            assert [m["ticker"] for m in moves] == ["TSLA", "NVDA"]  # cleaned, empty ticker dropped
            assert moves[1]["action"] == "ADD"
            state = json.loads((tmp / "data" / "state.json").read_text())
            assert 14 < sum(state["usage"].values()) < 16      # only the video-path minutes counted

            html = (tmp / "docs" / "index.html").read_text()
            assert "/*__DATA__*/null" not in html and '"TSLA"' in html
            assert (tmp / "docs" / "stock_moves.csv").read_text().count("\n") == 5  # header + 4 moves

            # second run: nothing new to do
            assert main(["run", "--sleep", "0"]) == 0
            # reprocess + digest preview
            assert main(["reprocess", "--video", "v0"]) == 0
            assert json.loads((tmp / "data" / "videos.json").read_text())["v0"]["status"] == "pending"
            assert main(["digest", "--dry-run"]) == 0
            assert "Portfolio moves" in (tmp / "data" / "last_digest.html").read_text()
    finally:
        shutil.rmtree(tmp)


def test_busy_model_is_retried_without_using_attempts():
    from tracker.gemini import GeminiBusy
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "data").mkdir()
        cfg = tmp / "channels.yaml"
        cfg.write_text("channels:\n  - handle: '@testinv'\n    profile: stocks\n")
        with mock.patch.object(store_mod, "DATA_DIR", tmp / "data"), \
             mock.patch.object(report_mod, "DOCS_DIR", tmp / "docs"), \
             mock.patch("tracker.config.load_config.__defaults__", (cfg,)), \
             mock.patch("tracker.youtube._get", side_effect=fake_get), \
             mock.patch("tracker.gemini._call", side_effect=GeminiBusy("Gemini 503 (model busy)")):
            from tracker.__main__ import main
            assert main(["run", "--sleep", "0"]) == 0
            vids = json.loads((tmp / "data" / "videos.json").read_text())
            assert vids["v0"]["status"] == "pending" and vids["v0"]["attempts"] == 0
            assert "busy" in vids["v0"]["error"]
    finally:
        shutil.rmtree(tmp)


def test_local_dates():
    from tracker.positions import local_date
    # 9pm Central on Nov 3 is already Nov 4 in UTC
    assert local_date("2026-11-04T03:00:00Z", "America/Chicago") == "2026-11-03"
    assert local_date("2026-11-04T03:00:00Z", None) == "2026-11-04"


def test_positions():
    from tracker.positions import ticker_summaries
    base = {"channel_id": "c", "channel_title": "C", "company": "X", "is_own_position": True}
    ms = [{**base, "ticker": "AAA", "action": "BUY", "date": "2026-01-01", "published_at": "2026-01-01"},
          {**base, "ticker": "AAA", "action": "MENTION", "date": "2026-02-01", "published_at": "2026-02-01"},
          {**base, "ticker": "BBB", "action": "BUY", "date": "2026-01-01", "published_at": "2026-01-01"},
          {**base, "ticker": "BBB", "action": "SELL", "date": "2026-03-01", "published_at": "2026-03-01"},
          {**base, "ticker": "CCC", "action": "WATCH", "is_own_position": False, "date": "2026-03-01", "published_at": "2026-03-01"}]
    rows = {r["ticker"]: r for r in ticker_summaries(ms)}
    assert rows["AAA"]["status"] == "Holding"     # a later mention doesn't erase the buy
    assert rows["BBB"]["status"] == "Exited"
    assert rows["CCC"]["status"] == "Watching"


def test_grouped_channels():
    """Two channels from the same person → one combined position per ticker."""
    from tracker.positions import flatten_moves, ticker_summaries
    def vid(i, cid, date, action):
        return {"id": f"x{i}", "channel_id": cid, "channel_title": cid, "title": "t", "url": "u", "status": "ok",
                "published_at": date, "analysis": {"stock_moves": [
                    {"ticker": "TSLA", "company": "Tesla", "action": action, "is_own_position": True, "rationale": ""}]}}
    videos = {"x1": vid(1, "main", "2026-10-01T00:00:00Z", "BUY"), "x2": vid(2, "react", "2026-10-20T00:00:00Z", "SELL")}
    rows = ticker_summaries(flatten_moves(videos, {"main": "Jeremy", "react": "Jeremy"}))
    assert len(rows) == 1 and rows[0]["status"] == "Exited" and rows[0]["channel_ids"] == ["main", "react"]
    assert len(ticker_summaries(flatten_moves(videos))) == 2  # ungrouped → separate


if __name__ == "__main__":
    test_positions()
    test_grouped_channels()
    test_local_dates()
    test_busy_model_is_retried_without_using_attempts()
    test_full_run()
    print("all tests passed")
