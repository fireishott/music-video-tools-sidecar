from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import schedule
import uvicorn
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import load_settings, save_runtime_config
from app.models import AppStatus, DownloadRequest, DownloadRulesUpdate, QueueItemCreate, ScanRequest, ScheduleConfigUpdate
from app.services.downloads import perform_batch_download
from app.services.filesystem import count_artist_videos, disk_usage_percent, list_artist_folders
from app.services.library_scan import run_library_scan
from app.services.metadata import create_artist_nfo
from app.services.youtube import search_youtube_for_artist
from app.state import AppState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("music-video-tools")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Music Video Tools")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

state = AppState(config=load_settings())
MAIN_LOOP: asyncio.AbstractEventLoop | None = None
_LAST_CPU_SAMPLE: tuple[int, int] | None = None


def read_cpu_percent() -> float:
    global _LAST_CPU_SAMPLE
    try:
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            fields = handle.readline().split()
        if len(fields) < 5 or fields[0] != "cpu":
            return 0.0
        values = [int(value) for value in fields[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        current = (idle, total)
        if _LAST_CPU_SAMPLE is None:
            _LAST_CPU_SAMPLE = current
            return 0.0
        previous_idle, previous_total = _LAST_CPU_SAMPLE
        _LAST_CPU_SAMPLE = current
        total_delta = total - previous_total
        idle_delta = idle - previous_idle
        if total_delta <= 0:
            return 0.0
        usage = 100.0 * (1 - (idle_delta / total_delta))
        return round(max(0.0, min(100.0, usage)), 1)
    except Exception:
        return 0.0


def read_memory_percent() -> float:
    try:
        values: dict[str, int] = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if ":" not in line:
                    continue
                key, raw_value = line.split(":", 1)
                amount = raw_value.strip().split()[0]
                values[key] = int(amount)
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", 0)
        if total <= 0:
            return 0.0
        used = total - available
        return round(max(0.0, min(100.0, (used / total) * 100)), 1)
    except Exception:
        return 0.0


def _read_percent_file(candidate: Path) -> float | None:
    try:
        raw_value = candidate.read_text(encoding="utf-8").strip().rstrip("%")
        if not raw_value:
            return None
        return round(max(0.0, min(100.0, float(raw_value))), 1)
    except Exception:
        return None


def _iter_gpu_percent_paths() -> list[Path]:
    candidates: list[Path] = []
    seen: set[Path] = set()
    explicit_paths = (
        Path("/sys/class/drm/card0/gt_busy_percent"),
        Path("/sys/class/drm/card1/gt_busy_percent"),
        Path("/sys/class/drm/card0/device/gpu_busy_percent"),
        Path("/sys/class/drm/card1/device/gpu_busy_percent"),
        Path("/sys/class/drm/card0/engine/rcs0/busy_percent"),
        Path("/sys/class/drm/card1/engine/rcs0/busy_percent"),
    )
    for candidate in explicit_paths:
        if candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)
    drm_root = Path("/sys/class/drm")
    if drm_root.exists():
        patterns = (
            "card*/gt_busy_percent",
            "card*/device/gpu_busy_percent",
            "card*/engine/*/busy_percent",
            "card*/device/tile*/gt*/busy_percent",
            "card*/device/gt*/busy_percent",
        )
        for pattern in patterns:
            for candidate in drm_root.glob(pattern):
                if candidate not in seen:
                    seen.add(candidate)
                    candidates.append(candidate)
    return candidates


def _read_sysfs_gpu_percent() -> tuple[float | None, str | None]:
    for candidate in _iter_gpu_percent_paths():
        if not candidate.exists():
            continue
        value = _read_percent_file(candidate)
        if value is not None:
            return value, str(candidate)
    return None, None


def _extract_busy_values(payload: object) -> list[float]:
    values: list[float] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            if lowered in {"busy", "busy_percent", "value"} and isinstance(value, (int, float)):
                number = float(value)
                if 0.0 <= number <= 100.0:
                    values.append(number)
            values.extend(_extract_busy_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_extract_busy_values(item))
    return values


def _read_intel_gpu_top_percent() -> tuple[float | None, str | None]:
    intel_gpu_top = shutil.which("intel_gpu_top")
    if not intel_gpu_top:
        return None, None
    commands = (
        [intel_gpu_top, "-J", "-s", "100", "-o", "-"],
        [intel_gpu_top, "-J", "-s", "100"],
    )
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=2, check=False)
        except Exception:
            continue
        if result.returncode != 0 or not result.stdout.strip():
            continue
        lines = [line.strip().rstrip(",") for line in result.stdout.splitlines() if line.strip()]
        for line in reversed(lines):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            busy_values = _extract_busy_values(payload)
            if busy_values:
                return round(max(busy_values), 1), "intel_gpu_top"
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            continue
        busy_values = _extract_busy_values(payload)
        if busy_values:
            return round(max(busy_values), 1), "intel_gpu_top"
    return None, None


