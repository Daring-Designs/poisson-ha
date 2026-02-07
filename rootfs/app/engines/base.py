from __future__ import annotations
"""Abstract base class for traffic noise engines."""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import Optional

logger = logging.getLogger(__name__)


class ActivityEntry:
    """A single logged activity for the UI feed."""

    __slots__ = ("timestamp", "engine", "action", "detail")

    def __init__(self, engine: str, action: str, detail: str = ""):
        self.timestamp = time.time()
        self.engine = engine
        self.action = action
        self.detail = detail

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "engine": self.engine,
            "action": self.action,
            "detail": self.detail,
        }


class BaseEngine(ABC):
    """Base class all traffic engines inherit from.

    Provides:
    - Activity logging (recent activity ring buffer)
    - Stats tracking
    - Common execute interface
    """

    def __init__(self, name: str, session_manager=None):
        self.name = name
        self.session_manager = session_manager
        self.enabled = True
        self._activity_log: deque[ActivityEntry] = deque(maxlen=200)
        self._request_count = 0
        self._bytes_count = 0
        self._error_count = 0
        self._last_run: Optional[float] = None

    @abstractmethod
    async def execute(self, action: str = "browse", topic: Optional[str] = None):
        """Perform a single traffic action."""
        ...

    def log_activity(self, action: str, detail: str = ""):
        """Record an activity for the UI feed."""
        entry = ActivityEntry(self.name, action, detail)
        self._activity_log.append(entry)
        logger.info("[%s] %s: %s", self.name, action, detail)

    def get_recent_activity(self, count: int = 50) -> list[dict]:
        """Return recent activity entries for the API."""
        items = list(self._activity_log)[-count:]
        return [a.to_dict() for a in items]

    def get_stats(self) -> dict:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "requests": self._request_count,
            "bytes": self._bytes_count,
            "errors": self._error_count,
            "last_run": self._last_run,
        }

    def get_topics(self) -> list[str]:
        """Override in subclasses that provide topic lists."""
        return []
