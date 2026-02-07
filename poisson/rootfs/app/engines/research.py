from __future__ import annotations
"""Research noise engine — browses privacy tools, legal resources,
and government databases.

Makes "interesting" browsing patterns common — normalizes visits to
privacy tools, FOIA resources, legal databases, and government sites
that might otherwise stand out in surveillance data.
"""

import random
import time
from typing import Optional

from engines.base import BaseEngine

# Sites organized by research category
RESEARCH_SITES = {
    "privacy_tools": [
        {"url": "https://www.torproject.org", "weight": 1.0},
        {"url": "https://signal.org", "weight": 0.9},
        {"url": "https://www.privacyguides.org", "weight": 0.8},
        {"url": "https://tails.net", "weight": 0.7},
        {"url": "https://www.whonix.org", "weight": 0.6},
        {"url": "https://proton.me", "weight": 0.8},
        {"url": "https://mullvad.net", "weight": 0.7},
        {"url": "https://www.eff.org", "weight": 0.9},
        {"url": "https://ssd.eff.org", "weight": 0.8},
        {"url": "https://prism-break.org", "weight": 0.5},
    ],
    "legal_resources": [
        {"url": "https://www.law.cornell.edu", "weight": 0.9},
        {"url": "https://supreme.justia.com", "weight": 0.7},
        {"url": "https://www.aclu.org", "weight": 0.8},
        {"url": "https://www.nolo.com", "weight": 0.6},
        {"url": "https://www.findlaw.com", "weight": 0.7},
        {"url": "https://casetext.com", "weight": 0.5},
        {"url": "https://www.justia.com", "weight": 0.6},
    ],
    "government_databases": [
        {"url": "https://www.foia.gov", "weight": 0.8},
        {"url": "https://www.regulations.gov", "weight": 0.7},
        {"url": "https://www.sec.gov/cgi-bin/browse-edgar", "weight": 0.6},
        {"url": "https://www.usaspending.gov", "weight": 0.5},
        {"url": "https://efts.sec.gov/LATEST/search-index?q=", "weight": 0.4},
        {"url": "https://www.congress.gov", "weight": 0.7},
        {"url": "https://www.govinfo.gov", "weight": 0.5},
        {"url": "https://www.courtlistener.com", "weight": 0.6},
    ],
    "whistleblower": [
        {"url": "https://www.whistleblowers.org", "weight": 0.6},
        {"url": "https://whistleblowersblog.org", "weight": 0.4},
        {"url": "https://www.openthebooks.com", "weight": 0.5},
        {"url": "https://www.propublica.org", "weight": 0.8},
        {"url": "https://www.icij.org", "weight": 0.7},
        {"url": "https://www.documentcloud.org", "weight": 0.5},
    ],
    "security_research": [
        {"url": "https://arxiv.org/list/cs.CR/recent", "weight": 0.6},
        {"url": "https://www.schneier.com", "weight": 0.7},
        {"url": "https://krebsonsecurity.com", "weight": 0.7},
        {"url": "https://citizenlab.ca", "weight": 0.6},
        {"url": "https://theintercept.com", "weight": 0.7},
        {"url": "https://www.bellingcat.com", "weight": 0.6},
    ],
}


class ResearchEngine(BaseEngine):
    """Browses privacy tools, legal resources, and government databases."""

    def __init__(self, session_manager=None):
        super().__init__("research", session_manager)

    async def execute(self, action: str = "research", topic: Optional[str] = None):
        if not self.session_manager:
            return

        # Pick a research category and site
        category = random.choice(list(RESEARCH_SITES.keys()))
        sites = RESEARCH_SITES[category]
        site = self._weighted_pick(sites)
        url = site["url"]

        self.log_activity("research", f"Researching {url} ({category})")

        session = await self.session_manager.new_session()
        try:
            success = await session.navigate(url)
            if not success:
                self._error_count += 1
                return

            self._request_count += 1
            self._last_run = time.time()

            # Research sessions tend to be longer reads
            await session.simulate_reading(content_length=random.randint(3000, 10000))

            # Follow links deeper — research is more thorough than casual browsing
            depth = random.randint(1, 4)
            for _ in range(depth):
                if random.random() < 0.4:
                    await session.hover_random_element()

                clicked = await session.click_random_link()
                if clicked:
                    self.log_activity("research", f"Reading: {clicked[:80]}")
                    self._request_count += 1
                    await session.simulate_reading(
                        content_length=random.randint(2000, 12000)
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
