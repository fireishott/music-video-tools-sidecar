from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.config import AppConfig

logger = logging.getLogger("music-video-tools.enrichment")

APP_USER_AGENT = "music-video-tools-sidecar/0.1 (https://github.com/fireishott/music-video-tools-sidecar)"


def _fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 20) -> dict[str, Any]:
    request_headers = {"User-Agent": APP_USER_AGENT, "Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    request = Request(url, headers=request_headers)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _safe_fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 20) -> dict[str, Any]:
    try:
        return _fetch_json(url, headers=headers, timeout=timeout)
    except Exception as exc:
        logger.debug("fetch failed for %s: %s", url, exc)
        return {}


def _normalize_name(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def get_lidarr_artist(config: AppConfig, artist_name: str) -> dict[str, Any]:
    if not (config.lidarr_enabled and config.lidarr_api_key and config.lidarr_url):
        return {}
    url = f"{config.lidarr_url.rstrip('/')}/api/v1/artist"
    headers = {"X-Api-Key": config.lidarr_api_key}
    payload = _safe_fetch_json(url, headers=headers)
    artists = payload if isinstance(payload, list) else []
    normalized_target = _normalize_name(artist_name)
    for artist in artists:
        name = artist.get("artistName") or artist.get("cleanName") or ""
        if _normalize_name(name) == normalized_target:
            return artist
    for artist in artists:
        name = artist.get("artistName") or artist.get("cleanName") or ""
        if normalized_target and normalized_target in _normalize_name(name):
            return artist
    return {}


def search_musicbrainz_artist(artist_name: str) -> dict[str, Any]:
    query = quote(f'artist:"{artist_name}"')
    url = f"https://musicbrainz.org/ws/2/artist?query={query}&limit=1&fmt=json"
    payload = _safe_fetch_json(url)
    artists = payload.get("artists", [])
    return artists[0] if artists else {}


def get_musicbrainz_artist_details(artist_mbid: str) -> dict[str, Any]:
    if not artist_mbid:
        return {}
    time.sleep(1.1)
    url = f"https://musicbrainz.org/ws/2/artist/{artist_mbid}?fmt=json&inc=genres+release-groups"
    return _safe_fetch_json(url)


def search_wikipedia_artist(artist_name: str) -> dict[str, Any]:
    params = urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": artist_name,
            "utf8": "1",
            "format": "json",
            "srlimit": "1",
        }
    )
    payload = _safe_fetch_json(f"https://en.wikipedia.org/w/api.php?{params}")
    search = payload.get("query", {}).get("search", [])
    return search[0] if search else {}


def get_wikipedia_extract(page_title: str) -> str:
    if not page_title:
        return ""
    params = urlencode(
        {
            "action": "query",
            "prop": "extracts",
            "exintro": "1",
            "explaintext": "1",
            "titles": page_title,
            "redirects": "1",
            "format": "json",
        }
    )
    payload = _safe_fetch_json(f"https://en.wikipedia.org/w/api.php?{params}")
    pages = payload.get("query", {}).get("pages", {})
    for page in pages.values():
        extract = page.get("extract")
        if extract:
            return extract.strip()
    return ""


def get_artist_context(config: AppConfig, artist_name: str) -> dict[str, Any]:
    lidarr_artist = get_lidarr_artist(config, artist_name)
    artist_mbid = lidarr_artist.get("foreignArtistId") or ""
    mb_artist: dict[str, Any] = {}
    if config.enable_musicbrainz:
        mb_artist = get_musicbrainz_artist_details(artist_mbid) if artist_mbid else search_musicbrainz_artist(artist_name)
        if not artist_mbid:
            artist_mbid = mb_artist.get("id", "")
            if artist_mbid:
                mb_artist = get_musicbrainz_artist_details(artist_mbid)
    wiki_match = search_wikipedia_artist(artist_name)
    biography = get_wikipedia_extract(wiki_match.get("title", artist_name))
    genres = []
    for genre in lidarr_artist.get("genres", []) or []:
        if genre and genre not in genres:
            genres.append(genre)
    for genre in mb_artist.get("genres", []) or []:
        name = genre.get("name")
        if name and name not in genres:
            genres.append(name)
    albums = []
    seen_titles: set[str] = set()
    for group in mb_artist.get("release-groups", []) or []:
        title = group.get("title")
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        year = ""
        first_date = group.get("first-release-date") or ""
        if len(first_date) >= 4:
            year = first_date[:4]
        albums.append({"title": title, "year": year})
    def album_sort_key(item: dict[str, str]) -> tuple[int, str]:
        year = item.get("year", "")
        return (-(int(year) if year.isdigit() else 0), item.get("title", ""))
    albums.sort(key=album_sort_key)
    return {
        "name": lidarr_artist.get("artistName") or mb_artist.get("name") or artist_name,
        "sort_name": lidarr_artist.get("sortName") or mb_artist.get("sort-name") or artist_name,
        "musicbrainz_artist_id": artist_mbid,
        "genres": genres[:12],
        "moods": [],
        "biography": lidarr_artist.get("overview") or biography,
        "type": mb_artist.get("type", "").lower(),
        "yearsactive": "",
        "albums": albums[:25],
        "wikipedia_title": wiki_match.get("title", ""),
    }


def search_musicbrainz_recording(artist_name: str, song_title: str) -> dict[str, Any]:
    query = quote(f'recording:"{song_title}" AND artist:"{artist_name}"')
    url = f"https://musicbrainz.org/ws/2/recording?query={query}&limit=1&fmt=json"
    payload = _safe_fetch_json(url)
    recordings = payload.get("recordings", [])
    return recordings[0] if recordings else {}


def get_musicbrainz_recording_details(recording_id: str) -> dict[str, Any]:
    if not recording_id:
        return {}
    time.sleep(1.1)
    url = f"https://musicbrainz.org/ws/2/recording/{recording_id}?fmt=json&inc=releases+genres+artists"
    return _safe_fetch_json(url)


def get_recording_context(config: AppConfig, artist_name: str, song_title: str) -> dict[str, Any]:
    if not config.enable_musicbrainz:
        return {}
    recording = search_musicbrainz_recording(artist_name, song_title)
    recording_id = recording.get("id", "")
    details = get_musicbrainz_recording_details(recording_id) if recording_id else {}
    releases = details.get("releases", []) or recording.get("releases", []) or []
    release = releases[0] if releases else {}
    release_group = release.get("release-group", {})
    genres = []
    for genre in details.get("genres", []) or recording.get("genres", []) or []:
        name = genre.get("name")
        if name and name not in genres:
            genres.append(name)
    artist_credits = details.get("artist-credit", []) or recording.get("artist-credit", []) or []
    album_artist = artist_name
    if artist_credits:
        first_credit = artist_credits[0]
        if isinstance(first_credit, dict):
            album_artist = first_credit.get("name") or first_credit.get("artist", {}).get("name") or artist_name
    return {
        "musicbrainz_recording_id": recording_id,
        "musicbrainz_release_group_id": release_group.get("id", ""),
        "musicbrainz_album_id": release.get("id", ""),
        "album": release.get("title", ""),
        "album_artist": album_artist,
        "disc": "1",
        "genres": genres[:8],
    }
