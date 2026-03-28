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

function formatPercent(value) {
    const numeric = Number(value || 0);
    if (!Number.isFinite(numeric)) return "0%";
    if (numeric === 0 || numeric >= 10) return `${Math.round(numeric)}%`;
    return `${numeric.toFixed(1)}%`;
}

function formatEta(seconds) {
    if (seconds == null || !Number.isFinite(Number(seconds))) return "Calculating...";
    const total = Math.max(0, Math.round(Number(seconds)));
    if (total === 0) return "Almost done";
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    if (hours > 0) return `${hours}h ${minutes}m`;
    if (minutes > 0) return `${minutes}m ${secs}s`;
    return `${secs}s`;
}

function formatStepCount(completed, total) {
    if (!total) return "0 / 0";
    return `${completed || 0} / ${total || 0}`;
}

function humanizeIssueType(value) {
    return String(value || "unknown_issue")
        .replace(/_/g, " ")
        .replace(/\b\w/g, (char) => char.toUpperCase());
}

function setStatus(text, variant, detail) {
    const badge = document.getElementById("status-badge");
    badge.className = `status-badge ${variant}`;
    badge.textContent = text;
    document.getElementById("current-status").textContent = detail;
}

function setScanControlsVisible(visible) {
    document.getElementById("stopScanBtn").style.display = visible ? "inline-block" : "none";
}

function setResumeControlsVisible(visible) {
    document.getElementById("resumeScanBtn").style.display = visible ? "inline-block" : "none";
    document.getElementById("resumeScheduleBtn").style.display = visible ? "inline-block" : "none";
}

function appendScheduleEvent(message) {
    if (!message) return;
    const panel = document.getElementById("scheduleInfo");
    const timestamp = new Date().toLocaleTimeString();
    const existing = panel.textContent.trim();
    const nextLine = `[${timestamp}] ${message}`;
    panel.textContent = existing && existing !== "Waiting for the next schedule event."
        ? `${existing}\n${nextLine}`
        : nextLine;
    panel.scrollTop = panel.scrollHeight;
}

function appendScheduleDebugLog(message) {
    if (!message) return;
    const panel = document.getElementById("scheduleDebugPanel");
    const existing = panel.textContent.trim();
    panel.textContent = existing && existing !== "Waiting for scheduler trace output."
        ? `${existing}\n${message}`
        : message;
    panel.scrollTop = panel.scrollHeight;
}

function resetScheduleEventLog(messages) {
    const panel = document.getElementById("scheduleInfo");
    if (Array.isArray(messages) && messages.length) {
        panel.textContent = messages.map((entry) => `- ${entry}`).join("\n");
    } else {
        panel.textContent = "Waiting for the next schedule event.";
    }
}

function resetScheduleDebugLog(messages) {
    const panel = document.getElementById("scheduleDebugPanel");
    if (Array.isArray(messages) && messages.length) {
        panel.textContent = messages.join("\n");
    } else {
        panel.textContent = "Waiting for scheduler trace output.";
    }
}

function renderIssueBreakdown(breakdown) {
    const container = document.getElementById("scheduleIssueBreakdown");
    const entries = Object.entries(breakdown || {}).sort((left, right) => right[1] - left[1]);
    if (!entries.length) {
        container.innerHTML = '<div class="schedule-issue-empty">No findings yet.</div>';
        return;
    }
    container.innerHTML = entries.map(([issue, count]) => `
        <div class="schedule-issue-row">
            <div class="schedule-issue-name">${escapeHtml(humanizeIssueType(issue))}</div>
            <div class="schedule-issue-count">${count}</div>
        </div>
    `).join("");
}

function renderScheduleProgressBars(payload) {
    const overall = Number(payload.progress || 0);
    const currentAction = Number(payload.current_action_progress || 0);
    const currentArtist = Number(payload.current_artist_progress || 0);

    document.getElementById("scheduleOverallFill").style.width = `${overall}%`;
    document.getElementById("scheduleCurrentActionFill").style.width = `${currentAction}%`;
    document.getElementById("scheduleArtistFill").style.width = `${currentArtist}%`;

    document.getElementById("scheduleOverallPercent").textContent = formatPercent(overall);
    document.getElementById("scheduleCurrentActionPercent").textContent = formatPercent(currentAction);
    document.getElementById("scheduleArtistPercent").textContent = formatPercent(currentArtist);

    document.getElementById("scheduleOverallNote").textContent = payload.running
        ? `${payload.artists_completed || 0} of ${payload.artists_total || 0} artist folders completed`
        : "Waiting for the next run.";
    document.getElementById("scheduleCurrentActionNote").textContent = payload.current_action_total_steps
        ? `${formatStepCount(payload.current_action_completed_steps, payload.current_action_total_steps)} steps in this action`
        : "No active action.";
    document.getElementById("scheduleArtistProgressNote").textContent = payload.current_artist_total_steps
        ? `${formatStepCount(payload.current_artist_completed_steps, payload.current_artist_total_steps)} steps in this artist folder`
        : "No artist in flight.";
}

