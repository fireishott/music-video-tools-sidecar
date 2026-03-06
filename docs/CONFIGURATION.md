# Configuration Guide

## Configuration File Location
The script looks for its configuration at `/config/video.conf` inside your Lidarr container.

---

## Required Settings

| Setting | Description | Example |
|---------|-------------|---------|
| `enableVideo` | Enable the script | `true` |
| `videoPath` | Where to save videos (must be mounted in container) | `/mnt/musicvideos` |

---

## Optional Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `videoContainer` | Output video format (mkv or mp4) | `mkv` |
| `youtubeSubtitleLanguage` | Subtitle language (en, es, fr, etc.) | `en` |
| `videoDownloadTag` | Only process artists with this Lidarr tag | (none) |
| `videoScriptInterval` | How often to run (15m, 1h, etc.) | `15m` |

---

## Using Tags

If you want to limit video downloads to specific artists:

1. **In Lidarr**, add a tag (e.g., "music-videos") to the artists you want videos for
2. **In your config**, set `videoDownloadTag` to that tag name
3. **Only tagged artists** will be processed when the script runs

Example:
```bash
videoDownloadTag="music-videos"
