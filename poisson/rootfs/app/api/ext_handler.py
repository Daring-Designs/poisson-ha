from __future__ import annotations
"""Extension manager — handles companion browser extension communication.

Tracks connected extension state, generates noise tasks for the extension
to execute in the user's real browser, and stores deep fingerprint data.
"""

import logging
import random
import time
from typing import Any, Optional
from urllib.parse import quote_plus

from patterns.personas import Persona
from patterns.topics import TopicGenerator

logger = logging.getLogger(__name__)

# Search engine URL templates (same weights as engines/search.py)
SEARCH_ENGINES = [
    {"name": "Google", "url": "https://www.google.com/search?q={query}", "weight": 0.55},
    {"name": "Bing", "url": "https://www.bing.com/search?q={query}", "weight": 0.15},
    {"name": "DuckDuckGo", "url": "https://duckduckgo.com/?q={query}", "weight": 0.20},
    {"name": "Yahoo", "url": "https://search.yahoo.com/search?p={query}", "weight": 0.10},
]

# Browse targets — sites with interesting content
BROWSE_SITES = [
    "https://en.wikipedia.org/wiki/Special:Random",
    "https://www.reddit.com/r/all",
    "https://news.ycombinator.com",
    "https://www.bbc.co.uk/news",
    "https://www.reuters.com",
    "https://arstechnica.com",
    "https://www.theverge.com",
    "https://www.nytimes.com",
    "https://www.cnn.com",
    "https://www.wired.com",
    "https://www.amazon.com",
    "https://www.etsy.com",
    "https://www.imdb.com",
    "https://www.youtube.com",
    "https://stackoverflow.com",
    "https://www.foxnews.com",
    "https://www.aljazeera.com",
    "https://scholar.google.com",
    "https://www.walmart.com",
    "https://www.ebay.com",
]

# Ad-heavy sites for ad click tasks
AD_SITES = [
    "https://www.weather.com",
    "https://www.allrecipes.com",
    "https://www.webmd.com",
    "https://www.dictionary.com",
    "https://www.speedtest.net",
    "https://www.accuweather.com",
    "https://www.thesaurus.com",
    "https://www.mapquest.com",
]

# Delay ranges by task type (milliseconds)
DELAY_RANGES = {
    "search": (5000, 15000),
    "browse": (8000, 25000),
    "ad_click": (6000, 12000),
}

# Task type weights
TASK_WEIGHTS = {
    "search": 0.45,
    "browse": 0.40,
    "ad_click": 0.15,
}


