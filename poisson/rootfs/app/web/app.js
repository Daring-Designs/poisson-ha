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

  // --- Polling loop ---
  async function poll() {
    await Promise.all([updateStatus(), updateStats(), updateActivity(), updateEngines()]);
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
