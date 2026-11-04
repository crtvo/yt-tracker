"""YouTube Data API v3 helpers: resolve a channel and list its recent uploads.

Needs a free API key in the YOUTUBE_API_KEY environment variable.
Quota use is tiny: ~1 unit per 50 videos listed (default daily quota is 10,000).
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

import requests

API = "https://www.googleapis.com/youtube/v3"


class YouTubeError(RuntimeError):
    pass


def _get(endpoint: str, **params) -> dict:
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise YouTubeError("YOUTUBE_API_KEY is not set")
    params["key"] = key
    r = requests.get(f"{API}/{endpoint}", params=params, timeout=30)
    if r.status_code != 200:
        raise YouTubeError(f"YouTube API {endpoint} failed ({r.status_code}): {r.text[:300]}")
    return r.json()


def _parse_channel_ref(ch) -> dict:
    """Turn a ChannelConfig into the right channels.list filter."""
    if ch.id:
        return {"id": ch.id}
    if ch.handle:
        return {"forHandle": ch.handle if ch.handle.startswith("@") else "@" + ch.handle}
    if ch.url:
        m = re.search(r"youtube\.com/channel/(UC[\w-]{20,})", ch.url)
        if m:
            return {"id": m.group(1)}
        m = re.search(r"youtube\.com/(@[\w.\-]+)", ch.url)
        if m:
            return {"forHandle": m.group(1)}
        m = re.search(r"youtube\.com/(?:user|c)/([\w.\-]+)", ch.url)
        if m:
            return {"forUsername": m.group(1)}
    raise YouTubeError(f"Can't work out which channel this is: {ch}")


def resolve_channel(ch) -> dict:
    data = _get("channels", part="snippet,contentDetails,statistics", **_parse_channel_ref(ch))
    items = data.get("items") or []
    if not items:
        raise YouTubeError(f"Channel not found: {ch.key}")
    it = items[0]
    sn = it["snippet"]
    return {
        "id": it["id"],
        "title": ch.label or sn["title"],
        "handle": sn.get("customUrl", ""),
        "thumbnail": (sn.get("thumbnails", {}).get("default") or {}).get("url", ""),
        "uploads_playlist": it["contentDetails"]["relatedPlaylists"]["uploads"],
        "subscribers": int(it.get("statistics", {}).get("subscriberCount", 0) or 0),
        "profile": ch.profile,
    }


_DUR = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def iso_duration_to_seconds(s: str) -> int:
    m = _DUR.fullmatch(s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def list_recent_videos(channel: dict, since: datetime, max_pages: int = 20) -> list[dict]:
    """Uploads newer than `since`, newest first, with duration and live status."""
    ids: list[str] = []
    token = None
    for _ in range(max_pages):
        params = dict(part="contentDetails", playlistId=channel["uploads_playlist"], maxResults=50)
        if token:
            params["pageToken"] = token
        data = _get("playlistItems", **params)
        stop = False
        for it in data.get("items", []):
            published = it["contentDetails"].get("videoPublishedAt")
            if not published:
                continue  # private / deleted
            if _ts(published) < since:
                stop = True
                continue
            ids.append(it["contentDetails"]["videoId"])
        token = data.get("nextPageToken")
        if stop or not token:
            break

    videos = []
    for i in range(0, len(ids), 50):
        data = _get("videos", part="snippet,contentDetails,liveStreamingDetails", id=",".join(ids[i : i + 50]))
        for v in data.get("items", []):
            sn = v["snippet"]
            thumbs = sn.get("thumbnails", {})
            videos.append({
                "id": v["id"],
                "channel_id": channel["id"],
                "channel_title": channel["title"],
                "title": sn["title"],
                "url": f"https://www.youtube.com/watch?v={v['id']}",
                "published_at": sn["publishedAt"],
                "duration_sec": iso_duration_to_seconds(v["contentDetails"].get("duration", "")),
                "thumbnail": (thumbs.get("medium") or thumbs.get("default") or {}).get("url", ""),
                "live_status": sn.get("liveBroadcastContent", "none"),  # none | live | upcoming
                "description": (sn.get("description") or "")[:1500],
            })
    videos.sort(key=lambda v: v["published_at"], reverse=True)
    return videos


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def backfill_cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)
