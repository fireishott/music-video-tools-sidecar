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
    detect_orphans: bool = True
    remove_orphans: bool = False
    detect_duplicates: bool = True
    detect_quality_issues: bool = True
    detect_fake_video_traits: bool = True
    remove_videos_without_metadata: bool = False
    update_stale_stats: bool = True
    upgrade_lower_quality: bool = False
    concurrent_files: int = 4
    max_downloads_per_artist: int = 5


class DownloadRulesUpdate(BaseModel):
    min_resolution: int | None = None
    min_duration: int | None = None
    max_duration: int | None = None
    filter_audio_only: bool | None = None


class DownloadRequest(BaseModel):
    artist: str
    videos: list[dict[str, Any]] = Field(default_factory=list)
    allow_flagged: bool = False


class QueueItemCreate(BaseModel):
    type: str
    path: str
    newName: str | None = None
    artist: str | None = None


class AppStatus(BaseModel):
    running: bool
    progress: int
    results: dict[str, Any]
