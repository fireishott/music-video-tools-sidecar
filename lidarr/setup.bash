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

# Install yt-dlp if not present
echo "Checking for yt-dlp..."
if ! command -v yt-dlp &> /dev/null; then
    echo "yt-dlp not found, installing..."
    # Try apk first (Alpine package manager)
    if command -v apk &> /dev/null; then
        apk add --no-cache yt-dlp || {
            echo "Failed to install yt-dlp via apk, trying pip..."
            pip install yt-dlp --break-system-packages || {
                echo "ERROR: Could not install yt-dlp"
                exit 1
            }
        }
    else
        # Fallback to pip if apk not available
        pip install yt-dlp --break-system-packages || {
            echo "ERROR: Could not install yt-dlp via pip"
            exit 1
        }
    fi
else
    echo "yt-dlp already installed"
fi

# Verify yt-dlp is now available
if ! command -v yt-dlp &> /dev/null; then
    echo "ERROR: yt-dlp installation failed"
    exit 1
fi

echo "Downloading main script..."
curl -sfL "${REPO_BASE}/Video" -o "${SCRIPT_DIR}/Video"
chmod +x "${SCRIPT_DIR}/Video"

# Copy to custom-services.d for auto-start
mkdir -p /custom-services.d
cp "${SCRIPT_DIR}/Video" /custom-services.d/Video
chmod +x /custom-services.d/Video

echo "Downloading functions..."
curl -sfL "${REPO_BASE}/functions" -o "${SCRIPT_DIR}/functions"
chmod +x "${SCRIPT_DIR}/functions"

echo "Downloading example config..."
curl -sfL "${REPO_BASE}/extended.conf.example" -o "${SCRIPT_DIR}/extended.conf.example"

echo "Installation complete"
exit 0
