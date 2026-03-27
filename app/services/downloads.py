from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

from app.config import AppConfig
from app.services.enrichment import get_artist_context, get_recording_context
from app.services.metadata import clean_song_title, create_video_nfo, slugify, write_artist_nfo
from app.state import AppState


def download_video_with_ytdlp(config: AppConfig, url: str, output_template: str) -> tuple[bool, str]:
    base_command = [
        "yt-dlp",
        "--extractor-args",
        "youtube:player_client=android,mweb,tv_simply;player_skip=webpage,configs",
        "--user-agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "-f",
        "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format",
        "mkv",
        "--remux-video",
        "mkv",
        "--no-write-info-json",
        "--no-write-description",
        "--no-write-thumbnail",
        "--no-write-subs",
        "--no-mtime",
        "--geo-bypass",
        "-o",
        output_template,
        url,
    ]
    attempts: list[list[str]] = [base_command[:]]
    if config.cookies_file.exists():
        attempts.append(base_command[:1] + ["--cookies", str(config.cookies_file)] + base_command[1:])
    errors: list[str] = []
    for command in attempts:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
            if result.returncode == 0:
                return True, "Download successful"
            stderr = (result.stderr or result.stdout or "Download failed").strip()
            errors.append(stderr[:300])
        except subprocess.TimeoutExpired:
            errors.append("Download timeout")
        except Exception as exc:
            errors.append(str(exc))
    return False, " | ".join(errors[:2])


def get_youtube_video_details(config: AppConfig, video_id: str) -> dict[str, Any]:
    if not video_id:
        return {}
    base_command = [
        "yt-dlp",
        "--extractor-args",
        "youtube:player_client=android,mweb,tv_simply;player_skip=webpage,configs",
        "--dump-json",
        "--skip-download",
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    attempts: list[list[str]] = [base_command[:]]
    if config.cookies_file.exists():
        attempts.append(base_command[:1] + ["--cookies", str(config.cookies_file)] + base_command[1:])
    for command in attempts:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)
        except Exception:
            continue
    return {}


async def perform_batch_download(state: AppState, artist: str, videos: list[dict[str, Any]], allow_flagged: bool = False) -> None:
    async with state.download_lock:
        artist_context = await asyncio.to_thread(get_artist_context, state.config, artist)
        if artist_context:
            await asyncio.to_thread(write_artist_nfo, state.config, artist_context)
        filtered_videos = videos if allow_flagged else [video for video in videos if not video.get("is_fake")]
        total = len(filtered_videos)
        processed = 0
        state.download_stopped = False
        if not filtered_videos:
            await state.manager.broadcast({"type": "download_complete", "message": "No eligible videos to download"})
            return
        for video in filtered_videos:
            if state.download_stopped:
                await state.manager.broadcast({"type": "download_stopped", "message": "Download cancelled"})
                break
            processed += 1
            await state.manager.broadcast(
                {
                    "type": "download_progress",
                    "progress": int((processed / total) * 100),
                    "processed": processed,
                    "total": total,
                    "current": video.get("title", ""),
                }
            )
            url = video.get("url")
            title = video.get("title")
            if not url or not title:
                continue
            song_title = clean_song_title(title, artist)
            safe_filename = slugify(song_title)
            artist_dir = state.config.music_videos_path / artist
            artist_dir.mkdir(parents=True, exist_ok=True)
            existing_files = [item for item in artist_dir.iterdir() if item.stem == safe_filename and item.suffix.lower() in {".mkv", ".mp4"}]
            if existing_files:
                await state.manager.broadcast(
                    {"type": "download_log", "message": f"Skipped {song_title} - already exists", "level": "warning"}
                )
                continue
            youtube_metadata = await asyncio.to_thread(get_youtube_video_details, state.config, video.get("id", ""))
            year = ""
            upload_date = str(youtube_metadata.get("upload_date") or video.get("upload_date") or "")
            if len(upload_date) >= 4:
                year = upload_date[:4]
            recording_metadata = await asyncio.to_thread(get_recording_context, state.config, artist, song_title)
            if artist_context.get("genres") and not recording_metadata.get("genres"):
                recording_metadata["genres"] = artist_context["genres"]
            output_template = str(artist_dir / f"{safe_filename}.%(ext)s")
            success, message = await asyncio.to_thread(download_video_with_ytdlp, state.config, url, output_template)
            if success:
                await asyncio.to_thread(
                    create_video_nfo,
                    state.config,
                    artist,
                    str(artist_context.get("musicbrainz_artist_id") or ""),
                    song_title,
                    title,
                    video.get("id", ""),
                    year,
                    str(youtube_metadata.get("channel") or video.get("uploader") or ""),
                    recording_metadata,
                    youtube_metadata,
                )
                await state.manager.broadcast({"type": "download_log", "message": f"Downloaded: {song_title}", "level": "success"})
            else:
                await state.manager.broadcast({"type": "download_log", "message": f"Failed: {song_title} - {message}", "level": "error"})
            await asyncio.sleep(1)
        if not state.download_stopped:
            await state.manager.broadcast({"type": "download_complete", "message": "Download batch complete"})
        state.download_stopped = False
