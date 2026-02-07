from __future__ import annotations
"""Local API server for the Ingress UI and HA sensor integration.

Endpoints:
- GET /api/status — overall status
- GET /api/stats — detailed statistics
- GET /api/activity — recent activity feed
- GET /api/engines — engine status and toggles
- POST /api/engines/{name}/toggle — enable/disable an engine
- POST /api/intensity — change intensity level
- GET /api/config — current configuration
"""

import logging
import pathlib
from typing import Optional

from aiohttp import web

logger = logging.getLogger(__name__)


class APIServer:
    """aiohttp-based API for Ingress UI and HA sensors."""

    def __init__(self, scheduler, config: dict, port: int = 8099):
        self._scheduler = scheduler
        self._config = config
        self._port = port
        self._app = web.Application()
        self._runner: Optional[web.AppRunner] = None
        self._setup_routes()

    def _setup_routes(self):
        self._app.router.add_get("/api/status", self._handle_status)
        self._app.router.add_get("/api/stats", self._handle_stats)
        self._app.router.add_get("/api/activity", self._handle_activity)
        self._app.router.add_get("/api/engines", self._handle_engines)
        self._app.router.add_post("/api/engines/{name}/toggle", self._handle_engine_toggle)
        self._app.router.add_post("/api/intensity", self._handle_intensity)
        self._app.router.add_get("/api/config", self._handle_config)
        # Serve static UI files
        self._app.router.add_get("/", self._handle_index)
        self._app.router.add_static("/", path="/app/web", name="static")

    async def _handle_index(self, request: web.Request) -> web.Response:
        index_path = pathlib.Path("/app/web/index.html")
        return web.FileResponse(index_path)

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
        return web.json_response({
            "status": "running" if running else "paused",
            "uptime_seconds": stats["uptime_seconds"],
            "intensity": self._config.get("intensity", "medium"),
            "active_engines": engines_active,
            "current_persona": (
                self._scheduler._engines.get("browse", None)
                and getattr(
                    getattr(self._scheduler._engines.get("browse"), "session_manager", None),
                    "_personas", None
                )
                and getattr(
                    getattr(self._scheduler._engines.get("browse"), "session_manager", None)._personas,
                    "current", None
                )
                and getattr(
                    getattr(self._scheduler._engines.get("browse"), "session_manager", None)._personas.current,
                    "name", "unknown"
                )
            ) or "unknown",
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