def read_gpu_percent() -> tuple[float | None, str | None]:
    percent, source = _read_sysfs_gpu_percent()
    if percent is not None:
        return percent, source
    percent, source = _read_intel_gpu_top_percent()
    if percent is not None:
        return percent, source
    return None, None


def log_gpu_telemetry() -> None:
    percent, source = read_gpu_percent()
    if percent is None:
        logger.info("GPU telemetry probe did not find a readable Intel usage source")
        return
    logger.info("GPU telemetry probe detected %s%% usage from %s", percent, source)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request, "app_name": "Music Video Tools"})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/folders")
async def get_folders() -> list[str]:
    return list_artist_folders(state.config.music_videos_path)


@app.get("/api/status", response_model=AppStatus)
async def get_status() -> dict[str, object]:
    return state.status_payload()


@app.post("/api/scan")
async def start_scan(request: ScanRequest) -> dict[str, str]:
    if state.scanning:
        raise HTTPException(status_code=409, detail="Scan already in progress")
    artists = request.artists or list_artist_folders(state.config.music_videos_path)
    state.scan_stop_requested = False
    asyncio.create_task(perform_scan(artists, request.mode == "deep"))
    return {"status": "Scan started"}


async def perform_scan(artists: list[str], apply_maintenance: bool = False) -> None:
    await run_library_scan(state, artists, apply_maintenance=apply_maintenance)


@app.post("/api/stop")
async def stop_scan() -> dict[str, str]:
    state.scan_stop_requested = True
    await state.manager.broadcast({"type": "scan_stopping", "message": "Stop requested for current scan"})
    return {"status": "Scan stop requested"}


@app.post("/api/emergency-stop")
async def emergency_stop() -> dict[str, str]:
    state.scan_stop_requested = True
    state.download_stopped = True
    await state.manager.broadcast({"type": "scan_stopping", "message": "Emergency stop requested"})
    await state.manager.broadcast({"type": "download_stopped", "message": "Emergency stop requested"})
    return {"status": "Emergency stop requested"}


@app.post("/api/download/search")
async def search_downloads(request: Request) -> dict[str, object]:
    payload = await request.json()
    query = (payload.get("query") or "").strip()
    limit = int(payload.get("limit", 25))
    if not query:
        raise HTTPException(status_code=400, detail="No search query")
    artist_name = query.replace(" official music video", "").replace(" official video", "").strip()
    results = await search_youtube_for_artist(state.config, artist_name, limit)
    return {"results": results}


@app.post("/api/download/start")
async def start_download_batch(request: DownloadRequest) -> dict[str, object]:
    if not request.artist or not request.videos:
        raise HTTPException(status_code=400, detail="Missing artist or videos")
    filtered_videos = request.videos if request.allow_flagged else [video for video in request.videos if not video.get("is_fake")]
    if not filtered_videos:
        raise HTTPException(status_code=400, detail="No eligible videos to download")
    asyncio.create_task(perform_batch_download(state, request.artist, filtered_videos, request.allow_flagged))
    return {"status": "Download started", "count": len(filtered_videos)}


@app.post("/api/download/stop")
async def stop_download() -> dict[str, str]:
    state.download_stopped = True
    await state.manager.broadcast({"type": "download_stopped", "message": "Download stopped by user"})
    return {"status": "stopped"}


@app.get("/api/download/rules")
async def get_download_rules() -> dict[str, object]:
    return {
        "min_resolution": state.config.min_video_dimension,
        "min_duration": state.config.min_duration,
        "max_duration": state.config.max_duration,
        "filter_audio_only": state.config.filter_audio_only,
    }


