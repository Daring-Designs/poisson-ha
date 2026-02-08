# Poisson — Traffic Noise Generator

## What is Poisson?

Poisson is a Home Assistant add-on that generates realistic decoy network traffic. It creates noise that makes behavioral profiling, data broker collection, and mass surveillance more expensive and less reliable.

Rather than trying to hide your traffic (which is detectable), Poisson drowns your real browsing patterns in a sea of realistic noise.

## How it works

Poisson uses a **Poisson process** (a mathematical model of random events) to generate traffic that looks like real human browsing. The timing engine produces bursty activity with natural quiet gaps — not the uniform, robotic patterns that automated tools typically create.

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
| `schedule_mode` | `always` | When to run: always, home_only, away_only, custom |

## Intensity Levels

- **Low**: ~18 events/hour. Minimal resource usage.
- **Medium**: ~60 events/hour. Good balance of noise and resources.
- **High**: ~150 events/hour. Significant noise generation.
- **Paranoid**: ~300 events/hour. Maximum noise. Uses more bandwidth and CPU.

## Schedule Modes

- **Always**: Runs 24/7 (recommended — real humans browse at all hours)
- **Home Only**: Only when someone is home (uses HA presence detection)
- **Away Only**: Only when no one is home
- **Custom**: Control via HA automations

## Dashboard

Access the Poisson dashboard from the Home Assistant sidebar. It shows:
- Current status and uptime
- Live activity feed
- Engine toggles
- Session and request statistics
- Bandwidth usage

## Sensors

Poisson exposes several sensors to Home Assistant:

- `sensor.poisson_status` — running / paused / error
- `sensor.poisson_sessions_today` — browsing sessions generated
- `sensor.poisson_requests_today` — total HTTP requests made
- `sensor.poisson_bandwidth_today` — MB of noise traffic

## FAQ

**Is this legal?**
Yes. Poisson only performs legal activities: visiting public websites, making search queries, resolving DNS, and using Tor (legal in the US and most countries).

**Will this slow my internet?**
At the default settings (medium intensity, 50 MB/hr cap), the impact is minimal. You can adjust the bandwidth limit and intensity to match your connection.

**Does this actually work?**
Mass surveillance depends on behavioral patterns being meaningful. When your network generates diverse, realistic noise, it raises the cost and lowers the accuracy of profiling. It's the same principle as chaff in radar: you don't need to be invisible, just indistinguishable.

**What about HTTPS?**
Poisson visits real websites over HTTPS. While the content is encrypted, the domains you visit (SNI), DNS queries, and traffic metadata are visible to your ISP. That's exactly what Poisson poisons.

## Resource Usage

Poisson runs headless Chromium for browser-based engines. On typical HA hardware:

- **RAM**: ~200-400 MB (depends on concurrent sessions)
- **CPU**: Low average, occasional spikes during page loads
- **Bandwidth**: Configurable, default 50 MB/hr cap
- **Storage**: Minimal (~50 MB for the container)

## Credits

Inspired by:
- [AdNauseam](https://adnauseam.io/) — ad click obfuscation
- [TrackMeNot](https://trackmenot.io/) — search query noise
- *Obfuscation: A User's Guide for Privacy and Protest* by Finn Brunton & Helen Nissenbaum
