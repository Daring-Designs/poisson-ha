from __future__ import annotations
"""Ad click engine — pollutes ad tracking profiles.

Visits pages known to have heavy ad presence, finds and clicks
ad-like elements to generate noise in ad network tracking data.
"""

import random
import time
from typing import Optional

from engines.base import BaseEngine

# Sites with heavy ad presence across different verticals
AD_HEAVY_SITES = [
    {"url": "https://www.weather.com", "weight": 1.0},
    {"url": "https://www.allrecipes.com", "weight": 0.8},
    {"url": "https://www.dictionary.com", "weight": 0.7},
    {"url": "https://www.merriam-webster.com", "weight": 0.6},
    {"url": "https://www.thesaurus.com", "weight": 0.5},
    {"url": "https://www.investopedia.com", "weight": 0.8},
    {"url": "https://www.healthline.com", "weight": 0.7},
    {"url": "https://www.webmd.com", "weight": 0.7},
    {"url": "https://www.about.com", "weight": 0.5},
    {"url": "https://www.howstuffworks.com", "weight": 0.6},
    {"url": "https://www.cnet.com", "weight": 0.7},
    {"url": "https://www.tomsguide.com", "weight": 0.6},
    {"url": "https://www.pcmag.com", "weight": 0.6},
    {"url": "https://www.foodnetwork.com", "weight": 0.5},
    {"url": "https://www.people.com", "weight": 0.5},
    {"url": "https://www.usmagazine.com", "weight": 0.4},
    {"url": "https://www.tmz.com", "weight": 0.4},
    {"url": "https://www.buzzfeed.com", "weight": 0.5},
    {"url": "https://www.msn.com", "weight": 0.6},
    {"url": "https://www.huffpost.com", "weight": 0.6},
]

# JS to find ad-like elements (iframes, sponsored links, ad containers)
FIND_ADS_JS = """
() => {
    const candidates = [];

    // Ad iframes
    document.querySelectorAll('iframe').forEach(f => {
        const src = (f.src || '').toLowerCase();
        if (src.includes('ad') || src.includes('doubleclick') ||
            src.includes('googlesyndication') || src.includes('amazon-adsystem')) {
            const r = f.getBoundingClientRect();
            if (r.width > 50 && r.height > 50 && r.top > 0)
                candidates.push({x: r.x + r.width/2, y: r.y + r.height/2, type: 'iframe'});
        }
    });

    // Sponsored / ad links
    document.querySelectorAll('a').forEach(a => {
        const text = (a.textContent || '').toLowerCase();
        const href = (a.href || '').toLowerCase();
        const cls = (a.className || '').toLowerCase();
        if ((text.includes('sponsor') || text.includes('promoted') ||
             cls.includes('ad') || href.includes('click') ||
             href.includes('track') || href.includes('redirect')) &&
            a.offsetParent !== null) {
            const r = a.getBoundingClientRect();
            if (r.width > 20 && r.height > 10 && r.top > 0)
                candidates.push({x: r.x + r.width/2, y: r.y + r.height/2, type: 'link',
                                 href: a.href.substring(0, 100)});
        }
    });

    // Elements with ad-related class/id names
    document.querySelectorAll('[class*="ad-"], [class*="advert"], [id*="ad-"], [id*="advert"]').forEach(el => {
        const links = el.querySelectorAll('a');
        links.forEach(a => {
            if (a.offsetParent !== null) {
                const r = a.getBoundingClientRect();
                if (r.width > 20 && r.height > 10 && r.top > 0)
                    candidates.push({x: r.x + r.width/2, y: r.y + r.height/2, type: 'ad-container',
                                     href: (a.href || '').substring(0, 100)});
            }
        });
    });

    return candidates.slice(0, 20);
}
"""


class AdClickEngine(BaseEngine):
    """Clicks ads to pollute ad tracking profiles."""

    def __init__(self, session_manager=None):
        super().__init__("ad_clicks", session_manager)

    async def execute(self, action: str = "ad_click", topic: Optional[str] = None):
        if not self.session_manager:
            return

        site = self._weighted_pick(AD_HEAVY_SITES)
        url = site["url"]

        self.log_activity("ad_click", f"Visiting {url} for ad interaction")

        session = await self.session_manager.new_session()
        try:
            success = await session.navigate(url)
            if not success:
                self._error_count += 1
                return

            self._request_count += 1
            self._last_run = time.time()

            # Read the page briefly first (looks more natural)
            await session.simulate_reading(content_length=1500)

            # Find ad elements
            ads = await session.page.evaluate(FIND_ADS_JS)

            if ads:
                # Click 1-2 ads
                click_count = min(random.randint(1, 2), len(ads))
                targets = random.sample(ads, click_count)

                for ad in targets:
                    try:
                        await session.page.mouse.move(ad["x"], ad["y"])
                        await session.page.mouse.click(ad["x"], ad["y"])
                        self.log_activity("ad_click",
                                          f"Clicked {ad['type']} ad" +
                                          (f": {ad.get('href', '')[:60]}" if ad.get("href") else ""))
                        self._request_count += 1

                        # Brief pause on the ad landing page
                        await session.simulate_reading(content_length=800)

                        # Go back to find more ads
                        if click_count > 1:
                            await session.page.go_back()
                    except Exception:
                        pass
            else:
                # No ads found, just browse normally
                self.log_activity("ad_click", f"No ads found on {url}, browsing instead")
                clicked = await session.click_random_link()
                if clicked:
                    self._request_count += 1

            self._bytes_count += session.bytes_transferred

        except Exception:
            self._error_count += 1
        finally:
            await session.close()

    @staticmethod
    def _weighted_pick(sites: list[dict]) -> dict:
        weights = [s.get("weight", 1.0) for s in sites]
        return random.choices(sites, weights=weights, k=1)[0]
