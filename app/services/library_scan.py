from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path

from app.services.downloads import get_youtube_video_details, perform_batch_download
from app.services.filesystem import list_artist_folders
from app.services.metadata import clean_song_title, extract_youtube_id_from_nfo, nfo_stats_need_refresh, sanitize_filename, update_video_nfo_stats
from app.services.visual_analysis import analyze_visual_profile
from app.services.youtube import search_youtube_for_artist
from app.state import AppState

VIDEO_EXTENSIONS = {".mkv", ".mp4"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
LYRIC_KEYWORDS = ("lyric", "lyrics")


def normalize_media_name(value: str) -> str:
    cleaned = sanitize_filename(value)
    return "".join(ch.lower() for ch in cleaned if ch.isalnum())


def probe_media_file(path: Path) -> dict[str, object]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
    except Exception:
        return {}
    if result.returncode != 0 or not result.stdout:
        return {}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}
    streams = payload.get("streams", []) or []
    format_info = payload.get("format", {}) or {}
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})

    def parse_rate(value: str) -> float:
        if not value or value in {"0/0", "N/A"}:
            return 0.0
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            if denominator and float(denominator):
                return float(numerator) / float(denominator)
            return 0.0
        return float(value)

    return {
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "video_codec": video_stream.get("codec_name") or "",
        "audio_codec": audio_stream.get("codec_name") or "",
        "video_bitrate": int(video_stream.get("bit_rate") or 0),
        "audio_bitrate": int(audio_stream.get("bit_rate") or 0),
        "duration": float(format_info.get("duration") or 0),
        "fps": round(parse_rate(str(video_stream.get("avg_frame_rate") or "")), 2),
    }


