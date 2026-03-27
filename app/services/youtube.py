from __future__ import annotations

import re
import unicodedata
from typing import Any

import yt_dlp

from app.config import AppConfig


AUDIO_ONLY_KEYWORDS = [
    "audio",
    "lyric",
    "lyrics",
    "visualizer",
    "visualiser",
    "official audio",
    "lyric video",
]


def normalize_search_text(value: str) -> str:
    cleaned = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    cleaned = cleaned.lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def has_artist_word_match(text: str, artist: str) -> bool:
    normalized_text = normalize_search_text(text)
    normalized_artist = normalize_search_text(artist)
    if not normalized_text or not normalized_artist:
        return False
    return re.search(rf"(^|\s){re.escape(normalized_artist)}($|\s)", normalized_text) is not None


def is_strong_artist_match(title: str, uploader: str, artist: str) -> bool:
    normalized_title = normalize_search_text(title)
    normalized_uploader = normalize_search_text(uploader)
    normalized_artist = normalize_search_text(artist)
    if not normalized_artist:
        return False
    if normalized_title.startswith(f"{normalized_artist} "):
        return True
    if normalized_title.startswith(normalized_artist):
        remainder = normalized_title[len(normalized_artist):len(normalized_artist) + 2]
        if remainder in {"", " ", " -", " :"}:
            return True
    if normalized_uploader == normalized_artist:
        return True
    if normalized_uploader.startswith(f"{normalized_artist} "):
        return True
    if normalized_uploader.endswith(f" {normalized_artist}"):
        return True
    if normalized_uploader.startswith(f"{normalized_artist} topic"):
        return True
    return False


def build_ydl_options(config: AppConfig) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "ignoreerrors": True,
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if config.cookies_file.exists():
        opts["cookiefile"] = str(config.cookies_file)
    return opts


async def search_youtube_for_artist(config: AppConfig, artist: str, limit: int = 25) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    queries = [
        f"{artist} official music video",
        f"{artist} music video",
        f"{artist} - Topic",
    ]
    ydl_opts = build_ydl_options(config)
    for query in queries:
        if len(results) >= limit:
            break
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        except Exception:
            continue
        for entry in info.get("entries", []) if isinstance(info, dict) else []:
            if not entry or len(results) >= limit:
                break
            video_id = entry.get("id")
            if not video_id or video_id in seen_ids:
                continue
            title = entry.get("title", "")
            uploader = entry.get("uploader", "")
            duration = entry.get("duration") or 0
            height = entry.get("height") or 0
            title_lower = title.lower()
            fake_reason = None
            if not has_artist_word_match(title, artist) and not has_artist_word_match(uploader, artist):
                fake_reason = "Artist not present in title or uploader"
            elif not is_strong_artist_match(title, uploader, artist):
                fake_reason = "Weak artist match"
            elif config.filter_audio_only and any(keyword in title_lower for keyword in AUDIO_ONLY_KEYWORDS):
                fake_reason = "Audio-only match"
            elif height and height < config.min_video_dimension:
                fake_reason = f"Low resolution ({height}p)"
            elif duration and duration > config.max_duration:
                fake_reason = f"Over max duration ({duration}s)"
            elif duration and duration < config.min_duration:
                fake_reason = f"Under min duration ({duration}s)"
            seen_ids.add(video_id)
            results.append(
                {
                    "id": video_id,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "uploader": uploader,
                    "duration": duration,
                    "thumbnail": f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                    "height": height,
                    "upload_date": entry.get("upload_date"),
                    "is_fake": fake_reason is not None,
                    "fake_reason": fake_reason,
                }
            )
    return results