class ExtensionManager:
    """Manages the companion browser extension connection and task generation."""

    def __init__(self, config: dict, persona_rotator=None):
        self._config = config
        self._persona_rotator = persona_rotator
        self._topics = TopicGenerator()
        self._connected = False
        self._last_seen: float = 0
        self._registered_at: float = 0
        self._extension_version: str = ""
        self._token: str = ""
        self._deep_fingerprint: dict = {}
        self._stats: dict = {}
        self._actions_completed: int = 0

    @property
    def connected(self) -> bool:
        if not self._connected:
            return False
        # Consider disconnected if no heartbeat in 5 minutes
        return (time.time() - self._last_seen) < 300

    def validate_token(self, token: str) -> bool:
        """Validate the extension's auth token.

        HA's ingress proxy already authenticates requests before they reach
        the add-on, so we just verify a Bearer token is present. We don't
        pin to a specific token value — that breaks on token refresh (every
        30 min) and on disconnect/reconnect (new OAuth flow = new token).
        """
        return bool(token)

    def register(self, data: dict) -> dict:
        """Handle extension registration."""
        self._connected = True
        self._last_seen = time.time()
        self._registered_at = time.time()
        self._extension_version = data.get("version", "unknown")

        fingerprint = data.get("fingerprint", {})
        if fingerprint:
            self._deep_fingerprint = fingerprint
            self._update_persona_from_fingerprint(fingerprint)

        logger.info("Extension registered (v%s)", self._extension_version)
        return {
            "status": "ok",
            "intensity": self._config.get("intensity", "medium"),
        }

    def heartbeat(self, data: dict) -> dict:
        """Handle extension heartbeat."""
        self._connected = True
        self._last_seen = time.time()

        if data.get("stats"):
            self._stats = data["stats"]

        if data.get("last_action"):
            self._actions_completed += 1

        return {
            "status": "ok",
            "intensity": self._config.get("intensity", "medium"),
            "enabled": True,
        }

    def store_fingerprint(self, fingerprint: dict) -> dict:
        """Store deep fingerprint data from extension."""
        self._deep_fingerprint = fingerprint
        self._update_persona_from_fingerprint(fingerprint)
        logger.info(
            "Deep fingerprint received: canvas=%s, webgl=%s, fonts=%d",
            fingerprint.get("canvas_hash", "?")[:12],
            fingerprint.get("webgl_renderer", "?")[:30],
            len(fingerprint.get("fonts", [])),
        )
        return {"status": "ok"}

    def generate_task(self) -> dict:
        """Generate a noise task for the extension to execute."""
        # Pick task type by weight
        types = list(TASK_WEIGHTS.keys())
        weights = list(TASK_WEIGHTS.values())
        task_type = random.choices(types, weights=weights, k=1)[0]

        delay_range = DELAY_RANGES.get(task_type, (5000, 15000))
        delay_ms = random.randint(*delay_range)

        if task_type == "search":
            return self._generate_search_task(delay_ms)
        elif task_type == "browse":
            return self._generate_browse_task(delay_ms)
        else:
            return self._generate_ad_click_task(delay_ms)

    def get_status(self) -> dict:
        """Return extension status for dashboard."""
        return {
            "connected": self.connected,
            "last_seen": self._last_seen,
            "registered_at": self._registered_at,
            "version": self._extension_version,
            "actions_completed": self._actions_completed,
            "has_fingerprint": bool(self._deep_fingerprint),
            "stats": self._stats,
        }

    def _generate_search_task(self, delay_ms: int) -> dict:
        query = self._topics.random_query()
        engine = self._pick_search_engine()
        url = engine["url"].format(query=quote_plus(query))
        return {
            "type": "search",
            "url": url,
            "query": query,
            "engine": engine["name"],
            "delay_ms": delay_ms,
        }

    def _generate_browse_task(self, delay_ms: int) -> dict:
        url = random.choice(BROWSE_SITES)
        return {
            "type": "browse",
            "url": url,
            "delay_ms": delay_ms,
        }

    def _generate_ad_click_task(self, delay_ms: int) -> dict:
        url = random.choice(AD_SITES)
        return {
            "type": "ad_click",
            "url": url,
            "delay_ms": delay_ms,
        }

    def _update_persona_from_fingerprint(self, fp: dict):
        """Update the persona rotator with deep fingerprint data."""
        if not self._persona_rotator:
            return
        if not self._config.get("match_browser_fingerprint", True):
            return

        ua = fp.get("user_agent", "")
        if not ua:
            return

        languages = fp.get("languages", ["en-US", "en"])
        platform = fp.get("platform", "Win32")
        width = fp.get("screen_width", 1920)
        height = fp.get("screen_height", 1080)

        persona = Persona(
            name="real_user_ext",
            user_agent=ua,
            viewport_width=width,
            viewport_height=height,
            platform=platform,
            languages=languages,
        )
        self._persona_rotator.set_real_persona(persona)
        logger.info("Updated persona from extension fingerprint: %s (%dx%d)",
                     ua[:60], width, height)

    @staticmethod
    def _pick_search_engine() -> dict:
        weights = [e["weight"] for e in SEARCH_ENGINES]
        return random.choices(SEARCH_ENGINES, weights=weights, k=1)[0]
