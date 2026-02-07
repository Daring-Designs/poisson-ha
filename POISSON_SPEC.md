# Poisson — Traffic Noise Generator for Home Assistant

**Repo:** `git@github.com:Daring-Designs/poisson.git`
**Description:** Traffic noise generator for Home Assistant. Make mass surveillance expensive and unreliable.

---

## Project Overview

Poisson is a Home Assistant add-on that generates realistic decoy network traffic to poison surveillance profiling, data broker collection, and behavioral analysis. Named for the Poisson distribution (used for timing), the French word for "fish" (swimming undetected), and its similarity to "poison" (what it does to surveillance data).

The core philosophy: if everyone's traffic looks "interesting," mass surveillance becomes cost-prohibitive and unreliable. Rather than hiding, Poisson drowns real browsing patterns in a sea of realistic noise.

---

## Architecture

### Tech Stack

- **Runtime:** Python 3.12+
- **Browser automation:** Playwright (headless Chromium/Firefox)
- **Tor integration:** Tor daemon with SOCKS proxy
- **Container:** Alpine Linux Docker image
- **HA integration:** Home Assistant add-on with Ingress web UI
- **Scheduling:** Custom Poisson-distribution timing engine
- **Config:** YAML-based configuration exposed through HA add-on options

### Repository Structure

```
poisson/
├── Dockerfile
├── build.yaml                  # HA add-on build config
├── config.yaml                 # HA add-on manifest (name, schema, ports, etc.)
├── DOCS.md                     # HA add-on documentation tab
├── README.md
├── LICENSE                     # MIT
├── icon.png                    # 256x256 add-on icon (fish dissolving into static)
├── logo.png                    # 256x256 add-on logo
├── translations/
│   └── en.yaml                 # HA add-on config UI translations
├── rootfs/
│   ├── etc/
│   │   ├── torrc               # Tor daemon configuration
│   │   └── services.d/
│   │       ├── tor/
│   │       │   └── run         # s6 service script for Tor
│   │       └── poisson/
│   │           └── run         # s6 service script for main app
│   └── app/
│       ├── main.py             # Entry point / orchestrator
│       ├── config.py           # Configuration loader (reads HA add-on options)
│       ├── scheduler.py        # Poisson timing engine
│       ├── session.py          # Browser session manager (Playwright lifecycle)
│       ├── engines/
│       │   ├── __init__.py
│       │   ├── base.py         # Abstract base engine class
│       │   ├── search.py       # Fake search query engine
│       │   ├── browse.py       # Web browsing session engine
│       │   ├── adclick.py      # Ad interaction / click engine
│       │   ├── tor.py          # Tor circuit and .onion activity engine
│       │   ├── dns.py          # DNS noise generator
│       │   └── research.py     # "Academic/legal research" browsing engine
│       ├── patterns/
│       │   ├── __init__.py
│       │   ├── timing.py       # Poisson distribution + Markov chain scheduling
│       │   ├── personas.py     # User agent / fingerprint rotation
│       │   ├── behavior.py     # Realistic browsing behavior (scroll, pause, click patterns)
│       │   └── topics.py       # Topic/interest generation and "obsession" patterns
│       ├── data/
│       │   ├── wordlists/
│       │   │   ├── search_terms.yaml       # Categorized search term pools
│       │   │   ├── academic_terms.yaml     # Research/academic search terms
│       │   │   └── shopping_terms.yaml     # E-commerce browsing terms
│       │   ├── sites.yaml                  # Target sites by category
│       │   ├── personas.yaml               # Browser fingerprint profiles
│       │   ├── onion_sites.yaml            # Known .onion directories
│       │   └── user_agents.yaml            # User agent strings by browser/OS
│       ├── web/
│       │   ├── index.html      # Ingress UI - main dashboard
│       │   ├── style.css
│       │   └── app.js
│       └── api/
│           ├── __init__.py
│           └── server.py       # Local API for Ingress UI + HA sensors
├── tests/
│   ├── test_scheduler.py
│   ├── test_engines.py
│   └── test_patterns.py
└── scripts/
    └── dev.sh                  # Local development helper
```

---

## Core Components

### 1. Poisson Timing Engine (`scheduler.py` + `patterns/timing.py`)

This is the most critical component. It must make traffic indistinguishable from real human behavior.

