"""
Comparable Managers Agent
=========================
Finds peer investment managers from the IAPD universe and builds a
side-by-side benchmarking table.

Gives the IC context: "How does this manager compare to peers of similar
size, strategy, and geography?"

No LLM required — pure IAPD search + data extraction.
Strategy: search for firms with similar name tokens, same state, then
score and rank by similarity to the target firm.
"""

from tools.edgar_client import search_adviser_by_name, get_adviser_detail, extract_adv_summary
from tools.adv_parser import _get_13f_portfolio_value


def _extract_keywords(firm_name: str) -> list[str]:
    """Pull strategy-hinting keywords from a firm name."""
    skip = {
        "llc", "lp", "inc", "ltd", "co", "corp", "the", "and",
        "capital", "management", "advisors", "advisers", "partners",
        "group", "fund", "asset", "global", "investment", "investments",
        "financial", "services", "wealth", "associates",
    }
    tokens = firm_name.lower().replace(",", "").replace(".", "").split()
    return [t for t in tokens if t not in skip and len(t) > 2]


def _search_peers(firm_name: str, state: str = None, max_results: int = 20) -> list[dict]:
    """
    Search IAPD for peer firms. Tries:
    1. Strategy keywords from firm name
    2. State-based search (if state known)
    Returns deduplicated list of raw IAPD hits.
    """
    seen_crds = set()
    results = []

    keywords = _extract_keywords(firm_name)
    # Use the most distinctive keyword (longest non-generic token)
    if keywords:
        query = max(keywords, key=len)
        hits = search_adviser_by_name(query, max_results=max_results)
        for h in hits:
            crd = h.get("crd")
            if crd and crd not in seen_crds:
                seen_crds.add(crd)
                results.append(h)

    # Supplement with state-based search if we have fewer than 10 peers
    if state and len(results) < 10:
        hits = search_adviser_by_name(f"{state} capital management", max_results=10)
        for h in hits:
            crd = h.get("crd")
            if crd and crd not in seen_crds:
                seen_crds.add(crd)
                results.append(h)

    return results


def run(firm_name: str, adv_summary: dict, raw_data: dict,
        max_peers: int = 6) -> dict:
    """
    Find comparable managers and build a benchmarking table.

    Args:
        firm_name:   The target firm name.
        adv_summary: The target firm's parsed ADV summary (from data_ingestion).
        raw_data:    Full raw_data dict (for 13F portfolio value of target).
        max_peers:   Max number of peer firms to return (default 6).

    Returns dict with:
      - target:      summary row for the target firm
      - peers:       list of peer firm summary rows
      - table:       flat list of all rows (target + peers) for display
      - note:        data quality / methodology note
    """
    print(f"[Comparables] Finding peers for '{firm_name}'...")

    target_state = adv_summary.get("state")
    target_13f   = (raw_data.get("adv_xml_data", {}).get("thirteenf") or {})
    target_pv    = target_13f.get("portfolio_value_usd")

    def _make_row(name: str, summary: dict, thirteenf: dict,
                  is_target: bool = False) -> dict:
        pv = (thirteenf or {}).get("portfolio_value_usd")
        return {
            "firm_name":           name,
            "is_target":           is_target,
            "crd":                 summary.get("crd_number"),
            "registration_status": summary.get("registration_status"),
            "is_sec_registered":   summary.get("is_sec_registered"),
            "has_disclosures":     summary.get("has_disclosures"),
            "city":                summary.get("city"),
            "state":               summary.get("state"),
            "adv_filing_date":     summary.get("adv_filing_date"),
            "portfolio_value_fmt": (thirteenf or {}).get("portfolio_value_fmt"),
            "portfolio_value_usd": pv,
            "holdings_count":      (thirteenf or {}).get("holdings_count"),
        }

    # Build target row
    target_row = _make_row(
        firm_name, adv_summary, target_13f, is_target=True
    )

    # Search for peers
    candidates = _search_peers(firm_name, state=target_state, max_results=25)

    # Filter out the target firm itself
    target_crd = adv_summary.get("crd_number") or adv_summary.get("crd")
    candidates = [
        c for c in candidates
        if str(c.get("crd", "")) != str(target_crd)
        and (c.get("firm_name") or "").lower() != firm_name.lower()
    ]

    # Score peers: prefer same state + SEC registered + similar portfolio size
    def _peer_score(c: dict) -> float:
        score = 0.0
        if c.get("state") == target_state:
            score += 0.4
        if (c.get("registration_status") or "").upper() in ("ACTIVE", ""):
            score += 0.3
        if not c.get("has_disclosures"):
            score += 0.1
        return score

    candidates.sort(key=_peer_score, reverse=True)
    top_candidates = candidates[:max_peers * 2]  # fetch more than needed, filter after

    # Enrich top candidates with ADV detail + 13F
    peers = []
    print(f"[Comparables] Enriching {len(top_candidates)} candidates...")
    for c in top_candidates:
        if len(peers) >= max_peers:
            break
        crd = c.get("crd")
        name = c.get("firm_name", "")
        if not crd or not name:
            continue
        try:
            detail = get_adviser_detail(str(crd))
            if not detail:
                continue
            summary = extract_adv_summary(detail, search_hit=c)

            # Quick 13F lookup (no XML parsing — just portfolio value)
            thirteenf = _get_13f_portfolio_value(name)

            peers.append(_make_row(name, summary, thirteenf))
        except Exception:
            continue

    # Sort peers by portfolio value desc (nulls last)
    peers.sort(key=lambda x: x.get("portfolio_value_usd") or -1, reverse=True)

    table = [target_row] + peers

    # Size rank for target
    all_pvs = [r.get("portfolio_value_usd") for r in table if r.get("portfolio_value_usd")]
    size_rank = None
    if target_pv and all_pvs:
        all_pvs_sorted = sorted(all_pvs, reverse=True)
        size_rank = all_pvs_sorted.index(target_pv) + 1

    print(f"[Comparables] Done — {len(peers)} peers found.")
    return {
        "target":     target_row,
        "peers":      peers,
        "table":      table,
        "size_rank":  size_rank,
        "total_in_comparison": len(table),
        "note": (
            "Peers sourced from IAPD universe by strategy keyword + geography. "
            "13F portfolio value used as AUM proxy (US public equity managers only). "
            "This is a screening comparison — not a definitive peer set."
        ),
    }
