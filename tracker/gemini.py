"""Gemini analysis: hands Gemini the YouTube URL and gets structured JSON back.

Needs GEMINI_API_KEY (free from https://aistudio.google.com/apikey).
Primary path: Gemini watches the video directly (no transcript needed).
Fallback: transcript text via youtube-transcript-api (used for very long videos,
or if the video path fails).
"""

from __future__ import annotations

import json
import os
import time

import requests

from . import ANALYSIS_VERSION, PROMPTS_DIR

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

CATEGORIES = [
    "Portfolio Update", "Buy/Sell Decision", "Stock Deep Dive", "Earnings Reaction",
    "Market Commentary", "Watchlist", "Education", "News", "Q&A / Livestream", "Other",
]
ACTIONS = ["BUY", "ADD", "TRIM", "SELL", "HOLD", "WATCH", "MENTION"]

# OpenAPI-style schema accepted by Gemini's responseSchema.
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "summary": {"type": "STRING"},
        "key_points": {"type": "ARRAY", "items": {"type": "STRING"}},
        "category": {"type": "STRING", "enum": CATEGORIES},
        "topics": {"type": "ARRAY", "items": {"type": "STRING"}},
        "sentiment": {"type": "STRING", "enum": ["bullish", "neutral", "bearish", "mixed"]},
        "market_view": {"type": "STRING"},
        "stock_moves": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "ticker": {"type": "STRING"},
                    "company": {"type": "STRING"},
                    "action": {"type": "STRING", "enum": ACTIONS},
                    "is_own_position": {"type": "BOOLEAN"},
                    "timeframe": {"type": "STRING"},
                    "price": {"type": "STRING"},
                    "position_note": {"type": "STRING"},
                    "rationale": {"type": "STRING"},
                    "timestamp": {"type": "STRING"},
                },
                "required": ["ticker", "company", "action", "is_own_position", "rationale"],
                "propertyOrdering": ["ticker", "company", "action", "is_own_position", "timeframe",
                                     "price", "position_note", "rationale", "timestamp"],
            },
        },
        "portfolio_snapshot": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {"ticker": {"type": "STRING"}, "weight_pct": {"type": "NUMBER"}},
                "required": ["ticker"],
            },
        },
    },
    "required": ["summary", "key_points", "category", "topics", "sentiment", "stock_moves"],
    "propertyOrdering": ["summary", "key_points", "category", "topics", "sentiment",
                         "market_view", "stock_moves", "portfolio_snapshot"],
}


class GeminiError(RuntimeError):
    pass


class QuotaExhausted(GeminiError):
    """Daily free-tier limit hit — stop this run, try again next run."""


class GeminiBusy(GeminiError):
    """Model overloaded (5xx). Temporary — retry on a later run without counting an attempt."""


def _prompt(profile: str, video: dict, notes: str = "") -> str:
    tmpl = (PROMPTS_DIR / f"{profile}.md").read_text(encoding="utf-8")
    text = tmpl.format(title=video["title"], channel=video["channel_title"], published=video["published_at"][:10])
    if notes and notes.strip():
        text += "\n\nNotes about this specific channel:\n" + notes.strip()
    return text


