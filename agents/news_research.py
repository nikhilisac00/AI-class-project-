"""
News Research Agent — Tool-Use Agent
=====================================
GPT-4o autonomously decides what to search, reads results, decides whether
to search more, and stops when it has sufficient coverage.

This is a real agent: GPT-4o uses web_search tool_use in a loop,
adapting its queries based on what it finds.

Tools available:
  web_search(query) — Tavily / DuckDuckGo

Output:
  firm_name, research_rounds, total_sources, news_flags, news_summary,
  findings, sources_consulted, queries_used, coverage_gaps, errors
"""

import json
from tools.llm_client import LLMClient
from tools import web_search_client


# ── Tool definition ───────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web for news, regulatory actions, litigation, fundraising activity, "
            "or personnel changes related to the investment manager. "
            "Returns titles, URLs, dates, and content snippets. "
            "Call this multiple times with different queries to build comprehensive coverage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Web search query. Be specific — include the firm name.",
                }
            },
            "required": ["query"],
        },
    },
]


SYSTEM_PROMPT = """You are a senior LP due diligence analyst performing news and regulatory research.

Your goal: find all LP-material news and regulatory history for an investment manager using web search.

RESEARCH AREAS — cover all of these:
1. SEC / CFTC / DOJ enforcement actions, fines, consent orders, bars
2. Fundraising: new fund launches, final closes, capital raised (especially for named funds)
3. Key personnel changes: departures, hires, succession, key person events
4. Litigation: lawsuits filed or settled involving the firm or its principals
5. Performance or strategy: notable wins/losses, mandate changes, style drift
6. LP concerns: redemption gates, disputes, side pockets, conflicts of interest
7. ESG / governance issues reported in the press

HOW TO RESEARCH:
- Run 6-10 searches covering different topics and time periods
- If you find named funds, search for each fund specifically
- If you find a regulatory action, search for follow-up
- Include recent searches (2023, 2024, 2025) AND historical searches
- Include the firm name in every query

WHEN TO STOP:
Stop when you've covered all 7 areas above or exhausted reasonable queries.

FINAL OUTPUT:
After all searches, output ONLY a JSON object:
{
  "news_summary": "3-4 sentence factual synthesis of the most material news. No fluff.",
  "overall_news_risk": "HIGH | MEDIUM | LOW | CLEAN",
  "news_flags": [
    {
      "category": "Regulatory | Fundraising | Personnel | Litigation | Performance | ESG | General",
      "severity": "HIGH | MEDIUM | LOW | INFO",
      "finding": "specific factual statement",
      "source_url": "url or null",
      "date": "date or null",
      "lp_action": "recommended diligence follow-up or null"
    }
  ],
  "findings": [
    {
      "fact": "specific fact from search results",
      "source_url": "url",
      "published_date": "date or null",
      "query": "the query that found this",
      "category": "Regulatory | Fundraising | Personnel | Litigation | Performance | ESG | General"
    }
  ],
  "sources_consulted": [
    {"title": "...", "url": "...", "published_date": "..."}
  ],
  "queries_used": ["list of all queries run"],
  "coverage_gaps": ["topics where no news was found"]
}

RULES:
- Zero hallucination. Every finding must come from actual search results.
- Every news_flag must cite a source_url.
- If no material news found for a category, note it in coverage_gaps.
- Severity guide: HIGH = enforcement/bar/fraud/litigation, MEDIUM = fundraising/personnel,
  LOW = general press, INFO = background context.
"""


# ── Tool executor ─────────────────────────────────────────────────────────────

def _exec_web_search(inputs: dict, tavily_key: str = None) -> list[dict]:
    query = inputs.get("query", "").strip()
    if not query:
        return []
    try:
        results = web_search_client.search(query, api_key=tavily_key, max_results=5)
        return [
            {
                "title":          r.get("title", ""),
                "url":            r.get("url", ""),
                "published_date": r.get("published_date"),
                "content":        (r.get("content") or "")[:500],
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e)}]


