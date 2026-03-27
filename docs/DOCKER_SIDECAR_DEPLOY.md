# Docker Sidecar Deploy

## Host paths

- Appdata root: `/docker/appdata_remote`
- App folder: `/docker/appdata_remote/musicvideotools`

## Recommended folders

```text
/docker/appdata_remote/musicvideotools/
  config/
    cookies.txt
  data/
  downloads/
  logs/
  compose.yml
  .env
```

## First deployment

1. Copy `docker/compose.example.yml` to `compose.yml`.
2. Update the `/musicvideos` bind mount to your real media path.
3. Place your YouTube cookies file at `config/cookies.txt` if you need authenticated downloads.
4. Build and start the container:

```bash
docker compose up -d --build
```

5. Open `http://192.168.10.101:8080`

## Notes

- Lidarr integration is not wired in yet for artist sync; this first pass keeps the sidecar runnable on its own.
- The app stores runtime settings in `/app/data/runtime_config.json`.
- The current UI and API are a foundation release, not the full production cut yet.

