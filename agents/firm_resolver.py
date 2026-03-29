"""
Firm Name Resolution Agent
==========================
Resolves a rough user input (e.g. "Blackstone", "AQR Capital") to the correct
SEC-registered entity name and CRD number.

Steps:
  1. IAPD text search → up to 10 raw candidates
  2. Fuzzy-score each candidate against the user input (difflib)
  3. Return top 5 candidates ranked by score, with website (web-searched if needed)

No LLM required — pure search + string matching.
"""

import re
from difflib import SequenceMatcher
from tools.edgar_client import search_adviser_by_name
from tools import web_search_client


def _fuzzy_score(a: str, b: str) -> float:
    """SequenceMatcher ratio between two strings, case-insensitive."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _token_score(query: str, candidate: str) -> float:
    """
    Token overlap score: fraction of query words found in candidate name.
    Handles cases like "AQR" matching "AQR CAPITAL MANAGEMENT, LLC".
    """
    q_tokens = set(re.findall(r"\w+", query.lower()))
    c_tokens = set(re.findall(r"\w+", candidate.lower()))
    if not q_tokens:
        return 0.0
    return len(q_tokens & c_tokens) / len(q_tokens)


def _combined_score(query: str, candidate: str) -> float:
    """Blend of fuzzy ratio and token overlap."""
    return 0.4 * _fuzzy_score(query, candidate) + 0.6 * _token_score(query, candidate)


def _find_website(firm_name: str, tavily_key: str = None) -> str | None:
    """
    Quick web search to find the official website for a firm.
    Returns URL string or None.
    """
    query = f'"{firm_name}" official website investment adviser'
    try:
        results = web_search_client.search(query, api_key=tavily_key, max_results=3)
        for r in results:
            url = r.get("url", "")
            # Prefer .com domains that aren't SEC/Wikipedia
            if url and "sec.gov" not in url and "wikipedia" not in url:
                # Strip to domain only for display
                return url
    except Exception:
        pass
    return None


def resolve(
    user_input: str,
    tavily_key: str = None,
    max_candidates: int = 5,
) -> list[dict]:
    """
    Resolve a rough firm name to a ranked list of IAPD-registered candidates.

    Args:
        user_input:     Raw user input, e.g. "Blackstone" or "AQR Capital"
        tavily_key:     Optional Tavily API key for website lookup
        max_candidates: Number of candidates to return (default 5)

    Returns:
        List of candidate dicts, sorted by match score descending:
        {
            crd, firm_name, sec_number, registration_status,
            city, state, has_disclosures,
            match_score,   # 0.0–1.0
            website,       # URL or None
        }
    """
    if not user_input or not user_input.strip():
        return []

    query = user_input.strip()

    # Pull more raw candidates than we'll return so scoring can filter
    raw = search_adviser_by_name(query, max_results=15)

    if not raw:
        return []

    # Score and sort
    scored = []
    for c in raw:
        name = c.get("firm_name") or ""
        score = _combined_score(query, name)
        scored.append({**c, "match_score": round(score, 3)})

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    top = scored[:max_candidates]

    # Website lookup for top candidates (quick — only top 3 to avoid rate limits)
    for i, candidate in enumerate(top[:3]):
        if not candidate.get("website"):
            candidate["website"] = _find_website(
                candidate["firm_name"], tavily_key=tavily_key
            )

    return top