@app.post("/api/download/rules")
async def save_download_rules(update: DownloadRulesUpdate) -> dict[str, str]:
    if update.min_resolution is not None:
        state.config.min_video_dimension = update.min_resolution
    if update.min_duration is not None:
        state.config.min_duration = update.min_duration
    if update.max_duration is not None:
        state.config.max_duration = update.max_duration
    if update.filter_audio_only is not None:
        state.config.filter_audio_only = update.filter_audio_only
    save_runtime_config(state.config)
    return {"status": "success"}


@app.get("/api/artists-with-missing")
async def get_artists_with_missing_videos() -> dict[str, object]:
    missing = []
    for artist in list_artist_folders(state.config.music_videos_path):
        if count_artist_videos(state.config.music_videos_path / artist) == 0:
            missing.append(artist)
    return {"artists": missing, "count": len(missing)}


@app.post("/api/download-missing-all")
async def download_missing_for_all_artists() -> dict[str, object]:
    missing_artists = []
    for artist in list_artist_folders(state.config.music_videos_path):
        if count_artist_videos(state.config.music_videos_path / artist) == 0:
            missing_artists.append(artist)
    if not missing_artists:
        raise HTTPException(status_code=404, detail="No artists with missing videos found")
    asyncio.create_task(perform_missing_downloads(missing_artists))
    return {"status": "Started downloading for missing artists", "count": len(missing_artists)}


async def perform_missing_downloads(artists: list[str]) -> None:
    total = len(artists) or 1
    for index, artist in enumerate(artists, start=1):
        await state.manager.broadcast(
            {"type": "download_progress", "progress": int((index / total) * 100), "processed": index, "total": total, "current": artist}
        )
        results = await search_youtube_for_artist(state.config, artist, 5)
        videos = [video for video in results if not video.get("is_fake")]
        if videos:
            await perform_batch_download(state, artist, videos[:5], False)
        await asyncio.sleep(1)


@app.get("/api/schedule/status")
async def get_schedule_status() -> dict[str, object]:
    return state.schedule_payload()


@app.post("/api/schedule/configure")
async def configure_schedule(update: ScheduleConfigUpdate) -> dict[str, str]:
    state.config.schedule_enabled = update.enabled
    state.config.schedule_interval_hours = update.interval_hours
    state.config.auto_download_missing = update.auto_download
    state.config.auto_update_stats = update.auto_update_stats
    state.config.schedule_detect_orphans = update.detect_orphans
    state.config.schedule_remove_orphans = update.remove_orphans
    state.config.schedule_detect_duplicates = update.detect_duplicates
    state.config.schedule_detect_quality_issues = update.detect_quality_issues
    state.config.schedule_detect_fake_video_traits = update.detect_fake_video_traits
    state.config.schedule_remove_videos_without_metadata = update.remove_videos_without_metadata
    state.config.schedule_update_stale_stats = update.update_stale_stats
    state.config.schedule_upgrade_lower_quality = update.upgrade_lower_quality
    state.config.schedule_concurrent_files = max(1, min(update.concurrent_files, 16))
    state.config.schedule_max_downloads_per_artist = max(1, min(update.max_downloads_per_artist, 20))
    state.update_next_run()
    schedule.clear()
    if state.config.schedule_enabled:
        schedule.every(state.config.schedule_interval_hours).hours.do(schedule_scan)
    save_runtime_config(state.config)
    return {"status": "success"}


@app.post("/api/schedule/run")
async def run_schedule_now() -> dict[str, str]:
    if state.scheduled_scan_running:
        raise HTTPException(status_code=409, detail="Scheduled run already in progress")
    state.scan_stop_requested = False
    asyncio.create_task(run_full_scan())
    return {"status": "Scan started"}


async def run_full_scan() -> None:
    if state.scheduled_scan_running:
        return
    state.scheduled_scan_running = True
    state.scan_stop_requested = False
    try:
        await perform_scan(list_artist_folders(state.config.music_videos_path), apply_maintenance=True)
    finally:
        state.scheduled_scan_running = False


def schedule_scan() -> None:
    if MAIN_LOOP is None:
        logger.warning("schedule requested before main loop was ready")
        return
    MAIN_LOOP.call_soon_threadsafe(lambda: asyncio.create_task(run_full_scan()))


@app.get("/api/queue")
async def get_queue() -> dict[str, object]:
    return {"queue": state.queue_storage}


