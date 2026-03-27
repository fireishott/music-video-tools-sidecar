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
        return {
            "enabled": self.config.schedule_enabled,
            "interval_hours": self.config.schedule_interval_hours,
            "auto_download": self.config.auto_download_missing,
            "auto_update_stats": self.config.auto_update_stats,
            "last_run": self.last_scan_time.isoformat() if self.last_scan_time else None,
            "next_run": self.next_run_time.isoformat() if self.next_run_time else None,
            "running": self.scheduled_scan_running,
        }

    def update_next_run(self) -> None:
        if not self.config.schedule_enabled:
            self.next_run_time = None
            return
        base = self.last_scan_time or datetime.now()
        self.next_run_time = base + timedelta(hours=self.config.schedule_interval_hours)

