"""
RawData cache — crash-resumable persistence for the data-ingestion stage.

Serializes the assembled RawData payload to disk after ingestion completes.
On the next pipeline run for the same firm, loads from cache if the payload
is still fresh (configurable TTL, default 24 h).

Cache path: ``RAW_DATA_CACHE_DIR`` env var, default ``.cache/raw_data/``.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_DEFAULT_CACHE_DIR = ".cache/raw_data"
_DEFAULT_TTL_HOURS = 24


def _cache_dir() -> Path:
    """Return the cache directory, creating it if necessary."""
    d = Path(os.getenv("RAW_DATA_CACHE_DIR", _DEFAULT_CACHE_DIR))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize_key(firm_key: str) -> str:
    """Turn a firm name or CRD into a filesystem-safe cache key."""
    return re.sub(r"[^a-z0-9]+", "_", firm_key.strip().lower()).strip("_")


def save_raw_data(firm_key: str, raw_data: dict) -> Optional[Path]:
    """Persist *raw_data* to the cache directory.

    Returns the path written, or ``None`` if the write fails (errors are
    logged but never propagate — caching must not crash the pipeline).
    """
    try:
        path = _cache_dir() / f"{_sanitize_key(firm_key)}.json"
        payload = {
            "_cached_at": datetime.now(timezone.utc).isoformat(),
            "data": raw_data,
        }
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"[Cache] Saved raw data to {path}")
        return path
    except (OSError, TypeError, ValueError) as exc:
        print(f"[Cache] WARNING: failed to save raw data: {exc}")
        return None


def load_raw_data(firm_key: str, ttl_hours: float = _DEFAULT_TTL_HOURS) -> Optional[dict]:
    """Load cached RawData if a fresh payload exists.

    Args:
        firm_key:  Firm name or CRD used as the original pipeline input.
        ttl_hours: Maximum age (hours) before the cached file is considered stale.

    Returns:
        The cached ``RawData`` dict, or ``None`` if no fresh cache exists.
    """
    path = _cache_dir() / f"{_sanitize_key(firm_key)}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(payload["_cached_at"])
        age_hours = (datetime.now(timezone.utc) - cached_at).total_seconds() / 3600
        if age_hours > ttl_hours:
            print(f"[Cache] Stale cache ({age_hours:.1f}h old, TTL {ttl_hours}h) — refetching")
            return None
        print(f"[Cache] Loaded raw data from cache ({age_hours:.1f}h old)")
        return payload["data"]
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"[Cache] WARNING: failed to read cache: {exc}")
        return None
