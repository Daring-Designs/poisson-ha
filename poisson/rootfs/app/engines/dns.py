from __future__ import annotations
"""DNS noise generator — pollutes DNS query logs.

ISPs sell DNS query data to data brokers. This engine resolves
random domains to create noise in those logs.

Lightweight: no browser needed, runs independently of other engines.
"""

import asyncio
import logging
import random
import socket
import time
from typing import Optional

from engines.base import BaseEngine

logger = logging.getLogger(__name__)

# Domains to resolve across various categories.
# Mix of benign and "interesting" to create noise.
DNS_DOMAINS = {
    "news": [
        "cnn.com", "foxnews.com", "bbc.co.uk", "aljazeera.com",
        "reuters.com", "apnews.com", "rt.com", "dw.com",
        "nytimes.com", "washingtonpost.com", "theguardian.com",
    ],
    "shopping": [
        "amazon.com", "ebay.com", "etsy.com", "walmart.com",
        "aliexpress.com", "wish.com", "target.com", "bestbuy.com",
    ],
    "privacy": [
        "torproject.org", "signal.org", "protonmail.com", "tutanota.com",
        "privacytools.io", "tails.net", "whonix.org",
        "mullvad.net", "nordvpn.com", "expressvpn.com",
    ],
    "crypto": [
        "blockchain.com", "coinbase.com", "binance.com",
        "etherscan.io", "coingecko.com",
    ],
    "government": [
        "foia.gov", "pacer.uscourts.gov", "sec.gov",
        "usaspending.gov", "regulations.gov", "congress.gov",
    ],
    "tech": [
        "github.com", "stackoverflow.com", "hackernews.com",
        "arxiv.org", "medium.com", "dev.to",
    ],
    "social": [
        "reddit.com", "twitter.com", "facebook.com", "instagram.com",
        "mastodon.social", "discord.com", "linkedin.com",
    ],
    "vpn_tools": [
        "openvpn.net", "wireguard.com", "shadowsocks.org",
        "getlantern.org", "psiphon.ca",
    ],
    "foreign": [
        "yandex.ru", "baidu.com", "weibo.com", "naver.com",
        "mail.ru", "vk.com", "qq.com",
    ],
    "health": [
        "webmd.com", "mayoclinic.org", "nih.gov",
        "healthline.com", "medlineplus.gov",
    ],
}

# DNS resolvers to use (rotate to avoid all queries going to one place)
DNS_RESOLVERS = [
    "1.1.1.1",        # Cloudflare
    "8.8.8.8",        # Google
    "9.9.9.9",        # Quad9
    "208.67.222.222",  # OpenDNS
    "94.140.14.14",    # AdGuard
]


class DNSEngine(BaseEngine):
    """Generates DNS query noise without using a browser."""

    def __init__(self, session_manager=None):
        super().__init__("dns", session_manager=None)  # No browser needed

    async def execute(self, action: str = "resolve", topic: Optional[str] = None):
        # Pick a random category and domain
        category = random.choice(list(DNS_DOMAINS.keys()))
        domain = random.choice(DNS_DOMAINS[category])

        self.log_activity("dns", f"Resolving {domain} ({category})")

        try:
            # Run DNS resolution in a thread to avoid blocking
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._resolve, domain)
            self._request_count += 1
            self._last_run = time.time()
        except Exception:
            self._error_count += 1
            logger.debug("DNS resolution failed for %s", domain)

        # Occasionally do a burst of related resolutions
        if random.random() < 0.15:
            burst_count = random.randint(2, 5)
            burst_domains = random.sample(DNS_DOMAINS[category], min(burst_count, len(DNS_DOMAINS[category])))
            for d in burst_domains:
                try:
                    await loop.run_in_executor(None, self._resolve, d)
                    self._request_count += 1
                    self.log_activity("dns", f"Burst resolve: {d}")
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(0.1, 1.0))

    @staticmethod
    def _resolve(domain: str):
        """Perform a DNS lookup. The resolution itself creates the noise."""
        socket.getaddrinfo(domain, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
