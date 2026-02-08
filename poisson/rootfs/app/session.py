from __future__ import annotations
"""Browser session manager — Playwright lifecycle and anti-fingerprinting.

Manages headless Chromium instances with per-session persona rotation,
realistic page interaction, and resource cleanup.
"""

import asyncio
import logging
import os
import random
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from patterns.behavior import BehaviorSimulator, MouseMove, ScrollAction
from patterns.personas import Persona, PersonaRotator

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages browser instances and contexts for noise generation."""

    def __init__(self, config: dict):
        self._config = config
        self._max_concurrent = config.get("max_concurrent_sessions", 2)
        self._personas = PersonaRotator()
        self._behavior = BehaviorSimulator()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._active_contexts: list[BrowserContext] = []
        self._semaphore = asyncio.Semaphore(self._max_concurrent)

    async def start(self):
        """Launch the Playwright browser."""
        self._playwright = await async_playwright().start()
        # Use system Chromium if available (Docker/HA), otherwise let Playwright find its own
        chromium_path = os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium-browser")
        launch_kwargs = dict(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
            ],
        )
        if os.path.isfile(chromium_path):
            launch_kwargs["executable_path"] = chromium_path
        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        logger.info("Browser launched (max %d concurrent sessions)", self._max_concurrent)

    async def stop(self):
        """Shut down all contexts and the browser."""
        for ctx in self._active_contexts:
            try:
                await ctx.close()
            except Exception:
                pass
        self._active_contexts.clear()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser shut down")

    async def new_session(self, proxy: Optional[str] = None) -> "BrowsingSession":
        """Create a new browsing session with a fresh persona.

        Args:
            proxy: Optional proxy server URL (e.g. "socks5://127.0.0.1:9050" for Tor).
        """
        await self._semaphore.acquire()
        persona = self._personas.select()
        context = await self._create_context(persona, proxy=proxy)
        self._active_contexts.append(context)
        page = await context.new_page()
        return BrowsingSession(
            page=page,
            context=context,
            persona=persona,
            behavior=self._behavior,
            manager=self,
        )

    async def release_session(self, session: "BrowsingSession"):
        """Clean up a finished session."""
        try:
            if session.context in self._active_contexts:
                self._active_contexts.remove(session.context)
            await session.context.close()
        except Exception:
            logger.debug("Error closing session context", exc_info=True)
        finally:
            self._semaphore.release()

    async def _create_context(
        self, persona: Persona, proxy: Optional[str] = None
    ) -> BrowserContext:
        """Create a browser context configured with the given persona."""
        ctx_kwargs = dict(
            user_agent=persona.user_agent,
            viewport={"width": persona.viewport_width, "height": persona.viewport_height},
            locale=persona.languages[0] if persona.languages else "en-US",
            timezone_id=persona.timezone or self._random_timezone(),
            extra_http_headers={
                "Accept-Language": ", ".join(persona.languages),
            },
        )
        if proxy:
            ctx_kwargs["proxy"] = {"server": proxy}
        context = await self._browser.new_context(**ctx_kwargs)
        # Block unnecessary resources to save bandwidth
        await context.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf}", lambda route: route.abort())
        return context

    @staticmethod
    def _random_timezone() -> str:
        """Pick a plausible timezone."""
        timezones = [
            "America/New_York", "America/Chicago", "America/Denver",
            "America/Los_Angeles", "America/Phoenix", "America/Anchorage",
            "Europe/London", "Europe/Berlin", "Europe/Paris",
            "Asia/Tokyo", "Asia/Shanghai", "Australia/Sydney",
            "America/Toronto", "America/Sao_Paulo",
        ]
        return random.choice(timezones)


class BrowsingSession:
    """A single browsing session with realistic interaction capabilities."""

    def __init__(
        self,
        page: Page,
        context: BrowserContext,
        persona: Persona,
        behavior: BehaviorSimulator,
        manager: SessionManager,
    ):
        self.page = page
        self.context = context
        self.persona = persona
        self._behavior = behavior
        self._manager = manager
        self._bytes_transferred = 0

    async def navigate(self, url: str, timeout_ms: int = 30000) -> bool:
        """Navigate to a URL, return True on success."""
        # Only allow http/https to prevent file://, javascript:, data: attacks
        if not url.startswith(("http://", "https://")):
            logger.warning("Rejected non-HTTP URL: %s", url[:100])
            return False
        try:
            response = await self.page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            if response:
                self._bytes_transferred += len(await response.body()) if response.ok else 0
            return response is not None and response.ok
        except Exception:
            logger.debug("Navigation failed: %s", url)
            return False

    async def simulate_reading(self, content_length: int = 1000):
        """Simulate a human reading a page — scroll, pause, look around."""
        pause_time = self._behavior.reading_pause(content_length)

        # Get page dimensions
        dimensions = await self.page.evaluate(
            "() => ({height: document.body.scrollHeight, width: window.innerWidth})"
        )
        page_height = dimensions.get("height", 1000)
        viewport_height = self.persona.viewport_height

        # Generate and execute scroll sequence
        scrolls = self._behavior.scroll_sequence(page_height, viewport_height)
        for scroll in scrolls:
            await self._execute_scroll(scroll)

        # Final reading pause
        remaining = max(1.0, pause_time - sum(s.pause_after_ms / 1000 for s in scrolls))
        await asyncio.sleep(remaining)

    async def click_random_link(self) -> Optional[str]:
        """Find and click a random internal link on the page. Returns the URL clicked."""
        try:
            links = await self.page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    return links
                        .filter(a => {
                            const href = a.href;
                            return href.startsWith(window.location.origin)
                                && !href.includes('#')
                                && a.offsetParent !== null;
                        })
                        .map(a => ({href: a.href, x: a.getBoundingClientRect().x, y: a.getBoundingClientRect().y}))
                        .slice(0, 50);
                }
            """)
            if not links:
                return None

            link = random.choice(links)
            # Move mouse to link location first
            await self.page.mouse.move(link["x"] + 5, link["y"] + 5)
            await asyncio.sleep(random.uniform(0.1, 0.5))
            await self.page.mouse.click(link["x"] + 5, link["y"] + 5)
            await self.page.wait_for_load_state("domcontentloaded")
            return link["href"]
        except Exception:
            logger.debug("Failed to click link", exc_info=True)
            return None

    async def type_text(self, selector: str, text: str):
        """Type text with human-like delays."""
        delays = self._behavior.typing_delays(text)
        try:
            await self.page.click(selector)
            for char, delay in zip(text, delays):
                await self.page.keyboard.type(char, delay=int(delay * 1000))
        except Exception:
            logger.debug("Failed to type into %s", selector)

    async def hover_random_element(self):
        """Move mouse over a random visible element without clicking."""
        try:
            pos = await self.page.evaluate("""
                () => {
                    const els = document.querySelectorAll('a, button, img, h2, h3');
                    const visible = Array.from(els).filter(e => e.offsetParent !== null);
                    if (!visible.length) return null;
                    const el = visible[Math.floor(Math.random() * visible.length)];
                    const rect = el.getBoundingClientRect();
                    return {x: rect.x + rect.width/2, y: rect.y + rect.height/2};
                }
            """)
            if pos:
                await self.page.mouse.move(pos["x"], pos["y"])
                await asyncio.sleep(random.uniform(0.3, 1.5))
        except Exception:
            pass

    async def close(self):
        """End this session and release resources."""
        await self._manager.release_session(self)

    @property
    def bytes_transferred(self) -> int:
        return self._bytes_transferred

    async def _execute_scroll(self, scroll: ScrollAction):
        """Execute a single scroll action."""
        await self.page.mouse.wheel(0, scroll.delta_y)
        await asyncio.sleep(scroll.pause_after_ms / 1000)