**Requirements:**
- Use Poisson process for event timing (this models real human web activity — bursty with quiet gaps)
- Implement variable rate parameter (λ) that changes throughout the day
- Time-of-day weighting: more active during waking hours, but NOT zero at night (real humans browse at 3am sometimes)
- Weekly drift: shift the activity pattern slightly each week so it's not periodic
- "Obsession" mode: occasionally deep-dive on a single topic for hours/days, then abandon it (mimics real human curiosity patterns)
- Session-based: group activities into browsing "sessions" of varying length (30 seconds to 2+ hours)
- Inter-session gaps follow exponential distribution
- Intra-session timing uses Markov chain (visiting a news article → following links → reading comments is a chain)

**Key parameters (exposed in HA config):**
- `intensity`: low / medium / high / paranoid (controls base λ rate)
- `active_hours_bias`: weight toward certain hours (default: slight daytime bias)
- `session_length_mean`: average session duration in minutes
- `obsession_probability`: chance of entering deep-dive mode on a topic

### 2. Browser Session Manager (`session.py`)

Manages Playwright browser instances with anti-fingerprinting.

**Requirements:**
- Launch headless Chromium or Firefox via Playwright
- Rotate per session:
  - User agent string
  - Viewport size (common resolutions)
  - Accept-Language header (mix languages)
  - Timezone (occasionally)
  - Platform headers
- Realistic page interaction:
  - Scroll at human-like speed (not instant)
  - Random mouse movements
  - Pause on page for realistic "reading" duration (varies by page length)
  - Occasionally move mouse to elements without clicking
  - Click internal links to follow browsing chains
- Resource management:
  - Maximum concurrent sessions (configurable, default 2)
  - Memory limits per browser instance
  - Automatic cleanup of stale sessions
  - Respect system bandwidth (configurable max bandwidth)

### 3. Traffic Engines

Each engine generates a specific type of noise. They are independently toggleable.

#### Layer 1: Commercial Profile Pollution

**Search Engine (`engines/search.py`):**
- Send queries to Google, Bing, DuckDuckGo, Yahoo
- Mix of categories: shopping, news, health, travel, hobbies, tech, local services
- Sometimes click through to results
- Use autocomplete-style progressive typing
- Occasionally do multi-query sessions (research pattern)

**Browse Engine (`engines/browse.py`):**
- Visit random sites across categories:
  - News sites across political spectrum (CNN, Fox, BBC, Al Jazeera, RT, etc.)
  - Shopping sites (Amazon, Walmart, niche stores, Etsy)
  - Social media profiles/public pages
  - Entertainment (YouTube, Netflix, Spotify public pages)
  - Forums and communities (Reddit, Stack Exchange, niche forums)
  - Foreign language content (Arabic, Mandarin, Russian, Spanish news)
