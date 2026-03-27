from __future__ import annotations

import hashlib
import logging
import math
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("music-video-tools.visual-analysis")


def _short_error(stderr: bytes | str | None) -> str:
    if not stderr:
        return "no stderr"
    if isinstance(stderr, bytes):
        text = stderr.decode("utf-8", errors="ignore")
    else:
        text = stderr
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "no stderr"
    return lines[-1][:240]


def _run_ffmpeg_signature(path: Path, sample_interval: int, vaapi_device: str) -> tuple[list[str], str]:
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
    labels = ["vaapi", "cpu"]

    for label, command in zip(labels, attempts):
        try:
            result = subprocess.run(command, capture_output=True, timeout=180, check=False)
        except Exception as exc:
            logger.warning("Visual signature %s attempt failed for %s: %s", label, path.name, exc)
            continue
        if result.returncode != 0 or not result.stdout:
            logger.info(
                "Visual signature %s attempt did not produce frames for %s (code=%s, detail=%s)",
                label,
                path.name,
                result.returncode,
                _short_error(result.stderr),
            )
            continue
        frame_size = 160 * 90
        payload = result.stdout
        if len(payload) < frame_size:
            logger.info("Visual signature %s attempt returned too little data for %s", label, path.name)
            continue
        frames: list[str] = []
        for offset in range(0, len(payload), frame_size):
            chunk = payload[offset : offset + frame_size]
            if len(chunk) < frame_size:
                break
            frames.append(hashlib.md5(chunk).hexdigest())
        if frames:
            logger.info("Visual signature analysis used %s for %s (%s sampled frames)", label, path.name, len(frames))
            return frames, label
    logger.warning("Visual signature analysis failed for %s; no usable frames sampled", path.name)
    return [], "none"


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
    labels = ["vaapi", "cpu"]
    for label, command in zip(labels, attempts):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=180, check=False)
        except Exception as exc:
            logger.warning("Blackdetect %s attempt failed for %s: %s", label, path.name, exc)
            continue
        if result.returncode != 0 and not result.stderr:
            logger.info("Blackdetect %s attempt returned no stderr for %s", label, path.name)
            continue
        black_segments = [line for line in (result.stderr or "").splitlines() if "black_start:" in line]
        logger.info(
            "Blackdetect used %s for %s (%s segments, code=%s)",
            label,
            path.name,
            len(black_segments),
            result.returncode,
        )
        return {"black_segments": len(black_segments), "backend": label}
    logger.warning("Blackdetect failed for %s; defaulting to zero segments", path.name)
    return {"black_segments": 0, "backend": "none"}


def analyze_visual_profile(path: Path, duration: float, vaapi_device: str) -> dict[str, Any]:
    if duration <= 0:
        duration = 180.0
    sample_interval = max(5, min(20, int(math.ceil(duration / 12))))
    frame_hashes, signature_backend = _run_ffmpeg_signature(path, sample_interval, vaapi_device)
    blackdetect = _run_blackdetect(path, vaapi_device)
    total_frames = len(frame_hashes)
    if total_frames <= 1:
        return {
            "sample_interval_seconds": sample_interval,
            "sampled_frames": total_frames,
            "unique_ratio": 0.0,
            "change_ratio": 0.0,
            "black_segments": blackdetect["black_segments"],
            "signature_backend": signature_backend,
            "blackdetect_backend": blackdetect["backend"],
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
        "signature_backend": signature_backend,
        "blackdetect_backend": blackdetect["backend"],
        "profile": profile,
        "reasons": reasons,
    }
