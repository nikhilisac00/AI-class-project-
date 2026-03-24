# Research Brief — AI Alternative Investments Research Associate

**Course:** AI in Finance
**Team:** AI-Class-Project
**Date:** March 2026
**Status:** Week 1 Deliverable

---

## 1. Problem Statement

Junior alternatives analysts at institutional LPs spend 40–80 hours per fund conducting initial due diligence: pulling SEC filings, verifying registration status, checking disclosure history, building a risk flag summary, and drafting an IC memo. This work is highly structured and largely deterministic — the same 30 data points are checked for every manager.

**We build an autonomous agent that does this in under 3 minutes, grounded entirely in real public data.**

---

## 2. Domain Survey — Existing Tools

| Tool | What It Does | Limitation |
|------|-------------|-----------|
| **Preqin** | Fund data, performance, LP-GP relationships | Expensive subscription; no automation |
| **PitchBook** | PE/VC data, deals, fund stats | No structured memo output; requires manual synthesis |
| **EDGAR Online** | SEC filing viewer | Human-read only; no structured extraction |
| **Visible Alpha** | Analyst consensus models | Public equities focused; not alternatives |
| **Cobalt (iCapital)** | LP due diligence platform | Closed platform; requires GP data submission |
| **Canoe Intelligence** | Document ingestion for alternatives | Processes GP-sent docs; no public data ingestion |

**Gap:** None of these autonomously pull public regulatory data → structured analysis → IC memo without human intervention.

---

## 3. Data Source Mapping

### Currently Integrated
| Source | Endpoint | Data Retrieved | Auth |
|--------|----------|---------------|------|
| **IAPD** | `api.adviserinfo.sec.gov` | CRD lookup, ADV registration, disclosure flags, brochure metadata | None |
| **SEC EDGAR EFTS** | `efts.sec.gov/LATEST/search-index` | 13F-HR filing search, CIK resolution | None |
| **SEC EDGAR Submissions** | `data.sec.gov/submissions/` | Most recent 13F-HR accession number | None |
| **SEC EDGAR Archives** | `sec.gov/Archives/edgar/data/` | 13F XML: portfolio value, holdings count | None |
| **FRED** | `api.stlouisfed.org/fred/series` | Fed funds rate, 10Y yield, HY spread, VIX | Free key |

### Planned / Course Requirements
| Source | Status | Notes |
|--------|--------|-------|
| **financialdatasets.ai** | Not integrated | API key needed from instructor |
| **LSEG Workspace** | Not integrated | Requires enterprise credentials |

### Why Current Sources Are Valid
- IAPD + EDGAR cover 100% of SEC-registered investment advisers (13,000+ firms)
- EDGAR 13F covers all managers with >$100M in US public equities (~6,000 filers)
- FRED provides real-time macro context at no cost
- No hallucination risk: all fields are null if not found in API responses

---

## 4. Gap Analysis

| Gap | Impact | Mitigation |
|-----|--------|-----------|
| Regulatory AUM not in free APIs | Missing AUM for non-13F filers | Surface as data gap in memo; use 13F as proxy |
| ADV Part 2A content (fee details, strategy) | No fee/strategy detail | Flag as required LP ask; brochure metadata shown |
| Key personnel financials | No insider ownership beyond SEC filings | Use IAPD Schedule A disclosure |
| LSEG/financialdatasets.ai not integrated | Missing alternative data enrichment | Planned for Week 3 sprint |
| Historical performance data | Funds don't disclose returns publicly | Flag as standard GP ask |

---

## 5. System Architecture

```
Input: Fund name or CRD number
        │
        ▼
┌─────────────────────────────────────────────┐
│  Agent 1: Data Ingestion                    │
│  IAPD → CRD/ADV data                        │
│  EDGAR → 13F XML (portfolio value)          │
│  FRED → macro context                       │
└────────────────────┬────────────────────────┘
                     │ raw_data dict
                     ▼
┌─────────────────────────────────────────────┐
│  Agent 2: Fund Analysis (OpenAI o3)         │
│  Structured JSON: firm overview, fees,      │
│  personnel, 13F data, macro context         │
└────────────────────┬────────────────────────┘
                     │ analysis dict
                     ▼
┌─────────────────────────────────────────────┐
│  Agent 3: Risk Flagging (OpenAI o3)         │
│  LP DD risk flags: regulatory, key person,  │
│  fee/structure, data gaps                   │
└────────────────────┬────────────────────────┘
                     │ risk_report dict
                     ▼
┌─────────────────────────────────────────────┐
│  Agent 4: Memo Generation (OpenAI o3)       │
│  11-section IC-ready DD memo in Markdown    │
└────────────────────┬────────────────────────┘
                     │
                     ▼
        Output: DD Memo (.md) + JSON bundle
```

---

## 6. Build Plan

### Week 1 (complete)
- [x] Project scaffolding, 4-agent pipeline
- [x] IAPD + EDGAR + FRED integration
- [x] Streamlit UI with fund snapshot
- [x] ADV parser: 13F portfolio value from XML
- [x] CI/CD pipeline (GitHub Actions)
- [x] Deployed to Streamlit Cloud

### Week 2 (next)
- [ ] financialdatasets.ai API integration
- [ ] Branch protection + dev → feature workflow
- [ ] Test coverage ≥ 70%
- [ ] Team Charter finalized

### Week 3
- [ ] LSEG Workspace data enrichment (if credentials available)
- [ ] Performance benchmarking across 10+ fund types
- [ ] Final presentation / demo

---

## 7. Anti-Hallucination Design

The most critical requirement for financial AI is factual grounding. Our design:

1. **All null by default** — every field initialized to `null`; only populated if found in API response
2. **Explicit data gaps** — the memo includes a dedicated "DATA GAPS" section listing every null field
3. **Source tracing** — every fact in the memo maps to a specific API call
4. **No estimation** — system prompts explicitly forbid Claude/o3 from estimating missing values
5. **LP action items** — data gaps surface as specific asks for the fund manager (audited financials, LPA, etc.)
