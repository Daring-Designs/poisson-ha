"""Tests for the patterns module — personas, behavior, topics."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "rootfs" / "app"))

from patterns.behavior import BehaviorSimulator
from patterns.personas import PersonaRotator
from patterns.topics import TopicGenerator


class TestPersonaRotator:
    def test_builtin_defaults_exist(self):
        rotator = PersonaRotator(personas_file=Path("/nonexistent"))
        assert len(rotator._personas) >= 5

    def test_select_returns_persona(self):
        rotator = PersonaRotator(personas_file=Path("/nonexistent"))
        persona = rotator.select()
        assert persona.name
        assert persona.user_agent
        assert persona.viewport_width > 0
        assert persona.viewport_height > 0

    def test_current_tracks_selection(self):
        rotator = PersonaRotator(personas_file=Path("/nonexistent"))
        assert rotator.current is None
        p = rotator.select()
        assert rotator.current is p

    def test_loads_from_yaml(self):
        personas_file = Path(__file__).parent.parent / "rootfs" / "app" / "data" / "personas.yaml"
        if personas_file.exists():
            rotator = PersonaRotator(personas_file=personas_file)
            assert len(rotator._personas) >= 10


class TestBehaviorSimulator:
    def test_reading_pause_positive(self):
        sim = BehaviorSimulator()
        for length in [100, 1000, 10000, 50000]:
            pause = sim.reading_pause(length)
            assert pause >= 2.0

    def test_reading_pause_scales_with_content(self):
        sim = BehaviorSimulator()
        short_pauses = [sim.reading_pause(100) for _ in range(50)]
        long_pauses = [sim.reading_pause(50000) for _ in range(50)]
        import numpy as np
        assert np.mean(long_pauses) > np.mean(short_pauses)

    def test_scroll_sequence_empty_for_short_page(self):
        sim = BehaviorSimulator()
        scrolls = sim.scroll_sequence(page_height=500, viewport_height=1080)
        assert len(scrolls) == 0

    def test_scroll_sequence_nonempty_for_long_page(self):
        sim = BehaviorSimulator()
        # Run multiple times since it's stochastic
        has_scrolls = False
        for _ in range(10):
            scrolls = sim.scroll_sequence(page_height=5000, viewport_height=1080)
            if len(scrolls) > 0:
                has_scrolls = True
                break
        assert has_scrolls

    def test_mouse_movement_has_duration(self):
        sim = BehaviorSimulator()
        move = sim.mouse_movement(0, 0, 500, 300)
        assert move.duration_ms > 0
        assert move.target_x == 500
        assert move.target_y == 300

    def test_typing_delays_match_text_length(self):
        sim = BehaviorSimulator()
        text = "hello world"
        delays = sim.typing_delays(text)
        assert len(delays) == len(text)
        assert all(d > 0 for d in delays)


class TestTopicGenerator:
    def test_builtin_topics_exist(self):
        gen = TopicGenerator(wordlists_dir=Path("/nonexistent"))
        topics = gen.get_topics()
        assert len(topics) > 50

    def test_random_query_returns_string(self):
        gen = TopicGenerator(wordlists_dir=Path("/nonexistent"))
        q = gen.random_query()
        assert isinstance(q, str)
        assert len(q) > 0

    def test_random_category(self):
        gen = TopicGenerator(wordlists_dir=Path("/nonexistent"))
        cat = gen.random_category()
        assert cat in gen.get_categories()

    def test_obsession_queries(self):
        gen = TopicGenerator(wordlists_dir=Path("/nonexistent"))
        queries = gen.queries_for_obsession("sourdough baking", count=5)
        assert len(queries) == 5
        assert all("sourdough baking" in q for q in queries)

    def test_loads_from_yaml(self):
        wordlists_dir = Path(__file__).parent.parent / "rootfs" / "app" / "data" / "wordlists"
        if wordlists_dir.exists():
            gen = TopicGenerator(wordlists_dir=wordlists_dir)
            topics = gen.get_topics()
            assert len(topics) > 100
