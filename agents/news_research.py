"""
News Research Agent — Karpathy-style iterative deep research
=============================================================
Performs multi-round web research on an investment manager, modeled after
Andrej Karpathy's autoresearch loop:

  Round 0 — LLM plans targeted queries from firm context
  Loop (up to max_rounds):
    1. Execute batch of search queries
    2. LLM extracts structured findings from raw results
    3. LLM decides: "sufficient" → break, OR "continue" → generate follow-ups
  Final — LLM synthesizes all findings into an LP-ready news report

No hallucination: every finding must cite source URL + date.
Missing data surfaces as a coverage gap, never an estimate.

Output dict keys:
  firm_name         : str
  research_rounds   : int   (rounds actually executed)
  total_sources     : int
  news_flags        : list  [{category, severity, finding, source_url, date}]
  news_summary      : str   (3-4 sentence synthesis for memo)
  findings          : list  [{fact, source_url, published_date, query}]
  sources_consulted : list  [{title, url, published_date}]
  queries_used      : list  [str]
  coverage_gaps     : list  [str]
  errors            : list  [str]
"""

import json
from tools.llm_client import LLMClient
from tools import web_search_client


# ── Prompts ───────────────────────────────────────────────────────────────────

_PLANNER_SYSTEM = """You are a due diligence research analyst at an institutional LP.
Your job is to plan targeted web search queries to gather LP-relevant news on an investment manager.

Focus areas (generate 1-2 queries each, prioritize by materiality):
- Regulatory actions, SEC/CFTC/DOJ enforcement, fines, consent orders
- Fundraising activity: new fund launches, closes, capital raised
- Personnel changes: key departures, new hires, succession
- Litigation: lawsuits filed or settled involving the firm or principals
- Performance or strategy news: notable wins/losses, style drift, mandate changes
- ESG / governance issues flagged by LPs or press

Rules:
- Queries must be specific and news-oriented (include firm name in each)
- Return ONLY a JSON array of query strings, no other text
- 4 to 6 queries total"""


_EXTRACTOR_SYSTEM = """You are a due diligence analyst extracting structured facts from web search results.

Rules:
1. Extract only facts that appear in the provided search results — never invent.
2. Every finding must cite the source URL and published date (null if not shown).
3. If results are irrelevant or low-quality, say so in coverage_gaps.
4. Flag any LP-material signals (regulatory, personnel, fundraising, litigation).
5. Assess whether the current findings are sufficient to write a news section of an LP memo.

Return ONLY a valid JSON object — no markdown, no preamble."""


_SYNTHESIZER_SYSTEM = """You are a senior research associate writing the news section of an LP due diligence memo.

Rules:
1. Only use facts from the provided findings — zero hallucination.
2. Every news flag must cite a source URL and date.
3. If no material news was found, say so plainly — do not pad.
4. Write for an IC audience: direct, factual, no marketing language.
5. Mark severity: HIGH (enforcement/litigation/key departure), MEDIUM (fundraising/personnel),
   LOW (general press), INFO (background context).

Return ONLY a valid JSON object — no markdown, no preamble."""


# ── Step 1: Plan queries ───────────────────────────────────────────────────────

def _plan_queries(firm_name: str, analysis: dict, client: LLMClient) -> list:
    """Ask the LLM to generate an initial set of targeted search queries."""
    firm_context = {
        "firm_name":    firm_name,
        "overview":     (analysis or {}).get("firm_overview", {}),
        "key_personnel": (analysis or {}).get("key_personnel", [])[:4],
        "disclosures":  (analysis or {}).get("regulatory_disclosures", {}),
    }
    user_msg = f"""Plan search queries for LP due diligence news research on:

<firm>
{json.dumps(firm_context, indent=2, default=str)}
</firm>

Return a JSON array of 4-6 query strings. No other text."""

    print("[News Research] Planning queries...")
    raw = client.complete(system=_PLANNER_SYSTEM, user=user_msg, max_tokens=800)

    # Strip markdown fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        queries = json.loads(raw)
        if isinstance(queries, list):
            return [str(q) for q in queries if q]
    except json.JSONDecodeError:
        pass

    # Fallback: basic queries if LLM parse fails
    return [
        f'"{firm_name}" SEC enforcement regulatory action',
        f'"{firm_name}" fundraising new fund close 2024 2025',
        f'"{firm_name}" lawsuit litigation settlement',
        f'"{firm_name}" personnel departure key person',
    ]


