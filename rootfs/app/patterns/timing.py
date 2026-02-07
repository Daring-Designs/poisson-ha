from __future__ import annotations
"""Poisson distribution timing engine with Markov chain session modeling.

This is the core of the noise generator. It must produce timing patterns
indistinguishable from real human browsing behavior:

- Poisson process for event timing (bursty with quiet gaps)
- Variable rate parameter (λ) that shifts throughout the day
- Weekly drift to avoid periodic fingerprinting
- "Obsession" mode for realistic deep-dive patterns
- Markov chain for intra-session page transitions
"""

import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np


class Intensity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PARANOID = "paranoid"


# Base lambda (events per minute) for each intensity level
INTENSITY_LAMBDA = {
    Intensity.LOW: 0.3,       # ~18 events/hour
    Intensity.MEDIUM: 1.0,    # ~60 events/hour
    Intensity.HIGH: 2.5,      # ~150 events/hour
    Intensity.PARANOID: 5.0,  # ~300 events/hour
}

# Hourly activity weights (0-23). Models a realistic human day:
# Low activity at night, peaks mid-morning and evening, dips at lunch.
# Non-zero at all hours — real humans do browse at 3am.
DEFAULT_HOURLY_WEIGHTS = [
    0.05, 0.03, 0.02, 0.02, 0.03, 0.05,  # 00-05: late night / early morning
    0.10, 0.25, 0.50, 0.80, 0.90, 0.85,  # 06-11: wake up → peak morning
    0.60, 0.70, 0.80, 0.85, 0.75, 0.65,  # 12-17: lunch dip → afternoon
    0.70, 0.80, 0.90, 0.75, 0.40, 0.15,  # 18-23: evening peak → wind down
]


@dataclass
class SessionConfig:
    """Configuration for a browsing session."""
    mean_duration_minutes: float = 15.0
    min_duration_minutes: float = 0.5
    max_duration_minutes: float = 180.0
    mean_pages_per_session: int = 8
    obsession_probability: float = 0.05
    obsession_duration_hours: tuple = (2.0, 48.0)


@dataclass
class TimingState:
    """Mutable state for the timing engine, persisted across restarts."""
    weekly_phase_offset: float = 0.0
    current_obsession_topic: Optional[str] = None
    obsession_start_time: Optional[float] = None
    obsession_end_time: Optional[float] = None
    session_count_today: int = 0
    last_session_end: float = 0.0
    drift_seed: int = field(default_factory=lambda: random.randint(0, 2**31))


class PoissonTimer:
    """Generates inter-event delays using a Poisson process with time-varying rate.

    The rate parameter λ varies by:
    - Time of day (hourly weights)
    - Day of week (weekday vs. weekend)
    - Weekly drift (slow phase shift to avoid periodicity)
    - Random jitter per interval
    """

    def __init__(
        self,
        intensity: Intensity = Intensity.MEDIUM,
        hourly_weights: Optional[list[float]] = None,
        session_config: Optional[SessionConfig] = None,
    ):
        self.intensity = intensity
        self.base_lambda = INTENSITY_LAMBDA[intensity]
        self.hourly_weights = hourly_weights or list(DEFAULT_HOURLY_WEIGHTS)
        self.session_config = session_config or SessionConfig()
        self.state = TimingState()
        self._rng = np.random.default_rng()

    def _current_lambda(self, timestamp: Optional[float] = None) -> float:
        """Compute the current Poisson rate parameter.

        Combines base intensity, hourly weight, day-of-week factor,
        and weekly drift into a single λ value.
        """
        ts = timestamp or time.time()
        lt = time.localtime(ts)
        hour = lt.tm_hour
        minute = lt.tm_min
        wday = lt.tm_wday  # 0=Monday, 6=Sunday

        # Interpolate between current and next hour for smooth transitions
        current_weight = self.hourly_weights[hour]
        next_weight = self.hourly_weights[(hour + 1) % 24]
        hour_frac = minute / 60.0
        interpolated_weight = current_weight * (1 - hour_frac) + next_weight * hour_frac

        # Weekend factor: slightly different pattern (more late morning, more evening)
        weekend_factor = 1.0
        if wday >= 5:  # Saturday, Sunday
            weekend_factor = 0.9 + 0.2 * math.sin(math.pi * hour / 12)

        # Weekly drift: slow sinusoidal offset to break periodicity
        # The phase shifts over weeks so the same hour on different weeks
        # produces different λ values.
        weeks_elapsed = ts / (7 * 86400)
        drift = 0.15 * math.sin(2 * math.pi * weeks_elapsed + self.state.drift_seed)

        # Per-interval jitter (±20%) to prevent pattern detection
        jitter = 1.0 + self._rng.uniform(-0.20, 0.20)

        lam = self.base_lambda * interpolated_weight * weekend_factor * (1 + drift) * jitter
        return max(lam, 0.005)  # Floor: never truly zero

    def next_event_delay(self, timestamp: Optional[float] = None) -> float:
        """Sample the next inter-event delay in seconds.

        Uses inverse transform sampling from the exponential distribution
        (which is the inter-arrival distribution for a Poisson process).
        """
        lam = self._current_lambda(timestamp)
        # Exponential variate: delay = -ln(U) / λ, where U ~ Uniform(0,1)
        delay_minutes = self._rng.exponential(1.0 / lam)
        delay_seconds = delay_minutes * 60.0

        # Clamp to reasonable bounds
        min_delay = 2.0      # Never faster than 2 seconds
        max_delay = 3600.0   # Never longer than 1 hour gap
        return float(np.clip(delay_seconds, min_delay, max_delay))

    def next_session_duration(self) -> float:
        """Sample session duration in seconds using a log-normal distribution.

        Log-normal models human session length well: most sessions are short,
        but a fat tail produces occasional long sessions.
        """
        cfg = self.session_config
        # Log-normal parameters from desired mean
        mu = math.log(cfg.mean_duration_minutes)
        sigma = 0.8  # Controls spread — higher = more variance
        duration_minutes = self._rng.lognormal(mu, sigma)
        duration_minutes = float(np.clip(
            duration_minutes,
            cfg.min_duration_minutes,
            cfg.max_duration_minutes,
        ))
        return duration_minutes * 60.0

    def next_inter_session_gap(self) -> float:
        """Sample gap between sessions in seconds.

        Uses exponential distribution (memoryless waiting).
        Mean gap scales inversely with intensity.
        """
        mean_gap_minutes = {
            Intensity.LOW: 45.0,
            Intensity.MEDIUM: 20.0,
            Intensity.HIGH: 8.0,
            Intensity.PARANOID: 3.0,
        }[self.intensity]

        # Add time-of-day factor — longer gaps at night
        hour = time.localtime().tm_hour
        night_factor = 1.0
        if 0 <= hour < 6:
            night_factor = 3.0
        elif 23 <= hour or hour < 1:
            night_factor = 2.0

        gap = self._rng.exponential(mean_gap_minutes * night_factor) * 60.0
        return float(np.clip(gap, 10.0, 7200.0))  # 10s to 2h


