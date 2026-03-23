# Product Overview — AI Alternative Investments Research Associate

## Vision

An autonomous agent system that does the job of a junior alternatives research analyst.
It ingests real public data, reasons over it carefully, and produces structured LP-grade
due diligence memos — the output a real IC expects, not a dashboard.

## User

Allocators who employ (or used to employ) junior analysts to prepare first-pass DD:
- Family offices
- Endowments and foundations
- Fund-of-funds
- Placement agents screening managers

Primary user: someone who spent years producing exactly this output and knows what
"good" looks like. They can evaluate the memo critically.

## Problem

Junior analyst work in alternatives is:
- Slow (4-8 hours per manager for a solid first-pass)
- Expensive ($80-150K/year for a capable analyst)
- Inconsistent (depends on individual analyst quality)
- Bottlenecked (one analyst = one memo at a time)

The public data is all there — IAPD, SEC EDGAR, FRED — but stitching it together into
a coherent memo takes time and judgment.

## Solution

A multi-agent Python system that:
1. Resolves a firm name or CRD number to real IAPD/EDGAR data
2. Extracts structured fields: AUM, team, fees, disclosures, registrations
3. Runs risk flagging calibrated to LP due diligence standards
4. Generates a structured memo with explicit data provenance

No hallucination. Every claim in the memo traces to a real API response.
Missing data is surfaced as data gaps — not filled with estimates.

## Architecture

```
main.py / app.py (CLI or Streamlit UI)
    |
    +-- Agent 1: Data Ingestion
    |       IAPD API → ADV summary
    |       SEC EDGAR → 13F filings
    |       FRED API → macro context
    |
    +-- Agent 2: Fund Analysis  (Claude Opus 4.6 + extended thinking)
    |       Structured JSON output, null-safe
    |
    +-- Agent 3: Risk Flagging  (Claude Opus 4.6 + extended thinking)
    |       Evidence-cited flags, severity tiers
    |       Optional: PAL MCP consensus validation (Gemini-3-Pro)
    |
    +-- Agent 4: Memo Generation (Claude Opus 4.6 + extended thinking)
            Formatted markdown memo
            Explicit data gap section
            Next steps for diligence team
```

## Success Criteria

- Memo is factually grounded: zero invented numbers
- Risk flags cite specific evidence from the data
- Data gaps are surfaced, not papered over
- Memo format matches what LPs actually use for IC review
- Runs end-to-end in under 5 minutes on a public fund
