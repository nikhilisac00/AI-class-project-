"""
FRED API Client
Pulls macroeconomic benchmark data for context in DD memos.
Requires a free FRED API key: https://fred.stlouisfed.org/docs/api/api_key.html
"""

import os
import requests

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Key series used in alternatives due diligence
SERIES = {
    "fed_funds_rate":    "FEDFUNDS",      # Effective Fed Funds Rate
    "sp500":             "SP500",          # S&P 500 level (monthly)
    "vix":               "VIXCLS",        # VIX (daily)
    "hy_spread":         "BAMLH0A0HYM2",  # ICE BofA US HY OAS
    "ig_spread":         "BAMLC0A0CM",    # ICE BofA US IG OAS
    "ten_yr_yield":      "DGS10",         # 10-Year Treasury
    "cpi_yoy":           "CPIAUCSL",      # CPI (all items)
    "real_gdp_growth":   "A191RL1Q225SBEA", # Real GDP growth QoQ SAAR
}

HEADERS = {"Accept-Encoding": "gzip, deflate"}


def _fetch_series(series_id: str, api_key: str,
                  obs_start: str = "2020-01-01",
                  limit: int = 12) -> list[dict]:
    """
    Pull up to `limit` most recent observations for a FRED series.
    Returns list of {date, value} dicts. Empty list on failure.
    """
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "observation_start": obs_start,
        "limit": limit,
    }
    try:
        r = requests.get(FRED_BASE, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        return [
            {"date": o["date"], "value": o["value"]}
            for o in obs
            if o["value"] != "."  # FRED uses "." for missing
        ]
    except requests.exceptions.RequestException as e:
        print(f"[FRED] Error fetching {series_id}: {e}")
        return []


def get_market_context(api_key: str = None, obs_start: str = "2023-01-01") -> dict:
    """
    Pull latest readings for all key macro series.
    Returns dict mapping friendly name -> list of {date, value}.
    Uses FRED_API_KEY env var if api_key not provided.
    """
    key = api_key or os.getenv("FRED_API_KEY")
    if not key:
        print("[FRED] No API key found. Set FRED_API_KEY in .env")
        return {}

    context = {}
    for friendly_name, series_id in SERIES.items():
        obs = _fetch_series(series_id, key, obs_start=obs_start, limit=6)
        if obs:
            context[friendly_name] = obs
    return context


def latest_value(series_obs: list[dict]) -> str | None:
    """Return the most recent non-null value from a series observation list."""
    if not series_obs:
        return None
    return series_obs[0]["value"]  # already sorted desc
