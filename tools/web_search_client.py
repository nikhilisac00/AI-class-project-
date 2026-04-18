"""
Web Search Client
Tavily API (primary — preferred for research) with DuckDuckGo fallback.
Each result: {title, url, content, published_date, source}

Auth:
  TAVILY_API_KEY env var — free tier at tavily.com (1,000 searches/month)
  No key needed for DuckDuckGo fallback (rate-limited, best-effort).
"""

import os
import re
import requests
from html.parser import HTMLParser


# ── HTML → plain text ─────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Minimal HTML stripper — skips script/style/nav blocks."""

    _SKIP_TAGS = {"script", "style", "nav", "footer", "header", "noscript"}

    def __init__(self):
        super().__init__()
        self._skip_depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0 and data.strip():
            self.parts.append(data.strip())

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts))


def _fetch_page_text(url: str, timeout: int = 8, max_chars: int = 3000) -> str:
    """Fetch a URL and return plain text (best-effort; returns '' on failure)."""
    # Bug #12: validate URL scheme before fetching to avoid non-HTTP URIs hanging
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return ""
    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DD-research-bot/1.0)"},
            stream=True,
        )
        r.raise_for_status()
        # Bug #12: check content-length before reading to avoid huge downloads
        content_length = int(r.headers.get("content-length", 0))
        if content_length > 5_000_000:  # skip files >5 MB
            return ""
        content_type = r.headers.get("content-type", "")
        if "html" not in content_type and "text" not in content_type:
            return ""
        raw = r.content[:max_chars * 4].decode("utf-8", errors="ignore")
        extractor = _TextExtractor()
        extractor.feed(raw)
        return extractor.get_text()[:max_chars]
    except Exception:
        return ""


# ── Tavily ────────────────────────────────────────────────────────────────────

def _search_tavily(query: str, api_key: str, max_results: int = 5) -> list:
    """
    Tavily search — returns clean excerpts with dates.
    Raises on import error (package not installed) or API error.
    """
    from tavily import TavilyClient  # lazy import — optional dependency

    client = TavilyClient(api_key=api_key)
    response = client.search(
        query=query,
        search_depth="advanced",
        max_results=max_results,
        include_answer=False,
    )
    results = []
    for r in response.get("results", []):
        results.append({
            "title":          r.get("title", ""),
            "url":            r.get("url", ""),
            "content":        (r.get("content") or "")[:2000],
            "published_date": r.get("published_date"),
            "source":         "tavily",
        })
    return results


# ── DuckDuckGo ────────────────────────────────────────────────────────────────

def _search_duckduckgo(query: str, max_results: int = 5) -> list:
    """
    DuckDuckGo fallback — fetches page text for each result.
    Raises on import error (package not installed).
    """
    from duckduckgo_search import DDGS  # lazy import — optional dependency

    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            url = r.get("href", "")
            content = _fetch_page_text(url) or r.get("body", "")
            results.append({
                "title":          r.get("title", ""),
                "url":            url,
                "content":        content[:2000],
                "published_date": None,
                "source":         "duckduckgo",
            })
    return results


# ── Public API ────────────────────────────────────────────────────────────────

def search(query: str, api_key: str = None, max_results: int = 5) -> list:
    """
    Execute a web search query.

    Tries Tavily first (if TAVILY_API_KEY is set or api_key is provided),
    then falls back to DuckDuckGo.

    Returns:
        List of dicts: {title, url, content, published_date, source}
        Empty list on complete failure.
    """
    key = api_key or os.getenv("TAVILY_API_KEY")

    if key:
        try:
            results = _search_tavily(query, key, max_results)
            if results:
                return results
        except Exception as e:
            print(f"[WebSearch] Tavily failed ({e}), trying DuckDuckGo...")

    try:
        return _search_duckduckgo(query, max_results)
    except Exception as e:
        print(f"[WebSearch] DuckDuckGo also failed: {e}")
        return []
