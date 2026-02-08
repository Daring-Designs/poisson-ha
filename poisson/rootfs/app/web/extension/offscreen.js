/**
 * Poisson — Offscreen fingerprint collector
 *
 * SECURITY TRANSPARENCY: This file collects your browser's fingerprint
 * so that Poisson's headless noise sessions can mimic your real browser.
 *
 * WHY: Trackers use canvas rendering, WebGL, and font lists to identify
 * unique browsers. If noise traffic has a different fingerprint than your
 * real browsing, trackers can trivially filter it out. By matching the
 * fingerprint, noise becomes indistinguishable from real traffic.
 *
 * WHAT IS COLLECTED:
 *   - Canvas hash: A hash of how your browser renders a test image (unique per GPU/driver)
 *   - WebGL vendor/renderer: Your graphics card info (e.g., "NVIDIA GeForce RTX 3080")
 *   - Installed fonts: Which fonts are available (detected via canvas text measurement)
 *   - Screen dimensions, color depth, pixel ratio
 *   - Hardware concurrency (CPU core count)
 *   - Timezone, language preferences, platform string
 *   - User agent string
 *
 * WHAT IS NOT COLLECTED:
 *   - No passwords, cookies, or form data
 *   - No browsing history or bookmarks
 *   - No file system access
 *   - No network requests (this file only measures and reports back)
 *
 * WHERE DOES IT GO:
 *   Sent via chrome.runtime message to background.js, which forwards it
 *   to YOUR Poisson server only. Never sent anywhere else.
 *
 * Source code: https://github.com/Daring-Designs/poisson
 */

(function () {
  "use strict";

  // -------------------------------------------------------------------
  // Canvas fingerprint — draws a test image and hashes the pixel data.
  // This is how trackers identify your browser's rendering engine.
  // We collect it so headless sessions can report the same hash.
  // -------------------------------------------------------------------
  function getCanvasHash() {
    var canvas = document.getElementById("fp-canvas");
    var ctx = canvas.getContext("2d");

    // Draw a standardized test image (same as common fingerprinting scripts)
    ctx.textBaseline = "top";
    ctx.font = "14px Arial";
    ctx.fillStyle = "#f60";
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = "#069";
    ctx.fillText("Poisson fp", 2, 15);
    ctx.fillStyle = "rgba(102, 204, 0, 0.7)";
    ctx.fillText("Poisson fp", 4, 17);

    // Arc shape (tests anti-aliasing behavior)
    ctx.beginPath();
    ctx.arc(50, 50, 50, 0, Math.PI * 2, true);
    ctx.closePath();
    ctx.fill();

    // Convert to data URL and hash with djb2
    var dataUrl = canvas.toDataURL();
    var hash = 5381;
    for (var i = 0; i < dataUrl.length; i++) {
      hash = ((hash << 5) + hash + dataUrl.charCodeAt(i)) & 0xffffffff;
    }
    return hash.toString(16);
  }

  // -------------------------------------------------------------------
  // WebGL fingerprint — reads the GPU vendor and renderer strings.
  // Trackers use this to narrow down your exact hardware.
  // -------------------------------------------------------------------
  function getWebGLInfo() {
    try {
      var canvas = document.createElement("canvas");
      var gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
      if (!gl) return { vendor: "unknown", renderer: "unknown" };

      // WEBGL_debug_renderer_info gives the real GPU name instead of generic "WebKit WebGL"
      var debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
      return {
        vendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
        renderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
      };
    } catch (e) {
      return { vendor: "error", renderer: "error" };
    }
  }

  // -------------------------------------------------------------------
  // Font detection — checks which fonts are installed by measuring
  // text width differences. If a font is installed, rendering text in
  // that font produces a different width than the fallback font.
  //
  // This is a common tracker technique. We collect your font list so
  // headless sessions can report the same set.
  // -------------------------------------------------------------------
  function getInstalledFonts() {
    // Common fonts that trackers check for
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

    // Baseline fonts that are always available
    var baseFonts = ["monospace", "sans-serif", "serif"];
    var testString = "mmmmmmmmmmlli"; // Characters chosen for width variation
    var testSize = "72px";            // Large size amplifies width differences

    var canvas = document.createElement("canvas");
    var ctx = canvas.getContext("2d");

    // Measure baseline widths (text rendered in generic fallback fonts)
    var baseWidths = {};
    baseFonts.forEach(function (base) {
      ctx.font = testSize + " " + base;
      baseWidths[base] = ctx.measureText(testString).width;
    });

    // For each test font: if rendering width differs from baseline, font is installed
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

  // -------------------------------------------------------------------
  // Collect all fingerprint signals into a single object.
  // This is the complete set of data sent to your Poisson server.
  // -------------------------------------------------------------------
  function collectFingerprint() {
    var webgl = getWebGLInfo();
    return {
      canvas_hash: getCanvasHash(),           // How your GPU renders a test image
      webgl_vendor: webgl.vendor,             // GPU manufacturer (e.g., "Google Inc.")
      webgl_renderer: webgl.renderer,         // GPU model (e.g., "ANGLE (Apple, ...)")
      fonts: getInstalledFonts(),             // List of installed font names
      screen_width: screen.width,             // Screen resolution width
      screen_height: screen.height,           // Screen resolution height
      screen_color_depth: screen.colorDepth,  // Color depth (usually 24 or 32)
      device_pixel_ratio: window.devicePixelRatio || 1, // Retina/HiDPI scaling factor
      hardware_concurrency: navigator.hardwareConcurrency || 0, // CPU core count
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, // e.g., "America/Chicago"
      languages: Array.from(navigator.languages || [navigator.language]), // e.g., ["en-US", "en"]
      platform: navigator.platform,           // e.g., "MacIntel", "Win32"
      do_not_track: navigator.doNotTrack,     // DNT header preference
      user_agent: navigator.userAgent,        // Full browser user agent string
    };
  }

  // -------------------------------------------------------------------
  // Communication — sends fingerprint data back to background.js
  // via Chrome's internal message passing (not a network request).
  // -------------------------------------------------------------------

  // Respond to explicit requests from background.js
  chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (msg.type === "collect-fingerprint") {
      var fp = collectFingerprint();
      sendResponse({ fingerprint: fp });
    }
    return true; // keep channel open for async response
  });

  // Also send fingerprint proactively on load (background.js may be waiting)
  var fp = collectFingerprint();
  chrome.runtime.sendMessage({ type: "fingerprint-result", fingerprint: fp });
})();
