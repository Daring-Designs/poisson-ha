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

  // -------------------------------------------------------------------
  // URL helpers — extract HA base URL from the full Poisson ingress URL.
  //
  // Poisson URL: https://home.example.com/api/hassio/ingress/abc123
  // HA base URL: https://home.example.com
  //
  // The OAuth endpoints are at the HA base URL (/auth/authorize, /auth/token).
  // API calls go to the full Poisson ingress URL.
  // -------------------------------------------------------------------
  function extractHaUrl(poissonUrl) {
    try {
      var url = new URL(poissonUrl);
      return url.origin; // e.g., "https://home.example.com"
    } catch (e) {
      return "";
    }
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
  // OAuth2 flow — uses HA's standard authorization code flow.
  //
  // 1. Open HA's /auth/authorize in a popup window
  // 2. User logs in with their HA credentials (we never see the password)
  // 3. HA redirects back with an authorization code
  // 4. We exchange the code for access + refresh tokens
  // 5. Tokens are stored locally and used for API calls
  //
  // client_id = chrome extension redirect URL (no client secret needed)
  // -------------------------------------------------------------------
  function startOAuthFlow(poissonUrl, cb) {
    var haUrl = extractHaUrl(poissonUrl);
    if (!haUrl) {
      cb(new Error("Invalid URL"));
      return;
    }

    var clientId = chrome.identity.getRedirectURL();
    var redirectUri = chrome.identity.getRedirectURL();
    var state = Math.random().toString(36).substring(2); // CSRF protection

    var authUrl = haUrl + "/auth/authorize"
      + "?client_id=" + encodeURIComponent(clientId)
      + "&redirect_uri=" + encodeURIComponent(redirectUri)
      + "&state=" + encodeURIComponent(state)
      + "&response_type=code";

    // Open HA's login page in a popup window
    chrome.identity.launchWebAuthFlow({
      url: authUrl,
      interactive: true,
    }, function (responseUrl) {
      if (chrome.runtime.lastError) {
        cb(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!responseUrl) {
        cb(new Error("No response from HA"));
        return;
      }

      // Extract the authorization code from the redirect URL
      var params = new URL(responseUrl).searchParams;
      var code = params.get("code");
      var returnedState = params.get("state");

      if (returnedState !== state) {
        cb(new Error("State mismatch — possible CSRF attack"));
        return;
      }
      if (!code) {
        cb(new Error("No authorization code received"));
        return;
      }

      // Exchange the code for access + refresh tokens
      var tokenBody = "grant_type=authorization_code"
        + "&code=" + encodeURIComponent(code)
        + "&client_id=" + encodeURIComponent(clientId);

      fetch(haUrl + "/auth/token", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: tokenBody,
      })
        .then(function (res) {
          if (!res.ok) throw new Error("Token exchange failed: HTTP " + res.status);
          return res.json();
        })
        .then(function (data) {
          // HA returns: { access_token, token_type, refresh_token, expires_in, ha_auth_provider }
          cb(null, {
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            tokenExpiry: Date.now() + (data.expires_in * 1000) - 60000, // 1 min buffer
          });
        })
        .catch(function (err) {
          cb(err);
        });
    });
  }

  // --- On popup open: check if already configured ---
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
    }
  });

  // --- Connect button: launch OAuth flow ---
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
    var haUrl = extractHaUrl(poissonUrl);

    connectBtn.textContent = "Signing in...";
    connectBtn.disabled = true;

    // Launch HA OAuth login flow
    startOAuthFlow(poissonUrl, function (err, tokens) {
      connectBtn.textContent = "Sign in to Home Assistant";
      connectBtn.disabled = false;

      if (err) {
        connectError.textContent = err.message || "Sign-in failed";
        connectError.classList.remove("hidden");
        return;
      }

      // Send tokens to background.js to store and start noise
      chrome.runtime.sendMessage({
        type: "oauth-connect",
        poissonUrl: poissonUrl,
        haUrl: haUrl,
        accessToken: tokens.accessToken,
        refreshToken: tokens.refreshToken,
        tokenExpiry: tokens.tokenExpiry,
      }, function (response) {
        if (chrome.runtime.lastError || !response || !response.ok) {
          connectError.textContent = "Failed to initialize. Try again.";
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
