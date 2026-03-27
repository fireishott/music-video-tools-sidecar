from __future__ import annotations

import asyncio
import subprocess
from typing import Any

from app.config import AppConfig
from app.services.metadata import clean_song_title, create_artist_nfo, create_video_nfo, slugify
from app.state import AppState


def download_video_with_ytdlp(config: AppConfig, url: str, output_template: str) -> tuple[bool, str]:
    command = [
        "yt-dlp",
        "--user-agent",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "-f",
        "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
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
    if config.cookies_file.exists():
        command[1:1] = ["--cookies", str(config.cookies_file)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
        if result.returncode == 0:
            return True, "Download successful"
        stderr = (result.stderr or result.stdout or "Download failed").strip()
        return False, stderr[:200]
    except subprocess.TimeoutExpired:
        return False, "Download timeout"
    except Exception as exc:
        return False, str(exc)


async def perform_batch_download(state: AppState, artist: str, videos: list[dict[str, Any]]) -> None:
    async with state.download_lock:
        total = len(videos)
        processed = 0
        state.download_stopped = False
        for video in videos:
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
            if video.get("is_fake") and state.config.filter_audio_only:
                await state.manager.broadcast(
                    {
                        "type": "download_log",
                        "message": f"Skipped {title} - {video.get('fake_reason', 'Audio-only')}",
                        "level": "warning",
                    }
                )
                continue
            song_title = clean_song_title(title, artist)
            safe_filename = slugify(song_title)
            artist_dir = state.config.music_videos_path / artist
            artist_dir.mkdir(parents=True, exist_ok=True)
            artist_nfo_path = artist_dir / "artist.nfo"
            if not artist_nfo_path.exists():
                create_artist_nfo(state.config, artist)
            existing_files = [item for item in artist_dir.iterdir() if item.stem == safe_filename and item.suffix.lower() in {".mkv", ".mp4"}]
            if existing_files:
                await state.manager.broadcast(
                    {"type": "download_log", "message": f"Skipped {song_title} - already exists", "level": "warning"}
                )
                continue
            year = ""
            upload_date = video.get("upload_date") or ""
            if len(upload_date) >= 4:
                year = upload_date[:4]
            output_template = str(artist_dir / f"{safe_filename}.%(ext)s")
            success, message = await asyncio.to_thread(download_video_with_ytdlp, state.config, url, output_template)
            if success:
                create_video_nfo(
                    state.config,
                    artist=artist,
                    artist_mbid=None,
                    song_title=song_title,
                    original_title=title,
                    video_id=video.get("id", ""),
                    year=year,
                    channel=video.get("uploader", ""),
                )
                await state.manager.broadcast({"type": "download_log", "message": f"Downloaded: {song_title}", "level": "success"})
            else:
                await state.manager.broadcast({"type": "download_log", "message": f"Failed: {song_title} - {message}", "level": "error"})
            await asyncio.sleep(1)
        if not state.download_stopped:
            await state.manager.broadcast({"type": "download_complete", "message": "Download batch complete"})
        state.download_stopped = False

