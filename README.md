# Lidarr Music Video Downloader

<p align="center">
  <strong>Automatically download official music videos for your Lidarr artists</strong>
</p>

<p align="center">
  <a href="https://github.com/RandomNinjaAtk/arr-scripts">
    <img src="https://img.shields.io/badge/based_on-RandomNinjaAtk-blueviolet?style=for-the-badge" alt="Based on RandomNinjaAtk arr-scripts">
  </a>
  <a href="https://github.com/sponsors/RandomNinjaAtk">
    <img src="https://img.shields.io/badge/sponsor-RandomNinjaAtk-red?style=for-the-badge" alt="Sponsor RandomNinjaAtk">
  </a>
</p>

---

## What It Does

This script runs inside your Lidarr container and automatically builds a music video library that Plex, Jellyfin, or Emby will love.

| Before | After |
|--------|-------|
|  Manually hunting YouTube for videos |  Automatic downloads while you sleep |
|  Hand-writing NFO files for metadata |  Perfectly formatted metadata files |
|  Missing thumbnails and artwork |  High-quality YouTube thumbnails |
|  Random filenames and organization |  Plex-ready naming convention |

## Features

| | |
|---|---|
| ** YouTube Direct** | Searches YouTube for official music videos with smart filtering |
| ** Metadata** | Creates NFO files with MusicBrainz artist IDs and genres |
| ** Thumbnails** | Downloads high-quality YouTube thumbnails for every video |
| ** Tag Support** | Only process artists with a specific Lidarr tag - you're in control |
| ** Safe Operation** | Never deletes, renames, or modifies your existing files |
| ** Optimized** | Built-in rate limiting to avoid YouTube blocks |
| ** One-Command Install** | The installer handles everything - dependencies, config, permissions |
| ** Docker First** | Works perfectly with any Lidarr Docker image |

##  Prerequisites

-  Lidarr running in Docker ([linuxserver](https://docs.linuxserver.io/images/docker-lidarr) or [hotio](https://hotio.dev/containers/lidarr) images)
-  Basic Docker knowledge (`docker exec`, `docker logs`)
-  A YouTube account (for cookies - trust me, you want this)

##  One-Command Installation

**Copy, paste, done:**

```bash
# On your Docker host, run:
docker exec -it lidarr bash -c "$(curl -fsSL https://raw.githubusercontent.com/fireishott/arr-scripts_Video/main/install.sh)"
