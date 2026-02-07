"""Tests for the traffic engine base classes and DNS engine."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "poisson" / "rootfs" / "app"))

import pytest

from engines.base import ActivityEntry, BaseEngine
from engines.dns import DNSEngine, DNS_DOMAINS


class ConcreteEngine(BaseEngine):
    """Minimal concrete engine for testing the base class."""

    async def execute(self, action="test", topic=None):
        self.log_activity(action, f"Test action: {topic or 'none'}")
        self._request_count += 1


class TestActivityEntry:
    def test_to_dict(self):
        entry = ActivityEntry("test_engine", "browse", "visiting example.com")
        d = entry.to_dict()
        assert d["engine"] == "test_engine"
        assert d["action"] == "browse"
        assert d["detail"] == "visiting example.com"
        assert d["timestamp"] > 0


class TestBaseEngine:
    def test_log_activity(self):
        engine = ConcreteEngine("test")
        engine.log_activity("browse", "example.com")
        recent = engine.get_recent_activity(10)
        assert len(recent) == 1
        assert recent[0]["detail"] == "example.com"

    def test_stats(self):
        engine = ConcreteEngine("test")
        stats = engine.get_stats()
        assert stats["name"] == "test"
        assert stats["requests"] == 0
        assert stats["enabled"] is True

    def test_activity_ring_buffer(self):
        engine = ConcreteEngine("test")
        for i in range(300):
            engine.log_activity("action", f"entry {i}")
        recent = engine.get_recent_activity(300)
        assert len(recent) == 200  # maxlen

    @pytest.mark.asyncio
    async def test_execute(self):
        engine = ConcreteEngine("test")
        await engine.execute("browse", "hiking")
        assert engine._request_count == 1


class TestDNSEngine:
    def test_domain_lists_populated(self):
        for category, domains in DNS_DOMAINS.items():
            assert len(domains) > 0, f"Category {category} is empty"

    @pytest.mark.asyncio
    async def test_execute_resolves(self):
        engine = DNSEngine()
        await engine.execute()
        assert engine._request_count >= 1

    def test_resolve_known_domain(self):
        """Verify the static resolve method works."""
        from engines.dns import DNSEngine
        # This should not raise for a well-known domain
        DNSEngine._resolve("google.com")