class MarkovSessionChain:
    """Markov chain for modeling intra-session page transitions.

    Models browsing behavior as transitions between states:
    - landing: initial page load
    - reading: consuming content on current page
    - clicking: following an internal link
    - searching: performing a new search
    - idle: brief pause / tabbed away
    - leaving: session end

    Transition probabilities shift based on time spent in session
    (people are more likely to leave as sessions get longer).
    """

    STATES = ["landing", "reading", "clicking", "searching", "idle", "leaving"]

    # Base transition matrix (row = from state, col = to state)
    # Order: landing, reading, clicking, searching, idle, leaving
    BASE_TRANSITIONS = np.array([
        # landing →
        [0.00, 0.60, 0.20, 0.10, 0.05, 0.05],
        # reading →
        [0.00, 0.15, 0.40, 0.15, 0.15, 0.15],
        # clicking →
        [0.00, 0.55, 0.15, 0.10, 0.10, 0.10],
        # searching →
        [0.00, 0.50, 0.25, 0.05, 0.10, 0.10],
        # idle →
        [0.00, 0.30, 0.15, 0.10, 0.10, 0.35],
        # leaving → absorbing state
        [0.00, 0.00, 0.00, 0.00, 0.00, 1.00],
    ])

    def __init__(self):
        self._rng = np.random.default_rng()
        self._current_state = "landing"
        self._steps = 0

    def reset(self):
        """Start a new session."""
        self._current_state = "landing"
        self._steps = 0

    @property
    def current_state(self) -> str:
        return self._current_state

    @property
    def is_done(self) -> bool:
        return self._current_state == "leaving"

    def step(self) -> str:
        """Advance one step in the Markov chain. Returns the new state."""
        state_idx = self.STATES.index(self._current_state)
        probs = self.BASE_TRANSITIONS[state_idx].copy()

        # Fatigue factor: increase leaving probability over time
        fatigue = min(0.4, self._steps * 0.03)
        leaving_idx = self.STATES.index("leaving")
        probs[leaving_idx] += fatigue
        # Re-normalize
        probs = probs / probs.sum()

        next_idx = self._rng.choice(len(self.STATES), p=probs)
        self._current_state = self.STATES[next_idx]
        self._steps += 1
        return self._current_state

    def state_duration(self) -> float:
        """Sample how long to stay in the current state (seconds).

        Different states have different dwell time distributions.
        """
        durations = {
            "landing": (2.0, 5.0),       # Quick page load
            "reading": (8.0, 120.0),      # Actually reading content
            "clicking": (0.5, 3.0),       # Click + page load
            "searching": (3.0, 15.0),     # Type query + submit
            "idle": (5.0, 60.0),          # Tabbed away / thinking
            "leaving": (0.0, 0.0),
        }
        lo, hi = durations[self._current_state]
        if hi == 0:
            return 0.0
        # Use beta distribution for more realistic shape (clustered toward lower end)
        return float(lo + (hi - lo) * self._rng.beta(2, 5))


class ObsessionTracker:
    """Tracks "obsession" deep-dive patterns.

    Occasionally, the generator fixates on a single topic for hours or days,
    mimicking how real humans fall down rabbit holes.
    """

    def __init__(self, probability: float = 0.05, duration_range_hours: tuple = (2.0, 48.0)):
        self.probability = probability
        self.duration_range = duration_range_hours
        self._rng = np.random.default_rng()
        self.active_topic: Optional[str] = None
        self.end_time: Optional[float] = None

    @property
    def is_active(self) -> bool:
        if self.active_topic is None:
            return False
        if time.time() > self.end_time:
            self.active_topic = None
            self.end_time = None
            return False
        return True

    def maybe_start(self, available_topics: list[str]) -> Optional[str]:
        """Roll the dice on starting a new obsession. Returns topic if started."""
        if self.is_active:
            return self.active_topic

        if self._rng.random() < self.probability:
            self.active_topic = self._rng.choice(available_topics)
            duration_hours = self._rng.uniform(*self.duration_range)
            self.end_time = time.time() + duration_hours * 3600
            return self.active_topic
        return None

    def get_topic(self) -> Optional[str]:
        """Return current obsession topic, or None."""
        if self.is_active:
            return self.active_topic
        return None
