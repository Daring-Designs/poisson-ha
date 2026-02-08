/**
 * Poisson — Offscreen fingerprint collector.
 *
 * Runs in an offscreen document (has DOM access) to collect deep
 * browser fingerprint signals that aren't available in a service worker.
 */

(function () {
  "use strict";

  // --- Canvas fingerprint ---
  function getCanvasHash() {
    var canvas = document.getElementById("fp-canvas");
    var ctx = canvas.getContext("2d");

    // Draw a standardized test image
    ctx.textBaseline = "top";
    ctx.font = "14px Arial";
    ctx.fillStyle = "#f60";
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = "#069";
    ctx.fillText("Poisson fp", 2, 15);
    ctx.fillStyle = "rgba(102, 204, 0, 0.7)";
    ctx.fillText("Poisson fp", 4, 17);

    // Arc
    ctx.beginPath();
    ctx.arc(50, 50, 50, 0, Math.PI * 2, true);
    ctx.closePath();
    ctx.fill();

    var dataUrl = canvas.toDataURL();
    // Simple hash (djb2)
    var hash = 5381;
    for (var i = 0; i < dataUrl.length; i++) {
      hash = ((hash << 5) + hash + dataUrl.charCodeAt(i)) & 0xffffffff;
    }
    return hash.toString(16);
  }

  // --- WebGL fingerprint ---
  function getWebGLInfo() {
    try {
      var canvas = document.createElement("canvas");
      var gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
      if (!gl) return { vendor: "unknown", renderer: "unknown" };

      var debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
      return {
        vendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
        renderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
      };
    } catch (e) {
      return { vendor: "error", renderer: "error" };
    }
  }

  // --- Font detection ---
  function getInstalledFonts() {
    var testFonts = [
      "Arial", "Arial Black", "Comic Sans MS", "Courier New", "Georgia",
      "Impact", "Lucida Console", "Lucida Sans Unicode", "Palatino Linotype",
      "Tahoma", "Times New Roman", "Trebuchet MS", "Verdana",
      "MS Gothic", "MS PGothic", "MS Mincho", "Meiryo",
      "Segoe UI", "Calibri", "Cambria", "Consolas",
      "Helvetica Neue", "Futura", "Optima", "Avenir",
      "Menlo", "Monaco", "SF Pro", "SF Mono",
      "Roboto", "Noto Sans", "Noto Serif", "Open Sans",
      "Ubuntu", "DejaVu Sans", "Liberation Sans", "Cantarell",
      "Fira Code", "Source Code Pro", "Droid Sans",
      "Gill Sans", "Century Gothic", "Franklin Gothic Medium",
      "Garamond", "Bookman Old Style", "Brush Script MT",
      "Copperplate", "Papyrus", "Rockwell", "Wingdings"
    ];

    var baseFonts = ["monospace", "sans-serif", "serif"];
    var testString = "mmmmmmmmmmlli";
    var testSize = "72px";

    var canvas = document.createElement("canvas");
    var ctx = canvas.getContext("2d");

    // Measure base widths
    var baseWidths = {};
    baseFonts.forEach(function (base) {
      ctx.font = testSize + " " + base;
      baseWidths[base] = ctx.measureText(testString).width;
    });

    var detected = [];
    testFonts.forEach(function (font) {
      var found = baseFonts.some(function (base) {
        ctx.font = testSize + " '" + font + "', " + base;
        return ctx.measureText(testString).width !== baseWidths[base];
      });
      if (found) detected.push(font);
    });

    return detected;
  }

  // --- Collect all signals ---
  function collectFingerprint() {
    var webgl = getWebGLInfo();
    return {
      canvas_hash: getCanvasHash(),
      webgl_vendor: webgl.vendor,
      webgl_renderer: webgl.renderer,
      fonts: getInstalledFonts(),
      screen_width: screen.width,
      screen_height: screen.height,
      screen_color_depth: screen.colorDepth,
      device_pixel_ratio: window.devicePixelRatio || 1,
      hardware_concurrency: navigator.hardwareConcurrency || 0,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      languages: Array.from(navigator.languages || [navigator.language]),
      platform: navigator.platform,
      do_not_track: navigator.doNotTrack,
      user_agent: navigator.userAgent,
    };
  }

  // Listen for request from background.js
  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (msg.type === "collect-fingerprint") {
      var fp = collectFingerprint();
      sendResponse({ fingerprint: fp });
    }
    return true; // keep channel open for async response
  });

  // Also send fingerprint proactively on load
  var fp = collectFingerprint();
  chrome.runtime.sendMessage({ type: "fingerprint-result", fingerprint: fp });
})();
