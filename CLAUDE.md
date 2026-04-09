# AI Alternative Investments Research Associate — Claude Code Context

## Project Purpose
Autonomous multi-agent system that performs LP-grade due diligence on investment managers.
Input: fund name or CRD number. Output: structured DD memo ready for IC review.

## Architecture
```
app.py              ← Streamlit UI (main entry point)
main.py             ← CLI entry point
agents/
  data_ingestion.py   ← Orchestrates all data pulls (no LLM); runs sub-agents in parallel
  firm_resolver.py    ← Resolves firm name/CRD from user input
  fund_analysis.py    ← GPT-4o structured analysis (firm type, 13F, funds, disclosures)
  risk_flagging.py    ← GPT-4o LP risk flags (regulatory, key person, fund structure)
  memo_generation.py  ← GPT-4o IC-ready DD memo (narrative synthesis only)
  enforcement.py      ← SEC enforcement deep-dive (EDGAR + web)
  fund_discovery.py   ← Form D + IAPD relying advisors + web search
  news_research.py    ← Multi-round news research and flagging
  comparables.py      ← Peer/comparable fund analysis
  ic_scorecard.py     ← IC scoring across risk dimensions
  research_director.py← Orchestrates multi-agent research pipeline
tools/
  edgar_client.py       ← IAPD search + EDGAR EFTS + ADV summary parser
  adv_parser.py         ← 13F XML parser + IAPD disclosure parser
  fred_client.py        ← FRED macro series (rates, spreads, VIX)
  llm_client.py         ← LLMClient wrapper (OpenAI gpt-4o / gpt-4o-mini)
  enforcement_client.py ← SEC enforcement data client
  formd_client.py       ← Form D filing data client
  web_search_client.py  ← Web search (Tavily primary, DuckDuckGo fallback)
  pal_client.py         ← PAL MCP optional consensus (not required)
tests/              ← pytest suite (run: pytest tests/ -v --cov=tools --cov=agents)
docs/               ← Research brief, architecture docs
driver-plan/        ← DRIVER planning artifacts
```

## Critical Rules (enforce in all code reviews)
1. **No hallucination**: agents must return `null` for any missing field, never estimate
2. **Trace every fact**: all memo content must cite a specific API field
3. **No hardcoded financial data**: AUM, fees, personnel must come from live API calls
4. **Error handling**: every external HTTP call must have try/except and return None on failure
5. **No secrets in code**: use env vars / Streamlit secrets only

## Data Sources
| Tool | API | Auth |
|------|-----|------|
| IAPD | adviserinfo.sec.gov | None |
| EDGAR EFTS | efts.sec.gov | None |
| EDGAR Submissions | data.sec.gov | None |
| FRED | api.stlouisfed.org | Free key (`FRED_API_KEY`) |
| OpenAI | api.openai.com | `OPENAI_API_KEY` |
| Tavily | tavily.com | Free key (`TAVILY_API_KEY`, optional) |

## LLM Stack
- **Primary model**: `gpt-4o` — used by fund_analysis, risk_flagging, memo_generation, enforcement, news_research, comparables, ic_scorecard
- **Fast model**: `gpt-4o-mini` — used by firm_resolver and conversational steps
- **Client**: `tools/llm_client.py` — `LLMClient` wraps `openai.OpenAI`

## Running Locally
```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY, FRED_API_KEY, TAVILY_API_KEY
streamlit run app.py   # Streamlit UI
python main.py "AQR Capital Management"  # CLI
```

## Running Tests
```bash
pytest tests/ -v --cov=tools --cov=agents --cov-report=term-missing
```

## Branch Strategy
- `main` — production, protected (requires PR + CI pass)
- `dev` — integration branch, merge features here first
- `feature/<name>-<task>` — individual feature work

## Environment Variables
```
OPENAI_API_KEY    # required — GPT-4o for all agent LLM calls
FRED_API_KEY      # optional — macro context (free at fred.stlouisfed.org)
TAVILY_API_KEY    # optional — news/web search (free tier at tavily.com)
```

## Streamlit Cloud Secrets (share.streamlit.io)
```toml
OPENAI_API_KEY = "sk-..."
FRED_API_KEY = "..."
TAVILY_API_KEY = "..."
```
