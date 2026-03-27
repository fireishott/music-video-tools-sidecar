from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AppConfig(BaseModel):
    music_videos_path: Path = Field(default=Path("/musicvideos"))
    downloads_path: Path = Field(default=Path("/downloads"))
    app_config_path: Path = Field(default=Path("/app/config"))
    app_data_path: Path = Field(default=Path("/app/data"))
    app_logs_path: Path = Field(default=Path("/app/logs"))
    cookies_file: Path = Field(default=Path("/app/config/cookies.txt"))
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080)
    lidarr_enabled: bool = Field(default=False)
    lidarr_url: str = Field(default="http://lidarr:8686")
    lidarr_api_key: str = Field(default="")
    min_video_dimension: int = Field(default=480)
    min_duration: int = Field(default=60)
    max_duration: int = Field(default=600)
    filter_audio_only: bool = Field(default=True)
    enable_musicbrainz: bool = Field(default=False)
    enable_youtube_stats: bool = Field(default=True)
    enable_featured_artists: bool = Field(default=True)
    auto_download_missing: bool = Field(default=True)
    auto_update_stats: bool = Field(default=True)
    stats_update_interval_seconds: int = Field(default=7 * 24 * 3600)
    schedule_enabled: bool = Field(default=False)
    schedule_interval_hours: int = Field(default=24)

    @property
    def runtime_config_file(self) -> Path:
        return self.app_data_path / "runtime_config.json"


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> AppConfig:
    config = AppConfig(
        music_videos_path=Path(os.getenv("MUSIC_VIDEOS_PATH", "/musicvideos")),
        downloads_path=Path(os.getenv("DOWNLOADS_PATH", "/downloads")),
        app_config_path=Path(os.getenv("APP_CONFIG_PATH", "/app/config")),
        app_data_path=Path(os.getenv("APP_DATA_PATH", "/app/data")),
        app_logs_path=Path(os.getenv("APP_LOGS_PATH", "/app/logs")),
        cookies_file=Path(os.getenv("COOKIES_FILE", "/app/config/cookies.txt")),
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8080")),
        lidarr_enabled=_env_bool("LIDARR_ENABLED", False),
        lidarr_url=os.getenv("LIDARR_URL", "http://lidarr:8686"),
        lidarr_api_key=os.getenv("LIDARR_API_KEY", ""),
        min_video_dimension=int(os.getenv("MIN_VIDEO_DIMENSION", "480")),
        min_duration=int(os.getenv("MIN_DURATION", "60")),
        max_duration=int(os.getenv("MAX_DURATION", "600")),
        filter_audio_only=_env_bool("FILTER_AUDIO_ONLY", True),
        enable_musicbrainz=_env_bool("ENABLE_MUSICBRAINZ", False),
        enable_youtube_stats=_env_bool("ENABLE_YOUTUBE_STATS", True),
        enable_featured_artists=_env_bool("ENABLE_FEATURED_ARTISTS", True),
        auto_download_missing=_env_bool("AUTO_DOWNLOAD_MISSING", True),
        auto_update_stats=_env_bool("AUTO_UPDATE_STATS", True),
        stats_update_interval_seconds=int(os.getenv("STATS_UPDATE_INTERVAL_SECONDS", str(7 * 24 * 3600))),
        schedule_enabled=_env_bool("SCHEDULE_ENABLED", False),
        schedule_interval_hours=int(os.getenv("SCHEDULE_INTERVAL_HOURS", "24")),
    )
    ensure_directories(config)
    return merge_runtime_config(config)


def ensure_directories(config: AppConfig) -> None:
    for path in (
        config.music_videos_path,
        config.downloads_path,
        config.app_config_path,
        config.app_data_path,
        config.app_logs_path,
    ):
        path.mkdir(parents=True, exist_ok=True)


def merge_runtime_config(config: AppConfig) -> AppConfig:
    if not config.runtime_config_file.exists():
        return config
    try:
        data = json.loads(config.runtime_config_file.read_text(encoding="utf-8"))
        merged: dict[str, Any] = config.model_dump()
        merged.update(data)
        for key in ("music_videos_path", "downloads_path", "app_config_path", "app_data_path", "app_logs_path", "cookies_file"):
            if key in merged:
                merged[key] = Path(merged[key])
        return AppConfig(**merged)
    except Exception:
        return config


def save_runtime_config(config: AppConfig) -> None:
    payload = config.model_dump(mode="json")
    config.runtime_config_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