# ── Step 2: Extract findings from one round of results ────────────────────────

def _extract_findings(
    queries: list,
    search_results: list,          # flat list of {query, title, url, content, published_date}
    prior_findings: list,
    round_num: int,
    max_rounds: int,
    client: LLMClient,
) -> dict:
    """
    LLM reads the raw search results and:
      - Extracts structured findings
      - Assesses coverage sufficiency
      - If not sufficient AND rounds remain, proposes follow-up queries

    Returns dict with keys:
      findings, coverage_gaps, status ("sufficient"|"continue"), follow_up_queries
    """
    # Trim content to stay within token budget (~500 chars per result)
    trimmed_results = []
    for r in search_results:
        trimmed_results.append({
            "query":          r.get("query", ""),
            "title":          r.get("title", ""),
            "url":            r.get("url", ""),
            "published_date": r.get("published_date"),
            "content":        (r.get("content") or "")[:600],
        })

    is_last_round = (round_num >= max_rounds - 1)

    user_msg = f"""
Round {round_num + 1} of {max_rounds}. {"This is the FINAL round — return status: sufficient." if is_last_round else ""}

<search_results>
{json.dumps(trimmed_results, indent=2)}
</search_results>

<prior_findings_summary>
{json.dumps([f.get("fact", "") for f in prior_findings[:10]], indent=2)}
</prior_findings_summary>

Return a JSON object with this exact schema:
{{
  "findings": [
    {{
      "fact": "specific factual statement from the search results",
      "source_url": "url string",
      "published_date": "date string or null",
      "query": "which query found this",
      "category": "Regulatory|Fundraising|Personnel|Litigation|Performance|ESG|General"
    }}
  ],
  "coverage_gaps": ["list of LP-material topics not yet covered"],
  "status": "sufficient OR continue",
  "follow_up_queries": ["2-3 targeted queries to fill gaps — only if status is continue, else []"]
}}"""

    print(f"[News Research] Extracting findings (round {round_num + 1})...")
    result = client.complete_json(
        system=_EXTRACTOR_SYSTEM,
        user=user_msg,
        max_tokens=3000,
    )

    # Validate shape
    if "parse_error" in result:
        return {
            "findings":          [],
            "coverage_gaps":     ["LLM extraction parse error"],
            "status":            "sufficient",
            "follow_up_queries": [],
        }

    return result


# ── Step 3: Final synthesis ───────────────────────────────────────────────────

