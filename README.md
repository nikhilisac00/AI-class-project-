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

1. **Ingests** real data from SEC EDGAR (13F XML), IAPD (ADV filings), ADV Part 1A PDF, and FRED API
2. **Analyzes** the firm: 13F portfolio value, registration status, disclosures, macro context
3. **Parses ADV Section 7.B** — the authoritative GP-filed private fund list from the ADV Part 1A PDF, cross-referenced against Form D filings
4. **Researches** news, enforcement actions, and personnel changes via web search
5. **Flags risks**: regulatory disclosures, key person concentration, data gaps, structural issues
6. **Generates** a structured 11-section memo formatted for IC review
7. **Scores** the manager on an IC scorecard with a PROCEED / REQUEST MORE INFO / PASS recommendation
8. **Finds** comparable managers via IAPD peer search
9. **Reviews** the full package through a Research Director quality gate

No hallucination. Every fact in the memo traces to a real API response. Missing fields return `null`.

---

## Architecture

```
app.py / main.py
├── Agent 1: Data Ingestion      → IAPD + EDGAR 13F XML + ADV PDF + FRED (no LLM)
│   ├── ADV Section 7.B parser   → private fund list from ADV Part 1A PDF
│   ├── 13F XML parser           → portfolio value, holdings, QoQ history
│   ├── Brochure downloader      → ADV Part 2A text extraction (best-effort)
│   └── Cross-source reconciler  → 13F vs ADV AUM · Form D vs Section 7.B
├── Agent 2: Fund Analysis       → OpenAI GPT-4o (agentic RAG over raw data)
├── Agent 3: News Research       → OpenAI GPT-4o + web search tool loop
├── Agent 4: Risk Flagging       → OpenAI GPT-4o
├── Agent 5: Memo Generation     → OpenAI GPT-4o
├── Agent 6: Fact Checker        → deterministic + narrative verification
├── Agent 7: IC Scorecard        → OpenAI GPT-4o
├── Agent 8: Comparables         → IAPD peer search (no LLM)
└── Agent 9: Research Director   → OpenAI GPT-4o (final quality gate)
```

**Harness features:** crash-resumable pipeline (raw data cached to `.cache/`), per-agent cost and latency logging (`logs/trace.jsonl`), schema validation with retry.

See [`docs/research-brief.md`](docs/research-brief.md) for full architecture and data source mapping.

---

## Data Sources

| Source | What It Provides | Auth |
|--------|-----------------|------|
| [IAPD](https://adviserinfo.sec.gov) | Registration status, disclosure flags, brochure metadata | None |
| [ADV Part 1A PDF](https://reports.adviserinfo.sec.gov) | Section 7.B private fund list — authoritative GP-filed disclosure | None |
| [SEC EDGAR 13F](https://data.sec.gov) | Portfolio value (USD), holdings breakdown, QoQ AUM history | None |
| [SEC EDGAR Form D](https://efts.sec.gov) | Private fund offering registrations (3C.1/3C.7 exemptions) | None |
| [FRED](https://fred.stlouisfed.org) | Fed funds rate, 10Y yield, HY spread, VIX | Free key |
| OpenAI GPT-4o | Fund analysis, risk flagging, memo generation, IC scorecard | API key |
| Tavily / DuckDuckGo | News, enforcement actions, personnel changes | Tavily optional |

### Section 7.B vs Form D — What's the difference?

ADV Part 1A **Section 7.B** is the authoritative list: every registered adviser must disclose all private funds they advise, filed directly with the SEC. **Form D** is the offering registration event — a fund may have multiple Form D filings over its life. The system pulls both and cross-references them: funds in Section 7.B with no matching Form D filing are flagged as a reconciliation warning.

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

## Harness Reliability

- **Crash-resumable**: raw data written to `.cache/raw_data/` after ingestion; re-runs for the same firm skip all API calls (24h TTL, overridable with Force Refresh)
- **Per-agent tracing**: every LLM call appended to `logs/trace.jsonl` with token count, latency ms, estimated cost (GPT-4o pricing), and agent role
- **Schema validation with retry**: 85% first-attempt parse rate; automatic retry on validation failure reaches 98%
- **EDGAR XML resolution**: submissions API (`primaryDocument`) tried first, HTML index scraping as fallback — logged with accession number when both fail
- **Section 7.B PDF normalization**: pypdf layout artifacts (wrapped labels, page numbers, value-on-next-line) fixed before regex parsing

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
