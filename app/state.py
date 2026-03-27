from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from fastapi import WebSocket

from app.config import AppConfig


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        stale_connections: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                stale_connections.append(connection)
        for connection in stale_connections:
            self.disconnect(connection)


@dataclass
class AppState:
    config: AppConfig
    manager: ConnectionManager = field(default_factory=ConnectionManager)
    scanning: bool = False
    scan_progress: int = 0
    current_scan_results: dict[str, Any] = field(default_factory=dict)
    scheduled_scan_running: bool = False
    scan_stop_requested: bool = False
    current_scan_artist: str = ""
    scan_issue_count: int = 0
    scan_action_count: int = 0
    scan_artists_completed: int = 0
    scan_total_artists: int = 0
    recent_scan_events: list[str] = field(default_factory=list)
    last_scan_time: datetime | None = None
    next_run_time: datetime | None = None
    queue_storage: list[dict[str, Any]] = field(default_factory=list)
    download_stopped: bool = False
    scan_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    download_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def status_payload(self) -> dict[str, Any]:
        return {
            "running": self.scanning,
            "progress": self.scan_progress,
            "results": self.current_scan_results,
        }

    def schedule_payload(self) -> dict[str, Any]:
        running = self.scheduled_scan_running or self.scanning
        return {
            "enabled": self.config.schedule_enabled,
            "interval_hours": self.config.schedule_interval_hours,
            "auto_download": self.config.auto_download_missing,
            "auto_update_stats": self.config.auto_update_stats,
            "detect_orphans": self.config.schedule_detect_orphans,
            "remove_orphans": self.config.schedule_remove_orphans,
            "detect_duplicates": self.config.schedule_detect_duplicates,
            "detect_quality_issues": self.config.schedule_detect_quality_issues,
            "detect_fake_video_traits": self.config.schedule_detect_fake_video_traits,
            "remove_videos_without_metadata": self.config.schedule_remove_videos_without_metadata,
            "update_stale_stats": self.config.schedule_update_stale_stats,
            "upgrade_lower_quality": self.config.schedule_upgrade_lower_quality,
            "concurrent_files": self.config.schedule_concurrent_files,
            "max_downloads_per_artist": self.config.schedule_max_downloads_per_artist,
            "vaapi_device": self.config.vaapi_device,
            "progress": self.scan_progress,
            "current_artist": self.current_scan_artist,
            "issue_count": self.scan_issue_count,
            "action_count": self.scan_action_count,
            "artists_completed": self.scan_artists_completed,
            "artists_total": self.scan_total_artists,
            "recent_events": self.recent_scan_events[-8:],
            "last_run": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "next_run": self.next_run_time.isoformat() if self.next_run_time else None,
            "running": running,
        }

    def update_next_run(self) -> None:
        if not self.config.schedule_enabled:
            self.next_run_time = None
            return
        base = self.last_scan_time or datetime.now()
        self.next_run_time = base + timedelta(hours=self.config.schedule_interval_hours)
