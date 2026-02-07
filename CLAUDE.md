# Poisson — Claude Code Context

This is a Home Assistant add-on that generates realistic decoy network traffic
to poison surveillance profiling and data broker collection.

## Key Architecture

- **Timing engine** (`rootfs/app/patterns/timing.py` + `rootfs/app/scheduler.py`):
  The core. Uses Poisson process for event timing, Markov chains for session
  modeling, and obsession tracking for deep-dive patterns. This must produce
  timing indistinguishable from real human browsing.

- **Session manager** (`rootfs/app/session.py`): Manages headless Chromium via
  Playwright with per-session persona rotation and realistic interaction.

- **Engines** (`rootfs/app/engines/`): Pluggable traffic generators — search,
  browse, DNS. Each implements `BaseEngine.execute()`.

- **Config** (`rootfs/app/config.py`): Reads from HA `/data/options.json`,
  env vars, or defaults. Safe defaults: Tor and research noise are OFF.

- **API** (`rootfs/app/api/server.py`): aiohttp server on port 8099 for
  Ingress UI and HA sensor data.

## Development

```bash
./scripts/dev.sh test   # Run tests
./scripts/dev.sh run    # Run locally
./scripts/dev.sh build  # Build Docker image
```

## Phase Status

- Phase 1 (Foundation): BUILT — timing engine, session manager, search/browse/DNS
  engines, API, Ingress UI, HA add-on config
- Phase 2 (Realism): Markov chains built into timing.py, behavior.py has
  scroll/mouse/typing simulation. Still needs: ad click engine, weekly drift
  tuning, expanded data files
- Phase 3 (Tor & Advanced): Tor config present, engine stubs needed
- Phase 4 (Polish): Charts, heatmaps, MQTT discovery, community site lists

## Design Principles

1. Traffic must be indistinguishable from real human browsing
2. Safe defaults (Tor and suspect layers OFF)
3. Resource respectful (runs on HA hardware)
4. No telemetry, no phoning home
5. YAML data files are community-extensible
