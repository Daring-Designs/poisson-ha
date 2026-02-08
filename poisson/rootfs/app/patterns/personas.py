from __future__ import annotations
"""Browser persona rotation — user agents, viewports, fingerprints.

Each session gets a randomly selected persona to make traffic appear
to come from different devices/browsers/operating systems.
"""

import logging
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"


@dataclass
class Persona:
    name: str
    user_agent: str
    viewport_width: int
    viewport_height: int
    platform: str
    languages: list[str]
    timezone: Optional[str] = None


class PersonaRotator:
    """Loads personas from YAML and selects them for sessions."""

    def __init__(self, personas_file: Optional[Path] = None):
        self._personas: list[Persona] = []
        self._current: Optional[Persona] = None
        self._real_persona: Optional[Persona] = None
        path = personas_file or DATA_DIR / "personas.yaml"
        self._load(path)

    def _load(self, path: Path):
        if not path.exists():
            logger.warning("Personas file not found: %s — using built-in defaults", path)
            self._personas = self._builtin_defaults()
            return
        with open(path) as f:
            data = yaml.safe_load(f)
        for p in data.get("personas", []):
            vp = p.get("viewport", {})
            self._personas.append(Persona(
                name=p["name"],
                user_agent=p["user_agent"],
                viewport_width=vp.get("width", 1920),
                viewport_height=vp.get("height", 1080),
                platform=p.get("platform", "Win32"),
                languages=p.get("languages", ["en-US", "en"]),
                timezone=p.get("timezone"),
            ))
        logger.info("Loaded %d personas", len(self._personas))

    def set_real_persona(self, persona: Persona):
        """Set the real user's browser persona for fingerprint matching."""
        self._real_persona = persona
        self._current = persona
        logger.info("Captured real browser fingerprint: %s (%dx%d)",
                     persona.user_agent[:60], persona.viewport_width, persona.viewport_height)

    def select(self) -> Persona:
        """Pick a persona for a new session.

        When a real persona is set, use it to match the user's fingerprint.
        Falls back to random selection if no real persona captured yet.
        """
        if self._real_persona:
            self._current = self._real_persona
        else:
            self._current = random.choice(self._personas)
        return self._current

    @property
    def current(self) -> Optional[Persona]:
        return self._current

    @staticmethod
    def _builtin_defaults() -> list[Persona]:
        return [
            Persona(
                name="chrome_windows",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport_width=1920, viewport_height=1080,
                platform="Win32", languages=["en-US", "en"],
            ),
            Persona(
                name="firefox_mac",
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
                viewport_width=1440, viewport_height=900,
                platform="MacIntel", languages=["en-US", "en"],
            ),
            Persona(
                name="chrome_linux",
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport_width=1366, viewport_height=768,
                platform="Linux x86_64", languages=["en-US", "en", "de"],
            ),
            Persona(
                name="safari_mac",
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
                viewport_width=1512, viewport_height=982,
                platform="MacIntel", languages=["en-US", "en"],
            ),
            Persona(
                name="edge_windows",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
                viewport_width=1536, viewport_height=864,
                platform="Win32", languages=["en-US", "en"],
            ),
            Persona(
                name="chrome_android",
                user_agent="Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
                viewport_width=412, viewport_height=915,
                platform="Linux armv81", languages=["en-US", "en"],
            ),
            Persona(
                name="safari_iphone",
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                viewport_width=390, viewport_height=844,
                platform="iPhone", languages=["en-US", "en"],
            ),
        ]
