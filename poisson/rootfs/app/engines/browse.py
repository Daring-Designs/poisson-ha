from __future__ import annotations
"""Web browsing noise engine — visits random sites across categories.

Generates realistic browsing sessions:
- Visits sites from a categorized list
- Follows internal links
- Simulates reading behavior
- Spans news, shopping, entertainment, forums, foreign language content
"""

import random
import time
from pathlib import Path
from typing import Optional

import yaml

from engines.base import BaseEngine

DATA_DIR = Path(__file__).parent.parent / "data"

# Fallback site list if sites.yaml isn't present
BUILTIN_SITES = {
    "news_left": [
        {"url": "https://www.cnn.com", "weight": 1.0},
        {"url": "https://www.msnbc.com", "weight": 0.8},
        {"url": "https://www.nytimes.com", "weight": 0.9},
    ],
    "news_right": [
        {"url": "https://www.foxnews.com", "weight": 1.0},
        {"url": "https://www.dailywire.com", "weight": 0.7},
    ],
    "news_international": [
        {"url": "https://www.aljazeera.com", "weight": 0.9},
        {"url": "https://www.bbc.co.uk", "weight": 1.0},
        {"url": "https://www.reuters.com", "weight": 0.9},
        {"url": "https://www.dw.com", "weight": 0.7},
    ],
    "shopping": [
        {"url": "https://www.amazon.com", "weight": 1.0},
        {"url": "https://www.etsy.com", "weight": 0.7},
        {"url": "https://www.walmart.com", "weight": 0.8},
        {"url": "https://www.ebay.com", "weight": 0.7},
    ],
    "tech": [
        {"url": "https://news.ycombinator.com", "weight": 0.9},
        {"url": "https://www.theverge.com", "weight": 0.8},
        {"url": "https://arstechnica.com", "weight": 0.8},
        {"url": "https://www.wired.com", "weight": 0.7},
    ],
    "forums": [
        {"url": "https://www.reddit.com", "weight": 1.0},
        {"url": "https://stackoverflow.com", "weight": 0.8},
    ],
    "entertainment": [
        {"url": "https://www.youtube.com", "weight": 1.0},
        {"url": "https://www.imdb.com", "weight": 0.6},
        {"url": "https://www.spotify.com", "weight": 0.5},
    ],
    "government": [
        {"url": "https://www.usa.gov", "weight": 0.5},
        {"url": "https://www.foia.gov", "weight": 0.4},
        {"url": "https://www.sec.gov/cgi-bin/browse-edgar", "weight": 0.3},
    ],
    "education": [
        {"url": "https://en.wikipedia.org", "weight": 1.0},
        {"url": "https://scholar.google.com", "weight": 0.6},
        {"url": "https://www.khanacademy.org", "weight": 0.5},
    ],
}


class BrowseEngine(BaseEngine):
    """Generates realistic website browsing noise."""

    def __init__(self, session_manager=None):
        super().__init__("browse", session_manager)
        self._sites: dict[str, list[dict]] = {}
        self._load_sites()

    def _load_sites(self):
        sites_file = DATA_DIR / "sites.yaml"
        if sites_file.exists():
            with open(sites_file) as f:
                data = yaml.safe_load(f) or {}
            self._sites = data.get("categories", {})
        if not self._sites:
            self._sites = dict(BUILTIN_SITES)

    async def execute(self, action: str = "browse", topic: Optional[str] = None):
        if not self.session_manager:
            return

        # Pick a category and site
        category = random.choice(list(self._sites.keys()))
        sites = self._sites[category]
        site = self._weighted_pick(sites)
        url = site["url"] if site["url"].startswith("http") else f"https://{site['url']}"

        self.log_activity("browse", f"Visiting {url} ({category})")

        session = await self.session_manager.new_session()
        try:
            success = await session.navigate(url)
            if not success:
                self._error_count += 1
                return

            self._request_count += 1
            self._last_run = time.time()

            # Simulate reading the landing page
            await session.simulate_reading(content_length=3000)

            # Follow internal links (browsing chain)
            depth = random.randint(0, 3)
            for _ in range(depth):
                if random.random() < 0.5:
                    await session.hover_random_element()

                clicked = await session.click_random_link()
                if clicked:
                    self.log_activity("browse", f"Following link: {clicked[:80]}")
                    self._request_count += 1
                    await session.simulate_reading(content_length=random.randint(1000, 8000))
                else:
                    break

            self._bytes_count += session.bytes_transferred

        except Exception:
            self._error_count += 1
        finally:
            await session.close()

    @staticmethod
    def _weighted_pick(sites: list[dict]) -> dict:
        if not sites:
            return {"url": "https://en.wikipedia.org", "weight": 1.0}
        weights = [s.get("weight", 1.0) for s in sites]
        return random.choices(sites, weights=weights, k=1)[0]
