/**
 * Poisson — Extension popup UI
 *
 * SECURITY TRANSPARENCY: This file controls the popup that appears when
 * you click the Poisson icon in your browser toolbar.
 *
 * WHAT IT DOES:
 *   - Shows a setup form to enter your Poisson URL
 *   - Launches HA's standard OAuth2 login flow (you sign in through HA)
 *   - Shows connection status and daily noise statistics
 *   - Lets you enable/disable noise and change intensity
 *
 * AUTHENTICATION:
 *   Uses chrome.identity.launchWebAuthFlow to open HA's login page.
 *   The extension never sees your password. After you log in, HA gives
 *   the extension short-lived OAuth tokens (expire every 30 min, auto-refresh).
 *   Disconnect revokes the tokens with HA.
 *
 * WHAT IT DOES NOT DO:
 *   - Does not see or store your HA password
 *   - Does not access any page content or browsing data
 *   - Does not make requests to anything except your HA instance
 *
 * Source code: https://github.com/Daring-Designs/poisson
 */

(function () {
  "use strict";

  // --- DOM references ---
  var setupView = document.getElementById("setup-view");
  var statusView = document.getElementById("status-view");
  var connectBtn = document.getElementById("connect-btn");
  var disconnectBtn = document.getElementById("disconnect-btn");
  var connectError = document.getElementById("connect-error");
  var serverUrlInput = document.getElementById("server-url");
  var connBadge = document.getElementById("conn-badge");
  var enabledToggle = document.getElementById("enabled-toggle");
  var intensitySelector = document.getElementById("intensity-selector");
  var statSearches = document.getElementById("stat-searches");
  var statPages = document.getElementById("stat-pages");
  var statAds = document.getElementById("stat-ads");

  // --- View switching ---
  function showSetup() {
    setupView.classList.remove("hidden");
    statusView.classList.add("hidden");
  }

  function showStatus() {
    setupView.classList.add("hidden");
    statusView.classList.remove("hidden");
  }

  // --- Update the status view with current data ---
  function updateStatusUI(status) {
    // Connection badge
    if (status.connected) {
      connBadge.textContent = "Connected";
      connBadge.className = "badge badge-connected";
    } else {
      connBadge.textContent = "Disconnected";
      connBadge.className = "badge badge-disconnected";
    }

    // Noise toggle
    enabledToggle.checked = status.enabled;

    // Highlight active intensity button
    intensitySelector.querySelectorAll(".int-btn").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.level === status.intensity);
    });

    // Daily stats (reset at midnight)
    var stats = status.stats || {};
    var today = new Date().toISOString().slice(0, 10);
    if (stats.today !== today) {
      stats = { searches: 0, pages: 0, ads: 0 };
    }
    statSearches.textContent = stats.searches || 0;
    statPages.textContent = stats.pages || 0;
    statAds.textContent = stats.ads || 0;
  }

  // Ensure the Poisson URL uses the API ingress path, not the frontend path.
  // Frontend: /hassio/ingress/xxx  →  API: /api/hassio/ingress/xxx
  function normalizePoissonUrl(input) {
    try {
      var url = new URL(input);
      var path = url.pathname.replace(/\/$/, "");
      // Convert frontend path to API proxy path if needed
      if (path.match(/^\/hassio\/ingress\//) && !path.startsWith("/api/")) {
        url.pathname = "/api" + path;
      }
      return url.origin + url.pathname.replace(/\/$/, "");
    } catch (e) {
      return input;
    }
  }

  // -------------------------------------------------------------------
  // On popup open: check if already configured.
  // This is the primary view-switching logic — after OAuth completes in
  // the background service worker, the user reopens the popup and this
  // check sees hasAuth: true, switching to the status view.
  // -------------------------------------------------------------------
  chrome.runtime.sendMessage({ type: "get-status" }, function (status) {
    if (chrome.runtime.lastError || !status) {
      showSetup();
      return;
    }
    if (status.poissonUrl && status.hasAuth) {
      showStatus();
      updateStatusUI(status);
    } else {
      showSetup();
      // Show any error from a previous auth attempt
      if (status.lastAuthError) {
        connectError.textContent = status.lastAuthError;
        connectError.classList.remove("hidden");
      }
    }
  });

  // -------------------------------------------------------------------
  // Connect button — sends the OAuth request to the background service
  // worker (background.js), which handles the ENTIRE flow. This is
  // necessary because Chrome closes the popup when the auth window
  // opens (focus shifts). The service worker persists through the flow.
  //
  // After the user completes login and reopens the popup, the
  // get-status check above will see hasAuth: true and show status.
  // -------------------------------------------------------------------
  connectBtn.addEventListener("click", function () {
    var poissonUrl = serverUrlInput.value.trim();
    connectError.classList.add("hidden");

    if (!poissonUrl) {
      connectError.textContent = "Please enter your Poisson URL (copy from dashboard)";
      connectError.classList.remove("hidden");
      return;
    }

    // Auto-add https:// if missing
    if (!poissonUrl.startsWith("http")) {
      poissonUrl = "https://" + poissonUrl;
    }
    poissonUrl = normalizePoissonUrl(poissonUrl);

    connectBtn.textContent = "Signing in...";
    connectBtn.disabled = true;

    // Tell the background service worker to start the OAuth flow.
    // The popup will likely close when the auth window opens — that's fine.
    // The background worker handles everything, and when the user
    // reopens the popup, get-status will show the connected state.
    chrome.runtime.sendMessage({
      type: "start-oauth",
      poissonUrl: poissonUrl,
    }, function (response) {
      // This callback only fires if the popup is still open (unlikely)
      connectBtn.textContent = "Sign in to Home Assistant";
      connectBtn.disabled = false;

      if (chrome.runtime.lastError) return; // Popup was closed — expected
      if (!response || !response.ok) {
        connectError.textContent = (response && response.error) || "Sign-in failed. Try again.";
        connectError.classList.remove("hidden");
        return;
      }

      // If popup survived (rare), switch to status view
      showStatus();
      chrome.runtime.sendMessage({ type: "get-status" }, function (status) {
        if (status) updateStatusUI(status);
      });
    });
  });

  // --- Disconnect button: revoke tokens and stop ---
  disconnectBtn.addEventListener("click", function () {
    chrome.runtime.sendMessage({ type: "disconnect" }, function () {
      showSetup();
      serverUrlInput.value = "";
    });
  });

  // --- Noise toggle ---
  enabledToggle.addEventListener("change", function () {
    chrome.runtime.sendMessage({
      type: "set-enabled",
      enabled: enabledToggle.checked,
    });
  });

  // --- Intensity selector ---
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