function syncGlobalScanHud(payload) {
    const progress = Number(payload.progress || 0);
    document.getElementById("scan-progress").style.width = `${progress}%`;
    document.getElementById("scan-progress-stat").textContent = formatPercent(progress);
    if (payload.running) {
        const detail = payload.current_artist || "Scheduled scan running";
        setStatus("Scanning", "status-running", detail);
        setScanControlsVisible(true);
        setResumeControlsVisible(false);
        document.getElementById("scanResults").textContent =
            `${detail}\nArtists: ${payload.artists_completed || 0}/${payload.artists_total || 0}\nIssues: ${payload.issue_count || 0}\nActions: ${payload.action_count || 0}\nAction: ${payload.current_action_label || "Working"}`;
    } else if (payload.progress && payload.progress >= 100) {
        setStatus("Idle", "status-idle", "Ready");
        setScanControlsVisible(false);
    }
    setResumeControlsVisible(!!payload.resume_available && !payload.running);
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
    window.__lastSchedulePayload = payload;
    document.getElementById("schedule-indicator").textContent = payload.enabled ? `Every ${payload.interval_hours}h` : "Off";
    document.getElementById("scheduleEnabled").checked = !!payload.enabled;
    document.getElementById("scheduleIntervalHours").value = String(payload.interval_hours);
    document.getElementById("scheduleAutoDownload").checked = !!payload.auto_download;
    document.getElementById("scheduleAutoStats").checked = !!payload.auto_update_stats;
    document.getElementById("scheduleDetectOrphans").checked = !!payload.detect_orphans;
    document.getElementById("scheduleRemoveOrphans").checked = !!payload.remove_orphans;
    document.getElementById("scheduleDetectDuplicates").checked = !!payload.detect_duplicates;
    document.getElementById("scheduleDetectQualityIssues").checked = !!payload.detect_quality_issues;
    document.getElementById("scheduleDetectFakeTraits").checked = !!payload.detect_fake_video_traits;
    document.getElementById("scheduleRemoveNoMetadata").checked = !!payload.remove_videos_without_metadata;
    document.getElementById("scheduleUpdateStaleStats").checked = !!payload.update_stale_stats;
    document.getElementById("scheduleLowerQualityAction").value = payload.lower_quality_action || (payload.upgrade_lower_quality ? "quarantine" : "none");
    document.getElementById("scheduleConcurrentFiles").value = String(payload.concurrent_files);
    document.getElementById("scheduleMaxDownloadsPerArtist").value = String(payload.max_downloads_per_artist);
    document.getElementById("scheduleVaapiDevice").textContent = payload.vaapi_device || "/dev/dri/renderD128";
    renderScheduleStatus(payload);
    syncGlobalScanHud(payload);
    resetScheduleEventLog(payload.recent_events);
    resetScheduleDebugLog(payload.debug_logs);
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
    window.__lastSchedulePayload = payload;
    const cadenceLabel = `Every ${payload.interval_hours} hour${payload.interval_hours === 1 ? "" : "s"}`;
    const running = !!payload.running;
    const enabled = !!payload.enabled;
    const statePill = document.getElementById("scheduleStatePill");
    const currentArtist = payload.current_artist || (running ? "Starting..." : "Idle");
    const currentActionLabel = payload.current_action_label || (running ? "Preparing" : "Waiting");

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
    document.getElementById("scheduleRunStartValue").textContent = running
        ? formatScheduleDate(payload.scan_started_at)
        : payload.last_run
            ? formatScheduleDate(payload.last_run)
            : "Not running";
    document.getElementById("scheduleActionEtaValue").textContent = running
        ? formatEta(payload.current_action_eta_seconds)
        : "Waiting";
    document.getElementById("scheduleTotalEtaValue").textContent = running
        ? formatEta(payload.total_eta_seconds)
        : enabled
            ? "Waiting for next run"
            : "Schedule disabled";
    document.getElementById("scheduleCurrentArtist").textContent = currentArtist;
    document.getElementById("scheduleCurrentArtistNote").textContent = running
        ? `Started ${formatScheduleDate(payload.current_artist_started_at)}`
        : "No scan is active right now.";
    document.getElementById("scheduleArtistsDone").textContent = `${payload.artists_completed || 0} / ${payload.artists_total || 0}`;
    document.getElementById("scheduleArtistsDoneNote").textContent = running
        ? "Completed artist folders in this run."
        : "Waiting for the next run.";
    document.getElementById("scheduleActionLabel").textContent = currentActionLabel;
    document.getElementById("scheduleActionDetail").textContent = payload.current_action_detail || "No scheduled work is active.";
    document.getElementById("scheduleIssueCount").textContent = String(payload.issue_count || 0);
    document.getElementById("scheduleActionCount").textContent = String(payload.action_count || 0);

    statePill.textContent = running ? "Schedule Running" : enabled ? "Schedule Active" : "Schedule Off";
    statePill.className = `schedule-state-pill ${running ? "is-running" : enabled ? "is-active" : "is-off"}`;

    const saveButton = document.getElementById("saveScheduleBtn");
    const runButton = document.getElementById("runScheduleBtn");
    const resumeButton = document.getElementById("resumeScheduleBtn");
    runButton.disabled = running;
    resumeButton.disabled = running || !payload.resume_available;
    saveButton.disabled = false;
    setResumeControlsVisible(!!payload.resume_available && !running);

    const summaryParts = [
        enabled ? `${cadenceLabel} schedule enabled.` : "Schedule disabled.",
        payload.auto_download ? "Auto-download missing videos is on." : "Auto-download missing videos is off.",
        payload.auto_update_stats ? "Auto-update stats is on." : "Auto-update stats is off.",
        `Concurrency: ${payload.concurrent_files} file${payload.concurrent_files === 1 ? "" : "s"} at a time.`,
        `Per-artist download cap: ${payload.max_downloads_per_artist}.`,
    ];
    if (payload.detect_orphans) summaryParts.push("Orphan detection enabled.");
    if (payload.remove_orphans) summaryParts.push("Orphan cleanup enabled.");
    if (payload.detect_duplicates) summaryParts.push("Duplicate detection enabled.");
    if (payload.detect_quality_issues) summaryParts.push("Quality mismatch checks enabled.");
    if (payload.detect_fake_video_traits) summaryParts.push(`Fake-video trait checks enabled with ffmpeg sampling on ${payload.vaapi_device || "/dev/dri/renderD128"}.`);
    if (payload.remove_videos_without_metadata) summaryParts.push("Videos without metadata will be removed.");
    if (payload.lower_quality_action === "quarantine") summaryParts.push("Lower-quality bundles will be moved into a root _quarantine folder.");
    if (payload.lower_quality_action === "delete") summaryParts.push("Lower-quality bundles will be deleted during maintenance runs.");
    if (running) {
        summaryParts.push(`Current action: ${currentActionLabel}.`);
        summaryParts.push(`Current artist: ${currentArtist}.`);
    } else if (payload.resume_available) {
        summaryParts.push("A paused scan can be resumed from the interrupted artist.");
    } else if (enabled && payload.next_run) {
        summaryParts.push(`Next run: ${formatScheduleDate(payload.next_run)}.`);
    }
    document.getElementById("scheduleSummary").textContent = summaryParts.join(" ");
    renderScheduleProgressBars(payload);
    renderIssueBreakdown(payload.issue_breakdown);
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
    document.getElementById("gpu-usage").textContent = payload.gpu_percent == null ? "N/A" : `${payload.gpu_percent}%`;
    document.getElementById("gpu-usage").title = payload.gpu_source || "No GPU telemetry source detected";
}

