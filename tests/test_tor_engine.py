"""Tests for the Tor browsing engine and proxy parameter flow."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "poisson" / "rootfs" / "app"))

import pytest

from engines.tor import TOR_PROXY, TOR_SITES, TorEngine


class TestTorSiteLists:
    def test_all_categories_populated(self):
        for category, sites in TOR_SITES.items():
            assert len(sites) > 0, f"Category {category} is empty"

    def test_all_sites_have_url_and_weight(self):
        for category, sites in TOR_SITES.items():
            for site in sites:
                assert "url" in site, f"Missing url in {category}"
                assert "weight" in site, f"Missing weight in {category}"
                assert site["url"].startswith("https://"), (
                    f"Non-HTTPS url in {category}: {site['url']}"
                )
                assert 0.0 < site["weight"] <= 1.0, (
                    f"Invalid weight in {category}: {site['weight']}"
                )

    def test_tor_proxy_address(self):
        assert TOR_PROXY == "socks5://127.0.0.1:9050"


class TestTorEngine:
    def test_engine_name(self):
        engine = TorEngine()
        assert engine.name == "tor"

    def test_no_session_manager_returns_early(self):
        engine = TorEngine(session_manager=None)
        asyncio.get_event_loop().run_until_complete(engine.execute())
        assert engine._request_count == 0

    @pytest.mark.asyncio
    async def test_execute_with_mocked_session(self):
        mock_session = AsyncMock()
        mock_session.navigate = AsyncMock(return_value=True)
        mock_session.simulate_reading = AsyncMock()
        mock_session.click_random_link = AsyncMock(return_value=None)
        mock_session.hover_random_element = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session.bytes_transferred = 1234

        mock_manager = AsyncMock()
        mock_manager.new_session = AsyncMock(return_value=mock_session)

        engine = TorEngine(session_manager=mock_manager)
        await engine.execute()

        # Verify proxy was passed to new_session
        mock_manager.new_session.assert_called_once_with(proxy=TOR_PROXY)
        assert engine._request_count >= 1
        assert engine._bytes_count == 1234

    @pytest.mark.asyncio
    async def test_execute_handles_navigation_failure(self):
        mock_session = AsyncMock()
        mock_session.navigate = AsyncMock(return_value=False)
        mock_session.close = AsyncMock()
        mock_session.bytes_transferred = 0

        mock_manager = AsyncMock()
        mock_manager.new_session = AsyncMock(return_value=mock_session)

        engine = TorEngine(session_manager=mock_manager)
        await engine.execute()

        assert engine._request_count == 0
        assert engine._error_count == 1

    @pytest.mark.asyncio
    async def test_execute_handles_exception(self):
        mock_session = AsyncMock()
        mock_session.navigate = AsyncMock(side_effect=Exception("connection failed"))
        mock_session.close = AsyncMock()

        mock_manager = AsyncMock()
        mock_manager.new_session = AsyncMock(return_value=mock_session)

        engine = TorEngine(session_manager=mock_manager)
        await engine.execute()

        assert engine._error_count == 1

    def test_weighted_pick(self):
        sites = [
            {"url": "https://example.com", "weight": 1.0},
            {"url": "https://example.org", "weight": 0.5},
        ]
        picks = {TorEngine._weighted_pick(sites)["url"] for _ in range(100)}
        # Both sites should be picked at least once in 100 tries
        assert len(picks) == 2


class TestSessionManagerProxy:
    """Test that the proxy parameter flows through SessionManager."""

    def test_proxy_param_in_source(self):
        """Verify new_session and _create_context accept proxy parameter."""
        import ast

        session_path = (
            Path(__file__).parent.parent / "poisson" / "rootfs" / "app" / "session.py"
        )
        source = session_path.read_text()
        tree = ast.parse(source)

        # Find the SessionManager class and check method signatures
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "new_session":
                arg_names = [a.arg for a in node.args.args]
                assert "proxy" in arg_names, "new_session missing proxy parameter"
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_create_context":
                arg_names = [a.arg for a in node.args.args]
                assert "proxy" in arg_names, "_create_context missing proxy parameter"

    def test_proxy_dict_in_create_context(self):
        """Verify _create_context passes proxy dict to new_context."""
        session_path = (
            Path(__file__).parent.parent / "poisson" / "rootfs" / "app" / "session.py"
        )
        source = session_path.read_text()
        assert '"server"' in source or "'server'" in source, (
            "_create_context should pass proxy as {'server': proxy}"
        )
