/**
 * Poisson — Background service worker.
 *
 * Manages connection to the Poisson add-on server, schedules noise
 * actions via chrome.alarms, and handles tab lifecycle for noise browsing.
 */

(function () {
  "use strict";

  var ALARM_NAME = "poisson-noise";
  var HEARTBEAT_ALARM = "poisson-heartbeat";
  var HEARTBEAT_INTERVAL_MIN = 1; // chrome.alarms minimum is 1 minute
  var offscreenCreated = false;

  // --- Intensity → lambda (events per minute) ---
  var INTENSITY_LAMBDA = {
    low: 0.3 / 60,       // ~18/hour → 0.005/min
    medium: 1.0 / 60,    // ~60/hour → 0.0167/min
    high: 2.5 / 60,      // ~150/hour → 0.0417/min
    paranoid: 5.0 / 60,  // ~300/hour → 0.0833/min
  };

  // --- Storage helpers ---
  function getConfig(cb) {
    chrome.storage.local.get(["serverUrl", "token", "enabled", "intensity", "stats"], function (data) {
      cb({
        serverUrl: data.serverUrl || "",
        token: data.token || "",
        enabled: data.enabled !== false,
        intensity: data.intensity || "medium",
        stats: data.stats || { searches: 0, pages: 0, ads: 0, today: "" },
      });
    });
  }

  function saveStats(stats) {
    var today = new Date().toISOString().slice(0, 10);
    if (stats.today !== today) {
      stats = { searches: 0, pages: 0, ads: 0, today: today };
    }
    chrome.storage.local.set({ stats: stats });
  }

  // --- API helpers ---
  function apiCall(config, method, path, body, cb) {
    var url = config.serverUrl.replace(/\/$/, "") + path;
    var opts = {
      method: method,
      headers: {
        "Authorization": "Bearer " + config.token,
        "Content-Type": "application/json",
      },
    };
    if (body) opts.body = JSON.stringify(body);

    fetch(url, opts)
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) { if (cb) cb(null, data); })
      .catch(function (err) { if (cb) cb(err, null); });
  }

  // --- Offscreen document management ---
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
      // Already exists
      if (e.message && e.message.includes("single offscreen")) {
        offscreenCreated = true;
      }
    }
  }

  function collectFingerprint(cb) {
    ensureOffscreen().then(function () {
      chrome.runtime.sendMessage({ type: "collect-fingerprint" }, function (response) {
        if (chrome.runtime.lastError || !response) {
          // Fallback: try via onMessage listener
          cb(null);
          return;
        }
        cb(response.fingerprint);
      });
    });
  }

  // --- Registration ---
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
          if (data && data.intensity) {
            chrome.storage.local.set({ intensity: data.intensity });
          }
        }
      });

      // Also send fingerprint to dedicated endpoint if we got one
      if (fingerprint) {
        apiCall(config, "POST", "/papi/ext/fingerprint", fingerprint, function () {});
      }
    });
  }

  // --- Heartbeat ---
  function heartbeat(config) {
    apiCall(config, "POST", "/papi/ext/heartbeat", {
      stats: config.stats,
    }, function (err, data) {
      if (err) {
        chrome.storage.local.set({ connected: false });
        return;
      }
      chrome.storage.local.set({ connected: true });
      if (data && data.intensity) {
        chrome.storage.local.set({ intensity: data.intensity });
      }
      if (data && data.enabled === false) {
        chrome.storage.local.set({ enabled: false });
        chrome.alarms.clear(ALARM_NAME);
      }
    });
  }

  // --- Noise scheduling ---
  function scheduleNextNoise(intensity) {
    var lambda = INTENSITY_LAMBDA[intensity] || INTENSITY_LAMBDA.medium;
    // Poisson delay: exponential distribution, clamped to [1, 30] minutes
    // (chrome.alarms minimum period is 1 minute)
    var delayMin = Math.max(1, Math.min(30, -Math.log(Math.random()) / lambda));
    chrome.alarms.create(ALARM_NAME, { delayInMinutes: delayMin });
  }

  function executeNoiseTask(config) {
    apiCall(config, "GET", "/papi/ext/next-task", null, function (err, task) {
      if (err || !task || !task.url) {
        scheduleNextNoise(config.intensity);
        return;
      }

      // Open a background tab
      chrome.tabs.create({ url: task.url, active: false }, function (tab) {
        if (chrome.runtime.lastError || !tab) {
          scheduleNextNoise(config.intensity);
          return;
        }

        var tabId = tab.id;
        var delay = task.delay_ms || 8000;

        // Update stats
        var stats = config.stats;
        var today = new Date().toISOString().slice(0, 10);
        if (stats.today !== today) {
          stats = { searches: 0, pages: 0, ads: 0, today: today };
        }
        if (task.type === "search") stats.searches++;
        else if (task.type === "ad_click") stats.ads++;
        else stats.pages++;
        saveStats(stats);

        // Report completion after delay, then close tab
        setTimeout(function () {
          // Report the action back to server
          apiCall(config, "POST", "/papi/ext/heartbeat", {
            stats: stats,
            last_action: { type: task.type, url: task.url },
          }, function () {});

          // Close the tab
          chrome.tabs.remove(tabId, function () {
            if (chrome.runtime.lastError) {
              // Tab might already be closed
            }
          });

          // Schedule next
          scheduleNextNoise(config.intensity);
        }, delay);
      });
    });
  }

  // --- Alarm handler ---
  chrome.alarms.onAlarm.addListener(function (alarm) {
    if (alarm.name === HEARTBEAT_ALARM) {
      getConfig(function (config) {
        if (config.serverUrl && config.token) {
          heartbeat(config);
        }
      });
      return;
    }

    if (alarm.name === ALARM_NAME) {
      getConfig(function (config) {
        if (!config.serverUrl || !config.token || !config.enabled) return;
        executeNoiseTask(config);
      });
    }
  });

  // --- Message handler (from popup and offscreen) ---
  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (msg.type === "fingerprint-result") {
      // Proactive fingerprint from offscreen document
      getConfig(function (config) {
        if (config.serverUrl && config.token) {
          apiCall(config, "POST", "/papi/ext/fingerprint", msg.fingerprint, function () {});
        }
      });
      return;
    }

    if (msg.type === "connect") {
      chrome.storage.local.set({
        serverUrl: msg.serverUrl,
        token: msg.token,
        enabled: true,
      }, function () {
        getConfig(function (config) {
          register(config);
          // Start heartbeat alarm
          chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: HEARTBEAT_INTERVAL_MIN });
          // Start noise scheduling
          scheduleNextNoise(config.intensity);
          sendResponse({ ok: true });
        });
      });
      return true; // keep channel open
    }

    if (msg.type === "disconnect") {
      chrome.alarms.clearAll();
      chrome.storage.local.set({ connected: false, enabled: false });
      sendResponse({ ok: true });
      return;
    }

    if (msg.type === "set-enabled") {
      chrome.storage.local.set({ enabled: msg.enabled }, function () {
        if (msg.enabled) {
          getConfig(function (config) {
            scheduleNextNoise(config.intensity);
            chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: HEARTBEAT_INTERVAL_MIN });
          });
        } else {
          chrome.alarms.clear(ALARM_NAME);
        }
      });
      sendResponse({ ok: true });
      return;
    }

    if (msg.type === "set-intensity") {
      chrome.storage.local.set({ intensity: msg.intensity });
      sendResponse({ ok: true });
      return;
    }

    if (msg.type === "get-status") {
      getConfig(function (config) {
        chrome.storage.local.get(["connected"], function (data) {
          sendResponse({
            connected: !!data.connected,
            enabled: config.enabled,
            intensity: config.intensity,
            stats: config.stats,
            serverUrl: config.serverUrl,
            hasToken: !!config.token,
          });
        });
      });
      return true; // keep channel open
    }
  });

  // --- On install / startup ---
  chrome.runtime.onInstalled.addListener(function () {
    console.log("[Poisson] Extension installed");
    getConfig(function (config) {
      if (config.serverUrl && config.token) {
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
      if (config.serverUrl && config.token) {
        heartbeat(config);
        chrome.alarms.create(HEARTBEAT_ALARM, { periodInMinutes: HEARTBEAT_INTERVAL_MIN });
        if (config.enabled) {
          scheduleNextNoise(config.intensity);
        }
      }
    });
  });
})();
