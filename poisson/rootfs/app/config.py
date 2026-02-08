from __future__ import annotations
"""Configuration loader for the Poisson add-on.

Reads configuration from:
1. Home Assistant add-on options (/data/options.json)
2. Environment variables (POISSON_*)
3. Fallback defaults

All config values are safe defaults — Tor and "suspect" layers are off.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Config file paths — the run script dumps config via the Supervisor API
# to /tmp/options.json (readable by poisson user). Fall back to the
# original /data/options.json for environments where it's readable.
OPTIONS_PATHS = [
    Path("/tmp/options.json"),
    Path("/data/options.json"),
]

DEFAULTS = {
    "intensity": "medium",
    "enable_search_noise": True,
    "enable_browse_noise": True,
    "enable_ad_clicks": False,
    "enable_tor": False,
    "enable_dns_noise": True,
    "enable_research_noise": False,
    "max_bandwidth_mb_per_hour": 50,
    "max_concurrent_sessions": 2,
    "schedule_mode": "always",
    "session_length_mean": 15.0,
    "obsession_probability": 0.05,
    "match_browser_fingerprint": True,
    "log_level": "INFO",
    "api_port": 8099,
}


def load_config() -> dict[str, Any]:
    """Load configuration with priority: HA options > env vars > defaults."""
    config = dict(DEFAULTS)

    # Layer 1: HA add-on options.json
    ha_loaded = False
    for opts_path in OPTIONS_PATHS:
        if not opts_path.exists():
            continue
        try:
            with open(opts_path) as f:
                ha_opts = json.load(f)
            if not isinstance(ha_opts, dict):
                logger.warning("Ignoring %s: not a JSON object", opts_path)
                continue
            # The Supervisor API wraps config in {"result":"ok","data":{...}}
            if "data" in ha_opts and isinstance(ha_opts["data"], dict):
                ha_opts = ha_opts["data"]
            matched = []
            for key in DEFAULTS:
                if key in ha_opts:
                    config[key] = ha_opts[key]
                    if config[key] != DEFAULTS[key]:
                        matched.append(f"{key}={config[key]}")
            logger.info("Loaded HA options from %s (%d keys, %d non-default: %s)",
                        opts_path, len(ha_opts), len(matched),
                        ", ".join(matched) or "none")
            ha_loaded = True
            break
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s", opts_path, e)
    if not ha_loaded:
        logger.warning("No readable HA options file found — using defaults")

    # Layer 2: Environment variable overrides (POISSON_INTENSITY, etc.)
    for key in DEFAULTS:
        env_key = f"POISSON_{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            config[key] = _coerce(env_val, type(DEFAULTS[key]), DEFAULTS[key])

    logger.info(
        "Config loaded: intensity=%s, engines=[%s]",
        config["intensity"],
        ", ".join(
            name.replace("enable_", "").replace("_noise", "").replace("_clicks", "")
            for name in DEFAULTS
            if name.startswith("enable_") and config.get(name)
        ),
    )
    return config


def _coerce(value: str, target_type: type, default: Any = None) -> Any:
    """Coerce a string environment variable to the target type."""
    if target_type is bool:
        return value.lower() in ("true", "1", "yes")
    try:
        if target_type is int:
            return int(value)
        if target_type is float:
            return float(value)
    except (ValueError, TypeError):
        logger.warning("Invalid env var value '%s' for type %s, using default", value, target_type.__name__)
        return default
    return value
