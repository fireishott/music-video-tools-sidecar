#  Configuration Guide

##  Configuration File Location
The script looks for its configuration at `/config/extended.conf` inside your Lidarr container.

---

##  Required Settings

| Setting | Description | Example |
|---------|-------------|---------|
| `LidarrApiKey` | Your Lidarr API key (found in Lidarr Settings → General) | `your-api-key-here` |
| `videoPath` | Where to save videos (must be mounted in container) | `/mnt/musicvideos` |
| `enableVideo` | Enable the video download script | `true` |

---

##  Optional Settings

### Core Settings
| Setting | Description | Default |
|---------|-------------|---------|
| `videoScriptInterval` | How often to run (15m, 1h, etc.) | `15m` |
| `videoContainer` | Output video format (mkv or mp4) | `mkv` |
| `downloadPath` | Temporary download location | `/config/extended/downloads` |
| `youtubeCookiesFile` | Path to cookies.txt for YouTube | `/config/cookies.txt` |
| `youtubeSubtitleLanguage` | Subtitle language (en, es, fr, etc.) | `en` |
| `videoDownloadTag` | Only process artists with this Lidarr tag | (none) |

### Search & Filtering
| Setting | Description | Default |
|---------|-------------|---------|
| `strictArtistFiltering` | Only download videos with artist name in title/channel | `true` |
| `filterLyricVideos` | Skip lyric/audio videos | `true` |
| `filterCompilations` | Skip full album/playlist/mix videos | `true` |
| `maxSearchResults` | Number of YouTube results to process per artist | `40` |
| `ytdlpRateLimit` | Seconds between YouTube searches | `2` |

### Download Settings
| Setting | Description | Default |
|---------|-------------|---------|
| `downloadDelay` | Seconds between downloads | `2` |
| `maxRetries` | Number of retry attempts for failed downloads | `3` |
| `minimumVideoHeight` | Minimum video quality (360, 480, 720, 1080) | `360` |

### Metadata
| Setting | Description | Default |
|---------|-------------|---------|
| `createNfoFiles` | Create Plex/Jellyfin metadata files | `true` |
| `createJpgThumbnails` | Download video thumbnails | `true` |

### Advanced yt-dlp Options
| Setting | Description | Default |
|---------|-------------|---------|
| `ytdlpExtraArgs` | Additional yt-dlp arguments | `--no-mtime --geo-bypass --no-write-info-json --no-write-description --no-write-annotations` |
| `ytdlpCacheDir` | yt-dlp cache directory | `/config/extended/cache/ytdlp` |

### Rescan Behavior
| Setting | Description | Default |
|---------|-------------|---------|
| `alwaysRescanArtists` | Scan all artists on every run | `true` |
| `ignoreCompletionLogs` | Ignore previous completion logs | `true` |

---

##  Using Tags

If you want to limit video downloads to specific artists:

1. **In Lidarr**, add a tag (e.g., "music-videos") to the artists you want videos for
2. **In your config**, set `videoDownloadTag` to that tag name
3. **Only tagged artists** will be processed when the script runs

Example:
```bash
videoDownloadTag="music-videos"
