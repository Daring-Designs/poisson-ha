from __future__ import annotations
"""Tor browsing noise engine — routes traffic through Tor SOCKS proxy.

Browses a mix of clearnet privacy/Tor-adjacent sites and public .onion
directories. Uses longer reading times and deeper link chains to mimic
real Tor browsing behavior (users expect slowness and browse deliberately).
"""

import random
import time
from typing import Optional

from engines.base import BaseEngine

TOR_PROXY = "socks5://127.0.0.1:9050"

# Sites organized by category — clearnet privacy sites and .onion directories
TOR_SITES = {
    "tor_project": [
        {"url": "https://www.torproject.org", "weight": 1.0},
        {"url": "https://support.torproject.org", "weight": 0.8},
        {"url": "https://blog.torproject.org", "weight": 0.7},
        {"url": "https://metrics.torproject.org", "weight": 0.5},
    ],
    "onion_directories": [
        {"url": "https://ahmia.fi", "weight": 1.0},
        {"url": "https://dark.fail", "weight": 0.8},
    ],
    "privacy_news": [
        {"url": "https://www.eff.org", "weight": 1.0},
        {"url": "https://ssd.eff.org", "weight": 0.9},
        {"url": "https://www.privacyguides.org", "weight": 0.8},
        {"url": "https://theintercept.com", "weight": 0.7},
        {"url": "https://freedom.press", "weight": 0.7},
        {"url": "https://citizenlab.ca", "weight": 0.6},
    ],
    "secure_services": [
        {"url": "https://proton.me", "weight": 0.9},
        {"url": "https://mullvad.net", "weight": 0.8},
        {"url": "https://signal.org", "weight": 0.8},
        {"url": "https://tails.net", "weight": 0.7},
        {"url": "https://www.whonix.org", "weight": 0.6},
        {"url": "https://keys.openpgp.org", "weight": 0.5},
    ],
    "onion_mirrors": [
        {"url": "https://www.propublica.org", "weight": 0.9},
        {"url": "https://www.nytimes.com", "weight": 0.8},
        {"url": "https://www.bbc.com/news", "weight": 0.8},
        {"url": "https://duckduckgo.com", "weight": 1.0},
    ],
    "research": [
        {"url": "https://arxiv.org/list/cs.CR/recent", "weight": 0.6},
        {"url": "https://www.schneier.com", "weight": 0.7},
        {"url": "https://krebsonsecurity.com", "weight": 0.7},
        {"url": "https://www.bellingcat.com", "weight": 0.6},
        {"url": "https://www.icij.org", "weight": 0.6},
    ],
}


class TorEngine(BaseEngine):
    """Generates browsing noise routed through Tor."""

    def __init__(self, session_manager=None):
        super().__init__("tor", session_manager)

    async def execute(self, action: str = "browse", topic: Optional[str] = None):
        if not self.session_manager:
            return

        # Pick a category and site
        category = random.choice(list(TOR_SITES.keys()))
        sites = TOR_SITES[category]
        site = self._weighted_pick(sites)
        url = site["url"]

        self.log_activity("tor_browse", f"Visiting {url} ({category}) via Tor")

        session = await self.session_manager.new_session(proxy=TOR_PROXY)
        try:
            # Tor connections are slower — use a longer timeout
            success = await session.navigate(url, timeout_ms=60000)
            if not success:
                self._error_count += 1
                return

            self._request_count += 1
            self._last_run = time.time()

            # Tor users read more deliberately — longer reading times
            await session.simulate_reading(
                content_length=random.randint(4000, 15000)
            )

            # Deeper link-following chains — Tor browsing is research-style
            depth = random.randint(2, 5)
            for _ in range(depth):
                if random.random() < 0.3:
                    await session.hover_random_element()

                clicked = await session.click_random_link()
                if clicked:
                    self.log_activity("tor_browse", f"Following: {clicked[:80]}")
                    self._request_count += 1
                    # Longer reading between clicks (Tor latency + deliberate reading)
                    await session.simulate_reading(
                        content_length=random.randint(3000, 18000)
                    )
                else:
                    break

            self._bytes_count += session.bytes_transferred

        except Exception:
            self._error_count += 1
        finally:
            await session.close()

    @staticmethod
    def _weighted_pick(sites: list[dict]) -> dict:
        weights = [s.get("weight", 1.0) for s in sites]
        return random.choices(sites, weights=weights, k=1)[0]
