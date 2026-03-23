# AI Alternative Investments Research Associate

An autonomous multi-agent system that performs the work of a junior alternatives research analyst — ingesting real public data and producing structured LP-grade due diligence memos.

**The output is the memo. Not a dashboard.**

---

## What It Does

Given a fund name or CRD number, the system autonomously:

1. **Ingests** real data from SEC EDGAR (ADV filings, 13F filings) and FRED API
2. **Analyzes** the firm: AUM, team, fee structure, client concentration, registrations
3. **Flags risks**: regulatory disclosures, key person concentration, data gaps, structural issues
4. **Generates** a structured due diligence memo formatted for IC review

No hallucination. Every fact in the memo traces to a real API response.

---

## Architecture

```
main.py
├── Agent 1: Data Ingestion     → IAPD/EDGAR/FRED APIs (no auth for most)
├── Agent 2: Fund Analysis      → Claude Opus 4.6 + extended thinking
├── Agent 3: Risk Flagging      → Claude Opus 4.6 + extended thinking
└── Agent 4: Memo Generation    → Claude Opus 4.6 + extended thinking
```

Each agent is a separate module. Claude uses **extended thinking** to reason carefully before writing — this is the core mechanism for minimizing hallucination in financial analysis.

---

## Data Sources

| Source | What It Provides | Auth |
|--------|-----------------|------|
| [IAPD (adviserinfo.sec.gov)](https://adviserinfo.sec.gov) | ADV filings: AUM, fees, personnel, disclosures | None |
| [SEC EDGAR](https://efts.sec.gov) | 13F filings (public equity holdings) | None |
| [FRED API](https://fred.stlouisfed.org) | Macro context: rates, spreads, VIX | Free key |

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
#   ANTHROPIC_API_KEY=your_key
#   FRED_API_KEY=your_fred_key  (optional but recommended)
```

### 3. Run
```bash
# By firm name
python main.py "AQR Capital Management"

# By CRD number
python main.py 149729

# Skip FRED (no FRED API key)
python main.py "Bridgewater Associates" --no-fred

# Only pull data, skip Claude analysis
python main.py "Two Sigma" --raw-only

# Custom output directory
python main.py "Renaissance Technologies" --output-dir ./my_memos
```

---

## Output

Each run produces four files in `./output/memos/`:

```
20241201_143022_AQR Capital Management_DD_MEMO.md       ← the memo
20241201_143022_AQR Capital Management_analysis.json    ← structured analysis
20241201_143022_AQR Capital Management_risk_report.json ← risk flags
20241201_143022_AQR Capital Management_raw_data.json    ← raw API responses
```

### Memo Structure

1. Header (firm, CRD, date, data sources, status)
2. Executive Summary
3. Firm Overview (AUM, registration, team size)
4. Investment Team (personnel, ownership)
5. Fee Structure
6. Regulatory & Compliance
7. Risk Flags Table (Category | Severity | Finding | Action)
8. Macro Context (rates, spreads)
9. Data Gaps & Limitations
10. Next Steps for diligence team
11. Appendix: Data Quality Log

---

## No-Hallucination Design

- Claude is instructed to output `null` for any missing field, never estimate
- Risk flags require explicit evidence citations from the data
- Extended thinking gives Claude reasoning budget before writing
- Raw API responses are saved alongside the memo so every claim is auditable
- Data gaps are surfaced explicitly — the memo tells you what it *doesn't* know

---

## What This Does Not Do

- **Fund performance**: Private fund returns are not public. The system flags this as a data gap and notes you need direct GP engagement.
- **Real-time news**: No news/earnings scraping in MVP (next version).
- **Proprietary databases**: No Preqin, PitchBook, or Bloomberg data.

---

## Roadmap

- [ ] News & earnings transcript ingestion (web search agent)
- [ ] Peer comparison across a manager universe
- [ ] Portfolio monitoring: re-run on schedule, diff against prior memo
- [ ] Email/calendar integration (AI Chief of Staff mode)
- [ ] PDF export of final memo

---

## Get a Free FRED API Key

[https://fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html) — takes 30 seconds.

---

*Built as an AI class project. Uses Claude Opus 4.6 with extended thinking.*
