/**
 * Poisson — Extension popup UI logic.
 */

(function () {
  "use strict";

  var setupView = document.getElementById("setup-view");
  var statusView = document.getElementById("status-view");
  var connectBtn = document.getElementById("connect-btn");
  var disconnectBtn = document.getElementById("disconnect-btn");
  var connectError = document.getElementById("connect-error");
  var serverUrlInput = document.getElementById("server-url");
  var tokenInput = document.getElementById("token");
  var connBadge = document.getElementById("conn-badge");
  var enabledToggle = document.getElementById("enabled-toggle");
  var intensitySelector = document.getElementById("intensity-selector");
  var statSearches = document.getElementById("stat-searches");
  var statPages = document.getElementById("stat-pages");
  var statAds = document.getElementById("stat-ads");

  function showSetup() {
    setupView.classList.remove("hidden");
    statusView.classList.add("hidden");
  }

  function showStatus() {
    setupView.classList.add("hidden");
    statusView.classList.remove("hidden");
  }

  function updateStatusUI(status) {
    if (status.connected) {
      connBadge.textContent = "Connected";
      connBadge.className = "badge badge-connected";
    } else {
      connBadge.textContent = "Disconnected";
      connBadge.className = "badge badge-disconnected";
    }

    enabledToggle.checked = status.enabled;

    // Intensity buttons
    intensitySelector.querySelectorAll(".int-btn").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.level === status.intensity);
    });

    // Stats
    var stats = status.stats || {};
    var today = new Date().toISOString().slice(0, 10);
    if (stats.today !== today) {
      stats = { searches: 0, pages: 0, ads: 0 };
    }
    statSearches.textContent = stats.searches || 0;
    statPages.textContent = stats.pages || 0;
    statAds.textContent = stats.ads || 0;
  }

  // Check if already configured
  chrome.runtime.sendMessage({ type: "get-status" }, function (status) {
    if (chrome.runtime.lastError || !status) {
      showSetup();
      return;
    }
    if (status.serverUrl && status.hasToken) {
      showStatus();
      updateStatusUI(status);
    } else {
      showSetup();
    }
  });

  // Connect
  connectBtn.addEventListener("click", function () {
    var serverUrl = serverUrlInput.value.trim();
    var token = tokenInput.value.trim();

    connectError.classList.add("hidden");

    if (!serverUrl) {
      connectError.textContent = "Please enter your Home Assistant URL";
      connectError.classList.remove("hidden");
      return;
    }
    if (!token) {
      connectError.textContent = "Please enter your access token";
      connectError.classList.remove("hidden");
      return;
    }

    // Normalize URL
    if (!serverUrl.startsWith("http")) {
      serverUrl = "https://" + serverUrl;
    }

    connectBtn.textContent = "Connecting...";
    connectBtn.disabled = true;

    chrome.runtime.sendMessage({
      type: "connect",
      serverUrl: serverUrl,
      token: token,
    }, function (response) {
      connectBtn.textContent = "Connect";
      connectBtn.disabled = false;

      if (chrome.runtime.lastError || !response || !response.ok) {
        connectError.textContent = "Connection failed. Check your URL and token.";
        connectError.classList.remove("hidden");
        return;
      }

      // Switch to status view
      showStatus();
      chrome.runtime.sendMessage({ type: "get-status" }, function (status) {
        if (status) updateStatusUI(status);
      });
    });
  });

  // Disconnect
  disconnectBtn.addEventListener("click", function () {
    chrome.runtime.sendMessage({ type: "disconnect" }, function () {
      showSetup();
      serverUrlInput.value = "";
      tokenInput.value = "";
    });
  });

  // Toggle enabled
  enabledToggle.addEventListener("change", function () {
    chrome.runtime.sendMessage({
      type: "set-enabled",
      enabled: enabledToggle.checked,
    });
  });

  // Intensity selector
  intensitySelector.addEventListener("click", function (e) {
    if (e.target.classList.contains("int-btn")) {
      var level = e.target.dataset.level;
      chrome.runtime.sendMessage({ type: "set-intensity", intensity: level });
      intensitySelector.querySelectorAll(".int-btn").forEach(function (btn) {
        btn.classList.toggle("active", btn.dataset.level === level);
      });
    }
  });
})();
