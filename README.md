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
6. **Generates** a structured 12-section memo formatted for IC review
7. **Scores** the manager on an IC scorecard with a PROCEED / REQUEST MORE INFO / PASS recommendation
8. **Finds** comparable managers via IAPD peer search
9. **Reviews** the full package through a Research Director quality gate

No hallucination. Every fact in the memo traces to a real API response. Missing fields return `null`.

---

## Architecture

```
app.py / main.py
├── Firm Resolver              → fuzzy + token scoring to resolve firm name/CRD (no LLM)
├── Data Ingestion             → IAPD + EDGAR 13F XML + ADV PDF + FRED (no LLM)
│   ├── Fund Discovery         → GPT-4o tool-use over Form D + IAPD relying advisors
│   ├── Enforcement            → GPT-4o + EDGAR/web search, agentic query adaptation
│   ├── ADV Section 7.B parser → private fund list from ADV Part 1A PDF
│   ├── 13F XML parser         → portfolio value, holdings, QoQ history
│   ├── Brochure downloader    → ADV Part 2A text extraction (best-effort)
│   └── Cross-source reconciler→ 13F vs ADV AUM · Form D vs Section 7.B
├── Fund Analysis              → OpenAI GPT-4o (agentic RAG over raw data)
├── News Research              → OpenAI GPT-4o + web search tool loop
├── Risk Flagging              → OpenAI GPT-4o
├── Memo Generation            → OpenAI GPT-4o
│   ├── Fact Checker           → deterministic + narrative verification (shown in Memo tab)
│   └── PAL Consensus          → optional Gemini-3-Pro via MCP (shown in Memo tab)
├── IC Scorecard               → OpenAI GPT-4o
├── Comparables                → IAPD peer search (no LLM)
├── Comparison                 → GPT-4o side-by-side manager comparison
├── Portfolio Fit              → GPT-4o LP portfolio scoring
└── Research Director          → OpenAI GPT-4o (final quality gate)
```

**Harness features:** crash-resumable pipeline (raw data cached to `.cache/`), per-agent cost and latency logging (`logs/trace.jsonl`), schema validation with retry.

See [`docs/research-brief.md`](docs/research-brief.md) for full architecture and data source mapping.

---

## Agents

The pipeline is composed of 14 specialized agents organized into four stages. Fund Discovery and Enforcement run inside the Data Ingestion step; Fact Checker and PAL Consensus appear as collapsible panels inside the Memo tab rather than standalone tabs.

### Orchestration

| Agent | File | Description |
|---|---|---|
| **Research Director** | `agents/research_director.py` | Final quality gate — reads all prior agent outputs, challenges inconsistencies, flags gaps the other agents missed, and confirms or overrides the IC recommendation |

### Data Collection

| Agent | File | Description |
|---|---|---|
| **Data Ingestion** | `agents/data_ingestion.py` | Orchestrates all data pulls for a given firm (EDGAR, IAPD, FRED, ADV PDF); steps 3–7 run in parallel via `ThreadPoolExecutor` |
| **Firm Resolver** | `agents/firm_resolver.py` | Resolves a rough user input (e.g. "Blackstone") to the correct SEC-registered entity name and CRD number using fuzzy + token scoring — no LLM |
| **Fund Discovery** | `agents/fund_discovery.py` | Agentic — GPT-4o uses tool-use to autonomously search EDGAR Form D filings, web, and IAPD relying advisors, trying name variants until confident it has found all discoverable funds |

### Analysis

| Agent | File | Description |
|---|---|---|
| **Fund Analysis** | `agents/fund_analysis.py` | Agentic RAG — GPT-4o issues 6–10 targeted `retrieve()` calls per pass to pull only relevant data chunks, then produces structured JSON (strategy, fees, personnel, 13F holdings) |
| **Comparables** | `agents/comparables.py` | Finds peer investment managers from the IAPD universe and builds a side-by-side benchmarking table — no LLM, pure IAPD search + scoring |
| **Comparison** | `agents/comparison.py` | Side-by-side comparison of two managers across all LP due diligence dimensions with a per-dimension winner recommendation |
| **Portfolio Fit** | `agents/portfolio_fit.py` | Scores how well a candidate manager fits an LP's existing portfolio across strategy overlap, geographic diversification, vintage exposure, size fit, and risk budget |

### Risk & Compliance

| Agent | File | Description |
|---|---|---|
| **Risk Flagging** | `agents/risk_flagging.py` | Reasoning agent — GPT-4o contextualizes risk flags (enforcement history, regulatory disclosures, pattern recognition) using an LP risk framework |
| **Enforcement** | `agents/enforcement.py` | Agentic — GPT-4o autonomously investigates regulatory history via targeted web search and EDGAR, adapting queries based on what it finds |
| **News Research** | `agents/news_research.py` | Agentic — GPT-4o loops through web searches, adapting queries based on findings, and stops when it has sufficient coverage |
| **Fact Checker** | `agents/fact_checker.py` | Deterministic checks comparing raw API data against LLM-generated analysis to detect hallucinations, transcription errors, and data drift before the memo reaches the IC |

### Output

| Agent | File | Description |
|---|---|---|
| **IC Scorecard** | `agents/ic_scorecard.py` | Synthesizes all prior agent outputs into a structured IC verdict: recommendation (PROCEED / REQUEST MORE INFO / PASS), confidence, dimension scores, and minimum diligence checklist |
| **Memo Generation** | `agents/memo_generation.py` | The only agent that produces narrative prose — synthesizes all structured JSON outputs into the final IC-ready due diligence memo in markdown |


---

## Streamlit UI Tabs

The Streamlit app (`app.py`) organises results into 13 tabs:

| Tab | What it shows |
|-----|--------------|
| **DD Memo** | Full 12-section markdown memo; Fact Checker and PAL Consensus are collapsible panels inside this tab |
| **IC Scorecard** | PROCEED / REQUEST MORE INFO / PASS verdict, confidence score, dimension breakdown |
| **Risk Dashboard** | Risk flag summary with severity tiers |
| **Director Review** | Research Director quality-gate verdict and override notes |
| **Comparables** | Side-by-side IAPD peer benchmarking table |
| **Funds** | Private fund list from ADV Section 7.B cross-referenced with Form D |
| **News** | Web-sourced news and personnel change flags |
| **Raw Data** | Full JSON from every API call — every memo claim is auditable here |
| **AI Assistant** | In-app chat against the research package |
| **Portfolio Fit** | LP portfolio fit score across strategy, geography, vintage, size, and risk budget |
| **Compare** | Side-by-side comparison of two managers with per-dimension winner |
| **Watch List** | Saved managers for ongoing monitoring |
| **Enforcement** | Regulatory history, EDGAR enforcement-adjacent filings, web enforcement search |

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