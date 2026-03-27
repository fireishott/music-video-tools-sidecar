from __future__ import annotations

import re
import subprocess
import time
import unicodedata
from pathlib import Path

from app.config import AppConfig


def slugify(text: str) -> str:
    if not text:
        return "unknown"
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value)
    value = re.sub(r"[-\s]+", " ", value).strip()
    return value.replace(" ", "_") or "unknown"


def clean_song_title(title: str, artist: str) -> str:
    if not title:
        return "Unknown_Title"
    cleaned = title
    artist_escaped = re.escape(artist)
    cleaned = re.sub(r"^\s*" + artist_escaped + r"\s*[-:–—]\s*(.*)$", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^\s*" + artist_escaped + r"\s+(.*)$", r"\1", cleaned, flags=re.IGNORECASE)
    descriptors = [
        r"[\[\(]?[Oo]fficial[\]\)]? [\[\(]?[Mm]usic[\]\)]? [\[\(]?[Vv]ideo[\]\)]?",
        r"[\[\(]?[Oo]fficial[\]\)]? [\[\(]?[Vv]ideo[\]\)]?",
        r"[\[\(]?[Mm]usic[\]\)]? [\[\(]?[Vv]ideo[\]\)]?",
        r"[\[\(]?[Oo]fficial[\]\)]?",
        r"[\[\(]?[Vv]ideo[\]\)]?",
        r"[\[\(]?[Hh][Dd][\]\)]?",
        r"\s*[\(\[]?\d{4}[\)\]]?\s*",
    ]
    for pattern in descriptors:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+[\(\[]?(feat\.|featuring|ft\.|ft|with)[\(\[]?\s+[^\)\]]+[\)\]]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"[\\/*?:\"<>|]", "", cleaned)
    return cleaned or "Unknown_Title"


def extract_featured_artists(title: str) -> str:
    match = re.search(r"(feat\.|featuring|ft\.|ft|with)\s+(.+?)(?:\s*[\[\(]|$)", title or "", re.IGNORECASE)
    if not match:
        return ""
    featured = match.group(2)
    featured = re.sub(r" [(\[]?(official video|music video).*$", "", featured, flags=re.IGNORECASE)
    return featured.strip()


def create_artist_nfo(config: AppConfig, artist_name: str, artist_mbid: str | None = None) -> Path:
    artist_dir = config.music_videos_path / artist_name
    artist_dir.mkdir(parents=True, exist_ok=True)
    nfo_path = artist_dir / "artist.nfo"
    lines = ["<artist>", f"  <name>{artist_name}</name>"]
    if artist_mbid:
        lines.append(f"  <musicbrainzartistid>{artist_mbid}</musicbrainzartistid>")
    lines.append("  <thumb>artist.jpg</thumb>")
    lines.append("</artist>")
    nfo_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return nfo_path


def download_thumbnail(video_id: str, thumb_path: Path) -> None:
    for quality in ("maxresdefault.jpg", "hqdefault.jpg"):
        try:
            subprocess.run(
                ["curl", "-fsSL", f"https://img.youtube.com/vi/{video_id}/{quality}", "-o", str(thumb_path)],
                check=False,
                timeout=15,
            )
            if thumb_path.exists() and thumb_path.stat().st_size > 0:
                return
        except Exception:
            continue


def create_video_nfo(
    config: AppConfig,
    artist: str,
    artist_mbid: str | None,
    song_title: str,
    original_title: str,
    video_id: str,
    year: str = "",
    channel: str = "",
) -> Path:
    artist_dir = config.music_videos_path / artist
    artist_dir.mkdir(parents=True, exist_ok=True)
    if not song_title and original_title:
        song_title = clean_song_title(original_title, artist)
    safe_filename = slugify(song_title or "Unknown_Title")
    nfo_path = artist_dir / f"{safe_filename}.nfo"
    thumb_name = f"{safe_filename}.jpg"
    thumb_path = artist_dir / thumb_name
    if video_id and not thumb_path.exists():
        download_thumbnail(video_id, thumb_path)
    current_time = int(time.time())
    featured_artists = extract_featured_artists(original_title or song_title)
    lines = [
        "<musicvideo>",
        f"  <title>{song_title}</title>",
        f"  <artist>{artist}</artist>",
        "  <type>Music Video</type>",
    ]
    if year:
        lines.append(f"  <year>{year}</year>")
    if artist_mbid:
        lines.append(f"  <musicbrainzartistid>{artist_mbid}</musicbrainzartistid>")
    if config.enable_youtube_stats:
        lines.append(f"  <lastupdated>{current_time}</lastupdated>")
    if channel:
        lines.append(f"  <channel>{channel}</channel>")
    if config.enable_featured_artists and featured_artists:
        order = 1
        for feat_artist in re.split(r"[,&]|\sand\s", featured_artists):
            feat_artist = feat_artist.strip()
            if feat_artist and feat_artist != artist:
                lines.extend(
                    [
                        "  <actor>",
                        f"    <name>{feat_artist}</name>",
                        "    <role>Featured Artist</role>",
                        f"    <order>{order}</order>",
                        "  </actor>",
                    ]
                )
                order += 1
    lines.extend(
        [
            "  <source>youtube</source>",
            f"  <source_url>https://www.youtube.com/watch?v={video_id}</source_url>",
            f"  <uniqueid type=\"YouTube\">{video_id}</uniqueid>",
            f"  <plot>{song_title} by {artist}</plot>",
            "  <outline>Music video</outline>",
            f"  <thumb>{thumb_name}</thumb>",
            "</musicvideo>",
        ]
    )
    nfo_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return nfo_path

