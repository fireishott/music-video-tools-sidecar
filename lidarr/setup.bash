#!/usr/bin/with-contenv bash
set -euo pipefail

REPO_BASE="https://raw.githubusercontent.com/fireishott/arr-scripts_Video/main/lidarr"
SCRIPT_DIR="/config/extended"

echo "Creating directories..."
mkdir -p "$SCRIPT_DIR"
mkdir -p "$SCRIPT_DIR/cache"
mkdir -p "$SCRIPT_DIR/cache/ytdlp"
mkdir -p "$SCRIPT_DIR/logs"
mkdir -p "$SCRIPT_DIR/logs/video"
mkdir -p "$SCRIPT_DIR/downloads"
mkdir -p "$SCRIPT_DIR/downloads/videos"

echo "Downloading main script..."
curl -sfL "${REPO_BASE}/Video" -o "${SCRIPT_DIR}/Video"
chmod +x "${SCRIPT_DIR}/Video"

echo "Downloading functions..."
curl -sfL "${REPO_BASE}/functions" -o "${SCRIPT_DIR}/functions"
chmod +x "${SCRIPT_DIR}/functions"

echo "Downloading example config..."
curl -sfL "${REPO_BASE}/extended.conf.example" -o "${SCRIPT_DIR}/extended.conf.example"

echo "Installation complete"
exit 0
