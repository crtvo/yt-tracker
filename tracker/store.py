"""Plain JSON storage, committed to the repo so every run builds on the last one.

data/videos.json    one record per video (metadata + analysis or error)
data/channels.json  resolved channel info
data/state.json     daily Gemini video-minute usage
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from . import DATA_DIR


def _load(name: str, default):
    p = DATA_DIR / name
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def _save(name: str, obj) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = DATA_DIR / name
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class Store:
    def __init__(self):
        self.videos: dict[str, dict] = _load("videos.json", {})
        self.channels: dict[str, dict] = _load("channels.json", {})
        self.state: dict = _load("state.json", {"usage": {}})

    def save(self):
        _save("videos.json", self.videos)
        _save("channels.json", self.channels)
        # keep only the last 14 days of usage
        usage = self.state.get("usage", {})
        self.state["usage"] = {d: usage[d] for d in sorted(usage)[-14:]}
        _save("state.json", self.state)

    # ── daily video budget ──
    def minutes_used_today(self) -> float:
        return self.state.get("usage", {}).get(today(), 0.0)

    def add_minutes(self, minutes: float):
        u = self.state.setdefault("usage", {})
        u[today()] = round(u.get(today(), 0.0) + minutes, 1)

    # ── videos ──
    def needs_processing(self, vid: str, max_attempts: int) -> bool:
        rec = self.videos.get(vid)
        if rec is None:
            return True
        if rec.get("status") == "ok" or rec.get("status") == "skipped":
            return False
        return rec.get("attempts", 0) < max_attempts

    def upsert_meta(self, video: dict):
        rec = self.videos.setdefault(video["id"], {})
        rec.update({k: v for k, v in video.items() if k != "description"})
        rec.setdefault("status", "pending")
        rec.setdefault("attempts", 0)

    def mark_ok(self, vid: str, result: dict, model: str):
        rec = self.videos[vid]
        rec.update(status="ok", analysis=result["analysis"], method=result["method"],
                   analysis_version=result["version"], model=model, processed_at=now_iso(),
                   tokens=result.get("usage", {}).get("totalTokenCount"))
        rec.pop("error", None)
        rec["attempts"] = rec.get("attempts", 0) + 1

    def mark_error(self, vid: str, err: str):
        rec = self.videos[vid]
        rec.update(status="error", error=err[:600], last_attempt_at=now_iso())
        rec["attempts"] = rec.get("attempts", 0) + 1

    def mark_deferred(self, vid: str, reason: str):
        """Temporary problem (model busy). Keep it queued; don't use up an attempt."""
        rec = self.videos[vid]
        rec.update(status="pending", error=reason[:300], last_attempt_at=now_iso())

    def mark_skipped(self, vid: str, reason: str):
        rec = self.videos[vid]
        rec.update(status="skipped", error=reason)
