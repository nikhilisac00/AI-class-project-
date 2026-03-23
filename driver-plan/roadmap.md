# Roadmap — AI Alternative Investments Research Associate

## Section 1: MVP — EDGAR Pipeline + Claude Memo (CURRENT)

**What it does:**
- Resolves firm name or CRD → IAPD ADV summary (AUM, fees, personnel, disclosures)
- Searches EDGAR for 13F filings
- Pulls macro context from FRED
- Claude Opus 4.6 + extended thinking: analysis → risk flags → memo
- Streamlit UI: firm search → progress → risk dashboard → memo viewer → download
- PAL MCP integration: optional Gemini-3-Pro consensus validation of risk flags

**Data sources:** IAPD, SEC EDGAR, FRED (all public, no auth for core features)

**Output:** Markdown DD memo + JSON bundle (raw data, analysis, risk report)

**Status:** Built

---

## Section 2: News & Earnings Context

**What it adds:**
- Web search agent pulls recent news on the GP (fundraise announcements, personnel changes, regulatory actions)
- Earnings transcript ingestion for GPs of publicly traded managers (e.g. Blackstone, Apollo, KKR)
- News summary integrated into memo Section 2 (Firm Overview) and risk flags
- Time-decay weighting: recent news weighted higher

**New agents:** NewsIngestionAgent, EarningsAgent
**New tools:** web_search_client.py (wraps search API)

---

## Section 3: Manager Universe & Peer Comparison

**What it adds:**
- Build a local SQLite database of ADV summaries for a universe of managers
- Peer comparison: AUM percentile, team size, fee structure vs. category peers
- Vintage year analysis for private fund managers
- Style drift detection: compare current 13F holdings to prior quarter

**New agents:** UniverseBuilder, PeerComparisonAgent
**New tools:** universe_db.py (SQLite wrapper)

---

## Section 4: Portfolio Monitoring Mode

**What it adds:**
- Schedule recurring runs (daily/weekly) on a watch list of managers
- Diff engine: compare new memo to prior memo, surface what changed
- Alert system: email/Slack notification on HIGH severity new flags
- LP portfolio exposure dashboard: aggregate risk across held managers

**New tools:** scheduler.py, diff_engine.py, notifier.py

---

## Section 5: MCP/AI Chief of Staff Integration

**What it adds:**
- Calendar integration: auto-schedule manager calls based on flagged items
- Email drafting: produce follow-up request letters to GPs for missing data
- Full Claude Code MCP server wrapper: expose the research pipeline as MCP tools
  so Claude can call it conversationally ("run a DD on CRD 149729")
- PAL integration deepened: use consensus for final memo sign-off across 3+ models

**New tools:** calendar_client.py, email_client.py, mcp_server.py