# ── Main entry point ──────────────────────────────────────────────────────────

def run(
    firm_name: str,
    analysis: dict = None,
    client: LLMClient = None,
    tavily_api_key: str = None,
    max_rounds: int = 3,          # kept for API compatibility, agent self-terminates
    queries_per_round: int = 5,   # kept for API compatibility
) -> dict:
    """
    Run the news research agent.

    Args:
        firm_name     : resolved firm name
        analysis      : fund_analysis output (provides context — fund names, personnel)
        client        : LLMClient instance
        tavily_api_key: Tavily API key
        max_rounds    : unused (agent decides when to stop), kept for compatibility

    Returns news_report dict.
    """
    news_report = {
        "firm_name":         firm_name,
        "research_rounds":   0,
        "total_sources":     0,
        "news_flags":        [],
        "news_summary":      None,
        "overall_news_risk": "UNKNOWN",
        "findings":          [],
        "sources_consulted": [],
        "queries_used":      [],
        "coverage_gaps":     [],
        "errors":            [],
    }

    if client is None:
        news_report["errors"].append("No LLMClient provided — news research skipped.")
        return news_report

    # Build context from analysis to guide the agent
    fund_names = [
        f.get("name") for f in
        (analysis or {}).get("funds_analysis", {}).get("funds", [])[:8]
        if f.get("name")
    ]
    key_personnel = [
        p.get("name") for p in
        (analysis or {}).get("key_personnel", [])[:4]
        if p.get("name")
    ]
    has_disclosures = (analysis or {}).get("regulatory_disclosures", {}).get("has_disclosures")

    context_lines = [f"Investment manager: {firm_name}"]
    if fund_names:
        context_lines.append(f"Known funds: {', '.join(fund_names)}")
    if key_personnel:
        context_lines.append(f"Key personnel: {', '.join(key_personnel)}")
    if has_disclosures:
        context_lines.append("Note: IAPD indicates this firm has regulatory disclosure events on record.")

    initial_message = (
        "\n".join(context_lines)
        + "\n\nResearch this firm thoroughly using web search. "
        "Cover enforcement, fundraising, personnel, litigation, and performance. "
        "If fund names are listed above, search for each one specifically. "
        "Output your final JSON when done."
    )

    tool_executor = {
        "web_search": lambda inp: _exec_web_search(inp, tavily_key=tavily_api_key),
    }

    print(f"[News Research Agent] Starting agent loop for '{firm_name}'...")
    try:
        result = client.agent_loop_json(
            system=SYSTEM_PROMPT,
            initial_message=initial_message,
            tools=TOOLS,
            tool_executor=tool_executor,
            max_tokens=4096,
            max_iterations=20,
        )
    except Exception as e:
        news_report["errors"].append(f"Agent loop failed: {e}")
        return news_report

    if "parse_error" in result:
        news_report["errors"].append(f"Agent output parse error: {result['parse_error'][:200]}")
        return news_report

    sources = result.get("sources_consulted", [])
    queries = result.get("queries_used", [])

    news_report["news_flags"]        = result.get("news_flags", [])
    news_report["news_summary"]      = result.get("news_summary")
    news_report["overall_news_risk"] = result.get("overall_news_risk", "UNKNOWN")
    news_report["findings"]          = result.get("findings", [])
    news_report["sources_consulted"] = sources
    news_report["queries_used"]      = queries
    news_report["coverage_gaps"]     = result.get("coverage_gaps", [])
    news_report["total_sources"]     = len(sources)
    news_report["research_rounds"]   = max(1, len(queries) // 3) if queries else 0

    print(
        f"[News Research Agent] Done — "
        f"{len(queries)} queries, {len(sources)} sources, "
        f"{len(news_report['news_flags'])} flags, "
        f"risk={news_report['overall_news_risk']}"
    )
    return news_report
