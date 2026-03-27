from __future__ import annotations

import asyncio
import logging
import os
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
    asyncio.create_task(perform_scan(artists))
    return {"status": "Scan started"}


async def perform_scan(artists: list[str]) -> None:
    async with state.scan_lock:
        state.scanning = True
        state.scan_progress = 0
        state.current_scan_results = {}
        total_artists = len(artists) or 1
        for index, artist in enumerate(artists, start=1):
            artist_path = state.config.music_videos_path / artist
            issues: list[dict[str, str]] = []
            if not artist_path.exists():
                continue
            artist_nfo = artist_path / "artist.nfo"
            if not artist_nfo.exists():
                issues.append({"type": "missing_artist_nfo", "file": "artist.nfo", "path": str(artist_path)})
            artist_jpg = artist_path / "artist.jpg"
            if not artist_jpg.exists() or artist_jpg.stat().st_size < 1000:
                issues.append({"type": "missing_artist_art", "file": "artist.jpg", "path": str(artist_path)})
            video_count = count_artist_videos(artist_path)
            state.current_scan_results[artist] = {"video_count": video_count, "issues": issues}
            state.scan_progress = int((index / total_artists) * 100)
            await state.manager.broadcast({"type": "scan_progress", "progress": state.scan_progress, "artist": artist, "issues": len(issues)})
            await asyncio.sleep(0.05)
        state.last_scan_time = datetime.now()
        state.update_next_run()
        state.scanning = False
        await state.manager.broadcast({"type": "scan_complete", "timestamp": state.last_scan_time.isoformat()})


@app.post("/api/stop")
async def stop_scan() -> dict[str, str]:
    state.scanning = False
    state.scan_progress = 0
    return {"status": "Scan stopped"}


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
    asyncio.create_task(perform_batch_download(state, request.artist, request.videos))
    return {"status": "Download started", "count": len(request.videos)}


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
            await perform_batch_download(state, artist, videos[:5])
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
    asyncio.create_task(run_full_scan())
    return {"status": "Scan started"}


async def run_full_scan() -> None:
    if state.scheduled_scan_running:
        return
    state.scheduled_scan_running = True
    try:
        await perform_scan(list_artist_folders(state.config.music_videos_path))
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
    return {
        "cpu_percent": 0,
        "memory_percent": 0,
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
    if state.config.schedule_enabled:
        state.update_next_run()
        schedule.every(state.config.schedule_interval_hours).hours.do(schedule_scan)
    asyncio.create_task(asyncio.to_thread(schedule_worker))


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=state.config.host, port=state.config.port, reload=False)
