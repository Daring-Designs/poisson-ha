# Poisson

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![HA Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-41BDF5.svg)](https://www.home-assistant.io/)

**Traffic noise generator for Home Assistant. Make mass surveillance expensive and unreliable.**

---

## The Problem

ISPs sell your DNS queries. Data brokers build behavioral profiles from your browsing. Mass surveillance systems flag "interesting" patterns. Your network traffic tells a story about you whether you like it or not.

## The Solution

Poisson generates realistic decoy traffic that drowns your real browsing in noise. Rather than hiding (which is detectable), it makes profiling unreliable by polluting the data. Named for the Poisson distribution (used for timing), the French word for "fish" (swimming undetected), and its similarity to "poison" (what it does to surveillance data).

## Quick Install

1. Add this repository to your Home Assistant add-on store
2. Install the **Poisson** add-on
3. Start it with default settings — you're done

Or manually:

```
Settings → Add-ons → Add-on Store → ⋮ → Repositories → Add:
https://github.com/Daring-Designs/poisson
```

## What It Does

| Layer | Engine | Default | Description |
|-------|--------|---------|-------------|
| Commercial Pollution | Search | ON | Fake queries to Google, Bing, DuckDuckGo, Yahoo |
| Commercial Pollution | Browse | ON | Visit news, shopping, tech, entertainment sites |
| Commercial Pollution | DNS | ON | Resolve random domains to pollute ISP logs |
| Ad Disruption | Ad Click | OFF | Click advertisements to poison ad profiles |
| Pattern Disruption | Timing | AUTO | Poisson process + Markov chains for realistic timing |
| Suspect Noise | Tor | OFF | Route traffic through Tor, browse .onion sites |
| Suspect Noise | Research | OFF | Privacy tools, legal resources, government databases |

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `intensity` | `medium` | low (~18/hr), medium (~60/hr), high (~150/hr), paranoid (~300/hr) |
| `max_bandwidth_mb_per_hour` | `50` | Max MB per hour (rolling window) |
| `max_concurrent_sessions` | `2` | Simultaneous browser sessions |
| `schedule_mode` | `always` | always, home_only, away_only, custom |

## FAQ

**Is this legal?** Yes. Poisson only visits public websites, makes search queries, resolves DNS, and optionally uses Tor — all legal activities.

**Will this slow my internet?** At default settings (medium, 10 Mbps cap), impact is minimal. Adjust to match your connection.

**Does this actually work?** Mass surveillance depends on patterns being meaningful. Diverse, realistic noise raises the cost and lowers the accuracy of profiling. Same principle as radar chaff.

## Contributing

Site lists, search terms, and personas are YAML files in `rootfs/app/data/`. PRs welcome.

## Credits

Inspired by [AdNauseam](https://adnauseam.io/), [TrackMeNot](https://trackmenot.io/), and *Obfuscation* by Finn Brunton & Helen Nissenbaum.

## License

MIT
