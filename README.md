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
3. **Flags risks**: regulatory disclosures, key person concentration, data gaps, structural issues
4. **Generates** a structured 11-section memo formatted for IC review

No hallucination. Every fact in the memo traces to a real API response. Missing fields return `null`.

---

## Architecture

```
app.py / main.py
├── Agent 1: Data Ingestion   → IAPD + EDGAR 13F XML + FRED (no LLM)
├── Agent 2: Fund Analysis    → OpenAI (gpt-4o)
├── Agent 3: Risk Flagging    → OpenAI (gpt-4o)
└── Agent 4: Memo Generation  → OpenAI (gpt-4o)
```

See [`docs/research-brief.md`](docs/research-brief.md) for full architecture and data source mapping.

---

## Data Sources

| Source | What It Provides | Auth |
|--------|-----------------|------|
| [IAPD](https://adviserinfo.sec.gov) | Registration status, disclosure flags, brochure metadata | None |
| [SEC EDGAR 13F](https://data.sec.gov) | Portfolio value (USD), holdings count — proxy AUM | None |
| [FRED](https://fred.stlouisfed.org) | Fed funds rate, 10Y yield, HY spread, VIX | Free key |
| OpenAI GPT-4o | Fund analysis, risk flagging, memo generation | API key |

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
#   TAVILY_API_KEY=your_key     (optional — free at tavily.com)
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
```

---

## Running Tests

```bash
pip install pytest pytest-cov
pytest tests/ -v --cov=tools --cov=agents --cov-report=term-missing
```

---

## Output

Each run saves four files to `./output/memos/`:

```
20260324_120000_AQR_Capital_Management_DD_MEMO.md
20260324_120000_AQR_Capital_Management_analysis.json
20260324_120000_AQR_Capital_Management_risk_report.json
20260324_120000_AQR_Capital_Management_raw_data.json
```

### Memo Sections
1. Header (firm, CRD, date, data sources)
2. Executive Summary
3. Firm Overview
4. Investment Team
5. Fee Structure
6. Regulatory & Compliance
7. Risk Flags Table (Category | Severity | Finding | Action)
8. Macro Context
9. Data Gaps & Limitations
10. Next Steps
11. Appendix: Data Quality Log

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
- Data gaps surface as LP action items (e.g., "request audited financials")
- Raw API responses saved alongside memo — every claim is auditable

---

## What This Does Not Do

- **Fund performance**: Private returns are not public. The system flags this and generates a standard GP ask.
- **Proprietary databases**: No Preqin, PitchBook, Bloomberg (planned: financialdatasets.ai, LSEG)
- **Real-time news**: Tavily/DuckDuckGo web search available when `TAVILY_API_KEY` is set

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key for GPT-4o |
| `FRED_API_KEY` | No | Free FRED key — adds macro context |
| `TAVILY_API_KEY` | No | Free Tavily key — adds news/web search |

---

*AI Finance class project · OpenAI GPT-4o · SEC EDGAR · IAPD · FRED*
