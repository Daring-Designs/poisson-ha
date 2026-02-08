/**
 * Poisson — Background service worker
 *
 * SECURITY TRANSPARENCY: This file is the core of the extension.
 * Here is exactly what it does and why:
 *
 * WHAT THIS EXTENSION DOES:
 *   1. Connects to YOUR Poisson add-on server (the URL you provide)
 *   2. Authenticates via HA's standard OAuth2 flow (you log in normally)
 *   3. Periodically opens browser tabs to random websites (noise traffic)
 *   4. Closes those tabs after a short delay
 *   5. Reports your browser fingerprint to YOUR server (so headless
 *      noise sessions can match your real fingerprint)
 *
 * WHAT THIS EXTENSION DOES NOT DO:
 *   - Does NOT collect passwords, form data, or browsing history
 *   - Does NOT read content from any page you visit
 *   - Does NOT inject scripts into any page
 *   - Does NOT communicate with any server other than YOUR HA instance
 *   - Does NOT run when disabled (toggle in popup)
 *   - Does NOT modify any page content
 *   - Does NOT store your HA password (uses standard OAuth tokens)
 *
 * PERMISSIONS EXPLAINED:
 *   - "alarms": Schedule noise actions (chrome.alarms API, min 1 min interval)
 *   - "storage": Save OAuth tokens and config locally in the browser
 *   - "offscreen": Create a hidden document to measure browser fingerprint
 *   - "tabs": Open and close noise tabs in the background
 *   - "identity": Use chrome.identity.launchWebAuthFlow for HA OAuth login
 *   - "<all_urls>": Needed so noise tabs can open any website
 *
 * AUTHENTICATION:
 *   Uses Home Assistant's standard OAuth2 flow. The extension never sees
 *   your password — you log in through HA's own login page. The extension
 *   receives short-lived access tokens (expire every 30 minutes) that
 *   auto-refresh. You can revoke access anytime in HA.
 *
 * DATA SENT TO YOUR SERVER:
 *   - Browser fingerprint (user agent, screen size, canvas hash, WebGL info,
 *     installed fonts, timezone) — so headless sessions look like your browser
 *   - Action counts (searches today, pages visited) — displayed on dashboard
 *   - That's it. No page content, no cookies, no browsing history.
 *
 * Source code: https://github.com/Daring-Designs/poisson
 */

