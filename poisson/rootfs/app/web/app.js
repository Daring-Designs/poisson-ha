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

  // --- API key (injected into HTML by the server, authenticated via HA ingress) ---
  const apiKeyMeta = document.querySelector('meta[name="api-key"]');
  const API_KEY = apiKeyMeta ? apiKeyMeta.getAttribute("content") : "";

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
  const statErrors = document.getElementById("stat-errors");
  const nextSessionEl = document.getElementById("next-session");
  const engineStatsSection = document.getElementById("engine-stats-section");
  const torBadge = document.getElementById("tor-badge");

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
      opts = opts || {};
      opts.headers = Object.assign({"X-Api-Key": API_KEY}, opts.headers || {});
      const res = await fetch(path, opts);
      if (!res.ok) return null;
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  // updateStatus is now handled by poll() -> updateStatusFromData()
  // Kept as a standalone for use by setIntensity()
  async function updateStatus() {
    var status = await fetchJSON("papi/status");
    if (status) updateStatusFromData(status);
  }

  async function updateStats() {
    const data = await fetchJSON("papi/stats");
    if (!data) return;

    statSessions.textContent = data.sessions_today;
    statRequests.textContent = data.requests_today;
    statBandwidth.textContent = data.bandwidth_today_mb + " MB";
    statActive.textContent = data.active_sessions;
    if (statErrors) statErrors.textContent = data.errors_today || 0;

    if (nextSessionEl) {
      if (data.next_session_in != null && data.active_sessions === 0) {
        var m = Math.floor(data.next_session_in / 60);
        var s = data.next_session_in % 60;
        nextSessionEl.textContent = "Next session in " + m + "m " + s + "s";
      } else if (data.active_sessions > 0) {
        nextSessionEl.textContent = "Session in progress";
      } else {
        nextSessionEl.textContent = "";
      }
    }
  }

  async function updateEngines() {
    const data = await fetchJSON("papi/engines");
    if (!data || !data.engines) return;

    engineToggles.innerHTML = "";
    Object.keys(data.engines).forEach(function (name) {
      var eng = data.engines[name];
      var el = document.createElement("div");
      el.className = "engine-toggle" + (eng.enabled ? " active" : "");
      el.innerHTML = '<span class="dot"></span>' + escapeHtml(name);
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
        '<span class="activity-engine">' + escapeHtml(entry.engine) + "</span>" +
        '<span class="activity-detail">' + escapeHtml(entry.detail) + "</span>";
      activityFeed.appendChild(el);
    });
  }

  // --- Per-engine stats pills ---
  async function updateEngineStats() {
    var data = await fetchJSON("papi/engines");
    if (!data || !data.engines || !engineStatsSection) return;

    engineStatsSection.innerHTML = "";
    Object.keys(data.engines).forEach(function (name) {
      var eng = data.engines[name];
      if (!eng.enabled) return;
      var pill = document.createElement("div");
      pill.className = "engine-stat-pill";
      pill.setAttribute("data-engine", name);
      var errHtml = eng.stats.errors > 0
        ? ' <span class="pill-errors">' + eng.stats.errors + " err</span>"
        : "";
      pill.innerHTML =
        '<span class="pill-dot"></span>' +
        '<span class="pill-name">' + escapeHtml(name) + "</span>" +
        '<span class="pill-count">' + eng.stats.requests + "</span>" +
        errHtml;
      engineStatsSection.appendChild(pill);
    });
  }

  // --- Activity chart (SVG stacked bars) ---
  var ENGINE_COLORS = {
    search: "#4f8cff",
    browse: "#34d058",
    dns: "#e08030",
    tor: "#c084fc",
    research: "#2dd4bf",
    ad_clicks: "#f0c040"
  };

  async function updateChart() {
    var data = await fetchJSON("papi/activity/chart");
    if (!data || !data.labels) return;
    var svg = document.getElementById("activity-chart");
    if (!svg) return;

    var engines = data.engines || {};
    var engineNames = Object.keys(engines);
    var hours = data.labels.length;

    // Compute stacked totals per hour
    var maxTotal = 0;
    var stacks = [];
    for (var i = 0; i < hours; i++) {
      var stack = [];
      var total = 0;
      for (var j = 0; j < engineNames.length; j++) {
        var v = engines[engineNames[j]][i] || 0;
        stack.push({ engine: engineNames[j], value: v, y0: total });
        total += v;
      }
      stacks.push(stack);
      if (total > maxTotal) maxTotal = total;
    }

    if (maxTotal === 0) maxTotal = 1;

    var svgWidth = svg.clientWidth || 600;
    var svgHeight = 160;
    var barGap = 2;
    var barWidth = Math.max(4, (svgWidth - barGap * hours) / hours);
    var ns = "http://www.w3.org/2000/svg";

    // Clear
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    svg.setAttribute("viewBox", "0 0 " + svgWidth + " " + svgHeight);

    for (var i = 0; i < hours; i++) {
      var x = i * (barWidth + barGap) + barGap;
      var stack = stacks[i];
      for (var k = 0; k < stack.length; k++) {
        if (stack[k].value === 0) continue;
        var segH = (stack[k].value / maxTotal) * (svgHeight - 20);
        var segY = svgHeight - 14 - stack[k].y0 / maxTotal * (svgHeight - 20) - segH;
        var rect = document.createElementNS(ns, "rect");
        rect.setAttribute("x", x);
        rect.setAttribute("y", segY);
        rect.setAttribute("width", barWidth);
        rect.setAttribute("height", segH);
        rect.setAttribute("rx", 2);
        rect.setAttribute("fill", ENGINE_COLORS[stack[k].engine] || "#888");
        rect.setAttribute("opacity", "0.85");
        svg.appendChild(rect);
      }
      // Hour label every 3 hours
      if (i % 3 === 0) {
        var text = document.createElementNS(ns, "text");
        text.setAttribute("x", x + barWidth / 2);
        text.setAttribute("y", svgHeight - 2);
        text.setAttribute("text-anchor", "middle");
        text.setAttribute("fill", "#8b8fa3");
        text.setAttribute("font-size", "9");
        text.setAttribute("font-family", "inherit");
        text.textContent = data.labels[i];
        svg.appendChild(text);
      }
    }
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

  // --- Extension modal ---
  var extSetupBtn = document.getElementById("ext-setup-btn");
  var extModal = document.getElementById("ext-modal");
  var modalClose = document.getElementById("modal-close");

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

  // --- Polling loop with backoff ---
  var POLL_NORMAL = 5000;
  var POLL_BACKOFF = 30000;
  var pollDelay = POLL_NORMAL;
  var consecutiveFailures = 0;

  async function poll() {
    // Use a single status check as connectivity probe
    var status = await fetchJSON("papi/status");
    if (!status) {
      consecutiveFailures++;
      if (consecutiveFailures >= 2) {
        // Addon is down — back off and show offline state
        pollDelay = POLL_BACKOFF;
        statusBadge.textContent = "Offline";
        statusBadge.className = "badge badge-error";
      }
      schedulePoll();
      return;
    }
    // Addon is up — reset backoff and fetch everything
    if (consecutiveFailures > 0) {
      consecutiveFailures = 0;
      pollDelay = POLL_NORMAL;
    }
    // Process the status response we already have
    updateStatusFromData(status);
    await Promise.all([updateStats(), updateActivity(), updateEngines(), updateEngineStats(), updateChart()]);
    schedulePoll();
  }

  function schedulePoll() {
    clearTimeout(pollInterval);
    pollInterval = setTimeout(poll, pollDelay);
  }

  // Extract status processing so we can reuse the already-fetched data
  function updateStatusFromData(status) {
    statusBadge.textContent = status.status;
    statusBadge.className = "badge badge-" + status.status;
    uptimeEl.textContent = "Uptime: " + formatUptime(status.uptime_seconds);
    personaEl.textContent = "Persona: " + status.current_persona;

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

    if (torBadge) {
      if (status.tor_status === "connected") {
        torBadge.textContent = "Tor Connected";
        torBadge.className = "badge badge-tor-on";
      } else if (status.tor_status === "offline") {
        torBadge.textContent = "Tor Offline";
        torBadge.className = "badge badge-tor-off";
      } else {
        torBadge.textContent = "Tor Disabled";
        torBadge.className = "badge badge-tor-disabled";
      }
    }

    intensitySelector.querySelectorAll(".intensity-btn").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.level === status.intensity);
    });
  }

  // Report real viewport dimensions for fingerprint matching
  fetch("papi/fingerprint", {
    method: "POST",
    headers: {"Content-Type": "application/json", "X-Api-Key": API_KEY},
    body: JSON.stringify({width: window.screen.width, height: window.screen.height})
  }).catch(function () {});

  // Initial load + start polling
  poll();
})();
