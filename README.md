# Lidarr Music Video Downloader

<p align="center">
  <strong>Automatically download official music videos for your Lidarr artists</strong>
</p>

## What It Does

This script runs inside your Lidarr container and automatically builds a music video library that Plex, Jellyfin, or Emby will love.

## Features

| | |
|---|---|
| ** YouTube Direct** | Searches YouTube for official music videos with smart filtering |
| ** Metadata** | Creates NFO files with MusicBrainz artist IDs and genres |
| ** Thumbnails** | Downloads high-quality YouTube thumbnails for every video |
| ** Tag Support** | Only process artists with a specific Lidarr tag - you're in control |
| ** Safe Operation** | Never deletes, renames, or modifies your existing files |
| ** Optimized** | Built-in rate limiting to avoid YouTube blocks |
| ** Docker First** | Works perfectly with any Lidarr Docker image |

##  Prerequisites

-  Lidarr running in Docker ([linuxserver](https://docs.linuxserver.io/images/docker-lidarr) or [hotio](https://hotio.dev/containers/lidarr) images)
-  Basic Docker knowledge (`docker exec`, `docker logs`)
-  A YouTube account (for cookies - trust me, you want this)

## Contributing
-  Fork the repository
-  Create your feature branch (git checkout -b feature/AmazingFeature)
-  Commit your changes (git commit -m 'Add some AmazingFeature')
-  Push to the branch (git push origin feature/AmazingFeature)
-  Open a Pull Request

## Credits
This project is based on the incredible work of RandomNinjaAtk whose arr-scripts provided the foundation and inspiration.
If you find this useful, please consider sponsoring the original author: https://github.com/sponsors/RandomNinjaAtk

<p align="center">
  <a href="https://github.com/RandomNinjaAtk/arr-scripts">
    <img src="https://img.shields.io/badge/based_on-RandomNinjaAtk-blueviolet?style=for-the-badge" alt="Based on RandomNinjaAtk arr-scripts">
  </a>
  <a href="https://github.com/sponsors/RandomNinjaAtk">
    <img src="https://img.shields.io/badge/sponsor-RandomNinjaAtk-red?style=for-the-badge" alt="Sponsor RandomNinjaAtk">
  </a>
</p>

