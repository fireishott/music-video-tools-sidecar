from __future__ import annotations

import shutil
from pathlib import Path


def list_artist_folders(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted(item.name for item in root.iterdir() if item.is_dir() and not item.name.startswith("_"))


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


def quarantine_media_bundle(root: Path, artist: str, video_path: Path) -> list[str]:
    quarantine_root = root / "_quarantine" / artist
    quarantine_root.mkdir(parents=True, exist_ok=True)
    moved_paths: list[str] = []
    for sibling in sorted(video_path.parent.glob(f"{video_path.stem}.*")):
        target = quarantine_root / sibling.name
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            counter = 1
            while target.exists():
                target = quarantine_root / f"{stem}_{counter}{suffix}"
                counter += 1
        shutil.move(str(sibling), str(target))
        moved_paths.append(str(target))
    return moved_paths


def delete_media_bundle(video_path: Path) -> list[str]:
    removed_paths: list[str] = []
    for sibling in sorted(video_path.parent.glob(f"{video_path.stem}.*")):
        sibling.unlink(missing_ok=True)
        removed_paths.append(str(sibling))
    return removed_paths