function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${protocol}://${window.location.host}/ws`);
    ws.onopen = () => debugLog("WebSocket connected");
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === "schedule_log") {
            appendScheduleDebugLog(data.message);
            return;
        }
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
            document.getElementById("scan-progress-stat").textContent = formatPercent(data.progress || 0);
            document.getElementById("scanResults").textContent = `Scanning ${data.artist}\nIssues found: ${data.issues}`;
            setScanControlsVisible(true);
            setStatus("Scanning", "status-running", data.artist || "Scanning");
            renderScheduleStatus({
                ...window.__lastSchedulePayload,
                running: true,
                progress: data.progress || 0,
                current_artist: data.artist || "",
                artists_completed: data.artist_index || 0,
                artists_total: data.artist_total || 0,
                issue_count: data.issue_total || 0,
                action_count: data.action_total || 0,
                current_action_label: data.current_action_label || window.__lastSchedulePayload?.current_action_label,
                current_action_detail: data.current_action_detail || window.__lastSchedulePayload?.current_action_detail,
                current_action_progress: data.current_action_progress ?? window.__lastSchedulePayload?.current_action_progress,
                current_artist_progress: data.current_artist_progress ?? window.__lastSchedulePayload?.current_artist_progress,
                current_action_completed_steps: window.__lastSchedulePayload?.current_action_completed_steps,
                current_action_total_steps: window.__lastSchedulePayload?.current_action_total_steps,
                current_artist_completed_steps: window.__lastSchedulePayload?.current_artist_completed_steps,
                current_artist_total_steps: window.__lastSchedulePayload?.current_artist_total_steps,
                issue_breakdown: data.issue_breakdown || window.__lastSchedulePayload?.issue_breakdown || {},
            });
            appendScheduleEvent(
                data.event || `${data.artist}: ${data.issues || 0} issue(s), ${data.actions || 0} action(s), ${data.downloads_added || 0} download(s)`
            );
        } else if (data.type === "scan_stopping") {
            debugLog(data.message || "Stopping scan");
            document.getElementById("scanResults").textContent = data.message || "Stopping scan";
            setScanControlsVisible(true);
            setStatus("Stopping", "status-running", data.message || "Stopping scan");
            appendScheduleEvent(data.message || "Stopping scan");
        } else if (data.type === "scan_stopped") {
            debugLog(data.message || "Scan stopped");
            document.getElementById("scanResults").textContent = data.message || "Scan stopped";
            setScanControlsVisible(false);
            setResumeControlsVisible(!!data.resume_available);
            setStatus("Idle", "status-idle", "Ready");
            appendScheduleEvent(data.message || "Scan stopped");
            loadScheduleStatus().catch((error) => debugLog(error.message));
        } else if (data.type === "scan_complete") {
            setScanControlsVisible(false);
            setStatus("Idle", "status-idle", "Ready");
            appendScheduleEvent(
                `Scan complete. ${data.issue_total || 0} issue(s), ${data.action_total || 0} action(s), ${data.artist_total || 0} artist(s).`
            );
            if (data.issue_breakdown) {
                renderIssueBreakdown(data.issue_breakdown);
            }
            loadScheduleStatus().catch((error) => debugLog(error.message));
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
                detect_orphans: document.getElementById("scheduleDetectOrphans").checked,
                remove_orphans: document.getElementById("scheduleRemoveOrphans").checked,
                detect_duplicates: document.getElementById("scheduleDetectDuplicates").checked,
                detect_quality_issues: document.getElementById("scheduleDetectQualityIssues").checked,
                detect_fake_video_traits: document.getElementById("scheduleDetectFakeTraits").checked,
                remove_videos_without_metadata: document.getElementById("scheduleRemoveNoMetadata").checked,
                update_stale_stats: document.getElementById("scheduleUpdateStaleStats").checked,
                upgrade_lower_quality: document.getElementById("scheduleLowerQualityAction").value !== "none",
                lower_quality_action: document.getElementById("scheduleLowerQualityAction").value,
                concurrent_files: Number(document.getElementById("scheduleConcurrentFiles").value),
                max_downloads_per_artist: Number(document.getElementById("scheduleMaxDownloadsPerArtist").value),
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
    setScanControlsVisible(true);
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
    const resumeScan = async () => {
        await getJson("/api/scan/resume", { method: "POST" });
        setResumeControlsVisible(false);
        setScanControlsVisible(true);
        setStatus("Scanning", "status-running", "Resuming paused scan");
        appendScheduleEvent("Resume requested. Restarting from the interrupted artist.");
        await loadScheduleStatus();
        debugLog("Paused scan resumed");
    };
    document.getElementById("resumeScanBtn").addEventListener("click", resumeScan);
    document.getElementById("resumeScheduleBtn").addEventListener("click", resumeScan);
    document.getElementById("runScheduleBtn").addEventListener("click", async () => {
        const runButton = document.getElementById("runScheduleBtn");
        runButton.disabled = true;
        runButton.textContent = "Starting...";
        try {
            renderScheduleStatus({
                ...window.__lastSchedulePayload,
                running: true,
                progress: 0,
                current_artist: "Starting scheduled run...",
                artists_completed: 0,
                artists_total: 0,
                issue_count: 0,
                action_count: 0,
                current_action_label: "Bootstrapping Run",
                current_action_detail: "Waking the scheduler worker and preparing scan state",
                current_action_progress: 0,
                current_artist_progress: 0,
                current_action_completed_steps: 0,
                current_action_total_steps: 1,
                current_artist_completed_steps: 0,
                current_artist_total_steps: 0,
                issue_breakdown: {},
            });
            appendScheduleEvent("Run requested. Preparing schedule worker...");
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
    document.getElementById("stopScanBtn").addEventListener("click", async () => {
        await getJson("/api/stop", { method: "POST" });
        debugLog("Stop requested for current scan");
    });
    document.getElementById("emergencyStopBtn").addEventListener("click", async () => {
        await getJson("/api/emergency-stop", { method: "POST" });
        debugLog("Emergency stop requested");
        setScanControlsVisible(false);
        document.getElementById("stopDownloadBtn").style.display = "none";
    });
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
    setInterval(() => {
        loadScheduleStatus().catch((error) => debugLog(error.message));
    }, 5000);
}

initialize().catch((error) => debugLog(error.message));
