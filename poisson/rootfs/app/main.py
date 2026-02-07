from __future__ import annotations
"""Poisson — Traffic Noise Generator for Home Assistant.

Entry point and orchestrator. Initializes configuration, engines,
scheduler, and API server.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Ensure the app directory is on the path
sys.path.insert(0, str(Path(__file__).parent))

from api.server import APIServer
from config import load_config
from engines.browse import BrowseEngine
from engines.dns import DNSEngine
from engines.search import SearchEngine
from scheduler import Scheduler
from session import SessionManager


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


async def main():
    config = load_config()
    setup_logging(config.get("log_level", "INFO"))
    logger = logging.getLogger("poisson")

    logger.info("=" * 60)
    logger.info("Poisson — Traffic Noise Generator")
    logger.info("Making mass surveillance expensive and unreliable.")
    logger.info("=" * 60)

    # Initialize components
    session_mgr = SessionManager(config)
    scheduler = Scheduler(config)

    # Register enabled engines
    if config.get("enable_search_noise", True):
        scheduler.register_engine("search", SearchEngine(session_manager=session_mgr))
    if config.get("enable_browse_noise", True):
        scheduler.register_engine("browse", BrowseEngine(session_manager=session_mgr))
    if config.get("enable_dns_noise", True):
        scheduler.register_engine("dns", DNSEngine())

    # API server for Ingress UI
    api = APIServer(
        scheduler=scheduler,
        config=config,
        port=config.get("api_port", 8099),
    )

    # Graceful shutdown
    shutdown_event = asyncio.Event()

    def handle_signal():
        logger.info("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal)

    try:
        # Start browser
        await session_mgr.start()
        logger.info("Session manager ready")

        # Start API server
        await api.start()

        # Start scheduler
        await scheduler.start()
        logger.info("All systems running")

        # Wait for shutdown signal
        await shutdown_event.wait()

    except Exception:
        logger.exception("Fatal error")
    finally:
        logger.info("Shutting down...")
        await scheduler.stop()
        await api.stop()
        await session_mgr.stop()
        logger.info("Goodbye.")


if __name__ == "__main__":
    asyncio.run(main())
