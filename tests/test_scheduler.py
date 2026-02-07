"""Tests for the Poisson scheduler and timing engine."""

import time

import numpy as np
import pytest

# Add app to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "poisson" / "rootfs" / "app"))

from patterns.timing import (
    Intensity,
    MarkovSessionChain,
    ObsessionTracker,
    PoissonTimer,
    SessionConfig,
)
from scheduler import Scheduler


class TestPoissonTimer:
    def test_next_event_delay_is_positive(self):
        timer = PoissonTimer(intensity=Intensity.MEDIUM)
        for _ in range(100):
            delay = timer.next_event_delay()
            assert delay >= 2.0, f"Delay {delay} is below minimum"
            assert delay <= 3600.0, f"Delay {delay} exceeds maximum"

    def test_intensity_affects_rate(self):
        """Higher intensity should produce shorter average delays."""
        low = PoissonTimer(intensity=Intensity.LOW)
        high = PoissonTimer(intensity=Intensity.HIGH)

        ts = time.time()
        low_delays = [low.next_event_delay(ts) for _ in range(500)]
        high_delays = [high.next_event_delay(ts) for _ in range(500)]

        assert np.mean(low_delays) > np.mean(high_delays), (
            f"Low intensity mean ({np.mean(low_delays):.1f}) should be > "
            f"high intensity mean ({np.mean(high_delays):.1f})"
        )

    def test_hourly_weight_affects_lambda(self):
        """Lambda should be higher during peak hours than at night."""
        timer = PoissonTimer(intensity=Intensity.MEDIUM)

        # Create timestamps for 10am (peak) and 3am (trough) in LOCAL time.
        # _current_lambda uses time.localtime(), so we need mktime (local), not timegm (UTC).
        import time as _time
        from datetime import datetime

        peak = datetime(2025, 1, 15, 10, 0, 0)
        trough = datetime(2025, 1, 15, 3, 0, 0)

        peak_ts = _time.mktime(peak.timetuple())
        trough_ts = _time.mktime(trough.timetuple())

        peak_lambdas = [timer._current_lambda(peak_ts) for _ in range(100)]
        trough_lambdas = [timer._current_lambda(trough_ts) for _ in range(100)]

        assert np.mean(peak_lambdas) > np.mean(trough_lambdas)

    def test_session_duration_positive(self):
        timer = PoissonTimer()
        for _ in range(100):
            duration = timer.next_session_duration()
            assert duration >= 30.0   # min 0.5 minutes
            assert duration <= 10800.0  # max 180 minutes

    def test_inter_session_gap_bounded(self):
        timer = PoissonTimer()
        for _ in range(100):
            gap = timer.next_inter_session_gap()
            assert gap >= 10.0
            assert gap <= 7200.0


class TestMarkovSessionChain:
    def test_starts_at_landing(self):
        chain = MarkovSessionChain()
        assert chain.current_state == "landing"

    def test_eventually_leaves(self):
        """The chain should always reach the 'leaving' state eventually."""
        chain = MarkovSessionChain()
        for _ in range(200):
            chain.step()
            if chain.is_done:
                break
        assert chain.is_done, "Chain did not reach 'leaving' in 200 steps"

    def test_reset(self):
        chain = MarkovSessionChain()
        chain.step()
        chain.step()
        chain.reset()
        assert chain.current_state == "landing"
        assert not chain.is_done

    def test_state_duration_positive(self):
        chain = MarkovSessionChain()
        for state in ["landing", "reading", "clicking", "searching", "idle"]:
            chain._current_state = state
            duration = chain.state_duration()
            assert duration >= 0.0

    def test_leaving_duration_is_zero(self):
        chain = MarkovSessionChain()
        chain._current_state = "leaving"
        assert chain.state_duration() == 0.0

    def test_fatigue_increases_leaving_probability(self):
        """After many steps, leaving should become more likely."""
        chains = [MarkovSessionChain() for _ in range(100)]
        early_leave = 0
        late_leave = 0

        for chain in chains:
            # Run 3 steps and check if leaving
            chain.reset()
            for _ in range(3):
                chain.step()
            if chain.is_done:
                early_leave += 1

        for chain in chains:
            # Run 20 more steps
            chain.reset()
            for _ in range(20):
                if chain.is_done:
                    break
                chain.step()
            if chain.is_done:
                late_leave += 1

        # More chains should have left by step 20 than step 3
        assert late_leave >= early_leave


class TestObsessionTracker:
    def test_not_active_by_default(self):
        tracker = ObsessionTracker(probability=0.0)
        assert not tracker.is_active
        assert tracker.get_topic() is None

    def test_always_starts_with_high_probability(self):
        tracker = ObsessionTracker(probability=1.0, duration_range_hours=(1.0, 2.0))
        topic = tracker.maybe_start(["topic_a", "topic_b"])
        assert topic is not None
        assert tracker.is_active
        assert tracker.get_topic() in ["topic_a", "topic_b"]

    def test_never_starts_with_zero_probability(self):
        tracker = ObsessionTracker(probability=0.0)
        for _ in range(100):
            result = tracker.maybe_start(["test"])
            assert result is None


class TestScheduler:
    def test_register_engine(self):
        sched = Scheduler({"intensity": "low"})

        class FakeEngine:
            enabled = True
            def get_topics(self):
                return ["fake"]

        sched.register_engine("fake", FakeEngine())
        assert "fake" in sched._engines

    def test_get_stats(self):
        sched = Scheduler({"intensity": "medium"})
        stats = sched.get_stats()
        assert "sessions_today" in stats
        assert "requests_today" in stats
        assert stats["sessions_today"] == 0