def _synthesize(firm_name: str, all_findings: list, all_sources: list, client: LLMClient) -> dict:
    """
    LLM synthesizes all gathered findings into a structured LP news report.
    """
    user_msg = f"""
Synthesize all research findings on {firm_name} into a structured LP news report.

<all_findings>
{json.dumps(all_findings, indent=2, default=str)}
</all_findings>

Return a JSON object:
{{
  "news_summary": "3-4 sentence factual synthesis of the most material news. No fluff.",
  "news_flags": [
    {{
      "category": "Regulatory|Fundraising|Personnel|Litigation|Performance|ESG|General",
      "severity": "HIGH|MEDIUM|LOW|INFO",
      "finding":  "specific factual statement",
      "source_url": "url or null",
      "date": "date or null",
      "lp_action": "recommended diligence follow-up or null"
    }}
  ],
  "coverage_gaps": ["list of LP-material topics where no news was found"],
  "overall_news_risk": "HIGH|MEDIUM|LOW|CLEAN — based on news flags found"
}}"""

    print("[News Research] Synthesizing final news report...")
    return client.complete_json(
        system=_SYNTHESIZER_SYSTEM,
        user=user_msg,
        max_tokens=4000,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def run(
    firm_name: str,
    analysis: dict = None,
    client: LLMClient = None,
    tavily_api_key: str = None,
    max_rounds: int = 3,
    queries_per_round: int = 5,
) -> dict:
    """
    Karpathy-style iterative deep research loop.

    Args:
        firm_name:       Resolved firm name (from ingestion agent).
        analysis:        Output of fund_analysis agent (provides context for query planning).
        client:          LLMClient instance.
        tavily_api_key:  Tavily API key; falls back to TAVILY_API_KEY env var, then DuckDuckGo.
        max_rounds:      Maximum research rounds (default 3).
        queries_per_round: Max search queries per round.

    Returns:
        news_report dict (see module docstring for keys).
    """
    news_report = {
        "firm_name":         firm_name,
        "research_rounds":   0,
        "total_sources":     0,
        "news_flags":        [],
        "news_summary":      None,
        "findings":          [],
        "sources_consulted": [],
        "queries_used":      [],
        "coverage_gaps":     [],
        "errors":            [],
    }

    if client is None:
        news_report["errors"].append("No LLMClient provided — news research skipped.")
        return news_report

    # ── Round 0: Plan queries ─────────────────────────────────────────────────
    try:
        queries = _plan_queries(firm_name, analysis or {}, client)
    except Exception as e:
        news_report["errors"].append(f"Query planning failed: {e}")
        queries = [
            f'"{firm_name}" SEC enforcement regulatory action',
            f'"{firm_name}" fundraising new fund 2024 2025',
            f'"{firm_name}" lawsuit litigation',
            f'"{firm_name}" personnel news',
        ]

    all_findings:   list = []
    all_sources:    list = []
    queries_used:   list = []

    # ── Research loop ─────────────────────────────────────────────────────────
    for round_num in range(max_rounds):
        round_queries = queries[:queries_per_round]
        if not round_queries:
            break

        queries_used.extend(round_queries)
        print(f"[News Research] Round {round_num + 1}/{max_rounds} — "
              f"{len(round_queries)} queries")

        # Execute searches
        round_results = []
        for q in round_queries:
            try:
                hits = web_search_client.search(
                    q, api_key=tavily_api_key, max_results=4
                )
                for h in hits:
                    h["query"] = q
                    round_results.append(h)
                    all_sources.append({
                        "title":          h.get("title", ""),
                        "url":            h.get("url", ""),
                        "published_date": h.get("published_date"),
                    })
            except Exception as e:
                news_report["errors"].append(f"Search failed for '{q}': {e}")

        if not round_results:
            news_report["errors"].append(
                f"Round {round_num + 1}: no search results returned — "
                "check TAVILY_API_KEY or network access."
            )
            break

        # Extract findings + decide whether to continue
        try:
            extraction = _extract_findings(
                queries=round_queries,
                search_results=round_results,
                prior_findings=all_findings,
                round_num=round_num,
                max_rounds=max_rounds,
                client=client,
            )
        except Exception as e:
            news_report["errors"].append(f"Extraction failed (round {round_num + 1}): {e}")
            break

        new_findings = extraction.get("findings", [])
        all_findings.extend(new_findings)
        news_report["research_rounds"] = round_num + 1

        status = extraction.get("status", "sufficient")
        follow_up = extraction.get("follow_up_queries", [])

        print(f"[News Research] Round {round_num + 1}: "
              f"{len(new_findings)} findings, status={status}")

        if status == "sufficient" or round_num == max_rounds - 1:
            break

        # Set up next round with follow-up queries
        queries = follow_up
        if not queries:
            break

    # ── Final synthesis ───────────────────────────────────────────────────────
    if all_findings:
        try:
            synthesis = _synthesize(firm_name, all_findings, all_sources, client)
            if "parse_error" not in synthesis:
                news_report["news_flags"]    = synthesis.get("news_flags", [])
                news_report["news_summary"]  = synthesis.get("news_summary")
                news_report["coverage_gaps"] = synthesis.get("coverage_gaps", [])
                news_report["overall_news_risk"] = synthesis.get("overall_news_risk", "UNKNOWN")
            else:
                news_report["errors"].append(
                    f"Synthesis parse error: {synthesis.get('parse_error')}"
                )
        except Exception as e:
            news_report["errors"].append(f"Synthesis failed: {e}")
    else:
        news_report["news_summary"] = (
            f"No news results were retrieved for {firm_name}. "
            "Verify search API credentials or run with --no-news to skip."
        )
        news_report["overall_news_risk"] = "UNKNOWN"

    news_report["findings"]          = all_findings
    news_report["sources_consulted"] = all_sources
    news_report["queries_used"]      = queries_used
    news_report["total_sources"]     = len(all_sources)

    print(f"[News Research] Done. "
          f"{news_report['research_rounds']} rounds, "
          f"{len(all_findings)} findings, "
          f"{len(all_sources)} sources. "
          f"Errors: {news_report['errors'] or 'none'}")

    return news_report
