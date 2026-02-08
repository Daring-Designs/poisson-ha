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

## How It Works

Poisson uses a **Poisson process** (a mathematical model of random events) to generate traffic that looks like real human browsing. The timing engine produces bursty activity with natural quiet gaps — not the uniform, robotic patterns that automated tools typically create.

Each session runs headless Chromium via Playwright with rotating browser personas, realistic scroll/mouse/typing behavior, and varied fingerprints to look like multiple real users on the network.

### Traffic Layers

**Layer 1: Commercial Profile Pollution** (enabled by default)
- **Search Noise**: Sends queries to Google, Bing, DuckDuckGo, and Yahoo across many topics
- **Browse Noise**: Visits websites across news, shopping, entertainment, tech, forums, and more
- **DNS Noise**: Resolves random domains to pollute ISP DNS logs (lightweight, no browser needed)

**Layer 2: Pattern Disruption** (automatic)
- Activity at unusual hours
- Varying pace (sometimes many requests, sometimes few)
- Mixed device fingerprints suggest multiple users
- No detectable periodicity

**Layer 3: "Everyone's a Suspect"** (opt-in)
- **Tor Traffic**: Route some traffic through Tor, browse .onion directories
- **Research Noise**: Visit privacy tools, legal resources, government databases

**Layer 4: Ad Click Engine** (opt-in)
- Click on advertisements to pollute ad tracking profiles

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `intensity` | `medium` | Traffic rate: low, medium, high, paranoid |
| `enable_search_noise` | `true` | Generate fake search queries |
| `enable_browse_noise` | `true` | Visit random websites |
| `enable_dns_noise` | `true` | DNS query noise |
| `enable_ad_clicks` | `false` | Click on advertisements |
| `enable_tor` | `false` | Tor traffic (requires understanding) |
| `enable_research_noise` | `false` | Privacy/legal/government browsing |
| `max_bandwidth_mb_per_hour` | `50` | Max MB of traffic per hour (rolling window) |
| `max_concurrent_sessions` | `2` | Simultaneous browser sessions |
| `match_browser_fingerprint` | `true` | Rotate browser fingerprints per session |
| `schedule_mode` | `always` | When to run: always, home_only, away_only, custom |

### Intensity Levels

| Level | Events/Hour | Use Case |
|-------|-------------|----------|
| **Low** | ~18 | Minimal resource usage, light noise |
| **Medium** | ~60 | Good balance of noise and resources |
| **High** | ~150 | Significant noise generation |
| **Paranoid** | ~300 | Maximum noise — uses more bandwidth and CPU |

### Schedule Modes

- **Always**: Runs 24/7 (recommended — real humans browse at all hours)
- **Home Only**: Only when someone is home (uses HA presence detection)
- **Away Only**: Only when no one is home
- **Custom**: Control via HA automations

## Browser Extension

Poisson includes an optional Chrome extension that generates noise from your **real browser** — making decoy traffic even harder to distinguish from your actual browsing.

### What It Does

- Opens background tabs to random websites at realistic Poisson-distributed intervals
- Generates searches, page visits, and ad clicks
- Closes tabs after a simulated reading delay
- Collects your browser fingerprint so the server can match headless sessions to your real browser profile

### Setup

1. Download the extension from the Poisson dashboard (Settings tab)
2. Install it in Chrome (or any Chromium-based browser) via `chrome://extensions` → Load unpacked
3. Click the Poisson icon in the toolbar and enter your Home Assistant URL
4. Sign in via Home Assistant OAuth — the extension never sees your password

### How It Connects

The extension authenticates with your HA instance via OAuth2 and receives tasks from the add-on server. It periodically checks in with a heartbeat, reports daily stats, and requests the next noise action to perform.

### Privacy & Security

- **OAuth2 auth** — no passwords stored, tokens auto-refresh
- **No data collection** — never reads page content, form data, cookies, or browsing history
- **No third parties** — only talks to YOUR Home Assistant instance
- **Open source** — fully auditable, same repo as the add-on

## Dashboard

Access the Poisson dashboard from the Home Assistant sidebar. It shows:
- Current status and uptime
- Live activity feed
- Engine toggles
- Session and request statistics
- Bandwidth usage

## Sensors

Poisson exposes sensors to Home Assistant for use in automations and dashboards:

| Sensor | Description |
|--------|-------------|
| `sensor.poisson_status` | running / paused / error |
| `sensor.poisson_sessions_today` | Browsing sessions generated today |
| `sensor.poisson_requests_today` | Total HTTP requests made today |
| `sensor.poisson_bandwidth_today` | MB of noise traffic today |

## Resource Usage

Poisson runs headless Chromium for browser-based engines. On typical HA hardware:

- **RAM**: ~200-400 MB (depends on concurrent sessions)
- **CPU**: Low average, occasional spikes during page loads
- **Bandwidth**: Configurable, default 50 MB/hr cap
- **Storage**: Minimal (~50 MB for the container)

## FAQ

**Is this legal?** Yes. Poisson only performs legal activities: visiting public websites, making search queries, resolving DNS, and using Tor (legal in the US and most countries).

**Will this slow my internet?** At default settings (medium, 50 MB/hr cap), impact is minimal. Adjust the bandwidth limit and intensity to match your connection.

**Does this actually work?** Mass surveillance depends on behavioral patterns being meaningful. When your network generates diverse, realistic noise, it raises the cost and lowers the accuracy of profiling. Same principle as chaff in radar: you don't need to be invisible, just indistinguishable.

**What about HTTPS?** Poisson visits real websites over HTTPS. While the content is encrypted, the domains you visit (SNI), DNS queries, and traffic metadata are visible to your ISP. That's exactly what Poisson poisons.

## Contributing

Site lists, search terms, and personas are YAML files in `rootfs/app/data/`. PRs welcome.

## Credits

Inspired by [AdNauseam](https://adnauseam.io/), [TrackMeNot](https://trackmenot.io/), and *Obfuscation* by Finn Brunton & Helen Nissenbaum.

## License

MIT