@app.post("/api/queue")
async def add_to_queue(item: QueueItemCreate) -> dict[str, object]:
    queue_item = {
        "id": len(state.queue_storage),
        "type": item.type,
        "path": item.path,
        "newName": item.newName,
        "artist": item.artist,
    }
    state.queue_storage.append(queue_item)
    return {"queue": state.queue_storage}


@app.post("/api/queue/clear")
async def clear_queue() -> dict[str, object]:
    state.queue_storage = []
    return {"queue": state.queue_storage}


@app.post("/api/queue/execute")
async def execute_queue() -> dict[str, object]:
    results = []
    success_count = 0
    for item in state.queue_storage:
        try:
            item_path = Path(item["path"])
            if item["type"] in {"orphaned_metadata", "orphaned_video"} and item_path.exists():
                item_path.unlink()
                results.append({"success": True, "message": f"Deleted: {item_path.name}"})
                success_count += 1
            elif item["type"] == "missing_artist_nfo" and item_path.exists():
                create_artist_nfo(state.config, item_path.name)
                results.append({"success": True, "message": f"Created artist.nfo for: {item_path.name}"})
                success_count += 1
        except Exception as exc:
            results.append({"success": False, "message": f"Error: {exc}"})
    total = len(results)
    state.queue_storage = []
    return {"success": success_count, "total": total, "results": results}


@app.get("/api/config")
async def get_config() -> dict[str, object]:
    return {
        "enable_musicbrainz": state.config.enable_musicbrainz,
        "enable_youtube_stats": state.config.enable_youtube_stats,
        "enable_featured_artists": state.config.enable_featured_artists,
        "filter_audio_only": state.config.filter_audio_only,
        "min_video_dimension": state.config.min_video_dimension,
        "min_duration": state.config.min_duration,
        "max_duration": state.config.max_duration,
        "lidarr_enabled": state.config.lidarr_enabled,
        "lidarr_url": state.config.lidarr_url,
    }


@app.post("/api/config")
async def save_config(request: Request) -> dict[str, str]:
    payload = await request.json()
    for field in (
        "enable_musicbrainz",
        "enable_youtube_stats",
        "enable_featured_artists",
        "filter_audio_only",
        "lidarr_enabled",
    ):
        if field in payload:
            setattr(state.config, field, payload[field])
    for field in ("min_video_dimension", "min_duration", "max_duration"):
        if field in payload:
            setattr(state.config, field, int(payload[field]))
    if "lidarr_url" in payload:
        state.config.lidarr_url = payload["lidarr_url"]
    save_runtime_config(state.config)
    return {"status": "saved"}


@app.get("/api/system/stats")
async def get_system_stats() -> dict[str, object]:
    uptime = "0:00:00"
    try:
        if os.path.exists("/proc/uptime"):
            with open("/proc/uptime", "r", encoding="utf-8") as handle:
                uptime_seconds = int(float(handle.readline().split()[0]))
            hours = uptime_seconds // 3600
            minutes = (uptime_seconds % 3600) // 60
            seconds = uptime_seconds % 60
            uptime = f"{hours}:{minutes:02d}:{seconds:02d}"
    except Exception:
        pass
    gpu_percent, gpu_source = read_gpu_percent()
    return {
        "cpu_percent": read_cpu_percent(),
        "memory_percent": read_memory_percent(),
        "gpu_percent": gpu_percent,
        "gpu_source": gpu_source,
        "disk_percent": disk_usage_percent(state.config.music_videos_path),
        "uptime": uptime,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await state.manager.connect(websocket)
    try:
        while True:
            await websocket.receive_json()
            await state.manager.broadcast({"type": "pong"})
    except WebSocketDisconnect:
        state.manager.disconnect(websocket)


def schedule_worker() -> None:
    while True:
        try:
            schedule.run_pending()
        except Exception as exc:
            logger.warning("schedule worker error: %s", exc)
        time.sleep(30)


@app.on_event("startup")
async def startup() -> None:
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    log_gpu_telemetry()
    if state.config.schedule_enabled:
        state.update_next_run()
        schedule.every(state.config.schedule_interval_hours).hours.do(schedule_scan)
    asyncio.create_task(asyncio.to_thread(schedule_worker))


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=state.config.host, port=state.config.port, reload=False)
