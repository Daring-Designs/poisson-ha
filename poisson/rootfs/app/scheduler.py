from __future__ import annotations
"""Poisson scheduler — orchestrates timing across all engines.

The scheduler owns the timing engine and decides when to dispatch
events to which engines, managing sessions and inter-session gaps.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from patterns.timing import (
    Intensity,
    MarkovSessionChain,
    ObsessionTracker,
    PoissonTimer,
    SessionConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class SchedulerStats:
    """Runtime statistics exposed to the API."""
    sessions_today: int = 0
    requests_today: int = 0
    bytes_today: int = 0
    start_time: float = field(default_factory=time.time)
    last_event_time: Optional[float] = None
    active_sessions: int = 0


class Scheduler:
    """Coordinates timing and dispatches work to engines.

    Lifecycle:
    1. Wait for inter-session gap
    2. Start a new session (pick persona, choose engines)
    3. Run Markov chain within the session, dispatching actions to engines
    4. End session, loop back to 1
    """

    def __init__(self, config: dict):
        intensity = Intensity(config.get("intensity", "medium"))
        session_cfg = SessionConfig(
            mean_duration_minutes=config.get("session_length_mean", 15.0),
            obsession_probability=config.get("obsession_probability", 0.05),
        )
        self.timer = PoissonTimer(intensity=intensity, session_config=session_cfg)
        self.chain = MarkovSessionChain()
        self.obsession = ObsessionTracker(
            probability=session_cfg.obsession_probability,
        )
        self.stats = SchedulerStats()
        self._engines = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register_engine(self, name: str, engine):
        """Register a traffic engine by name."""
        self._engines[name] = engine
        logger.info("Registered engine: %s", name)

    async def start(self):
        """Start the scheduler loop."""
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Scheduler started")

    async def stop(self):
        """Stop the scheduler gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _run_loop(self):
        """Main scheduling loop."""
        while self._running:
            try:
                # Inter-session gap
                gap = self.timer.next_inter_session_gap()
                logger.info("Next session in %.1f seconds", gap)
                await asyncio.sleep(gap)

                if not self._running:
                    break

                # Start a session
                await self._run_session()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in scheduler loop")
                await asyncio.sleep(30)

    async def _run_session(self):
        """Run a single browsing session using the Markov chain."""
        self.chain.reset()
        session_duration = self.timer.next_session_duration()
        session_start = time.time()
        self.stats.sessions_today += 1
        self.stats.active_sessions += 1

        # Check for obsession topic
        available_topics = self._get_available_topics()
        obsession_topic = self.obsession.maybe_start(available_topics)
        if obsession_topic:
            logger.info("Obsession mode: deep-diving on '%s'", obsession_topic)

        logger.info(
            "Starting session #%d (planned duration: %.0fs)",
            self.stats.sessions_today,
            session_duration,
        )

        try:
            while not self.chain.is_done and self._running:
                elapsed = time.time() - session_start
                if elapsed >= session_duration:
                    logger.debug("Session duration exceeded, ending")
                    break

                state = self.chain.step()
                dwell = self.chain.state_duration()

                if state == "leaving":
                    break

                # Dispatch to an appropriate engine based on state
                await self._dispatch_action(state, obsession_topic)
                self.stats.requests_today += 1
                self.stats.last_event_time = time.time()

                # Wait for the dwell time + Poisson jitter
                event_delay = self.timer.next_event_delay()
                total_wait = dwell + event_delay * 0.3  # Blend dwell with Poisson
                await asyncio.sleep(total_wait)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error during session")
        finally:
            self.stats.active_sessions -= 1
            logger.info(
                "Session #%d ended (%.0fs actual)",
                self.stats.sessions_today,
                time.time() - session_start,
            )

    async def _dispatch_action(self, state: str, obsession_topic: Optional[str] = None):
        """Route a Markov chain state to the appropriate engine."""
        if not self._engines:
            return

        # Map chain states to engine preferences
        state_engine_map = {
            "reading": ["browse", "search"],
            "clicking": ["browse", "search"],
            "searching": ["search", "browse"],
            "idle": ["dns"],
            "landing": ["browse", "search", "dns"],
        }

        preferred = state_engine_map.get(state, ["browse"])
        for engine_name in preferred:
            if engine_name in self._engines:
                engine = self._engines[engine_name]
                try:
                    await engine.execute(
                        action=state,
                        topic=obsession_topic,
                    )
                except Exception:
                    logger.exception("Engine '%s' failed on action '%s'", engine_name, state)
                break

    def _get_available_topics(self) -> list[str]:
        """Collect available topics from registered engines."""
        topics = []
        for engine in self._engines.values():
            if hasattr(engine, "get_topics"):
                topics.extend(engine.get_topics())
        if not topics:
            topics = [
                "hiking gear", "machine learning", "sourdough baking",
                "home automation", "vintage cameras", "electric vehicles",
                "cryptocurrency", "gardening", "3d printing",
                "immigration law", "cybersecurity", "astronomy",
            ]
        return topics

    def get_stats(self) -> dict:
        """Return current stats as a dict for the API."""
        return {
            "sessions_today": self.stats.sessions_today,
            "requests_today": self.stats.requests_today,
            "bandwidth_today_mb": round(self.stats.bytes_today / (1024 * 1024), 2),
            "uptime_seconds": int(time.time() - self.stats.start_time),
            "active_sessions": self.stats.active_sessions,
            "last_event_time": self.stats.last_event_time,
        }
