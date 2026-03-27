from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any


def _run_ffmpeg_signature(path: Path, sample_interval: int, vaapi_device: str) -> list[str]:
    base_command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-vf",
        f"fps=1/{sample_interval},scale=160:90,format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "-",
    ]
    attempts = [
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-hwaccel",
            "vaapi",
            "-vaapi_device",
            vaapi_device,
            "-i",
            str(path),
            "-vf",
            f"fps=1/{sample_interval},hwdownload,format=nv12,scale=160:90,format=gray",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "-",
        ],
        base_command,
    ]

    for command in attempts:
        try:
            result = subprocess.run(command, capture_output=True, timeout=180, check=False)
        except Exception:
            continue
        if result.returncode != 0 or not result.stdout:
            continue
        frame_size = 160 * 90
        payload = result.stdout
        if len(payload) < frame_size:
            continue
        frames: list[str] = []
        for offset in range(0, len(payload), frame_size):
            chunk = payload[offset : offset + frame_size]
            if len(chunk) < frame_size:
                break
            frames.append(hashlib.md5(chunk).hexdigest())
        if frames:
            return frames
    return []


def _run_blackdetect(path: Path, vaapi_device: str) -> dict[str, Any]:
    attempts = [
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-hwaccel",
            "vaapi",
            "-vaapi_device",
            vaapi_device,
            "-i",
            str(path),
            "-vf",
            "blackdetect=d=2:pix_th=0.10",
            "-an",
            "-f",
            "null",
            "-",
        ],
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "info",
            "-i",
            str(path),
            "-vf",
            "blackdetect=d=2:pix_th=0.10",
            "-an",
            "-f",
            "null",
            "-",
        ],
    ]
    for command in attempts:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        except Exception:
            continue
        if result.returncode != 0 and not result.stderr:
            continue
        black_segments = [line for line in (result.stderr or "").splitlines() if "black_start:" in line]
        return {"black_segments": len(black_segments)}
    return {"black_segments": 0}


def analyze_visual_profile(path: Path, duration: float, vaapi_device: str) -> dict[str, Any]:
    if duration <= 0:
        duration = 180.0
    sample_interval = max(5, min(20, int(math.ceil(duration / 12))))
    frame_hashes = _run_ffmpeg_signature(path, sample_interval, vaapi_device)
    blackdetect = _run_blackdetect(path, vaapi_device)
    total_frames = len(frame_hashes)
    if total_frames <= 1:
        return {
            "sample_interval_seconds": sample_interval,
            "sampled_frames": total_frames,
            "unique_ratio": 0.0,
            "change_ratio": 0.0,
            "black_segments": blackdetect["black_segments"],
            "profile": "insufficient_samples",
            "reasons": ["Not enough sampled frames for visual analysis"],
        }

    unique_frames = len(set(frame_hashes))
    changed_frames = sum(1 for left, right in zip(frame_hashes, frame_hashes[1:]) if left != right)
    unique_ratio = unique_frames / total_frames
    change_ratio = changed_frames / max(total_frames - 1, 1)

    reasons: list[str] = []
    profile = "normal_video"
    if unique_ratio <= 0.20 and change_ratio <= 0.20:
        profile = "album_art_video"
        reasons.append("Very low frame uniqueness across the sample set")
    elif unique_ratio <= 0.42 and change_ratio <= 0.45:
        profile = "slideshow_video"
        reasons.append("Low visual turnover across sampled frames")
    elif unique_ratio <= 0.62 and change_ratio <= 0.55:
        profile = "low_motion_video"
        reasons.append("Motion and scene changes are limited")

    if blackdetect["black_segments"] >= 3:
        reasons.append("Multiple long black segments detected")

    return {
        "sample_interval_seconds": sample_interval,
        "sampled_frames": total_frames,
        "unique_ratio": round(unique_ratio, 3),
        "change_ratio": round(change_ratio, 3),
        "black_segments": blackdetect["black_segments"],
        "profile": profile,
        "reasons": reasons,
    }
