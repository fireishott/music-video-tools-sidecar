# Configuration Guide

## Configuration File Location
The script looks for its configuration at `/config/extended.conf` inside your Lidarr container.

---

## Required Settings

| Setting | Description | Example |
|---------|-------------|---------|
| `enableVideo` | Enable the script | `true` |
| `videoPath` | Where to save videos (must be mounted in container) | `/mnt/musicvideos` |
| `LidarrApiKey` | Your Lidarr API key (found in Lidarr Settings → General) | `your-api-key-here` |

---

## Optional Settings

| Setting | Description | Default |
|---------|-------------|---------|
| `videoContainer` | Output video format (mkv or mp4) | `mkv` |
| `videoFormat` | yt-dlp format string | `bv[height<=1080]/bv[height<=720]/bv+ba` |
| `youtubeSubtitleLanguage` | Subtitle language (en, es, fr, etc.) | `en` |
| `videoDownloadTag` | Only process artists with this Lidarr tag | (none) |
| `videoScriptInterval` | How often to run (15m, 1h, etc.) | `15m` |
| `downloadPath` | Temporary download location | `/config/extended/downloads` |
| `videoInfoJson` | Save video info as JSON | `true` |
| `youtubeCookiesFile` | Path to cookies.txt for YouTube | `/config/cookies.txt` |

---

## Using Tags

If you want to limit video downloads to specific artists:

1. **In Lidarr**, add a tag (e.g., "music-videos") to the artists you want videos for
2. **In your config**, set `videoDownloadTag` to that tag name
3. **Only tagged artists** will be processed when the script runs

Example:
```bash
videoDownloadTag="music-videos"
