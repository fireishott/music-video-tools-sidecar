let allArtists = [];
let currentSearchResults = [];
let selectedVideos = new Set();
let currentArtist = "";
let ws = null;

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>]/g, (match) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[match]));
}

function formatDuration(seconds) {
    if (!seconds) return "N/A";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${String(secs).padStart(2, "0")}`;
}

function debugLog(message) {
    const panel = document.getElementById("debugPanel");
    const timestamp = new Date().toLocaleTimeString();
    panel.textContent += `\n[${timestamp}] ${message}`;
    panel.scrollTop = panel.scrollHeight;
}

function setStatus(text, variant, detail) {
    const badge = document.getElementById("status-badge");
    badge.className = `status-badge ${variant}`;
    badge.textContent = text;
    document.getElementById("current-status").textContent = detail;
}

async function getJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
    }
    return response.json();
}

async function loadFolders() {
    allArtists = await getJson("/api/folders");
    document.getElementById("total-artists").textContent = allArtists.length;
    const select = document.getElementById("downloadArtistSelect");
    select.innerHTML = '<option value="">Select Artist...</option>' + allArtists.map((artist) => `<option value="${escapeHtml(artist)}">${escapeHtml(artist)}</option>`).join("");
}

async function loadMissingCount() {
    const payload = await getJson("/api/artists-with-missing");
    document.getElementById("missing-count").textContent = payload.count;
}

async function loadQueue() {
    const payload = await getJson("/api/queue");
    document.getElementById("queue-count").textContent = payload.queue.length;
}

async function loadDownloadRules() {
    const rules = await getJson("/api/download/rules");
    document.getElementById("minResolution").value = String(rules.min_resolution);
    document.getElementById("minDuration").value = String(rules.min_duration);
    document.getElementById("maxDuration").value = String(rules.max_duration);
    document.getElementById("filterAudioOnly").checked = !!rules.filter_audio_only;
}

async function loadScheduleStatus() {
    const payload = await getJson("/api/schedule/status");
    document.getElementById("schedule-indicator").textContent = payload.enabled ? `Every ${payload.interval_hours}h` : "Off";
    document.getElementById("scheduleEnabled").checked = !!payload.enabled;
    document.getElementById("scheduleIntervalHours").value = String(payload.interval_hours);
    document.getElementById("scheduleAutoDownload").checked = !!payload.auto_download;
    document.getElementById("scheduleAutoStats").checked = !!payload.auto_update_stats;
    renderScheduleStatus(payload);
}

function formatScheduleDate(value) {
    if (!value) return "Never";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "Unknown";
    return new Intl.DateTimeFormat([], {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(parsed);
}

function renderScheduleStatus(payload) {
    const cadenceLabel = `Every ${payload.interval_hours} hour${payload.interval_hours === 1 ? "" : "s"}`;
    const running = !!payload.running;
    const enabled = !!payload.enabled;
    const statePill = document.getElementById("scheduleStatePill");

    document.getElementById("scheduleStatusValue").textContent = running ? "Running now" : enabled ? "Enabled" : "Disabled";
    document.getElementById("scheduleStatusNote").textContent = running
        ? "A scheduled scan is currently in progress."
        : enabled
            ? "Automatic scans are armed and waiting for the next window."
            : "Automatic scans are currently turned off.";
    document.getElementById("scheduleCadenceValue").textContent = cadenceLabel;
    document.getElementById("scheduleCadenceNote").textContent = enabled
        ? "The next run is calculated from the most recent completed scan."
        : "Turn the schedule on to start recurring scans.";
    document.getElementById("scheduleNextRunValue").textContent = enabled ? formatScheduleDate(payload.next_run) : "Not scheduled";
    document.getElementById("scheduleNextRunNote").textContent = enabled
        ? "This updates after each save or completed scan."
        : "Enable the schedule to queue the next scan.";
    document.getElementById("scheduleLastRunValue").textContent = formatScheduleDate(payload.last_run);
    document.getElementById("scheduleLastRunNote").textContent = payload.last_run
        ? "Most recent completed library scan."
        : "A manual or scheduled scan will show up here.";

    statePill.textContent = running ? "Schedule Running" : enabled ? "Schedule Active" : "Schedule Off";
    statePill.className = `schedule-state-pill ${running ? "is-running" : enabled ? "is-active" : "is-off"}`;

    const saveButton = document.getElementById("saveScheduleBtn");
    const runButton = document.getElementById("runScheduleBtn");
    runButton.disabled = running;
    saveButton.disabled = false;

    const summaryParts = [
        enabled ? `${cadenceLabel} schedule enabled.` : "Schedule disabled.",
        payload.auto_download ? "Auto-download missing videos is on." : "Auto-download missing videos is off.",
        payload.auto_update_stats ? "Auto-update stats is on." : "Auto-update stats is off.",
    ];
    if (running) {
        summaryParts.push("A run is currently in progress.");
    } else if (enabled && payload.next_run) {
        summaryParts.push(`Next run: ${formatScheduleDate(payload.next_run)}.`);
    }
    document.getElementById("scheduleSummary").textContent = summaryParts.join(" ");
    document.getElementById("scheduleInfo").textContent = JSON.stringify(payload, null, 2);
}

async function loadConfig() {
    const payload = await getJson("/api/config");
    document.getElementById("enableMusicBrainz").checked = !!payload.enable_musicbrainz;
    document.getElementById("enableYoutubeStats").checked = !!payload.enable_youtube_stats;
    document.getElementById("enableFeaturedArtists").checked = !!payload.enable_featured_artists;
    document.getElementById("lidarrEnabled").checked = !!payload.lidarr_enabled;
    document.getElementById("lidarrUrl").value = payload.lidarr_url || "";
}

async function loadSystemStats() {
    const payload = await getJson("/api/system/stats");
    document.getElementById("disk-usage").textContent = `${payload.disk_percent}%`;
    document.getElementById("uptime").textContent = payload.uptime;
    document.getElementById("cpu-usage").textContent = `${payload.cpu_percent}%`;
    document.getElementById("memory-usage").textContent = `${payload.memory_percent}%`;
}

function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
    ws.onopen = () => debugLog("WebSocket connected");
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "download_progress") {
            document.getElementById("downloadProgress").style.display = "block";
            document.getElementById("downloadProgressFill").style.width = `${data.progress || 0}%`;
            document.getElementById("downloadStatus").textContent = `${data.processed || 0}/${data.total || 0}`;
            document.getElementById("downloadCurrent").textContent = data.current || "";
            document.getElementById("stopDownloadBtn").style.display = "inline-block";
            setStatus("Downloading", "status-downloading", data.current || "Working");
        } else if (data.type === "download_log") {
            debugLog(data.message);
        } else if (data.type === "download_complete") {
            debugLog(data.message || "Download complete");
            setStatus("Idle", "status-idle", "Ready");
            document.getElementById("stopDownloadBtn").style.display = "none";
        } else if (data.type === "download_stopped") {
            debugLog(data.message || "Download stopped");
            document.getElementById("stopDownloadBtn").style.display = "none";
            setStatus("Idle", "status-idle", "Ready");
        } else if (data.type === "scan_progress") {
            document.getElementById("scan-progress").style.width = `${data.progress || 0}%`;
            document.getElementById("scan-progress-stat").textContent = `${data.progress || 0}%`;
            document.getElementById("scanResults").textContent = `Scanning ${data.artist}\nIssues found: ${data.issues}`;
            setStatus("Scanning", "status-running", data.artist || "Scanning");
        } else if (data.type === "scan_complete") {
            setStatus("Idle", "status-idle", "Ready");
        }
    };
    ws.onclose = () => {
        debugLog("WebSocket disconnected, retrying...");
        setTimeout(connectWebSocket, 2000);
    };
}

function renderVideoResults() {
    const container = document.getElementById("videoResults");
    if (!currentSearchResults.length) {
        container.innerHTML = '<div class="empty-state">No results</div>';
        return;
    }
    container.innerHTML = currentSearchResults.map((video) => `
        <label class="video-card ${selectedVideos.has(video.id) ? "selected" : ""}" data-id="${video.id}">
            <img class="video-thumb" src="${video.thumbnail || ""}" alt="">
            <div>
                <div class="video-title">${escapeHtml(video.title || "Unknown")}</div>
                <div class="video-meta">${escapeHtml(video.uploader || "Unknown")} | ${formatDuration(video.duration)}</div>
                <div class="badge ${video.is_fake ? "warning" : "success"}">${video.is_fake ? escapeHtml(video.fake_reason || "Flagged") : "Looks good"}</div>
            </div>
            <input type="checkbox" class="video-checkbox" ${selectedVideos.has(video.id) ? "checked" : ""}>
        </label>
    `).join("");
    document.querySelectorAll(".video-card").forEach((card) => {
        const checkbox = card.querySelector(".video-checkbox");
        const update = () => {
            const id = card.dataset.id;
            if (checkbox.checked) selectedVideos.add(id);
            else selectedVideos.delete(id);
            card.classList.toggle("selected", checkbox.checked);
            document.getElementById("downloadSelectedBtn").textContent = `Download Selected (${selectedVideos.size})`;
        };
        checkbox.addEventListener("change", (event) => {
            event.stopPropagation();
            update();
        });
        card.addEventListener("click", (event) => {
            if (event.target === checkbox) return;
            checkbox.checked = !checkbox.checked;
            update();
        });
    });
}

async function searchVideos() {
    const artist = document.getElementById("downloadArtistSelect").value;
    const query = document.getElementById("searchQuery").value.trim();
    currentArtist = artist || query;
    if (!currentArtist) {
        debugLog("Choose an artist or enter a search query");
        return;
    }
    const payload = await getJson("/api/download/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: currentArtist, limit: 25 }),
    });
    currentSearchResults = payload.results || [];
    selectedVideos = new Set();
    renderVideoResults();
    document.getElementById("downloadSelectedBtn").textContent = "Download Selected (0)";
    const goodCount = currentSearchResults.filter((video) => !video.is_fake).length;
    debugLog(`Found ${currentSearchResults.length} results for ${currentArtist} (${goodCount} looks good)`);
}

async function startDownload(selectedOnly) {
    if (!currentArtist) {
        debugLog("Select an artist first");
        return;
    }
    const includeFlagged = document.getElementById("includeFlaggedDownloads").checked;
    const videos = selectedOnly
        ? currentSearchResults.filter((video) => selectedVideos.has(video.id))
        : currentSearchResults.filter((video) => includeFlagged || !video.is_fake);
    if (!videos.length) {
        debugLog("No videos selected");
        return;
    }
    await getJson("/api/download/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ artist: currentArtist, videos, allow_flagged: selectedOnly ? true : includeFlagged }),
    });
    document.getElementById("downloadProgress").style.display = "block";
    document.getElementById("downloadStatus").textContent = `0/${videos.length}`;
    document.getElementById("downloadProgressFill").style.width = "0%";
    document.getElementById("stopDownloadBtn").style.display = "inline-block";
    setStatus("Downloading", "status-downloading", currentArtist);
}

async function saveDownloadRules() {
    await getJson("/api/download/rules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            min_resolution: Number(document.getElementById("minResolution").value),
            min_duration: Number(document.getElementById("minDuration").value),
            max_duration: Number(document.getElementById("maxDuration").value),
            filter_audio_only: document.getElementById("filterAudioOnly").checked,
        }),
    });
    debugLog("Download rules saved");
}

async function saveSchedule() {
    const saveButton = document.getElementById("saveScheduleBtn");
    saveButton.disabled = true;
    saveButton.textContent = "Saving...";
    try {
        await getJson("/api/schedule/configure", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                enabled: document.getElementById("scheduleEnabled").checked,
                interval_hours: Number(document.getElementById("scheduleIntervalHours").value),
                auto_download: document.getElementById("scheduleAutoDownload").checked,
                auto_update_stats: document.getElementById("scheduleAutoStats").checked,
            }),
        });
        await loadScheduleStatus();
        debugLog("Schedule updated");
    } finally {
        saveButton.disabled = false;
        saveButton.textContent = "Save Schedule";
    }
}

async function saveSettings() {
    await getJson("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            enable_musicbrainz: document.getElementById("enableMusicBrainz").checked,
            enable_youtube_stats: document.getElementById("enableYoutubeStats").checked,
            enable_featured_artists: document.getElementById("enableFeaturedArtists").checked,
            lidarr_enabled: document.getElementById("lidarrEnabled").checked,
            lidarr_url: document.getElementById("lidarrUrl").value.trim(),
        }),
    });
    debugLog("Settings saved");
}

async function scanAllArtists() {
    await getJson("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ artists: [] }),
    });
    setStatus("Scanning", "status-running", "All artists");
}

async function downloadMissingAll() {
    await getJson("/api/download-missing-all", { method: "POST" });
    debugLog("Started missing artist downloads");
}

async function initialize() {
    document.getElementById("themeToggle").addEventListener("click", () => document.body.classList.toggle("light"));
    document.querySelectorAll(".tab-btn").forEach((button) => {
        button.addEventListener("click", () => {
            document.querySelectorAll(".tab-btn").forEach((item) => item.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach((item) => item.classList.remove("active"));
            button.classList.add("active");
            document.getElementById(`${button.dataset.tab}-tab`).classList.add("active");
        });
    });
    document.getElementById("searchBtn").addEventListener("click", searchVideos);
    document.getElementById("downloadSelectedBtn").addEventListener("click", () => startDownload(true));
    document.getElementById("downloadAllBtn").addEventListener("click", () => startDownload(false));
    document.getElementById("stopDownloadBtn").addEventListener("click", async () => {
        await getJson("/api/download/stop", { method: "POST" });
    });
    document.getElementById("applyFiltersBtn").addEventListener("click", saveDownloadRules);
    document.getElementById("saveScheduleBtn").addEventListener("click", saveSchedule);
    document.getElementById("runScheduleBtn").addEventListener("click", async () => {
        const runButton = document.getElementById("runScheduleBtn");
        runButton.disabled = true;
        runButton.textContent = "Starting...";
        try {
            await getJson("/api/schedule/run", { method: "POST" });
            await loadScheduleStatus();
            debugLog("Manual scheduled run started");
        } finally {
            runButton.disabled = false;
            runButton.textContent = "Run Now";
        }
    });
    document.getElementById("saveSettingsBtn").addEventListener("click", saveSettings);
    document.getElementById("scanAllBtn").addEventListener("click", scanAllArtists);
    document.getElementById("refreshArtistsBtn").addEventListener("click", async () => {
        await loadFolders();
        await loadMissingCount();
    });
    document.getElementById("downloadMissingAllBtn").addEventListener("click", downloadMissingAll);
    document.getElementById("searchQuery").addEventListener("keydown", (event) => {
        if (event.key === "Enter") searchVideos();
    });

    await loadFolders();
    await loadMissingCount();
    await loadQueue();
    await loadDownloadRules();
    await loadScheduleStatus();
    await loadConfig();
    await loadSystemStats();
    connectWebSocket();
    setInterval(loadSystemStats, 5000);
}

initialize().catch((error) => debugLog(error.message));