(function () {
  "use strict";

  // Alarm names used by chrome.alarms API
  var ALARM_NAME = "poisson-noise";          // Fires to trigger a noise action
  var HEARTBEAT_ALARM = "poisson-heartbeat"; // Fires every minute to check in with server
  var HEARTBEAT_INTERVAL_MIN = 1;            // chrome.alarms minimum period is 1 minute

  // Track whether the offscreen document (for fingerprinting) has been created
  var offscreenCreated = false;

  // -------------------------------------------------------------------
  // Intensity levels — controls how often noise tabs are opened.
  // Lambda = average events per minute. Higher = more frequent noise.
  // These match the server-side values in patterns/timing.py.
  // Note: chrome.alarms has a 1-minute minimum, so high/paranoid batch
  // multiple tabs per alarm firing to reach the target rate.
  // -------------------------------------------------------------------
  var INTENSITY_LAMBDA = {
    low: 0.3,       // ~18 events/hour
    medium: 1.0,    // ~60 events/hour
    high: 2.5,      // ~150 events/hour
    paranoid: 5.0,  // ~300 events/hour
  };

  // -------------------------------------------------------------------
  // Storage helpers — all config is stored locally in chrome.storage.local.
  // Nothing is sent anywhere except to the server URL you configure.
  // -------------------------------------------------------------------
  function getConfig(cb) {
    chrome.storage.local.get([
      "poissonUrl", "haUrl", "accessToken", "refreshToken", "tokenExpiry",
      "enabled", "intensity", "stats",
    ], function (data) {
      cb({
        poissonUrl: data.poissonUrl || "",   // Full ingress URL for API calls
        haUrl: data.haUrl || "",             // HA base URL for OAuth token refresh
        accessToken: data.accessToken || "",
        refreshToken: data.refreshToken || "",
        tokenExpiry: data.tokenExpiry || 0,
        enabled: data.enabled !== false,
        intensity: data.intensity || "medium",
        stats: data.stats || { searches: 0, pages: 0, ads: 0, today: "" },
      });
    });
  }

  // Reset daily stats at midnight (based on date string comparison)
  function saveStats(stats) {
    var today = new Date().toISOString().slice(0, 10);
    if (stats.today !== today) {
      stats = { searches: 0, pages: 0, ads: 0, today: today };
    }
    chrome.storage.local.set({ stats: stats });
  }

  // -------------------------------------------------------------------
  // OAuth2 token management — handles HA's standard OAuth2 flow.
  //
  // HA access tokens expire every 30 minutes. Before each API call,
  // we check if the token is expired and refresh it automatically
  // using the refresh token. The user never has to re-authenticate
  // unless they revoke access in HA.
  //
  // Token endpoint: {haUrl}/auth/token (POST, form-urlencoded)
  // No client secret needed — HA uses the public client flow.
  // -------------------------------------------------------------------
  function refreshAccessToken(config, cb) {
    if (!config.haUrl || !config.refreshToken) {
      cb(new Error("No refresh token"));
      return;
    }

    var body = "grant_type=refresh_token"
      + "&refresh_token=" + encodeURIComponent(config.refreshToken)
      + "&client_id=" + encodeURIComponent(chrome.identity.getRedirectURL());

    fetch(config.haUrl + "/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body,
    })
      .then(function (res) {
        if (!res.ok) throw new Error("Token refresh failed: HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        // HA returns: { access_token, token_type, expires_in, ha_auth_provider }
        var expiry = Date.now() + (data.expires_in * 1000) - 60000; // 1 min buffer
        chrome.storage.local.set({
          accessToken: data.access_token,
          tokenExpiry: expiry,
        });
        cb(null, data.access_token);
      })
      .catch(function (err) {
        console.error("[Poisson] Token refresh failed:", err);
        cb(err, null);
      });
  }

  // Get a valid access token, refreshing if expired
  function getValidToken(config, cb) {
    if (config.accessToken && Date.now() < config.tokenExpiry) {
      // Token still valid
      cb(null, config.accessToken);
    } else {
      // Token expired — refresh it
      refreshAccessToken(config, cb);
    }
  }

  // -------------------------------------------------------------------
  // API helpers — all requests go ONLY to the Poisson URL you configured,
  // which routes through HA's ingress proxy. Auth uses the OAuth access
  // token from HA's standard login flow.
  // -------------------------------------------------------------------
  function apiCall(config, method, path, body, cb) {
    getValidToken(config, function (err, token) {
      if (err || !token) {
        if (cb) cb(err || new Error("No token"), null);
        return;
      }

      // Build URL from YOUR configured Poisson ingress address
      var url = config.poissonUrl.replace(/\/$/, "") + path;
      var opts = {
        method: method,
        headers: {
          "Authorization": "Bearer " + token, // HA OAuth access token
          "Content-Type": "application/json",
        },
      };
      if (body) opts.body = JSON.stringify(body);

      fetch(url, opts)
        .then(function (res) {
          if (res.status === 401) {
            // Token rejected — try refreshing once
            refreshAccessToken(config, function (refreshErr, newToken) {
              if (refreshErr || !newToken) {
                chrome.storage.local.set({ connected: false });
                if (cb) cb(refreshErr || new Error("Auth failed"), null);
                return;
              }
              // Retry with new token
              opts.headers["Authorization"] = "Bearer " + newToken;
              fetch(url, opts)
                .then(function (r) { return r.ok ? r.json() : Promise.reject("HTTP " + r.status); })
                .then(function (data) { if (cb) cb(null, data); })
                .catch(function (e) { if (cb) cb(e, null); });
            });
            return;
          }
          if (!res.ok) throw new Error("HTTP " + res.status);
          return res.json();
        })
        .then(function (data) { if (data !== undefined && cb) cb(null, data); })
        .catch(function (fetchErr) { if (cb) cb(fetchErr, null); });
    });
  }

  // -------------------------------------------------------------------
  // Offscreen document — used ONLY for fingerprint collection.
  // Creates a hidden page (offscreen.html) that has DOM access so it
  // can draw on a canvas and measure fonts. See offscreen.js for details.
  // -------------------------------------------------------------------
  async function ensureOffscreen() {
    if (offscreenCreated) return;
    try {
      await chrome.offscreen.createDocument({
        url: "offscreen.html",
        reasons: ["DOM_PARSER"],
        justification: "Collect browser fingerprint signals (canvas, WebGL, fonts)",
      });
      offscreenCreated = true;
    } catch (e) {
      // Document already exists (only one offscreen doc allowed at a time)
      if (e.message && e.message.includes("single offscreen")) {
        offscreenCreated = true;
      }
    }
  }

  // Ask the offscreen document to collect fingerprint data
  function collectFingerprint(cb) {
    ensureOffscreen().then(function () {
      chrome.runtime.sendMessage({ type: "collect-fingerprint" }, function (response) {
        if (chrome.runtime.lastError || !response) {
          cb(null);
          return;
        }
        cb(response.fingerprint);
      });
    });
  }

  // -------------------------------------------------------------------
  // URL helpers — extract HA base URL from the full Poisson ingress URL.
  // Duplicated here from popup.js because the background service worker
  // needs them for the OAuth flow (popup may close during auth).
  // -------------------------------------------------------------------
  function extractHaUrl(poissonUrl) {
    try {
      return new URL(poissonUrl).origin;
    } catch (e) {
      return "";
    }
  }

  function normalizePoissonUrl(input) {
    try {
      var url = new URL(input);
      var path = url.pathname.replace(/\/$/, "");
      if (path.match(/^\/hassio\/ingress\//) && !path.startsWith("/api/")) {
        url.pathname = "/api" + path;
      }
      return url.origin + url.pathname.replace(/\/$/, "");
    } catch (e) {
      return input;
    }
  }

  // -------------------------------------------------------------------
  // OAuth2 flow — runs entirely in the background service worker so it
  // survives the popup closing (which happens when the auth window opens).
  //
  // 1. Open HA's /auth/authorize via chrome.identity.launchWebAuthFlow
  // 2. User logs in with their HA credentials (we never see the password)
  // 3. HA redirects back with an authorization code
  // 4. We exchange the code for access + refresh tokens
  // 5. Tokens are stored and noise generation starts
  // -------------------------------------------------------------------
  function startOAuthFlow(poissonUrl, cb) {
    var haUrl = extractHaUrl(poissonUrl);
    if (!haUrl) {
      cb(new Error("Invalid URL"));
      return;
    }

    var clientId = chrome.identity.getRedirectURL();
    var redirectUri = chrome.identity.getRedirectURL();
    var state = Math.random().toString(36).substring(2);

    var authUrl = haUrl + "/auth/authorize"
      + "?client_id=" + encodeURIComponent(clientId)
      + "&redirect_uri=" + encodeURIComponent(redirectUri)
      + "&state=" + encodeURIComponent(state)
      + "&response_type=code";

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

      var params = new URL(responseUrl).searchParams;
      var code = params.get("code");
      var returnedState = params.get("state");

      if (returnedState !== state) {
        cb(new Error("State mismatch"));
        return;
      }
      if (!code) {
        cb(new Error("No authorization code received"));
        return;
      }

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
          cb(null, {
            haUrl: haUrl,
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            tokenExpiry: Date.now() + (data.expires_in * 1000) - 60000,
          });
        })
        .catch(function (err) {
          cb(err);
        });
    });
  }

  // -------------------------------------------------------------------
  // Registration — called after successful OAuth login.
  // Sends your browser fingerprint to YOUR server so headless noise
  // sessions can mimic your real browser's characteristics.
  // -------------------------------------------------------------------
  function register(config) {
    collectFingerprint(function (fingerprint) {
      var payload = {
        version: chrome.runtime.getManifest().version,
        fingerprint: fingerprint || {},
      };
      apiCall(config, "POST", "/papi/ext/register", payload, function (err, data) {
        if (err) {
          console.error("[Poisson] Registration failed:", err);
          chrome.storage.local.set({ connected: false });
        } else {
          console.log("[Poisson] Registered with server");
          chrome.storage.local.set({ connected: true });
          // Server may send back the current intensity setting
          if (data && data.intensity) {
            chrome.storage.local.set({ intensity: data.intensity });
          }
        }
      });

      // Also send fingerprint to dedicated endpoint for deeper storage
      if (fingerprint) {
        apiCall(config, "POST", "/papi/ext/fingerprint", fingerprint, function () {});
      }
    });
  }

  // -------------------------------------------------------------------
  // Heartbeat — periodic check-in with YOUR server every ~1 minute.
  // Sends: action counts (how many searches/pages today).
  // Receives: current intensity setting, whether noise is still enabled.
  // -------------------------------------------------------------------
  function heartbeat(config) {
    apiCall(config, "POST", "/papi/ext/heartbeat", {
      stats: config.stats,
    }, function (err, data) {
      if (err) {
        chrome.storage.local.set({ connected: false });
        return;
      }
      chrome.storage.local.set({ connected: true });
      // Sync intensity from server if it was changed on the dashboard
      if (data && data.intensity) {
        chrome.storage.local.set({ intensity: data.intensity });
      }
      // Server can remotely disable noise generation
      if (data && data.enabled === false) {
        chrome.storage.local.set({ enabled: false });
        chrome.alarms.clear(ALARM_NAME);
      }
    });
  }

  // -------------------------------------------------------------------
  // Noise scheduling — uses Poisson process (exponential distribution)
  // to randomize the delay between noise actions, making the timing
  // pattern look like natural human browsing rather than a fixed interval.
  //
  // chrome.alarms has a 1-minute minimum. For intensities that want
  // more than 1 event/minute, we store how many tasks to batch on
  // the next alarm fire.
  // -------------------------------------------------------------------
  var pendingBatchCount = 1;

  function scheduleNextNoise(intensity) {
    var lambda = INTENSITY_LAMBDA[intensity] || INTENSITY_LAMBDA.medium;
    // Exponential random variable: -ln(U) / lambda, where U ~ Uniform(0,1)
    var delayMin = -Math.log(Math.random()) / lambda;

    if (delayMin < 1) {
      // Delay is sub-minute — batch multiple tasks into the next 1-min alarm.
      // Count how many events would fit in 1 minute at this rate.
      pendingBatchCount = Math.max(1, Math.round(lambda));
      delayMin = 1;
    } else {
      pendingBatchCount = 1;
      delayMin = Math.min(30, delayMin);
    }

    chrome.alarms.create(ALARM_NAME, { delayInMinutes: delayMin });
    console.log("[Poisson] Next noise in " + delayMin.toFixed(1) + " min (" + pendingBatchCount + " tasks)");
  }

  // -------------------------------------------------------------------
  // Execute a noise action — this is the core noise generation loop:
  //
  // 1. Ask YOUR server for the next task (a URL to visit)
  // 2. Open that URL in a background tab (active: false)
  // 3. Wait for the specified delay (simulating reading time)
  // 4. Close the tab
  // 5. Schedule the next noise action
  //
  // The extension does NOT read any content from the opened tabs.
  // It simply opens and closes them to generate network traffic.
  // -------------------------------------------------------------------
  function executeSingleNoiseTask(config, cb) {
    apiCall(config, "GET", "/papi/ext/next-task", null, function (err, task) {
      if (err || !task || !task.url) {
        console.warn("[Poisson] Failed to get task:", err);
        if (cb) cb();
        return;
      }

      console.log("[Poisson] Opening noise tab:", task.type, task.url.substring(0, 60));

      chrome.tabs.create({ url: task.url, active: false }, function (tab) {
        if (chrome.runtime.lastError || !tab) {
          console.warn("[Poisson] Tab create failed:", chrome.runtime.lastError);
          if (cb) cb();
          return;
        }

        var tabId = tab.id;
        var delay = task.delay_ms || 8000;

        // Update local action counters (re-read from storage for accuracy)
        chrome.storage.local.get(["stats"], function (data) {
          var stats = data.stats || { searches: 0, pages: 0, ads: 0, today: "" };
          var today = new Date().toISOString().slice(0, 10);
          if (stats.today !== today) {
            stats = { searches: 0, pages: 0, ads: 0, today: today };
          }
          if (task.type === "search") stats.searches++;
          else if (task.type === "ad_click") stats.ads++;
          else stats.pages++;
          saveStats(stats);
          console.log("[Poisson] Stats:", JSON.stringify(stats));

          setTimeout(function () {
            apiCall(config, "POST", "/papi/ext/heartbeat", {
              stats: stats,
              last_action: { type: task.type, url: task.url },
            }, function () {});

            chrome.tabs.remove(tabId, function () {
              if (chrome.runtime.lastError) { /* tab already closed */ }
            });

            if (cb) cb();
          }, delay);
        });
      });
    });
  }

  function executeNoiseTask(config) {
    var count = pendingBatchCount || 1;
    console.log("[Poisson] Executing " + count + " noise task(s)");
    var completed = 0;

    for (var i = 0; i < count; i++) {
      // Stagger batch tasks so they don't all fire simultaneously
      (function (idx) {
        setTimeout(function () {
          executeSingleNoiseTask(config, function () {
            completed++;
            // Schedule next round after the last task in the batch completes
            if (completed >= count) {
              scheduleNextNoise(config.intensity);
            }
          });
        }, idx * 3000); // 3-second stagger between batch tasks
      })(i);
    }
  }

  // -------------------------------------------------------------------
  // Alarm handler — chrome.alarms fires these callbacks.
  // -------------------------------------------------------------------
  chrome.alarms.onAlarm.addListener(function (alarm) {
    if (alarm.name === HEARTBEAT_ALARM) {
      // Periodic heartbeat to YOUR server
      getConfig(function (config) {
        if (config.poissonUrl && config.accessToken) {
          heartbeat(config);
        }
      });
      return;
    }

    if (alarm.name === ALARM_NAME) {
      // Time to generate a noise action
      getConfig(function (config) {
        if (!config.poissonUrl || !config.accessToken || !config.enabled) return;
        executeNoiseTask(config);
      });
    }
  });

  // -------------------------------------------------------------------
  // Message handler — receives messages from the popup UI and the
  // offscreen document. These are internal extension messages only.
  // -------------------------------------------------------------------
  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    // Fingerprint data sent proactively from the offscreen document
    if (msg.type === "fingerprint-result") {
      getConfig(function (config) {
        if (config.poissonUrl && config.accessToken) {
          apiCall(config, "POST", "/papi/ext/fingerprint", msg.fingerprint, function () {});
        }
      });
      return;
    }

    // -------------------------------------------------------------------
    // Start OAuth — popup triggers this, then the ENTIRE OAuth flow runs
    // here in the background service worker. This is critical because the
    // popup closes when the auth window opens (Chrome dismisses popups
    // when focus shifts). The service worker persists through the flow.
    //
    // When the user reopens the popup, get-status will see hasAuth: true
    // and show the connected status view.
    // -------------------------------------------------------------------
    if (msg.type === "start-oauth") {
      var poissonUrl = normalizePoissonUrl(msg.poissonUrl);

      startOAuthFlow(poissonUrl, function (err, tokens) {
        if (err) {
          console.error("[Poisson] OAuth failed:", err);
          // Store the error so popup can show it when reopened
          chrome.storage.local.set({ lastAuthError: err.message || "Sign-in failed" });
          // Try to respond (popup may be gone — that's OK)
          try { sendResponse({ ok: false, error: err.message }); } catch (e) {}
          return;
        }

        // Store tokens and start noise generation
        chrome.storage.local.set({
          poissonUrl: poissonUrl,
          haUrl: tokens.haUrl,
          accessToken: tokens.accessToken,
          refreshToken: tokens.refreshToken,
          tokenExpiry: tokens.tokenExpiry,
          enabled: true,
          lastAuthError: "",
        }, function () {
          getConfig(function (config) {
            register(config);
            chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: HEARTBEAT_INTERVAL_MIN });
            scheduleNextNoise(config.intensity);
            // Try to respond (popup may be gone — that's OK)
            try { sendResponse({ ok: true }); } catch (e) {}
          });
        });
      });
      return true; // keep message channel open for async sendResponse
    }

    // User clicked "Disconnect" in the popup
    if (msg.type === "disconnect") {
      // Revoke the refresh token with HA
      getConfig(function (config) {
        if (config.haUrl && config.refreshToken) {
          // Tell HA to revoke our tokens
          fetch(config.haUrl + "/auth/token", {
            method: "DELETE",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: "token=" + encodeURIComponent(config.refreshToken)
              + "&action=revoke",
          }).catch(function () {}); // Best-effort revocation
        }
      });
      chrome.alarms.clearAll(); // Stop all scheduled noise and heartbeats
      chrome.storage.local.set({
        connected: false,
        enabled: false,
        accessToken: "",
        refreshToken: "",
        tokenExpiry: 0,
        poissonUrl: "",
        haUrl: "",
        lastAuthError: "",
      });
      sendResponse({ ok: true });
      return;
    }

    // User toggled noise on/off in the popup
    if (msg.type === "set-enabled") {
      chrome.storage.local.set({ enabled: msg.enabled }, function () {
        if (msg.enabled) {
          getConfig(function (config) {
            scheduleNextNoise(config.intensity);
            chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: HEARTBEAT_INTERVAL_MIN });
          });
        } else {
          chrome.alarms.clear(ALARM_NAME); // Stop noise but keep heartbeat
        }
      });
      sendResponse({ ok: true });
      return;
    }

    // User changed intensity in the popup
    if (msg.type === "set-intensity") {
      chrome.storage.local.set({ intensity: msg.intensity });
      sendResponse({ ok: true });
      return;
    }

    // Popup requesting current status for display
    if (msg.type === "get-status") {
      getConfig(function (config) {
        chrome.storage.local.get(["connected", "lastAuthError"], function (data) {
          sendResponse({
            connected: !!data.connected,
            enabled: config.enabled,
            intensity: config.intensity,
            stats: config.stats,
            poissonUrl: config.poissonUrl,
            hasAuth: !!(config.accessToken && config.refreshToken),
            lastAuthError: data.lastAuthError || "",
          });
        });
      });
      return true; // keep message channel open for async sendResponse
    }
  });

  // -------------------------------------------------------------------
  // Lifecycle — on install or browser startup, resume noise if configured
  // -------------------------------------------------------------------
  chrome.runtime.onInstalled.addListener(function () {
    console.log("[Poisson] Extension installed");
    getConfig(function (config) {
      if (config.poissonUrl && config.accessToken) {
        register(config);
        chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: HEARTBEAT_INTERVAL_MIN });
        if (config.enabled) {
          scheduleNextNoise(config.intensity);
        }
      }
    });
  });

  chrome.runtime.onStartup.addListener(function () {
    getConfig(function (config) {
      if (config.poissonUrl && config.accessToken) {
        heartbeat(config);
        chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: HEARTBEAT_INTERVAL_MIN });
        if (config.enabled) {
          scheduleNextNoise(config.intensity);
        }
      }
    });
  });
})();