def _call(model: str, parts: list, use_schema: bool = True, low_res: bool = True) -> dict:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiError("GEMINI_API_KEY is not set")
    gen = {"responseMimeType": "application/json"}
    if use_schema:
        gen["responseSchema"] = SCHEMA
    if low_res:
        gen["mediaResolution"] = "MEDIA_RESOLUTION_LOW"  # ~3x fewer tokens; talking-head videos don't need HD frames
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": gen}

    # 429 (rate limit) gets a few waits; 5xx "high demand" gets one quick retry, then we
    # move on and try that video again next run (each 5xx can take minutes to come back).
    delays = {429: [20, 60, 120], "5xx": [30]}
    tries = {429: 0, "5xx": 0}
    while True:
        r = requests.post(ENDPOINT.format(model=model), json=body, timeout=600,
                          headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        if r.status_code == 200:
            return r.json()
        txt = r.text[:500]
        if r.status_code == 429:
            if "per day" in txt.lower() or "PerDay" in txt or "daily" in txt.lower():
                raise QuotaExhausted(txt)
        if r.status_code == 400 and (use_schema or low_res):
            # Some models reject a config field — retry once with the plain config.
            return _call(model, parts, use_schema=False, low_res=False)
        kind = 429 if r.status_code == 429 else "5xx" if r.status_code >= 500 else None
        if kind is not None and tries[kind] < len(delays[kind]):
            time.sleep(delays[kind][tries[kind]])
            tries[kind] += 1
            continue
        if kind == "5xx":
            raise GeminiBusy(f"Gemini {r.status_code} (model busy): {txt[:200]}")
        raise GeminiError(f"Gemini {r.status_code}: {txt}")


def _extract_json(resp: dict) -> dict:
    cands = resp.get("candidates") or []
    if not cands:
        raise GeminiError(f"No candidates (blocked?): {json.dumps(resp.get('promptFeedback', {}))[:300]}")
    parts = cands[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise GeminiError(f"Bad JSON from model: {e}: {text[:200]}") from e


def _normalize(a: dict) -> dict:
    a.setdefault("key_points", [])
    a.setdefault("topics", [])
    a.setdefault("market_view", "")
    a.setdefault("sentiment", "neutral")
    a.setdefault("portfolio_snapshot", [])
    if a.get("category") not in CATEGORIES:
        a["category"] = "Other"
    moves = []
    for m in a.get("stock_moves") or []:
        t = (m.get("ticker") or "").strip().upper().lstrip("$")
        if not t:
            continue
        m["ticker"] = t
        m["action"] = (m.get("action") or "MENTION").upper()
        if m["action"] not in ACTIONS:
            m["action"] = "MENTION"
        for k in ("company", "timeframe", "price", "position_note", "rationale", "timestamp"):
            m[k] = (m.get(k) or "").strip()
        m["is_own_position"] = bool(m.get("is_own_position"))
        moves.append(m)
    a["stock_moves"] = moves
    return a


def get_transcript(video_id: str) -> str:
    from youtube_transcript_api import YouTubeTranscriptApi  # lazy import

    try:  # v1.x API
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en", "en-US", "en-GB"])
        return " ".join(s.text for s in fetched)
    except AttributeError:  # pre-1.0 API
        rows = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US", "en-GB"])
        return " ".join(r["text"] for r in rows)


def analyze_video(video: dict, profile: str, model: str, max_video_minutes: int, notes: str = "") -> dict:
    """Returns {'analysis': {...}, 'method': 'video'|'transcript', 'usage': {...}}."""
    prompt = _prompt(profile, video, notes)
    too_long = video["duration_sec"] > max_video_minutes * 60
    errors = []

    if not too_long:
        try:
            resp = _call(model, [{"fileData": {"fileUri": video["url"]}}, {"text": prompt}])
            return {"analysis": _normalize(_extract_json(resp)), "method": "video",
                    "usage": resp.get("usageMetadata", {}), "version": ANALYSIS_VERSION}
        except (QuotaExhausted, GeminiBusy):
            raise  # the transcript path would hit the same busy model
        except GeminiError as e:
            errors.append(f"video: {e}")

    try:
        transcript = get_transcript(video["id"])
    except Exception as e:  # noqa: BLE001 — many failure types (no captions, IP blocked…)
        errors.append(f"transcript: {type(e).__name__}: {str(e)[:200]}")
        raise GeminiError(" | ".join(errors)) from e

    text = f"{prompt}\n\n(You are reading the transcript, not watching the video.)\n\nTRANSCRIPT:\n{transcript[:400_000]}"
    resp = _call(model, [{"text": text}], low_res=False)
    return {"analysis": _normalize(_extract_json(resp)), "method": "transcript",
            "usage": resp.get("usageMetadata", {}), "version": ANALYSIS_VERSION}
