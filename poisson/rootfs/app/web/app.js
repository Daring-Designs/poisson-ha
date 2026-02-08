/**
 * Poisson — Ingress UI
 * Lightweight dashboard with live activity feed.
 *
 * Uses /papi/ prefix (not /api/) to avoid collision with HA's own
 * /api/ namespace which its service worker intercepts.
 */

(function () {
  "use strict";

  let pollInterval = null;

  // --- DOM references ---
  const statusBadge = document.getElementById("status-badge");
  const uptimeEl = document.getElementById("uptime");
  const personaEl = document.getElementById("persona");
  const intensitySelector = document.getElementById("intensity-selector");
  const engineToggles = document.getElementById("engine-toggles");
  const activityFeed = document.getElementById("activity-feed");
  const statSessions = document.getElementById("stat-sessions");
  const statRequests = document.getElementById("stat-requests");
  const statBandwidth = document.getElementById("stat-bandwidth");
  const statActive = document.getElementById("stat-active");

  // --- Helpers ---
  function formatUptime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h > 0) return h + "h " + m + "m";
    return m + "m";
  }

  function formatTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  async function fetchJSON(path, opts) {
    try {
      const res = await fetch(path, opts);
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  // --- Status polling ---
  async function updateStatus() {
    const status = await fetchJSON("papi/status");
    if (!status) {
      statusBadge.textContent = "Error";
      statusBadge.className = "badge badge-error";
      return;
    }

    statusBadge.textContent = status.status;
    statusBadge.className = "badge badge-" + status.status;
    uptimeEl.textContent = "Uptime: " + formatUptime(status.uptime_seconds);
    personaEl.textContent = "Persona: " + status.current_persona;

    // Show fingerprint matching status
    var fpEl = document.getElementById("fingerprint-status");
    if (fpEl) {
      if (status.fingerprint_matched) {
        fpEl.textContent = "Fingerprint Matched";
        fpEl.className = "badge badge-fingerprint active";
      } else {
        fpEl.textContent = "Fingerprint Unmatched";
        fpEl.className = "badge badge-fingerprint";
      }
    }

    // Update intensity buttons
    intensitySelector.querySelectorAll(".intensity-btn").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.level === status.intensity);
    });
  }

  async function updateStats() {
    const data = await fetchJSON("papi/stats");
    if (!data) return;

    statSessions.textContent = data.sessions_today;
    statRequests.textContent = data.requests_today;
    statBandwidth.textContent = data.bandwidth_today_mb + " MB";
    statActive.textContent = data.active_sessions;
  }

  async function updateEngines() {
    const data = await fetchJSON("papi/engines");
    if (!data || !data.engines) return;

    engineToggles.innerHTML = "";
    Object.keys(data.engines).forEach(function (name) {
      var eng = data.engines[name];
      var el = document.createElement("div");
      el.className = "engine-toggle" + (eng.enabled ? " active" : "");
      el.innerHTML = '<span class="dot"></span>' + name;
      el.addEventListener("click", function () {
        toggleEngine(name);
      });
      engineToggles.appendChild(el);
    });
  }

  async function updateActivity() {
    const data = await fetchJSON("papi/activity?count=50");
    if (!data || !data.activity || data.activity.length === 0) return;

    activityFeed.innerHTML = "";
    data.activity.forEach(function (entry) {
      var el = document.createElement("div");
      el.className = "activity-entry";
      el.innerHTML =
        '<span class="activity-time">' + formatTime(entry.timestamp) + "</span>" +
        '<span class="activity-engine ' + entry.engine + '">' + entry.engine + "</span>" +
        '<span class="activity-detail">' + escapeHtml(entry.detail) + "</span>";
      activityFeed.appendChild(el);
    });
  }

  function escapeHtml(text) {
    var el = document.createElement("span");
    el.textContent = text;
    return el.innerHTML;
  }

  // --- Actions ---
  async function toggleEngine(name) {
    await fetchJSON("papi/engines/" + name + "/toggle", { method: "POST" });
    updateEngines();
  }

  async function setIntensity(level) {
    await fetchJSON("papi/intensity", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ intensity: level }),
    });
    updateStatus();
  }

  // --- Event listeners ---
  intensitySelector.addEventListener("click", function (e) {
    if (e.target.classList.contains("intensity-btn")) {
      setIntensity(e.target.dataset.level);
    }
  });

  // --- Extension status ---
  var extStatus = document.getElementById("ext-status");
  var extDetail = document.getElementById("ext-detail");
  var extSetupBtn = document.getElementById("ext-setup-btn");
  var extModal = document.getElementById("ext-modal");
  var modalClose = document.getElementById("modal-close");

  async function updateExtStatus() {
    var data = await fetchJSON("papi/ext/status");
    if (!data) return;

    if (data.connected) {
      extStatus.textContent = "Connected";
      extStatus.className = "badge badge-ext-on";
      var detail = "v" + (data.version || "?");
      if (data.actions_completed > 0) {
        detail += " \u2022 " + data.actions_completed + " actions";
      }
      if (data.has_fingerprint) {
        detail += " \u2022 Fingerprint captured";
      }
      extDetail.textContent = detail;
      extSetupBtn.textContent = "Setup Guide";
    } else {
      extStatus.textContent = "Not Connected";
      extStatus.className = "badge badge-ext-off";
      extDetail.textContent = "Generate noise from your real browser with logged-in sessions";
      extSetupBtn.textContent = "Setup Guide";
    }
  }

  // Modal logic
  if (extSetupBtn && extModal) {
    extSetupBtn.addEventListener("click", function () {
      extModal.classList.remove("hidden");
    });
    modalClose.addEventListener("click", function () {
      extModal.classList.add("hidden");
    });
    extModal.addEventListener("click", function (e) {
      if (e.target === extModal) {
        extModal.classList.add("hidden");
      }
    });
  }

  // Compute the external-accessible Poisson URL for the extension.
  // The dashboard loads via HA ingress at a path like:
  //   /hassio/ingress/<addon_id>/
  // The actual API proxy is at:
  //   /api/hassio/ingress/<addon_id>/
  // The extension needs the full URL so it works from any network.
  var poissonUrlEl = document.getElementById("ext-poisson-url");
  var copyUrlBtn = document.getElementById("copy-url-btn");
  if (poissonUrlEl) {
    var path = window.location.pathname.replace(/\/$/, "");
    // Convert frontend path (/hassio/ingress/xxx) to API proxy path (/api/hassio/ingress/xxx)
    var apiPath = path.startsWith("/hassio/ingress/")
      ? "/api" + path
      : path;
    var poissonUrl = window.location.origin + apiPath;
    poissonUrlEl.textContent = poissonUrl;

    if (copyUrlBtn) {
      copyUrlBtn.addEventListener("click", function () {
        navigator.clipboard.writeText(poissonUrl).then(function () {
          copyUrlBtn.textContent = "Copied!";
          setTimeout(function () { copyUrlBtn.textContent = "Copy"; }, 2000);
        });
      });
    }
  }

  // --- Polling loop ---
  async function poll() {
    await Promise.all([updateStatus(), updateStats(), updateActivity(), updateEngines(), updateExtStatus()]);
  }

  // Report real viewport dimensions for fingerprint matching
  fetch("papi/fingerprint", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({width: window.screen.width, height: window.screen.height})
  }).catch(function () {});

  // Initial load + start polling
  poll();
  pollInterval = setInterval(poll, 5000);
})();
