# AI Alternative Investments Research Associate — Claude Code Context

## Project Purpose
Autonomous multi-agent system that performs LP-grade due diligence on investment managers.
Input: fund name or CRD number. Output: structured DD memo ready for IC review.

## Architecture
```
app.py              ← Streamlit UI (main entry point)
main.py             ← CLI entry point
agents/
  data_ingestion.py ← Step 1: pulls IAPD + EDGAR 13F + FRED data
  fund_analysis.py  ← Step 2: GPT-4o structured analysis
  risk_flagging.py  ← Step 3: GPT-4o LP risk flags
  memo_generation.py← Step 4: GPT-4o IC-ready memo
tools/
  edgar_client.py   ← IAPD search + EDGAR EFTS + ADV summary parser
  adv_parser.py     ← 13F XML parser + IAPD disclosure parser
  fred_client.py    ← FRED macro series (rates, spreads, VIX)
  llm_client.py     ← LLMClient wrapper (OpenAI GPT-4o)
  pal_client.py     ← PAL MCP optional consensus (not required)
tests/              ← pytest suite (run: pytest tests/ -v --cov=tools --cov=agents)
docs/               ← Research brief, architecture docs
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

## Running Locally
```bash
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY and FRED_API_KEY
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
OPENAI_API_KEY     # required for all agent calls
FRED_API_KEY       # optional — macro context (free at fred.stlouisfed.org)
```

## Streamlit Cloud Secrets (share.streamlit.io)
```toml
OPENAI_API_KEY = "sk-..."
FRED_API_KEY = "..."
```
