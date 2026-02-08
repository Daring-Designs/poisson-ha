from __future__ import annotations
"""Topic and interest generation for browsing sessions.

Generates realistic "interest profiles" that evolve over time,
including obsession patterns where a user fixates on one topic.
"""

import random
from pathlib import Path
from typing import Optional

import yaml

DATA_DIR = Path(__file__).parent.parent / "data"

# Fallback topic categories if no data files are present
BUILTIN_TOPICS = {
    "technology": [
        "best laptop 2025", "python tutorial", "react vs vue",
        "kubernetes deployment", "raspberry pi projects",
        "home server setup", "linux distro comparison",
        "mechanical keyboard review", "AI image generation",
        "self-hosted alternatives", "docker compose examples",
    ],
    "shopping": [
        "best hiking boots", "wireless earbuds under 100",
        "standing desk review", "coffee grinder recommendations",
        "winter jacket sale", "running shoes for flat feet",
        "ergonomic mouse", "air purifier for allergies",
        "cast iron skillet", "backpack for travel",
    ],
    "news": [
        "latest tech news", "world news today",
        "climate change report", "election results",
        "stock market analysis", "space exploration news",
        "cybersecurity breach", "supply chain update",
    ],
    "health": [
        "intermittent fasting benefits", "best stretches for back pain",
        "sleep hygiene tips", "vitamin d deficiency symptoms",
        "meditation for beginners", "HIIT workout plan",
        "anti-inflammatory diet", "mental health resources",
    ],
    "travel": [
        "cheap flights to europe", "best time to visit japan",
        "road trip planner", "travel insurance comparison",
        "hostel vs airbnb", "passport renewal process",
        "visa requirements turkey", "train travel europe",
    ],
    "hobbies": [
        "sourdough starter recipe", "beginner woodworking projects",
        "indoor plants low light", "learn guitar online",
        "film photography developing", "board game recommendations",
        "watercolor techniques", "3d printing for beginners",
    ],
    "finance": [
        "how to budget", "index fund vs etf",
        "mortgage rates today", "credit score improve",
        "tax deductions freelancer", "retirement calculator",
        "crypto market analysis", "student loan refinance",
    ],
    "education": [
        "online courses free", "learn spanish fast",
        "GRE prep tips", "data science bootcamp",
        "coding interview prep", "academic writing guide",
        "scholarship applications", "study abroad programs",
    ],
    "privacy": [
        "best vpn service", "password manager comparison",
        "encrypted email providers", "browser privacy settings",
        "data broker opt out", "two factor authentication setup",
        "privacy focused search engine", "secure messaging apps",
    ],
    "legal": [
        "tenant rights", "small claims court process",
        "immigration lawyer near me", "FOIA request how to",
        "consumer protection laws", "workplace discrimination",
        "public records search", "pro bono legal aid",
    ],
}


class TopicGenerator:
    """Generates and manages browsing topics."""

    def __init__(self, wordlists_dir: Optional[Path] = None):
        self._topics: dict[str, list[str]] = {}
        self._wordlists_dir = wordlists_dir or DATA_DIR / "wordlists"
        self._load()

    def _load(self):
        """Load search terms from YAML wordlists, falling back to builtins."""
        loaded = False
        if self._wordlists_dir.exists():
            for yaml_file in self._wordlists_dir.glob("*.yaml"):
                try:
                    with open(yaml_file) as f:
                        data = yaml.safe_load(f)
                    if not isinstance(data, dict):
                        continue
                    for category, terms in data.items():
                        if isinstance(terms, list):
                            # Only accept string terms
                            valid = [t for t in terms if isinstance(t, str)]
                            if valid:
                                self._topics.setdefault(str(category), []).extend(valid)
                                loaded = True
                except (yaml.YAMLError, OSError) as exc:
                    import logging
                    logging.getLogger(__name__).warning("Bad wordlist %s: %s", yaml_file, exc)

        if not loaded:
            self._topics = dict(BUILTIN_TOPICS)

    def get_categories(self) -> list[str]:
        return list(self._topics.keys())

    def get_topics(self) -> list[str]:
        """Return flat list of all topic strings."""
        return [t for terms in self._topics.values() for t in terms]

    def random_query(self, category: Optional[str] = None) -> str:
        """Pick a random search query, optionally from a specific category."""
        if category and category in self._topics:
            pool = self._topics[category]
        else:
            pool = self.get_topics()
        return random.choice(pool)

    def random_category(self) -> str:
        return random.choice(self.get_categories())

    def queries_for_obsession(self, topic: str, count: int = 5) -> list[str]:
        """Generate related queries for an obsession deep-dive.

        Given a seed topic, produce variations that look like someone
        researching that topic thoroughly.
        """
        modifiers = [
            "{topic}",
            "{topic} review",
            "{topic} comparison",
            "{topic} reddit",
            "best {topic}",
            "{topic} pros and cons",
            "{topic} alternatives",
            "{topic} guide",
            "{topic} tutorial",
            "{topic} cost",
            "{topic} forum",
            "{topic} near me",
            "is {topic} worth it",
            "{topic} vs",
        ]
        selected = random.sample(modifiers, min(count, len(modifiers)))
        return [m.format(topic=topic) for m in selected]