- Follow internal links realistically (don't just hit homepages)
- Simulate reading time based on page content length
- Occasionally fill out but don't submit forms

**Ad Click Engine (`engines/adclick.py`):**
- Similar to AdNauseam approach
- Visit ad-heavy sites
- Click on ad elements (display ads, sponsored links)
- Follow through to landing pages
- Vary time spent on ad destinations
- Rotate through different ad categories

#### Layer 2: Pattern Disruption

Handled by the timing engine + persona rotation, not a separate engine. The timing engine ensures:
- Activity at unusual hours
- Varying cadence (sometimes 100 requests/hour, sometimes 2)
- No detectable periodicity
- Mixed device fingerprints suggest "multiple users"

#### Layer 3: "Everyone's a Suspect" (`engines/tor.py` + `engines/research.py`)

**Tor Engine (`engines/tor.py`):**
- Establish Tor circuits at random intervals
- Browse .onion directories (public ones like Ahmia)
- Make requests through Tor SOCKS proxy to clearnet sites
- Mix Tor and clearnet traffic so Tor usage isn't an "event"
- Optional: run as Tor relay (makes other people's traffic route through you = plausible deniability)
- Generate DNS queries for .onion resolution (visible to ISP)

**Research Engine (`engines/research.py`):**
- Visit privacy tool sites: Tails, Whonix, Signal, PGP key servers
- Browse legal resources: immigration law, criminal defense, civil liberties orgs
- Access government databases: PACER, FOIA.gov, SEC EDGAR, USAspending.gov
- Look up crypto/blockchain explorers
- Visit encrypted email providers: ProtonMail, Tutanota
- Browse academic papers on security topics
- Access VPN provider sites and comparison pages
- Lookup travel info for "flagged" countries

#### Layer 4: DNS Noise (`engines/dns.py`)

- Resolve random domains to pollute DNS logs (ISPs sell this data)
- Mix of benign and "interesting" domains
- Use multiple DNS resolvers (not just AdGuard)
- Resolve domains that would normally be associated with various activities
- Can run independently of browser engines (lighter weight)

### 4. Data Files

**`data/sites.yaml` structure:**
```yaml
categories:
  news_left:
    - url: cnn.com
      weight: 1.0
    - url: msnbc.com
      weight: 0.8
  news_right:
    - url: foxnews.com
      weight: 1.0
    - url: dailywire.com
      weight: 0.7
  news_international:
    - url: aljazeera.com
      weight: 0.9
    - url: bbc.co.uk
      weight: 1.0
    - url: rt.com
      weight: 0.5
  privacy_tools:
    - url: signal.org
      weight: 1.0
    - url: torproject.org
      weight: 0.8
  shopping:
    - url: amazon.com
      weight: 1.0
    - url: etsy.com
      weight: 0.7
  government:
    - url: pacer.uscourts.gov
      weight: 0.6
    - url: foia.gov
      weight: 0.5
  # ... more categories
```

**`data/personas.yaml` structure:**
```yaml
personas:
  - name: chrome_windows
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."
    viewport: { width: 1920, height: 1080 }
    platform: "Win32"
    languages: ["en-US", "en"]
  - name: firefox_mac
    user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0)..."
    viewport: { width: 1440, height: 900 }
    platform: "MacIntel"
    languages: ["en-US", "en"]
  - name: chrome_linux
    user_agent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36..."
    viewport: { width: 1366, height: 768 }
    platform: "Linux x86_64"
    languages: ["en-US", "en", "de"]
  # ... more personas including mobile
```

### 5. Home Assistant Integration

**Add-on Configuration (`config.yaml`):**
```yaml
name: "Poisson"
description: "Traffic noise generator. Make mass surveillance expensive and unreliable."
version: "0.1.0"
slug: "poisson"
url: "https://github.com/Daring-Designs/poisson"
arch:
  - amd64
  - aarch64
  - armv7
ingress: true
ingress_port: 8099
panel_icon: "mdi:fish"
panel_title: "Poisson"
options:
  intensity: "medium"
  enable_search_noise: true
  enable_browse_noise: true
  enable_ad_clicks: false
  enable_tor: false
  enable_dns_noise: true
  enable_research_noise: false
  max_bandwidth_mbps: 10
  max_concurrent_sessions: 2
  tor_relay_mode: false
  schedule_mode: "always"
schema:
  intensity: list(low|medium|high|paranoid)
  enable_search_noise: bool
  enable_browse_noise: bool
  enable_ad_clicks: bool
  enable_tor: bool
  enable_dns_noise: bool
  enable_research_noise: bool
  max_bandwidth_mbps: int(1,100)
  max_concurrent_sessions: int(1,5)
  tor_relay_mode: bool
  schedule_mode: list(always|home_only|away_only|custom)
```

**HA Sensors (published via MQTT or REST):**
- `sensor.poisson_status` — running / paused / error
- `sensor.poisson_sessions_today` — number of browsing sessions generated
- `sensor.poisson_requests_today` — total HTTP requests made
- `sensor.poisson_bandwidth_today` — MB of noise traffic generated
- `sensor.poisson_tor_circuits` — active Tor circuits
- `sensor.poisson_active_engines` — which engines are currently running
- `sensor.poisson_current_persona` — active browser fingerprint
- `sensor.poisson_uptime` — how long the noise generator has been running

**HA Automations support:**
- Expose `switch.poisson` for on/off
- Expose `input_select.poisson_intensity` for intensity control
- Support `schedule_mode` options:
  - `always` — runs 24/7
  - `away_only` — only when no one is home (uses HA presence detection)
  - `home_only` — only when someone is home (looks more natural)
  - `custom` — user defines via HA automations

### 6. Ingress Web UI

Simple single-page dashboard accessible from HA sidebar.

**Dashboard sections:**
- **Status bar:** Running/paused, uptime, current intensity
- **Live activity feed:** Scrolling log of current actions ("Searching Google for 'best hiking boots colorado'", "Browsing rt.com/news via Tor", "DNS resolve: protonmail.com")
- **Engine toggles:** On/off switches for each traffic layer
- **Intensity slider:** Low → Medium → High → Paranoid
- **Stats panel:**
  - Sessions today / this week / this month
  - Bandwidth used
  - Requests by engine type (pie chart)
  - Activity heatmap (hour of day vs. day of week)
- **Tor status:** Circuit count, relay status if enabled
- **Settings:** Link to HA add-on configuration

**Tech:** Static HTML + vanilla JS + CSS. Communicates with local API server. No framework needed — keep it lightweight.

---

## Dockerfile

```dockerfile
FROM ghcr.io/home-assistant/amd64-base:3.19

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    tor \
    chromium \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Install Playwright browsers
RUN playwright install chromium --with-deps

# Copy application
COPY rootfs /

# Set permissions
RUN chmod a+x /etc/services.d/*/run

WORKDIR /app
```

**requirements.txt:**
```
playwright
aiohttp
pyyaml
numpy
```

---

## Development Phases

### Phase 1: Foundation (MVP)
- [ ] Repo setup, Dockerfile, HA add-on config
- [ ] Poisson timing engine with configurable λ
- [ ] Basic browser session manager (Playwright + persona rotation)
- [ ] Search engine (random queries to Google/Bing/DDG)
- [ ] Browse engine (visit random sites from categorized list)
- [ ] DNS noise engine (lightweight, no browser needed)
- [ ] Basic Ingress UI (status + activity log)
- [ ] HA sensors via REST API

### Phase 2: Realism
- [ ] Markov chain browsing sessions (follow links realistically)
- [ ] "Obsession" topic patterns
- [ ] Human-like scroll/pause/mouse behavior
- [ ] Session length variation
- [ ] Weekly pattern drift
- [ ] Ad click engine
- [ ] Expanded site/search term databases

### Phase 3: Tor & Advanced
- [ ] Tor daemon integration
- [ ] Tor browsing engine (.onion sites, mixed clearnet/Tor)
- [ ] Optional Tor relay mode
- [ ] Research engine (privacy tools, legal, government sites)
- [ ] Multi-language content browsing
- [ ] Bandwidth monitoring and throttling

### Phase 4: Polish
- [ ] Full Ingress UI with charts and heatmaps
- [ ] HA automation support (presence-based scheduling)
- [ ] MQTT discovery for sensors
- [ ] Community-contributed site lists (similar to ad filter lists)
- [ ] Documentation and onboarding flow
- [ ] ARM builds (aarch64 for Pi users)
- [ ] Performance optimization and memory management

---

## Key Design Principles

1. **Indistinguishable from real traffic.** Every technical decision should serve this goal. Fixed intervals, uniform distributions, and robotic patterns are the enemy.

2. **Safe defaults.** Out of the box, only commercial profile pollution is enabled. Tor and "suspect" traffic layers require explicit opt-in.

3. **Resource respectful.** Running on HA hardware means competing with home automation. Default to low resource usage, let users dial up.

4. **Privacy-first irony.** The tool itself must not leak data. No telemetry, no phoning home, no analytics. Local only.

5. **Community-extensible.** Site lists, search terms, and personas should be easy to contribute via YAML files and pull requests — similar to how ad filter lists work.

---

## Legal Notes

All traffic generated by Poisson consists of legal activities:
- Visiting public websites
- Making search queries
- Using Tor (legal in the US and most countries)
- Resolving DNS queries
- Clicking on advertisements (contentious but not illegal for end users)

The tool does NOT:
- Spoof identity or commit fraud
- Access restricted systems
- Generate illegal content requests
- Interfere with computer systems
- Violate the CFAA

Include a clear disclaimer in README and DOCS.md.

---

## README.md Outline

1. **One-liner + badge row** (HA version, license, stars)
2. **The problem** — mass surveillance, data brokers, behavioral profiling (2-3 sentences)
3. **The solution** — obfuscation, not deletion. Drown signal in noise. (2-3 sentences)
4. **Quick install** — HA add-on store or manual repo add
5. **What it does** — brief description of each traffic layer
6. **Configuration** — key options table
7. **FAQ** — Is this legal? Does this slow my internet? Does this actually work?
8. **Contributing** — how to add sites, search terms, personas
9. **Credits** — inspired by AdNauseam, TrackMeNot, Obfuscation (Brunton & Nissenbaum)
10. **License** — MIT
