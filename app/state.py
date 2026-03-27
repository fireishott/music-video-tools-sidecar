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
    scan_progress: float = 0.0
    current_scan_results: dict[str, Any] = field(default_factory=dict)
    scheduled_scan_running: bool = False
    scan_stop_requested: bool = False
    current_scan_artist: str = ""
    scan_issue_count: int = 0
    scan_action_count: int = 0
    scan_artists_completed: int = 0
    scan_total_artists: int = 0
    scan_issue_breakdown: dict[str, int] = field(default_factory=dict)
    recent_scan_events: list[str] = field(default_factory=list)
    schedule_debug_logs: list[str] = field(default_factory=list)
    last_scan_time: datetime | None = None
    next_run_time: datetime | None = None
    scan_started_at: datetime | None = None
    current_artist_started_at: datetime | None = None
    current_artist_progress: float = 0.0
    current_artist_completed_steps: int = 0
    current_artist_total_steps: int = 0
    current_action_label: str = ""
    current_action_detail: str = ""
    current_action_started_at: datetime | None = None
    current_action_progress: float = 0.0
    current_action_completed_steps: int = 0
    current_action_total_steps: int = 0
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
        current_action_eta = self.estimate_eta_seconds(
            self.current_action_started_at,
            self.current_action_progress,
            100.0,
        )
        current_artist_eta = self.estimate_eta_seconds(
            self.current_artist_started_at,
            self.current_artist_progress,
            100.0,
        )
        completed_artists = float(self.scan_artists_completed)
        current_artist_fraction = (self.current_artist_progress / 100.0) if self.current_artist_total_steps else 0.0
        total_scan_eta = self.estimate_eta_seconds(
            self.scan_started_at,
            completed_artists + current_artist_fraction,
            float(self.scan_total_artists or 0),
        )
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
            "lower_quality_action": self.config.schedule_lower_quality_action,
            "concurrent_files": self.config.schedule_concurrent_files,
            "max_downloads_per_artist": self.config.schedule_max_downloads_per_artist,
            "vaapi_device": self.config.vaapi_device,
            "progress": round(self.scan_progress, 1),
            "current_artist": self.current_scan_artist,
            "issue_count": self.scan_issue_count,
            "issue_breakdown": self.scan_issue_breakdown,
            "action_count": self.scan_action_count,
            "artists_completed": self.scan_artists_completed,
            "artists_total": self.scan_total_artists,
            "scan_started_at": self.scan_started_at.isoformat() if self.scan_started_at else None,
            "current_artist_started_at": self.current_artist_started_at.isoformat() if self.current_artist_started_at else None,
            "current_artist_progress": round(self.current_artist_progress, 1),
            "current_artist_completed_steps": self.current_artist_completed_steps,
            "current_artist_total_steps": self.current_artist_total_steps,
            "current_artist_eta_seconds": current_artist_eta,
            "current_action_label": self.current_action_label,
            "current_action_detail": self.current_action_detail,
            "current_action_started_at": self.current_action_started_at.isoformat() if self.current_action_started_at else None,
            "current_action_progress": round(self.current_action_progress, 1),
            "current_action_completed_steps": self.current_action_completed_steps,
            "current_action_total_steps": self.current_action_total_steps,
            "current_action_eta_seconds": current_action_eta,
            "total_eta_seconds": total_scan_eta,
            "recent_events": self.recent_scan_events[-8:],
            "debug_logs": self.schedule_debug_logs[-200:],
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

    @staticmethod
    def estimate_eta_seconds(started_at: datetime | None, completed: float, total: float) -> int | None:
        if started_at is None or total <= 0 or completed <= 0:
            return None
        elapsed = (datetime.now() - started_at).total_seconds()
        if elapsed <= 0:
            return None
        remaining_units = max(total - completed, 0.0)
        if remaining_units <= 0:
            return 0
        rate = completed / elapsed
        if rate <= 0:
            return None
        return max(0, int(remaining_units / rate))

    def append_schedule_event(self, message: str) -> None:
        self.recent_scan_events.append(message)
        self.recent_scan_events = self.recent_scan_events[-25:]

    def append_debug_log(self, message: str) -> None:
        self.schedule_debug_logs.append(message)
        self.schedule_debug_logs = self.schedule_debug_logs[-400:]
