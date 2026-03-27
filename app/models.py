from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    artists: list[str] = Field(default_factory=list)
    mode: str = "quick"


class ScheduleConfigUpdate(BaseModel):
    enabled: bool = False
    interval_hours: int = 24
    auto_download: bool = True
    auto_update_stats: bool = True


class DownloadRulesUpdate(BaseModel):
    min_resolution: int | None = None
    min_duration: int | None = None
    max_duration: int | None = None
    filter_audio_only: bool | None = None


class DownloadRequest(BaseModel):
    artist: str
    videos: list[dict[str, Any]] = Field(default_factory=list)


class QueueItemCreate(BaseModel):
    type: str
    path: str
    newName: str | None = None
    artist: str | None = None


class AppStatus(BaseModel):
    running: bool
    progress: int
    results: dict[str, Any]

