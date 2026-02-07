from __future__ import annotations
"""Realistic browsing behavior simulation.

Generates human-like scroll, pause, mouse movement, and click patterns
to make automated browsing indistinguishable from a real user.
"""

import math
import random
from dataclasses import dataclass

import numpy as np


@dataclass
class ScrollAction:
    """A single scroll movement."""
    delta_y: int       # pixels to scroll
    duration_ms: int   # how long the scroll takes
    pause_after_ms: int  # pause after scrolling


@dataclass
class MouseMove:
    """A mouse movement between two points."""
    target_x: int
    target_y: int
    duration_ms: int
    # Control points for bezier curve (makes movement non-linear)
    curve_intensity: float = 0.3


class BehaviorSimulator:
    """Generates realistic human browsing actions.

    All methods return action descriptors that the session manager
    translates into Playwright calls.
    """

    def __init__(self):
        self._rng = np.random.default_rng()

    def reading_pause(self, content_length: int = 1000) -> float:
        """How long to pause on a page (seconds), based on content length.

        Average reading speed: ~250 words/minute.
        We assume ~5 chars per word, then add noise.
        """
        words = content_length / 5
        # Only "read" 20-80% of the content
        read_fraction = self._rng.uniform(0.2, 0.8)
        words_to_read = words * read_fraction
        # Base time at ~200-300 WPM (variable reader speed)
        wpm = self._rng.uniform(200, 300)
        base_seconds = (words_to_read / wpm) * 60
        # Add scanning/skimming time
        scan_time = self._rng.exponential(3.0)
        return max(2.0, base_seconds + scan_time)

    def scroll_sequence(self, page_height: int, viewport_height: int) -> list[ScrollAction]:
        """Generate a realistic scroll sequence for a page.

        Humans don't scroll at constant speed — they burst-scroll,
        pause to read, sometimes scroll back up, etc.
        """
        scrolls = []
        current_y = 0
        max_scroll = max(0, page_height - viewport_height)

        if max_scroll == 0:
            return scrolls

        # Decide how far down the page to scroll (not always to the bottom)
        target_fraction = self._rng.beta(2, 2)  # Centered around 50%
        target_y = int(max_scroll * target_fraction)

        while current_y < target_y:
            # Scroll amount varies: small reads or big jumps
            if self._rng.random() < 0.7:
                # Normal scroll: 100-400px
                delta = int(self._rng.uniform(100, 400))
            else:
                # Big jump: 500-1500px (skipping content)
                delta = int(self._rng.uniform(500, 1500))

            delta = min(delta, target_y - current_y)
            duration = int(self._rng.uniform(200, 800))

            # Pause after scroll: reading time
            if self._rng.random() < 0.6:
                pause = int(self._rng.exponential(3000))  # ms
                pause = min(pause, 15000)
            else:
                pause = int(self._rng.uniform(200, 800))  # Quick glance

            scrolls.append(ScrollAction(
                delta_y=delta,
                duration_ms=duration,
                pause_after_ms=pause,
            ))
            current_y += delta

            # Occasionally scroll back up slightly
            if self._rng.random() < 0.1 and current_y > 200:
                back = int(self._rng.uniform(50, 200))
                scrolls.append(ScrollAction(
                    delta_y=-back,
                    duration_ms=int(self._rng.uniform(150, 400)),
                    pause_after_ms=int(self._rng.uniform(500, 2000)),
                ))
                current_y -= back

        return scrolls

    def mouse_movement(
        self, from_x: int, from_y: int, to_x: int, to_y: int
    ) -> MouseMove:
        """Generate a natural mouse movement path.

        Real mouse movements follow slightly curved paths, not straight lines.
        Speed varies (fast in middle, slow at start/end = Fitts's law).
        """
        distance = math.sqrt((to_x - from_x) ** 2 + (to_y - from_y) ** 2)
        # Duration based on Fitts's law approximation
        base_duration = 200 + distance * 1.5
        jitter = self._rng.uniform(0.7, 1.3)
        duration = int(base_duration * jitter)

        return MouseMove(
            target_x=to_x,
            target_y=to_y,
            duration_ms=min(duration, 3000),
            curve_intensity=self._rng.uniform(0.1, 0.5),
        )

    def should_click_link(self) -> bool:
        """Decide whether to click an internal link."""
        return self._rng.random() < 0.35

    def should_hover_element(self) -> bool:
        """Decide whether to hover over an element without clicking."""
        return self._rng.random() < 0.15

    def typing_delays(self, text: str) -> list[float]:
        """Generate per-character typing delays in seconds.

        Humans type at ~40-80 WPM with variable inter-key intervals.
        Occasional pauses for thinking, bursts for common words.
        """
        delays = []
        base_delay = self._rng.uniform(0.05, 0.15)  # 50-150ms base

        for i, char in enumerate(text):
            delay = base_delay * self._rng.uniform(0.5, 2.0)

            # Spaces and punctuation cause slight pauses
            if char in " .,!?":
                delay *= self._rng.uniform(1.5, 3.0)

            # Occasional "thinking" pause
            if self._rng.random() < 0.03:
                delay += self._rng.uniform(0.5, 2.0)

            # Typo simulation: occasionally type wrong then correct
            # (represented as negative delay = backspace)
            delays.append(max(0.02, delay))

        return delays
