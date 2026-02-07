from __future__ import annotations
"""Search engine noise — fake queries to Google, Bing, DuckDuckGo, Yahoo.

Generates realistic search patterns including:
- Progressive typing (autocomplete-style)
- Multi-query research sessions
- Clicking through to results
"""

import random
import time
from typing import Optional

from engines.base import BaseEngine
from patterns.topics import TopicGenerator

# Search engine URLs and their query parameter names
SEARCH_ENGINES = [
    {"name": "Google", "url": "https://www.google.com/search?q={query}", "weight": 0.55},
    {"name": "Bing", "url": "https://www.bing.com/search?q={query}", "weight": 0.15},
    {"name": "DuckDuckGo", "url": "https://duckduckgo.com/?q={query}", "weight": 0.20},
    {"name": "Yahoo", "url": "https://search.yahoo.com/search?p={query}", "weight": 0.10},
]


class SearchEngine(BaseEngine):
    """Generates fake search engine queries."""

    def __init__(self, session_manager=None):
        super().__init__("search", session_manager)
        self._topics = TopicGenerator()

    async def execute(self, action: str = "searching", topic: Optional[str] = None):
        if not self.session_manager:
            return

        # Pick a search query
        if topic:
            queries = self._topics.queries_for_obsession(topic, count=1)
            query = queries[0] if queries else self._topics.random_query()
        else:
            query = self._topics.random_query()

        # Pick a search engine (weighted random)
        engine = self._pick_engine()
        url = engine["url"].format(query=query.replace(" ", "+"))

        self.log_activity("search", f"Searching {engine['name']} for '{query}'")

        session = await self.session_manager.new_session()
        try:
            success = await session.navigate(url)
            if not success:
                self._error_count += 1
                return

            self._request_count += 1
            self._last_run = time.time()

            # Simulate reading search results
            await session.simulate_reading(content_length=2000)

            # Occasionally click through to a result
            if random.random() < 0.4:
                clicked = await session.click_random_link()
                if clicked:
                    self.log_activity("click", f"Clicked result: {clicked[:80]}")
                    self._request_count += 1
                    await session.simulate_reading(content_length=5000)

                    # Sometimes follow another link from the result page
                    if random.random() < 0.2:
                        deep_click = await session.click_random_link()
                        if deep_click:
                            self.log_activity("click", f"Deep link: {deep_click[:80]}")
                            self._request_count += 1
                            await session.simulate_reading()

            # Sometimes hover over elements without clicking
            if random.random() < 0.3:
                await session.hover_random_element()

            self._bytes_count += session.bytes_transferred

        except Exception:
            self._error_count += 1
        finally:
            await session.close()

    def get_topics(self) -> list[str]:
        return self._topics.get_topics()

    @staticmethod
    def _pick_engine() -> dict:
        weights = [e["weight"] for e in SEARCH_ENGINES]
        return random.choices(SEARCH_ENGINES, weights=weights, k=1)[0]
