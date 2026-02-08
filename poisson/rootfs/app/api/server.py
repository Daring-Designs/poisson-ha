from __future__ import annotations
"""Local API server for the Ingress UI and HA sensor integration.

Endpoints use /papi/ prefix (not /api/) to avoid collision with HA's
own /api/ namespace which its service worker intercepts.

Security model:
- A random API key is generated at startup.
- Dashboard gets the key embedded in index.html (served through HA ingress,
  which already authenticates the user session).
- Extension receives the key on registration (also through HA ingress).
- All subsequent API calls must include X-Api-Key header.
- Extension registration only requires a Bearer token (validated by HA ingress).

Read-only endpoints:
- GET /papi/status — overall status
- GET /papi/stats — detailed statistics
- GET /papi/activity — recent activity feed
- GET /papi/engines — engine status

State-changing endpoints (require API key):
- POST /papi/engines/{name}/toggle — enable/disable an engine
- POST /papi/intensity — change intensity level
- GET /papi/config — current configuration
- POST /papi/fingerprint — receive real browser viewport dimensions

Extension endpoints (require API key, except register):
- POST /papi/ext/register — extension registration (Bearer token only)
- POST /papi/ext/heartbeat — extension alive check
- POST /papi/ext/fingerprint — deep fingerprint data
- GET /papi/ext/next-task — get next noise action for extension
- GET /papi/ext/download — download extension zip
- GET /papi/ext/status — extension connection status for dashboard
"""

import asyncio
import json
import logging
import pathlib
import time
from collections import defaultdict
from typing import Optional

from aiohttp import web

from api.ext_handler import ExtensionManager
from patterns.personas import Persona, PersonaRotator

logger = logging.getLogger(__name__)

# Allowlist of config keys safe to expose publicly
SAFE_CONFIG_KEYS = {
    "intensity", "enable_search_noise", "enable_browse_noise",
    "enable_ad_clicks", "enable_tor", "enable_dns_noise",
    "enable_research_noise", "max_bandwidth_mb_per_hour",
    "max_concurrent_sessions", "schedule_mode",
    "match_browser_fingerprint",
}


