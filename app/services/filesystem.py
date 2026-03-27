from __future__ import annotations

import shutil
from pathlib import Path


def list_artist_folders(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(item.name for item in root.iterdir() if item.is_dir())


def count_artist_videos(artist_path: Path) -> int:
    if not artist_path.exists():
        return 0
    return len([item for item in artist_path.iterdir() if item.suffix.lower() in {".mkv", ".mp4"}])


def disk_usage_percent(path: Path) -> float:
    try:
        usage = shutil.disk_usage(path)
        return round((usage.used / usage.total) * 100, 1) if usage.total else 0.0
    except Exception:
        return 0.0