def collect_library_duplicate_maps(root: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    by_title: dict[str, list[str]] = {}
    by_youtube_id: dict[str, list[str]] = {}
    for artist in list_artist_folders(root):
        artist_path = root / artist
        for item in artist_path.iterdir():
            if item.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            key = normalize_media_name(item.stem)
            by_title.setdefault(key, []).append(str(item))
        for nfo_path in artist_path.glob("*.nfo"):
            if nfo_path.name.lower() == "artist.nfo":
                continue
            youtube_id = extract_youtube_id_from_nfo(nfo_path)
            if youtube_id:
                by_youtube_id.setdefault(youtube_id, []).append(str(nfo_path))
    return by_title, by_youtube_id


async def inspect_video_file(state: AppState, path: Path, semaphore: asyncio.Semaphore) -> dict[str, object]:
    async with semaphore:
        return await asyncio.to_thread(probe_media_file, path)


async def inspect_visual_profile(state: AppState, path: Path, duration: float, semaphore: asyncio.Semaphore) -> dict[str, object]:
    async with semaphore:
        return await asyncio.to_thread(analyze_visual_profile, path, duration, state.config.vaapi_device)


async def run_library_scan(state: AppState, artists: list[str], apply_maintenance: bool = False) -> None:
    async with state.scan_lock:
        state.scanning = True
        state.scan_progress = 0
        state.current_scan_results = {}
        state.current_scan_artist = ""
        state.scan_issue_count = 0
        state.scan_action_count = 0
        state.scan_artists_completed = 0
        state.scan_total_artists = len(artists)
        state.recent_scan_events = []
        total_artists = len(artists) or 1
        state.current_scan_artist = "Indexing library..."
        state.recent_scan_events.append("Indexing library and duplicate maps before artist scan")
        await state.manager.broadcast(
            {
                "type": "scan_progress",
                "progress": 0,
                "artist": "Indexing library...",
                "issues": 0,
                "actions": 0,
                "downloads_added": 0,
                "artist_index": 0,
                "artist_total": total_artists,
                "issue_total": 0,
                "action_total": 0,
                "event": "Indexing library and duplicate maps before artist scan",
            }
        )
        duplicate_titles, duplicate_youtube_ids = await asyncio.to_thread(collect_library_duplicate_maps, state.config.music_videos_path)
        semaphore = asyncio.Semaphore(max(1, min(state.config.schedule_concurrent_files, 16)))

        try:
            for index, artist in enumerate(artists, start=1):
                if state.scan_stop_requested:
                    await state.manager.broadcast(
                        {
                            "type": "scan_stopped",
                            "message": "Scan stopped by user",
                            "issue_total": state.scan_issue_count,
                            "action_total": state.scan_action_count,
                        }
                    )
                    break
                state.current_scan_artist = artist
                artist_result = await inspect_artist_folder(
                    state,
                    artist,
                    semaphore,
                    duplicate_titles,
                    duplicate_youtube_ids,
                    apply_maintenance,
                )
                state.current_scan_results[artist] = artist_result
                state.scan_progress = int((index / total_artists) * 100)
                state.scan_artists_completed = index
                state.scan_issue_count += len(artist_result.get("issues", []))
                state.scan_action_count += len(artist_result.get("actions", []))
                event_message = (
                    f"{artist}: {len(artist_result.get('issues', []))} issue(s), "
                    f"{len(artist_result.get('actions', []))} action(s), "
                    f"{artist_result.get('downloads_added', 0)} download(s)"
                )
                state.recent_scan_events.append(event_message)
                state.recent_scan_events = state.recent_scan_events[-25:]
                await state.manager.broadcast(
                    {
                        "type": "scan_progress",
                        "progress": state.scan_progress,
                        "artist": artist,
                        "issues": len(artist_result.get("issues", [])),
                        "actions": len(artist_result.get("actions", [])),
                        "downloads_added": artist_result.get("downloads_added", 0),
                        "artist_index": index,
                        "artist_total": total_artists,
                        "issue_total": state.scan_issue_count,
                        "action_total": state.scan_action_count,
                        "event": event_message,
                    }
                )
            if not state.scan_stop_requested:
                state.last_scan_time = datetime.now()
                state.update_next_run()
                await state.manager.broadcast(
                    {
                        "type": "scan_complete",
                        "timestamp": state.last_scan_time.isoformat(),
                        "issue_total": state.scan_issue_count,
                        "action_total": state.scan_action_count,
                        "artist_total": total_artists,
                    }
                )
        finally:
            state.scanning = False
            state.scan_stop_requested = False
            state.current_scan_artist = ""


async def inspect_artist_folder(
    state: AppState,
    artist: str,
    semaphore: asyncio.Semaphore,
    duplicate_titles: dict[str, list[str]],
    duplicate_youtube_ids: dict[str, list[str]],
    apply_maintenance: bool,
) -> dict[str, object]:
    artist_path = state.config.music_videos_path / artist
    issues: list[dict[str, str]] = []
    actions: list[str] = []
    if not artist_path.exists():
        return {"video_count": 0, "issues": issues, "actions": actions}
    if state.scan_stop_requested:
        return {"video_count": 0, "issues": issues, "actions": ["Scan stopped before artist processing completed"]}

    artist_nfo = artist_path / "artist.nfo"
    if not artist_nfo.exists():
        issues.append({"type": "missing_artist_nfo", "file": "artist.nfo", "path": str(artist_path)})
    artist_jpg = artist_path / "artist.jpg"
    if not artist_jpg.exists() or artist_jpg.stat().st_size < 1000:
        issues.append({"type": "missing_artist_art", "file": "artist.jpg", "path": str(artist_path)})

    items = list(artist_path.iterdir())
    videos = [item for item in items if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS]
    nfos = [item for item in items if item.is_file() and item.suffix.lower() == ".nfo" and item.name.lower() != "artist.nfo"]
    images = [item for item in items if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS and item.name.lower() != "artist.jpg"]
    video_stems = {item.stem: item for item in videos}

    for nfo_path in nfos:
        if state.scan_stop_requested:
            return {"video_count": len(videos), "issues": issues, "actions": actions}
        if nfo_path.stem not in video_stems and state.config.schedule_detect_orphans:
            issues.append({"type": "orphaned_metadata", "file": nfo_path.name, "path": str(nfo_path)})
            if apply_maintenance and state.config.schedule_remove_orphans:
                nfo_path.unlink(missing_ok=True)
                actions.append(f"Removed orphaned metadata: {nfo_path.name}")

    for image_path in images:
        if state.scan_stop_requested:
            return {"video_count": len(videos), "issues": issues, "actions": actions}
        if image_path.stem not in video_stems and state.config.schedule_detect_orphans:
            issues.append({"type": "orphaned_art", "file": image_path.name, "path": str(image_path)})
            if apply_maintenance and state.config.schedule_remove_orphans:
                image_path.unlink(missing_ok=True)
                actions.append(f"Removed orphaned artwork: {image_path.name}")

    video_probe_tasks = {
        video_path: asyncio.create_task(inspect_video_file(state, video_path, semaphore))
        for video_path in videos
        if state.config.schedule_detect_quality_issues or state.config.schedule_detect_fake_video_traits
    }
    probe_results = {path: await task for path, task in video_probe_tasks.items()}
    visual_tasks = {
        video_path: asyncio.create_task(
            inspect_visual_profile(state, video_path, float((probe_results.get(video_path, {}) or {}).get("duration") or 0), semaphore)
        )
        for video_path in videos
        if state.config.schedule_detect_fake_video_traits and probe_results.get(video_path)
    }
    visual_results = {path: await task for path, task in visual_tasks.items()}

    for video_path in videos:
        if state.scan_stop_requested:
            actions.append("Scan stopped during file analysis")
            return {
                "video_count": len(videos),
                "issues": issues,
                "actions": actions,
                "downloads_added": 0,
            }
        nfo_path = artist_path / f"{video_path.stem}.nfo"
        title_key = normalize_media_name(video_path.stem)
        if not nfo_path.exists():
            issues.append({"type": "missing_video_nfo", "file": nfo_path.name, "path": str(video_path)})
            if apply_maintenance and state.config.schedule_remove_videos_without_metadata:
                video_path.unlink(missing_ok=True)
                thumb_path = artist_path / f"{video_path.stem}.jpg"
                thumb_path.unlink(missing_ok=True)
                actions.append(f"Removed video without metadata: {video_path.name}")
                continue

        if state.config.schedule_detect_duplicates and len(duplicate_titles.get(title_key, [])) > 1:
            issues.append({"type": "possible_duplicate_title", "file": video_path.name, "path": str(video_path)})

        if nfo_path.exists():
            youtube_id = extract_youtube_id_from_nfo(nfo_path)
            if youtube_id and len(duplicate_youtube_ids.get(youtube_id, [])) > 1:
                issues.append({"type": "duplicate_youtube_id", "file": nfo_path.name, "path": str(nfo_path)})
            if apply_maintenance and state.config.schedule_update_stale_stats and youtube_id and nfo_stats_need_refresh(
                nfo_path, state.config.stats_update_interval_seconds
            ):
                youtube_metadata = await asyncio.to_thread(get_youtube_video_details, state.config, youtube_id)
                if youtube_metadata:
                    updated = await asyncio.to_thread(
                        update_video_nfo_stats,
                        nfo_path,
                        youtube_metadata.get("view_count"),
                        youtube_metadata.get("like_count"),
                    )
                    if updated:
                        actions.append(f"Refreshed NFO stats: {nfo_path.name}")

        probe = probe_results.get(video_path, {})
        if probe and state.config.schedule_detect_quality_issues:
            height = int(probe.get("height") or 0)
            width = int(probe.get("width") or 0)
            if height and height < state.config.min_video_dimension:
                issues.append(
                    {
                        "type": "low_resolution_video",
                        "file": video_path.name,
                        "path": str(video_path),
                        "detail": f"{width}x{height}",
                    }
                )
            video_bitrate = int(probe.get("video_bitrate") or 0)
            audio_bitrate = int(probe.get("audio_bitrate") or 0)
            if video_bitrate and audio_bitrate and audio_bitrate >= 192000 and video_bitrate <= 500000:
                issues.append(
                    {
                        "type": "quality_mismatch",
                        "file": video_path.name,
                        "path": str(video_path),
                        "detail": f"video={video_bitrate} audio={audio_bitrate}",
                    }
                )
        if probe and state.config.schedule_detect_fake_video_traits:
            stem_lower = video_path.stem.lower()
            if any(keyword in stem_lower for keyword in LYRIC_KEYWORDS):
                issues.append({"type": "possible_lyric_video", "file": video_path.name, "path": str(video_path)})
            fps = float(probe.get("fps") or 0)
            duration = float(probe.get("duration") or 0)
            if fps and fps < 10 and duration >= 60:
                issues.append(
                    {
                        "type": "possible_slideshow_video",
                        "file": video_path.name,
                        "path": str(video_path),
                        "detail": f"{fps}fps",
                    }
                )
            if not probe.get("audio_codec"):
                issues.append({"type": "missing_audio_stream", "file": video_path.name, "path": str(video_path)})
            if not probe.get("video_codec"):
                issues.append({"type": "missing_video_stream", "file": video_path.name, "path": str(video_path)})
            visual_profile = visual_results.get(video_path, {})
            profile_name = str(visual_profile.get("profile") or "")
            if profile_name in {"album_art_video", "slideshow_video", "low_motion_video"}:
                issues.append(
                    {
                        "type": profile_name,
                        "file": video_path.name,
                        "path": str(video_path),
                        "detail": (
                            f"profile={profile_name} "
                            f"unique={visual_profile.get('unique_ratio')} "
                            f"change={visual_profile.get('change_ratio')}"
                        ),
                    }
                )
            black_segments = int(visual_profile.get("black_segments") or 0)
            if black_segments >= 3:
                issues.append(
                    {
                        "type": "heavy_black_segments",
                        "file": video_path.name,
                        "path": str(video_path),
                        "detail": f"segments={black_segments}",
                    }
                )

    downloads_added = 0
    if apply_maintenance and state.config.auto_download_missing:
        if state.scan_stop_requested:
            return {"video_count": len(videos), "issues": issues, "actions": actions, "downloads_added": 0}
        existing_titles = {normalize_media_name(item.stem) for item in videos}
        candidate_results = await search_youtube_for_artist(
            state.config,
            artist,
            max(state.config.schedule_max_downloads_per_artist * 3, 20),
        )
        download_candidates: list[dict[str, object]] = []
        for candidate in candidate_results:
            if candidate.get("is_fake"):
                continue
            candidate_key = normalize_media_name(clean_song_title(str(candidate.get("title") or ""), artist))
            if candidate_key in existing_titles:
                continue
            existing_titles.add(candidate_key)
            download_candidates.append(candidate)
            if len(download_candidates) >= state.config.schedule_max_downloads_per_artist:
                break
        if download_candidates:
            downloads_added = len(download_candidates)
            asyncio.create_task(perform_batch_download(state, artist, download_candidates, False))
            actions.append(f"Queued background download batch for {downloads_added} missing video(s)")

    return {
        "video_count": len(videos),
        "issues": issues,
        "actions": actions,
        "downloads_added": downloads_added,
    }
