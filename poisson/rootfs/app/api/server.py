from __future__ import annotations
"""Local API server for the Ingress UI and HA sensor integration.

Endpoints use /papi/ prefix (not /api/) to avoid collision with HA's
own /api/ namespace which its service worker intercepts.

- GET /papi/status — overall status
- GET /papi/stats — detailed statistics
- GET /papi/activity — recent activity feed
- GET /papi/engines — engine status and toggles
- POST /papi/engines/{name}/toggle — enable/disable an engine
- POST /papi/intensity — change intensity level
- GET /papi/config — current configuration
- POST /papi/fingerprint — receive real browser viewport dimensions

Extension endpoints (auth via Bearer token):
- POST /papi/ext/register — extension registration + initial fingerprint
- POST /papi/ext/heartbeat — extension alive check
- POST /papi/ext/fingerprint — deep fingerprint data
- GET /papi/ext/next-task — get next noise action for extension
- GET /papi/ext/download — download extension zip
- GET /papi/ext/status — extension connection status for dashboard
"""

import logging
import pathlib
from typing import Optional

from aiohttp import web

from api.ext_handler import ExtensionManager
from patterns.personas import Persona, PersonaRotator

logger = logging.getLogger(__name__)


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
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._setup_routes()

    def _setup_routes(self):
        self._app.router.add_get("/papi/status", self._handle_status)
        self._app.router.add_get("/papi/stats", self._handle_stats)
        self._app.router.add_get("/papi/activity", self._handle_activity)
        self._app.router.add_get("/papi/engines", self._handle_engines)
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
        # Serve static UI files
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_static("/", path="/app/web", name="static")

    async def _handle_index(self, request: web.Request) -> web.Response:
        # Capture the real user's browser fingerprint from headers
        if (self._persona_rotator
                and self._config.get("match_browser_fingerprint", True)
                and not self._fingerprint_captured):
            self._capture_fingerprint(request)
        index_path = pathlib.Path("/app/web/index.html")
        resp = web.FileResponse(index_path)
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    def _capture_fingerprint(self, request: web.Request):
        """Build a Persona from the real user's HTTP headers."""
        ua = request.headers.get("User-Agent", "")
        if not ua:
            return

        # Parse Accept-Language into a list (e.g. "en-US,en;q=0.9" → ["en-US", "en"])
        accept_lang = request.headers.get("Accept-Language", "en-US,en")
        languages = [lang.split(";")[0].strip()
                     for lang in accept_lang.split(",") if lang.strip()]

        # Infer platform from UA
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

        # Default viewport (will be updated by JS POST to /papi/fingerprint)
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
        if not self._persona_rotator or not self._config.get("match_browser_fingerprint", True):
            return web.json_response({"status": "disabled"})

        try:
            data = await request.json()
            width = int(data.get("width", 0))
            height = int(data.get("height", 0))
            if width > 0 and height > 0 and self._persona_rotator._real_persona:
                self._persona_rotator._real_persona.viewport_width = width
                self._persona_rotator._real_persona.viewport_height = height
                logger.info("Updated real viewport: %dx%d", width, height)
            return web.json_response({"status": "ok"})
        except Exception:
            return web.json_response({"status": "error"}, status=400)

    async def start(self):
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await site.start()
        logger.info("API server listening on port %d", self._port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()

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
        return web.json_response({
            "status": "running" if running else "paused",
            "uptime_seconds": stats["uptime_seconds"],
            "intensity": self._config.get("intensity", "medium"),
            "active_engines": engines_active,
            "current_persona": persona_name,
            "fingerprint_matched": fingerprint_matched,
        })

    async def _handle_stats(self, request: web.Request) -> web.Response:
        stats = self._scheduler.get_stats()
        engine_stats = {
            name: eng.get_stats()
            for name, eng in self._scheduler._engines.items()
        }
        return web.json_response({
            **stats,
            "engines": engine_stats,
        })

    async def _handle_activity(self, request: web.Request) -> web.Response:
        count = int(request.query.get("count", "50"))
        activity = []
        for engine in self._scheduler._engines.values():
            activity.extend(engine.get_recent_activity(count))
        # Sort by timestamp descending
        activity.sort(key=lambda a: a["timestamp"], reverse=True)
        return web.json_response({"activity": activity[:count]})

    async def _handle_engines(self, request: web.Request) -> web.Response:
        engines = {
            name: {
                "enabled": eng.enabled,
                "stats": eng.get_stats(),
            }
            for name, eng in self._scheduler._engines.items()
        }
        return web.json_response({"engines": engines})

    async def _handle_engine_toggle(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        if name not in self._scheduler._engines:
            return web.json_response({"error": f"Unknown engine: {name}"}, status=404)
        engine = self._scheduler._engines[name]
        engine.enabled = not engine.enabled
        logger.info("Engine '%s' %s", name, "enabled" if engine.enabled else "disabled")
        return web.json_response({"name": name, "enabled": engine.enabled})

    async def _handle_intensity(self, request: web.Request) -> web.Response:
        data = await request.json()
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
        # Return safe config (no secrets)
        return web.json_response({
            k: v for k, v in self._config.items()
            if not k.startswith("_")
        })

    # --- Extension endpoints ---

    def _ext_auth(self, request: web.Request) -> bool:
        """Validate extension Bearer token."""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        token = auth[7:]
        return self._ext.validate_token(token)

    async def _handle_ext_register(self, request: web.Request) -> web.Response:
        if not self._ext_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        result = self._ext.register(data)
        return web.json_response(result)

    async def _handle_ext_heartbeat(self, request: web.Request) -> web.Response:
        if not self._ext_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        result = self._ext.heartbeat(data)
        return web.json_response(result)

    async def _handle_ext_fingerprint(self, request: web.Request) -> web.Response:
        if not self._ext_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        data = await request.json()
        result = self._ext.store_fingerprint(data)
        return web.json_response(result)

    async def _handle_ext_next_task(self, request: web.Request) -> web.Response:
        if not self._ext_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        task = self._ext.generate_task()
        return web.json_response(task)

    async def _handle_ext_download(self, request: web.Request) -> web.Response:
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
