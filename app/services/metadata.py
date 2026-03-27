from __future__ import annotations

from html import escape
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


def sanitize_filename(text: str) -> str:
    if not text:
        return "Unknown Title"
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[\\/*?:\"<>|]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.rstrip(".")
    return value or "Unknown Title"


def clean_song_title(title: str, artist: str) -> str:
    if not title:
        return "Unknown_Title"
    cleaned = title
    artist_escaped = re.escape(artist)
    cleaned = re.sub(r"^\s*" + artist_escaped + r"\s*[-:]\s*(.*)$", r"\1", cleaned, flags=re.IGNORECASE)
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
    return write_artist_nfo(
        config,
        {
            "name": artist_name,
            "musicbrainz_artist_id": artist_mbid or "",
            "sort_name": artist_name,
            "genres": [],
            "moods": [],
            "type": "",
            "yearsactive": "",
            "biography": "",
            "albums": [],
        },
    )


def write_artist_nfo(config: AppConfig, artist_metadata: dict[str, object]) -> Path:
    artist_name = str(artist_metadata.get("name") or "Unknown Artist")
    artist_dir = config.music_videos_path / artist_name
    artist_dir.mkdir(parents=True, exist_ok=True)
    nfo_path = artist_dir / "artist.nfo"
    lines = ["<artist>", f"  <name>{escape(artist_name)}</name>"]
    artist_mbid = str(artist_metadata.get("musicbrainz_artist_id") or "")
    if artist_mbid:
        lines.append(f"  <musicBrainzArtistID>{escape(artist_mbid)}</musicBrainzArtistID>")
        lines.append(f"  <musicbrainzartistid>{escape(artist_mbid)}</musicbrainzartistid>")
    sort_name = str(artist_metadata.get("sort_name") or "")
    if sort_name:
        lines.append(f"  <sortname>{escape(sort_name)}</sortname>")
    for genre in artist_metadata.get("genres", []) or []:
        lines.append(f"  <genre>{escape(str(genre))}</genre>")
    for mood in artist_metadata.get("moods", []) or []:
        lines.append(f"  <mood>{escape(str(mood))}</mood>")
    artist_type = str(artist_metadata.get("type") or "")
    if artist_type:
        lines.append(f"  <type>{escape(artist_type)}</type>")
    yearsactive = str(artist_metadata.get("yearsactive") or "")
    if yearsactive:
        lines.append(f"  <yearsactive>{escape(yearsactive)}</yearsactive>")
    biography = str(artist_metadata.get("biography") or "")
    if biography:
        lines.append(f"  <biography>{escape(biography)}</biography>")
    for album in artist_metadata.get("albums", []) or []:
        if not isinstance(album, dict):
            continue
        title = str(album.get("title") or "")
        year = str(album.get("year") or "")
        if not title:
            continue
        lines.append("  <album>")
        lines.append(f"    <title>{escape(title)}</title>")
        if year:
            lines.append(f"    <year>{escape(year)}</year>")
        lines.append("  </album>")
    lines.append("  <thumb>artist.jpg</thumb>")
    lines.extend(
        [
            "  <generator>",
            "    <appname>Music Video Tools</appname>",
            "    <appversion>0.1</appversion>",
            f"    <datetime>{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}</datetime>",
            "  </generator>",
        ]
    )
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
    recording_metadata: dict[str, object] | None = None,
    youtube_metadata: dict[str, object] | None = None,
) -> Path:
    artist_dir = config.music_videos_path / artist
    artist_dir.mkdir(parents=True, exist_ok=True)
    if not song_title and original_title:
        song_title = clean_song_title(original_title, artist)
    descriptive_name = sanitize_filename(song_title or "Unknown Title")
    nfo_path = artist_dir / f"{descriptive_name}.nfo"
    thumb_name = f"{descriptive_name}.jpg"
    thumb_path = artist_dir / thumb_name
    if video_id and not thumb_path.exists():
        download_thumbnail(video_id, thumb_path)
    current_time = int(time.time())
    featured_artists = extract_featured_artists(original_title or song_title)
    recording_metadata = recording_metadata or {}
    youtube_metadata = youtube_metadata or {}
    genres = recording_metadata.get("genres", []) or []
    views = youtube_metadata.get("view_count")
    likes = youtube_metadata.get("like_count")
    channel = channel or str(youtube_metadata.get("channel") or "")
    album = str(recording_metadata.get("album") or "")
    album_artist = str(recording_metadata.get("album_artist") or artist)
    disc = str(recording_metadata.get("disc") or "")
    lines = [
        "<musicvideo>",
        f"  <title>{escape(song_title)}</title>",
        f"  <artist>{escape(artist)}</artist>",
    ]
    if year:
        lines.append(f"  <year>{escape(year)}</year>")
    if artist_mbid:
        lines.append(f"  <musicbrainzartistid>{escape(artist_mbid)}</musicbrainzartistid>")
    recording_id = str(recording_metadata.get("musicbrainz_recording_id") or "")
    if recording_id:
        lines.append(f"  <musicbrainzrecordingid>{escape(recording_id)}</musicbrainzrecordingid>")
    release_group_id = str(recording_metadata.get("musicbrainz_release_group_id") or "")
    if release_group_id:
        lines.append(f"  <musicbrainzreleasegroupid>{escape(release_group_id)}</musicbrainzreleasegroupid>")
    album_id = str(recording_metadata.get("musicbrainz_album_id") or "")
    if album_id:
        lines.append(f"  <musicbrainzalbumid>{escape(album_id)}</musicbrainzalbumid>")
    if album:
        lines.append(f"  <album>{escape(album)}</album>")
    if album_artist:
        lines.append(f"  <albumartist>{escape(album_artist)}</albumartist>")
    if disc:
        lines.append(f"  <disc>{escape(disc)}</disc>")
    for genre in genres:
        lines.append(f"  <genre>{escape(str(genre))}</genre>")
    if views:
        lines.append(f"  <views>{escape(format(int(views), ','))}</views>")
    if likes:
        lines.append(f"  <likes>{escape(format(int(likes), ','))}</likes>")
    if config.enable_youtube_stats:
        lines.append(f"  <lastupdated>{current_time}</lastupdated>")
    if channel:
        lines.append(f"  <channel>{escape(channel)}</channel>")
    if config.enable_featured_artists and featured_artists:
        order = 1
        for feat_artist in re.split(r"[,&]|\sand\s", featured_artists):
            feat_artist = feat_artist.strip()
            if feat_artist and feat_artist != artist:
                lines.extend(
                    [
                        "  <actor>",
                        f"    <name>{escape(feat_artist)}</name>",
                        "    <role>Featured Artist</role>",
                        f"    <order>{order}</order>",
                        "  </actor>",
                    ]
                )
                order += 1
    lines.append("  <source>youtube</source>")
    lines.append(f"  <source_url>https://www.youtube.com/watch?v={escape(video_id)}</source_url>")
    lines.append(f"  <uniqueid type=\"YouTube\">{escape(video_id)}</uniqueid>")
    if recording_id:
        lines.append(f"  <uniqueid type=\"MusicBrainz\">{escape(recording_id)}</uniqueid>")
    plot = f"{song_title} by {artist}"
    if album:
        plot += f" from the album {album}"
    if year:
        plot += f" released in {year}"
    if featured_artists:
        plot += f" featuring {featured_artists}"
    lines.append(f"  <plot>{escape(plot)}</plot>")
    lines.append("  <outline>Music video</outline>")
    lines.append(f"  <tagline>{escape(f'From the album {album}') if album else 'Music video'}</tagline>")
    lines.append(f"  <thumb>{escape(thumb_name)}</thumb>")
    lines.append("</musicvideo>")
    nfo_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return nfo_path
