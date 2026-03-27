# Music Video Tools Sidecar

<p align="center">
  <strong>A standalone Docker sidecar for scanning, downloading, and managing music videos outside Lidarr.</strong>
</p>

## Overview

This project is the first pass of a major release that moves the old `arr-scripts_Video` workflow out of the Lidarr container and into its own web app.

The current sidecar includes:

- a FastAPI backend
- a browser-based UI
- YouTube search and download support through `yt-dlp`
- artist-folder scanning for missing metadata and missing videos
- NFO and thumbnail generation
- runtime settings persisted outside the container
- Docker packaging for standalone deployment

Lidarr integration is being reintroduced as an optional adapter instead of a hard dependency.

## Project Layout

```text
app/
  main.py
  config.py
  state.py
  models.py
  services/
  static/
  templates/
docker/
  compose.example.yml
docs/
```

## What This Release Is

- a sidecar-first architecture
- deployable in Docker without injecting scripts into Lidarr
- designed to own its own config, logs, and state

## What This Release Is Not Yet

- a finished Lidarr sync implementation
- a full migration of every legacy Bash feature
- a production-hardened final UI

## Requirements

- Docker with Compose support
- a writable appdata location
- a mounted music video library path
- optional YouTube cookies file for authenticated downloads

## Test Deployment

The examples below are written for your host layout:

- appdata root: `/docker/appdata_remote`
- app folder: `/docker/appdata_remote/musicvideotools`
- host: `192.168.10.101`

### 1. Prepare folders

Create the following folders on the Docker host:

```text
/docker/appdata_remote/musicvideotools/
  config/
  data/
  downloads/
  logs/
```

If you use YouTube cookies, place the file here:

```text
/docker/appdata_remote/musicvideotools/config/cookies.txt
```

### 2. Copy the compose example

Use [`docker/compose.example.yml`](docker/compose.example.yml) as your starting point.

### 3. Update the media bind mount

Replace this placeholder volume:

```yaml
- /path/to/your/musicvideos:/musicvideos
```

with your real host media path.

### 4. Build and start

From the deployment directory, run:

```bash
docker compose up -d --build
```

### 5. Open the app

Browse to:

```text
http://192.168.10.101:8080
```

### 6. Smoke test checklist

After the container starts:

1. Open the web UI.
2. Confirm the artist list loads from the mounted `/musicvideos` folder.
3. Run a scan and verify progress updates in the UI.
4. Search for a test artist in the Download tab.
5. Download one video and confirm the output file, `.nfo`, and thumbnail appear under that artist folder.
6. Change a setting and confirm it persists in `/app/data/runtime_config.json`.

## Runtime Paths

Inside the container, the app uses:

- `/app/config`
- `/app/data`
- `/app/logs`
- `/musicvideos`
- `/downloads`

## Environment Variables

Common settings:

- `APP_PORT`
- `MUSIC_VIDEOS_PATH`
- `DOWNLOADS_PATH`
- `COOKIES_FILE`
- `FILTER_AUDIO_ONLY`
- `MIN_VIDEO_DIMENSION`
- `MIN_DURATION`
- `MAX_DURATION`
- `SCHEDULE_ENABLED`
- `SCHEDULE_INTERVAL_HOURS`
- `LIDARR_ENABLED`
- `LIDARR_URL`
- `LIDARR_API_KEY`

See [`docker/compose.example.yml`](docker/compose.example.yml) and [`.env.example`](.env.example) for the current defaults.

## Local Development

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the app:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Current Status

This repository now contains both:

- the legacy Lidarr-coupled Bash workflow under [`lidarr/`](lidarr/)
- the new standalone sidecar app under [`app/`](app/)

The sidecar path is the active direction for the next major release.

## Related Docs

- [`docs/SIDECAR_RELEASE_PLAN.md`](docs/SIDECAR_RELEASE_PLAN.md)
- [`docs/DOCKER_SIDECAR_DEPLOY.md`](docs/DOCKER_SIDECAR_DEPLOY.md)

## Credits

This project is still inspired by the original `arr-scripts` ecosystem and the broader homelab media community.

Thanks to:

- RandomNinjaAtk for the original inspiration
- the Lidarr team
- the `yt-dlp` developers
- the self-hosting community pushing these workflows forward