class APIServer:
    """aiohttp-based API for Ingress UI and HA sensors."""

    def __init__(self, scheduler, config: dict, port: int = 8099,
                 persona_rotator: Optional[PersonaRotator] = None):
        self._scheduler = scheduler
        self._config = config
        self._port = port
        self._persona_rotator = persona_rotator
        self._fingerprint_captured = False
        self._ext = ExtensionManager(config, persona_rotator)
        self._app = web.Application(
            middlewares=[self._security_headers_middleware],
            client_max_size=64 * 1024,  # 64 KB max request body
        )
        self._runner: Optional[web.AppRunner] = None
        self._setup_routes()

    @web.middleware
    async def _security_headers_middleware(self, request, handler):
        """Add security headers to all responses."""
        resp = await handler(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self'"
        )
        return resp

    def _setup_routes(self):
        # Dashboard read-only endpoints (API key checked for state-changing)
        self._app.router.add_get("/papi/status", self._handle_status)
        self._app.router.add_get("/papi/stats", self._handle_stats)
        self._app.router.add_get("/papi/activity", self._handle_activity)
        self._app.router.add_get("/papi/engines", self._handle_engines)
        self._app.router.add_get("/papi/activity/chart", self._handle_activity_chart)
        self._app.router.add_post("/papi/engines/{name}/toggle", self._handle_engine_toggle)
        self._app.router.add_post("/papi/intensity", self._handle_intensity)
        self._app.router.add_get("/papi/config", self._handle_config)
        self._app.router.add_post("/papi/fingerprint", self._handle_fingerprint)
        # Extension endpoints
        self._app.router.add_post("/papi/ext/register", self._handle_ext_register)
        self._app.router.add_post("/papi/ext/heartbeat", self._handle_ext_heartbeat)
        self._app.router.add_post("/papi/ext/fingerprint", self._handle_ext_fingerprint)
        self._app.router.add_get("/papi/ext/next-task", self._handle_ext_next_task)
        self._app.router.add_get("/papi/ext/download", self._handle_ext_download)
        self._app.router.add_get("/papi/ext/status", self._handle_ext_status)
        # Serve static UI files (exclude extension/ directory)
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_get("/{path:(?!extension/).*}", self._handle_static)

    # --- Auth helpers ---

    def _check_api_key(self, request: web.Request) -> bool:
        """Validate the API key from X-Api-Key header."""
        key = request.headers.get("X-Api-Key", "")
        return self._ext.validate_api_key(key)

    def _require_api_key(self, request: web.Request) -> Optional[web.Response]:
        """Return a 401 response if API key is invalid, else None."""
        if not self._check_api_key(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        return None

    @staticmethod
    async def _parse_json(request: web.Request) -> tuple[Optional[dict], Optional[web.Response]]:
        """Safely parse JSON body. Returns (data, None) or (None, error_response)."""
        try:
            data = await request.json()
            if not isinstance(data, dict):
                return None, web.json_response(
                    {"error": "Expected JSON object"}, status=400)
            return data, None
        except (json.JSONDecodeError, ValueError):
            return None, web.json_response(
                {"error": "Invalid JSON"}, status=400)

    # --- Index ---

    async def _handle_index(self, request: web.Request) -> web.Response:
        # Capture the real user's browser fingerprint from headers
        if (self._persona_rotator
                and self._config.get("match_browser_fingerprint", True)
                and not self._fingerprint_captured):
            self._capture_fingerprint(request)

        # Read index.html and inject the API key so dashboard JS can use it.
        # This is safe because HA ingress already authenticated this request.
        index_path = pathlib.Path("/app/web/index.html")
        html = index_path.read_text()
        api_key_tag = f'<meta name="api-key" content="{self._ext.api_key}">'
        html = html.replace("</head>", f"  {api_key_tag}\n</head>")
        return web.Response(
            text=html,
            content_type="text/html",
            headers={"Cache-Control": "no-cache"},
        )

    def _capture_fingerprint(self, request: web.Request):
        """Build a Persona from the real user's HTTP headers."""
        ua = request.headers.get("User-Agent", "")
        if not ua:
            return

        accept_lang = request.headers.get("Accept-Language", "en-US,en")
        languages = [lang.split(";")[0].strip()
                     for lang in accept_lang.split(",") if lang.strip()]

        platform = "Win32"
        if "Macintosh" in ua or "Mac OS" in ua:
            platform = "MacIntel"
        elif "Linux" in ua and "Android" not in ua:
            platform = "Linux x86_64"
        elif "Android" in ua:
            platform = "Linux armv81"
        elif "iPhone" in ua:
            platform = "iPhone"
        elif "iPad" in ua:
            platform = "iPad"

        width, height = 1920, 1080
        if "Mobile" in ua:
            width, height = 412, 915

        persona = Persona(
            name="real_user",
            user_agent=ua,
            viewport_width=width,
            viewport_height=height,
            platform=platform,
            languages=languages or ["en-US", "en"],
        )
        self._persona_rotator.set_real_persona(persona)
        self._fingerprint_captured = True

    async def _handle_fingerprint(self, request: web.Request) -> web.Response:
        """Receive real viewport dimensions from the browser JS."""
        auth_err = self._require_api_key(request)
        if auth_err:
            return auth_err

        if not self._persona_rotator or not self._config.get("match_browser_fingerprint", True):
            return web.json_response({"status": "disabled"})

        data, err = await self._parse_json(request)
        if err:
            return err

        try:
            width = int(data.get("width", 0))
            height = int(data.get("height", 0))
            if (0 < width < 10000 and 0 < height < 10000
                    and self._persona_rotator._real_persona):
                self._persona_rotator._real_persona.viewport_width = width
                self._persona_rotator._real_persona.viewport_height = height
                logger.info("Updated real viewport: %dx%d", width, height)
            return web.json_response({"status": "ok"})
        except (ValueError, TypeError):
            return web.json_response({"status": "error"}, status=400)

    async def _handle_static(self, request: web.Request) -> web.Response:
        """Serve static files from /app/web, blocking extension/ directory."""
        rel_path = request.match_info.get("path", "")
        if not rel_path or rel_path.startswith("extension"):
            raise web.HTTPNotFound()
        file_path = pathlib.Path("/app/web") / rel_path
        # Resolve to prevent path traversal
        try:
            file_path = file_path.resolve()
            if not str(file_path).startswith("/app/web/"):
                raise web.HTTPNotFound()
        except (OSError, ValueError):
            raise web.HTTPNotFound()
        if not file_path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(file_path)

    async def start(self):
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("API server listening on port %d", self._port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

    # --- Dashboard read endpoints ---

    async def _check_tor_status(self) -> str:
        """Check Tor SOCKS proxy availability."""
        if not self._config.get("enable_tor", False):
            return "disabled"
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", 9050), timeout=2.0
            )
            writer.close()
            await writer.wait_closed()
            return "connected"
        except (OSError, asyncio.TimeoutError):
            return "offline"

    async def _handle_status(self, request: web.Request) -> web.Response:
        stats = self._scheduler.get_stats()
        running = self._scheduler._running
        engines_active = [
            name for name, eng in self._scheduler._engines.items()
            if eng.enabled
        ]
        persona_name = "unknown"
        fingerprint_matched = False
        if self._persona_rotator:
            if self._persona_rotator.current:
                persona_name = self._persona_rotator.current.name
            fingerprint_matched = self._fingerprint_captured
        tor_status = await self._check_tor_status()
        return web.json_response({
            "status": "running" if running else "paused",
            "uptime_seconds": stats["uptime_seconds"],
            "intensity": self._config.get("intensity", "medium"),
            "active_engines": engines_active,
            "current_persona": persona_name,
            "fingerprint_matched": fingerprint_matched,
            "tor_status": tor_status,
        })

    async def _handle_stats(self, request: web.Request) -> web.Response:
        stats = self._scheduler.get_stats()
        engine_stats = {
            name: eng.get_stats()
            for name, eng in self._scheduler._engines.items()
        }
        errors_today = sum(
            eng._error_count for eng in self._scheduler._engines.values()
        )
        next_session_in = None
        if stats.get("next_session_at"):
            remaining = stats["next_session_at"] - time.time()
            next_session_in = max(0, int(remaining))
        return web.json_response({
            **stats,
            "engines": engine_stats,
            "errors_today": errors_today,
            "next_session_in": next_session_in,
        })

    async def _handle_activity(self, request: web.Request) -> web.Response:
        try:
            count = max(1, min(int(request.query.get("count", "50")), 500))
        except (ValueError, TypeError):
            count = 50
        activity = []
        for engine in self._scheduler._engines.values():
            activity.extend(engine.get_recent_activity(count))
        activity.sort(key=lambda a: a["timestamp"], reverse=True)
        return web.json_response({"activity": activity[:count]})

    async def _handle_activity_chart(self, request: web.Request) -> web.Response:
        """Return hourly event counts for last 24h, broken down by engine."""
        now = time.time()
        cutoff = now - 24 * 3600
        # Initialize 24 hourly buckets per engine
        buckets = defaultdict(lambda: [0] * 24)
        for name, engine in self._scheduler._engines.items():
            for entry in engine.get_recent_activity(200):
                ts = entry["timestamp"]
                if ts < cutoff:
                    continue
                hours_ago = int((now - ts) / 3600)
                if 0 <= hours_ago < 24:
                    buckets[name][23 - hours_ago] += 1
        # Build hour labels (oldest first)
        from datetime import datetime
        labels = []
        for i in range(24):
            h = datetime.fromtimestamp(now - (23 - i) * 3600).strftime("%H:00")
            labels.append(h)
        return web.json_response({
            "labels": labels,
            "engines": dict(buckets),
        })

    async def _handle_engines(self, request: web.Request) -> web.Response:
        engines = {
            name: {
                "enabled": eng.enabled,
                "stats": eng.get_stats(),
            }
            for name, eng in self._scheduler._engines.items()
        }
        return web.json_response({"engines": engines})

    # --- Dashboard state-changing endpoints (require API key) ---

    async def _handle_engine_toggle(self, request: web.Request) -> web.Response:
        auth_err = self._require_api_key(request)
        if auth_err:
            return auth_err

        name = request.match_info["name"]
        if name not in self._scheduler._engines:
            return web.json_response({"error": "Unknown engine"}, status=404)
        engine = self._scheduler._engines[name]
        engine.enabled = not engine.enabled
        logger.info("Engine '%s' %s", name, "enabled" if engine.enabled else "disabled")
        return web.json_response({"name": name, "enabled": engine.enabled})

    async def _handle_intensity(self, request: web.Request) -> web.Response:
        auth_err = self._require_api_key(request)
        if auth_err:
            return auth_err

        data, err = await self._parse_json(request)
        if err:
            return err

        new_intensity = data.get("intensity")
        if new_intensity not in ("low", "medium", "high", "paranoid"):
            return web.json_response({"error": "Invalid intensity"}, status=400)
        from patterns.timing import Intensity, INTENSITY_LAMBDA
        self._scheduler.timer.intensity = Intensity(new_intensity)
        self._scheduler.timer.base_lambda = INTENSITY_LAMBDA[Intensity(new_intensity)]
        self._config["intensity"] = new_intensity
        logger.info("Intensity changed to: %s", new_intensity)
        return web.json_response({"intensity": new_intensity})

    async def _handle_config(self, request: web.Request) -> web.Response:
        auth_err = self._require_api_key(request)
        if auth_err:
            return auth_err
        # Allowlist only safe keys
        return web.json_response({
            k: v for k, v in self._config.items()
            if k in SAFE_CONFIG_KEYS
        })

    # --- Extension endpoints ---

    async def _handle_ext_register(self, request: web.Request) -> web.Response:
        """Registration only requires a Bearer token (HA ingress validates it)."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or len(auth) < 10:
            return web.json_response({"error": "Unauthorized"}, status=401)

        data, err = await self._parse_json(request)
        if err:
            return err
        result = self._ext.register(data)
        return web.json_response(result)

    async def _handle_ext_heartbeat(self, request: web.Request) -> web.Response:
        auth_err = self._require_api_key(request)
        if auth_err:
            return auth_err

        data, err = await self._parse_json(request)
        if err:
            return err
        result = self._ext.heartbeat(data)
        return web.json_response(result)

    async def _handle_ext_fingerprint(self, request: web.Request) -> web.Response:
        auth_err = self._require_api_key(request)
        if auth_err:
            return auth_err

        data, err = await self._parse_json(request)
        if err:
            return err
        result = self._ext.store_fingerprint(data)
        return web.json_response(result)

    async def _handle_ext_next_task(self, request: web.Request) -> web.Response:
        auth_err = self._require_api_key(request)
        if auth_err:
            return auth_err
        task = self._ext.generate_task()
        return web.json_response(task)

    async def _handle_ext_download(self, request: web.Request) -> web.Response:
        # No API key required — user needs to download before they can register.
        # HA ingress already authenticates this request.
        zip_path = pathlib.Path("/app/web/extension.zip")
        if not zip_path.exists():
            return web.json_response({"error": "Extension not packaged"}, status=404)
        return web.FileResponse(
            zip_path,
            headers={
                "Content-Disposition": "attachment; filename=poisson-extension.zip",
                "Content-Type": "application/zip",
            },
        )

    async def _handle_ext_status(self, request: web.Request) -> web.Response:
        return web.json_response(self._ext.get_status())
