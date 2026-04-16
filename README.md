# AI Alternative Investments Research Associate

[![CI](https://github.com/nikhilisac00/AI-class-project-/actions/workflows/ci.yml/badge.svg)](https://github.com/nikhilisac00/AI-class-project-/actions/workflows/ci.yml)
[![Live App](https://img.shields.io/badge/Streamlit-Live%20App-FF4B4B?logo=streamlit)](https://bg7t89xzs4fa25xcgzdtwh.streamlit.app/)

An autonomous multi-agent system that performs the work of a junior alternatives research analyst — ingesting real public data and producing structured LP-grade due diligence memos.

**Input:** fund name or CRD number → **Output:** IC-ready DD memo in under 3 minutes.

---

## Live Demo

**https://bg7t89xzs4fa25xcgzdtwh.streamlit.app/**

Try: `AQR Capital Management`, `Renaissance Technologies`, `Clearlake Capital`, or any CRD number.

---

## What It Does

Given a fund name or CRD number, the system autonomously:

1. **Ingests** real data from SEC EDGAR (13F XML), IAPD (ADV filings), and FRED API
2. **Analyzes** the firm: 13F portfolio value, registration status, disclosures, macro context
3. **Researches** news, enforcement actions, and personnel changes via web search
4. **Flags risks**: regulatory disclosures, key person concentration, data gaps, structural issues
5. **Generates** a structured 11-section memo formatted for IC review
6. **Scores** the manager on an IC scorecard with a PROCEED / REQUEST MORE INFO / PASS recommendation
7. **Finds** comparable managers via IAPD peer search
8. **Reviews** the full package through a Research Director quality gate

No hallucination. Every fact in the memo traces to a real API response. Missing fields return `null`.

---

## Architecture

```
app.py / main.py
├── Agent 1: Data Ingestion      → IAPD + EDGAR 13F XML + FRED (no LLM)
├── Agent 2: Fund Analysis       → OpenAI GPT-4o
├── Agent 3: News Research       → OpenAI GPT-4o + web search tool loop
├── Agent 4: Risk Flagging       → OpenAI GPT-4o
├── Agent 5: Memo Generation     → OpenAI GPT-4o
├── Agent 6: IC Scorecard        → OpenAI GPT-4o
├── Agent 7: Comparables         → IAPD peer search (no LLM)
└── Agent 8: Research Director   → OpenAI GPT-4o (final quality gate)
```

See [`docs/research-brief.md`](docs/research-brief.md) for full architecture and data source mapping.

---

## Data Sources

| Source | What It Provides | Auth |
|--------|-----------------|------|
| [IAPD](https://adviserinfo.sec.gov) | Registration status, disclosure flags, brochure metadata | None |
| [SEC EDGAR 13F](https://data.sec.gov) | Portfolio value (USD), holdings count — proxy AUM | None |
| [FRED](https://fred.stlouisfed.org) | Fed funds rate, 10Y yield, HY spread, VIX | Free key |
| OpenAI GPT-4o | Fund analysis, risk flagging, memo generation, IC scorecard | API key |
| Tavily / DuckDuckGo | News, enforcement actions, personnel changes | Tavily optional |

---

## Quickstart

### 1. Clone & install
```bash
git clone https://github.com/nikhilisac00/AI-class-project-.git
cd AI-class-project-
pip install -r requirements.txt
```

### 2. Set up environment
```bash
cp .env.example .env
# Edit .env and add:
#   OPENAI_API_KEY=your_key
#   FRED_API_KEY=your_fred_key  (optional — free at fred.stlouisfed.org)
#   TAVILY_API_KEY=your_key     (optional — free tier at tavily.com; falls back to DuckDuckGo)
```

### 3. Run (Streamlit UI)
```bash
streamlit run app.py
```

### 4. Run (CLI)
```bash
python main.py "AQR Capital Management"
python main.py 149729                          # by CRD number
python main.py "Bridgewater" --no-fred         # skip FRED
python main.py "Two Sigma" --raw-only          # data only, skip LLM
python main.py "Citadel" --no-news             # skip news research
python main.py "KKR" --news-rounds 5           # deeper news research (default: 3)
```

---

## Running Tests

```bash
pip install pytest pytest-cov
pytest tests/ -v --cov=tools --cov=agents --cov-report=term-missing
```

---

## Output

Each full run saves eight files to `./output/memos/` (all share the same timestamp prefix):

```
20260324_120000_AQR_Capital_Management_DD_MEMO.md
20260324_120000_AQR_Capital_Management_raw_data.json
20260324_120000_AQR_Capital_Management_analysis.json
20260324_120000_AQR_Capital_Management_risk_report.json
20260324_120000_AQR_Capital_Management_news_report.json
20260324_120000_AQR_Capital_Management_ic_scorecard.json
20260324_120000_AQR_Capital_Management_comparables.json
20260324_120000_AQR_Capital_Management_director_review.json
```

`news_report.json` is omitted when `--no-news` is passed.

### Memo Sections
1. Executive Summary
2. Firm Overview
3. Investment Team
4. Fee Structure
5. Regulatory & Compliance
6. Private Funds Discovered
7. News & Press Coverage
8. Risk Flags Summary
9. Macro Context
10. Data Gaps & Limitations
11. Next Steps
12. Appendix: Data Quality Log

---

## Branch Strategy

```
main   ← production (protected — requires PR + CI pass)
dev    ← integration branch
feature/<name>-<task>  ← individual work
```

PRs from `feature/*` → `dev` → `main`. CI runs on every push.

---

## No-Hallucination Design

- All fields initialized to `null`; only populated if found in an API response
- LLM system prompts explicitly forbid estimation of missing values
- Risk flags require explicit evidence citations
- News flags require a `source_url` — unsourced claims are not included
- Data gaps surface as LP action items (e.g., "request audited financials")
- Raw API responses saved alongside memo — every claim is auditable

---

## What This Does Not Do

- **Fund performance**: Private returns are not public. The system flags this and generates a standard GP ask.
- **Proprietary databases**: No Preqin, PitchBook, Bloomberg (planned: financialdatasets.ai, LSEG)

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4o |
| `FRED_API_KEY` | No | Free FRED key — adds macro context |
| `TAVILY_API_KEY` | No | Tavily search key — better news quality; falls back to DuckDuckGo |

---

*AI Finance class project · OpenAI GPT-4o · SEC EDGAR · IAPD · FRED*
