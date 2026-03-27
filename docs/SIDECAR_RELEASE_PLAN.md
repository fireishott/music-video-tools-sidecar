# Music Video Tools Sidecar Release Plan

## Goal

Turn `arr-scripts_Video` from a Lidarr-injected Bash script into a standalone sidecar app that:

- runs as its own Docker container
- optionally talks to Lidarr over HTTP instead of running inside it
- owns its own config, logs, state, downloads, and frontend
- can scan/download/update metadata without LinuxServer init hooks

## Current State

The current repo is tightly coupled to Lidarr container internals:

- startup depends on `/custom-cont-init.d` and `/custom-services.d`
- config is read from `/config/extended.conf`
- the main workflow is a single Bash service in `lidarr/Video`
- Lidarr is assumed to be available at `http://localhost:8686`
- artist discovery comes directly from the Lidarr API and container-mounted artist paths

The FastAPI prototype is the right direction, but it currently mixes:

- API logic
- background job state
- filesystem layout assumptions
- HTML/CSS/JS inline assets
- Linux-specific host inspection

## The Right First Cut

Before adding more features, we should define a stable standalone app shape:

1. Backend service
2. Frontend assets
3. Config/state storage
4. Docker packaging
5. Optional Lidarr integration layer

## Recommended Target Structure

```text
app/
  api/
  services/
  integrations/
  models/
  workers/
  templates/
  static/
  main.py
docker/
  Dockerfile
  compose.example.yml
data/
docs/
```

## Service Boundaries

### Core app

Owns:

- search YouTube
- download videos
- generate NFO and artwork
- manage queue and job progress
- schedule scans
- expose REST and WebSocket APIs

Should not assume Lidarr exists.

### Lidarr integration

Optional adapter that:

- fetches artists from Lidarr
- reads artist metadata and MusicBrainz IDs
- triggers rescans if needed

This should be configurable with environment variables like:

- `LIDARR_URL`
- `LIDARR_API_KEY`
- `LIDARR_TAG`
- `LIDARR_ENABLED`

## Docker Layout

For your host:

- appdata root: `/docker/appdata_remote`
- deploy directory: `/docker/appdata_remote/musicvideotools`

Recommended persistent mounts inside the container:

- `/app/config`
- `/app/data`
- `/musicvideos`
- `/downloads`

Suggested host layout:

```text
/docker/appdata_remote/musicvideotools/
  compose.yml
  .env
  config/
    cookies.txt
  data/
  logs/
```

If your media library already lives elsewhere, mount that existing location into `/musicvideos`.

## Phase Plan

### Phase 1: Extract a standalone backend

Build a Python service that:

- reads config from env vars or JSON
- uses a real app state object instead of module globals
- separates YouTube search/download/NFO generation into service modules
- writes state to `/app/data`

Deliverable:

- backend runs without Lidarr

### Phase 2: Clean frontend integration

Move inline HTML into:

- `templates/index.html`
- `static/app.css`
- `static/app.js`

Then make the frontend consume a stable API contract:

- `/api/config`
- `/api/folders`
- `/api/download/search`
- `/api/download/start`
- `/api/schedule/*`
- `/ws`

Deliverable:

- frontend and backend stop fighting over message shape and state assumptions

### Phase 3: Add optional Lidarr adapter

Implement a client module for:

- fetching artists
- reading artist paths
- reading MusicBrainz IDs
- optionally limiting by tag

Deliverable:

- app works with or without Lidarr

### Phase 4: Dockerize

Create:

- `Dockerfile`
- `docker-compose` example
- healthcheck
- volume strategy

Deliverable:

- deployable to `192.168.10.101`

### Phase 5: Release hardening

Add:

- persisted config
- better logging
- download retry handling
- graceful shutdown
- test coverage for core filename/NFO logic

## First Implementation Task

The best place to begin is:

`Extract the FastAPI prototype into a real standalone app skeleton and make it run from Docker without Lidarr.`

That means the first coding pass should focus on:

- creating a Python package layout
- moving globals into an app state/service layer
- externalizing paths and settings
- splitting the frontend into separate files

## Immediate Non-Goals

Do not do these first:

- deep UI polish
- more Lidarr-specific Bash work
- host-level system metrics tied to `/proc`
- auto-rescan behavior inside Lidarr containers

Those can come after the standalone service is stable.

## Definition of Done for the New Major Release

The release is successful when:

- the app runs as its own container
- Lidarr is optional, not required
- config is persisted outside the container
- downloads and NFO generation work through the web UI
- deployment only needs Docker mounts and environment variables

