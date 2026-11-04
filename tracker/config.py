"""Loads channels.yaml and fills in defaults."""

from __future__ import annotations

from dataclasses import dataclass, field

import yaml

from . import CONFIG_PATH

DEFAULTS = {
    "model": "gemini-flash-latest",
    "daily_video_minutes_budget": 450,
    "min_duration_seconds": 180,
    "max_video_minutes": 60,
    "default_backfill_days": 180,
    "max_attempts": 3,
    "report_title": "YouTube Channel Intelligence",
    "timezone": "America/Chicago",
}


@dataclass
class ChannelConfig:
    handle: str | None = None
    id: str | None = None
    url: str | None = None
    profile: str = "general"
    backfill_days: int | None = None
    label: str | None = None
    group: str | None = None  # channels with the same group share one position per ticker
    notes: str | None = None  # channel-specific instructions appended to the prompt

    @property
    def key(self) -> str:
        return self.id or self.handle or self.url or "?"


@dataclass
class Config:
    settings: dict = field(default_factory=dict)
    channels: list[ChannelConfig] = field(default_factory=list)

    def __getattr__(self, name):
        if name in self.settings:
            return self.settings[name]
        raise AttributeError(name)


def load_config(path=CONFIG_PATH) -> Config:
    raw = yaml.safe_load(open(path, encoding="utf-8")) or {}
    settings = {**DEFAULTS, **(raw.get("settings") or {})}
    channels = []
    for entry in raw.get("channels") or []:
        if not isinstance(entry, dict):
            continue
        ch = ChannelConfig(**{k: v for k, v in entry.items() if k in ChannelConfig.__dataclass_fields__})
        if (ch.handle or "").startswith("@REPLACE"):
            continue  # template placeholder
        if ch.profile not in ("stocks", "general"):
            ch.profile = "general"
        channels.append(ch)
    return Config(settings=settings, channels=channels)
