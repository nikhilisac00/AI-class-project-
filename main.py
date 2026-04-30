"""
AI Alternative Investments Research Associate
===
Autonomous agent system that produces LP-grade due diligence memos.

Usage:
    python main.py "Bridgewater Associates"
    python main.py 149729          # CRD number
    python main.py "AQR Capital"   --no-fred
    python main.py "Two Sigma"     --output-dir ./output/memos

Data sources: SEC EDGAR (IAPD/ADV + 13F), FRED API
Model: OpenAI GPT-4o
"""

import argparse
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

import agents.data_ingestion as ingestion_agent
import agents.fund_analysis as analysis_agent
import agents.news_research as news_agent
import agents.risk_flagging as risk_agent
import agents.memo_generation as memo_agent
import agents.ic_scorecard      as scorecard_agent
import agents.research_director as director_agent
import agents.comparables       as comparables_agent
import agents.fact_checker       as fact_checker_agent
from tools.llm_client     import make_client
from tools.reconciliation import run_all as reconcile_sources
from tools.trace          import set_current_firm, set_run_id
from tools.validation     import validate_firm_input
from tools.pipeline_state import PipelineState
from tools                import boundary_checks

load_dotenv()
console = Console()

# Harness seam map — which role atom and principal each agent serves
AGENT_ROLES = {
    "data_ingestion":    {"role_atom": "data_analyst",         "principal": "system_integrity"},
    "fund_analysis":     {"role_atom": "data_analyst",         "principal": "IC_committee"},
    "reconciliation":    {"role_atom": "compliance_checker",   "principal": "system_integrity"},
    "news_research":     {"role_atom": "research_synthesizer", "principal": "IC_committee"},
    "risk_flagging":     {"role_atom": "risk_assessor",        "principal": "LP_investor"},
    "memo_generation":   {"role_atom": "investment_advisor",   "principal": "IC_committee"},
    "ic_scorecard":      {"role_atom": "investment_advisor",   "principal": "IC_committee"},
    "fact_checker":      {"role_atom": "fact_verifier",        "principal": "compliance"},
    "comparables":       {"role_atom": "data_analyst",         "principal": "IC_committee"},
    "research_director": {"role_atom": "risk_assessor",        "principal": "LP_investor"},
}


def _setup_file_logging(output_dir: str, safe_name: str, ts: str) -> None:
    """Bug #24: write diagnostic output to a persistent log file."""
    log_dir = Path(output_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{ts}_{safe_name}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )
    print(f"[Logging] Writing session log to: {log_path}")


def _normalize_check_name(name: str) -> str:
    """Bug #8: normalize check names before comparison to handle LLM non-determinism."""
    return re.sub(r"[^\w]", "", (name or "").lower())


def _is_trust_low(verification: dict) -> bool:
    """Return True if the fact checker rated trust as LOW."""
    return verification.get("trust_label") == "LOW"


def _build_draft_header(score: int, timestamp: str) -> str:
    """Build the warning header prepended to DRAFT memos."""
    return (
        "> **DRAFT — DO NOT DISTRIBUTE**\n"
        f"> This memo failed automated fact-checking "
        f"(trust score: {score}/100, label: LOW).\n"
        "> It requires manual review before IC submission.\n"
        f"> Generated: {timestamp}\n"
        "---\n\n"
    )


def validate_env() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        console.print("[bold red]Error:[/] OPENAI_API_KEY not set. Add it to .env")
        sys.exit(1)
    return key


def save_outputs(firm_name: str, raw_data: dict, analysis: dict,
                 risk_report: dict, memo: str, output_dir: str,
                 ts: str, safe_name: str):
    """Save core agent outputs to timestamped files."""
    base = Path(output_dir) / f"{ts}_{safe_name}"
    base.parent.mkdir(parents=True, exist_ok=True)

    (base.parent / f"{base.name}_raw_data.json").write_text(
        json.dumps(raw_data, indent=2, default=str), encoding="utf-8"
    )
    (base.parent / f"{base.name}_analysis.json").write_text(
        json.dumps(analysis, indent=2, default=str), encoding="utf-8"
    )
    (base.parent / f"{base.name}_risk_report.json").write_text(
        json.dumps(risk_report, indent=2, default=str), encoding="utf-8"
    )
    memo_path = base.parent / f"{base.name}_DD_MEMO.md"
    memo_path.write_text(memo, encoding="utf-8")

    return memo_path


def print_risk_summary(risk_report: dict):
    """Print a risk flag table to the console."""
    tier = risk_report.get("overall_risk_tier", "UNKNOWN")
    color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(tier, "white")
    console.print(f"\n[bold {color}]Overall Risk Tier: {tier}[/]\n")

    flags = risk_report.get("flags", [])
    if flags:
        table = Table(title="Risk Flags", show_lines=True)
        table.add_column("Category", style="cyan", width=14)
        table.add_column("Severity", width=8)
        table.add_column("Finding", width=45)
        table.add_column("LP Action", width=30)

        sev_colors = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}
        for f in flags:
            sev = f.get("severity", "")
            table.add_row(
                f.get("category", ""),
                f"[{sev_colors.get(sev, 'white')}]{sev}[/]",
                f.get("finding", ""),
                f.get("lp_action", ""),
            )
        console.print(table)

    gaps = risk_report.get("critical_data_gaps", [])
    if gaps:
        console.print("\n[bold yellow]Critical Data Gaps:[/]")
        for g in gaps:
            console.print(f"  • {g}")


def main():
    parser = argparse.ArgumentParser(
        description="AI Alternative Investments Research Associate"
    )
    parser.add_argument(
        "firm",
        help="Firm name (e.g. 'AQR Capital Management') or CRD number",
    )
    parser.add_argument(
        "--no-fred",
        action="store_true",
        help="Skip FRED macro data pull (useful if no FRED API key)",
    )
    parser.add_argument(
        "--output-dir",
        default="./output/memos",
        help="Directory to save memo and JSON outputs (default: ./output/memos)",
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Only run data ingestion, skip LLM analysis",
    )
    parser.add_argument(
        "--no-news",
        action="store_true",
        help="Skip news research agent (faster; requires no TAVILY_API_KEY)",
    )
    parser.add_argument(
        "--news-rounds",
        type=int,
        default=3,
        help="Max research rounds for news agent (default: 3)",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Bypass cached raw data and re-fetch from all sources",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from a saved ingestion checkpoint instead of re-fetching from EDGAR/IAPD/FRED",
    )
    args = parser.parse_args()

    try:
        args.firm = validate_firm_input(args.firm)
    except ValueError as exc:
        console.print(f"[bold red]Input error:[/] {exc}")
        sys.exit(1)

    api_key  = validate_env()

    # Generate run-level correlation ID for trace
    run_id = str(uuid.uuid4())
    set_run_id(run_id)

    client   = make_client(api_key)
    fred_key = None if args.no_fred else os.getenv("FRED_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")

    # Bug #24: set up file logging early so all print/log output is persisted
    _ts_early   = datetime.now().strftime("%Y%m%d_%H%M%S")
    _safe_early = "".join(c if c.isalnum() or c in "_ -" else "_" for c in args.firm)[:40]
    _setup_file_logging(args.output_dir, _safe_early, _ts_early)

    # Harness session state — checkpoint every agent so the pipeline can resume
    # from any completed step after a crash (Agent = Model + Harness, Fowler 2026)
    state = PipelineState(Path(args.output_dir) / f"{_safe_early}_session")

    console.print(Panel(
        f"[bold]AI Alternatives Research Associate[/]\n"
        f"Target: [cyan]{args.firm}[/]\n"
        f"Model: {client.model}\n"
        f"Sources: IAPD · SEC EDGAR · {'FRED' if not args.no_fred else 'FRED skipped'}"
        f" · {'News (' + ('Tavily' if tavily_key else 'DuckDuckGo') + ')' if not args.no_news else 'News skipped'}",
        title="Starting Analysis",
        expand=False,
    ))

    # ── Agent 1: Data Ingestion ────────────────────────────────────────────────
    set_current_firm(args.firm)

    if args.resume and state.completed("raw_data"):
        console.print(f"[dim]Resuming: raw_data ← {state.session_dir}[/]")
        raw_data = state.load("raw_data")
    else:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as p:
            task = p.add_task("Ingesting data from EDGAR / IAPD / FRED...", total=None)
            raw_data = ingestion_agent.run(args.firm, fred_api_key=fred_key,
                                           force_refresh=args.force_refresh)
            p.update(task, description="Data ingestion complete", completed=True)
        state.save("raw_data", raw_data)
        console.print(f"[dim]Checkpoint: raw_data → {state.session_dir}[/]")

    firm_name = (
        raw_data.get("adv_summary", {}).get("firm_name")
        or raw_data.get("search_results", [{}])[0].get("firm_name", args.firm)
        if raw_data.get("search_results")
        else args.firm
    )
    # Update trace context with resolved CRD for downstream LLM calls
    if raw_data.get("crd"):
        set_current_firm(raw_data["crd"])

    if raw_data["errors"]:
        console.print(f"\n[yellow]Ingestion warnings:[/] {raw_data['errors']}")

    # Bug #5: halt on critical data source failures rather than silently continuing
    if raw_data.get("critical_data_failure"):
        console.print(
            "\n[bold red]Critical data source(s) failed:[/]\n"
            + "\n".join(f"  • {e}" for e in raw_data.get("critical_failure_detail", []))
        )
        console.print(
            "[yellow]Downstream analysis would be unreliable. "
            "Use --raw-only to inspect partial data, or retry.[/]"
        )
        sys.exit(1)

    if args.raw_only:
        out = Path(args.output_dir) / f"raw_{firm_name}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(raw_data, indent=2, default=str))
        console.print(f"\nRaw data saved to: {out}")
        return

    # ── Agent 2: Fund Analysis ────────────────────────────────────────────
    if args.resume and state.completed("analysis"):
        console.print("[dim]Resuming: analysis ← session checkpoint[/]")
        analysis = state.load("analysis")
    else:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as p:
            task = p.add_task("Running fund analysis (GPT-4o reasoning)...", total=None)
            client._current_agent = "fund_analysis"
            analysis = analysis_agent.run(raw_data, client)
            client._current_agent = None
            p.update(task, description="Fund analysis complete", completed=True)

        # Boundary sensor — retry once if schema is invalid
        _analysis_errors = boundary_checks.check_analysis(analysis)
        if _analysis_errors:
            console.print(
                f"[yellow]⚠ Boundary [fund_analysis]: {len(_analysis_errors)} issue(s) — retrying[/]"
            )
            client._current_agent = "fund_analysis_retry"
            analysis = analysis_agent.run(raw_data, client)
            client._current_agent = None
            _analysis_errors = boundary_checks.check_analysis(analysis)
            if _analysis_errors:
                console.print(f"[dim]Retry still has {len(_analysis_errors)} issue(s): {_analysis_errors[:2]}[/]")

        state.save("analysis", analysis)

    # Cross-source reconciliation
    recon_results = reconcile_sources(analysis, raw_data)
    raw_data["reconciliation"] = recon_results
    for r in recon_results:
        icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗", "SKIP": "–"}.get(r["status"], "?")
        # Bug #13: detail may be None if upstream agent omitted the field
        detail = r.get("detail") or ""
        console.print(f"  [dim]{icon} {r['check']}: {r['status']} — {detail[:80]}...[/dim]"
                      if len(detail) > 80 else
                      f"  [dim]{icon} {r['check']}: {r['status']} — {detail}[/dim]")

    # ── Agent 3: News Research ────────────────────────────────────────────
    news_report = None
    if args.resume and state.completed("news_report"):
        console.print("[dim]Resuming: news_report ← session checkpoint[/]")
        news_report = state.load("news_report")
    elif not args.no_news:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as p:
            task = p.add_task(
                f"Deep news research ({args.news_rounds} rounds, "
                f"{'Tavily' if tavily_key else 'DuckDuckGo'})...",
                total=None,
            )
            client._current_agent = "news_research"
            news_report = news_agent.run(
                firm_name=firm_name,
                analysis=analysis,
                client=client,
                tavily_api_key=tavily_key,
                max_rounds=args.news_rounds,
            )
            client._current_agent = None
            p.update(task, description=(
                f"News research complete — "
                f"{news_report['research_rounds']} rounds, "
                f"{news_report['total_sources']} sources"
            ), completed=True)

        # Boundary sensor
        _news_errors = boundary_checks.check_news_report(news_report)
        if _news_errors:
            console.print(f"[yellow]⚠ Boundary [news_research]: {_news_errors} — retrying[/]")
            client._current_agent = "news_research_retry"
            news_report = news_agent.run(
                firm_name=firm_name, analysis=analysis, client=client,
                tavily_api_key=tavily_key, max_rounds=args.news_rounds,
            )
            client._current_agent = None
            _news_errors2 = boundary_checks.check_news_report(news_report)
            if _news_errors2:
                console.print(f"[dim]Retry still has issues: {_news_errors2}[/]")

        state.save("news_report", news_report)

    if news_report:
        if news_report.get("errors"):
            console.print(f"\n[yellow]News research warnings:[/] {news_report['errors']}")

        risk_color = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(
            news_report.get("overall_news_risk", ""), "white"
        )
        console.print(
            f"\n[bold {risk_color}]News Risk: "
            f"{news_report.get('overall_news_risk', 'UNKNOWN')}[/] — "
            f"{len(news_report.get('news_flags', []))} flags, "
            f"{news_report.get('total_sources', 0)} sources"
        )

    # ── Agent 4: Risk Flagging ────────────────────────────────────────────
    if args.resume and state.completed("risk_report"):
        console.print("[dim]Resuming: risk_report ← session checkpoint[/]")
        risk_report = state.load("risk_report")
    else:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as p:
            task = p.add_task("Running risk flagging (GPT-4o reasoning)...", total=None)
            client._current_agent = "risk_flagging"
            risk_report = risk_agent.run(analysis, raw_data, client, news_report=news_report)
            client._current_agent = None
            p.update(task, description="Risk flagging complete", completed=True)

        # Boundary sensor
        _risk_errors = boundary_checks.check_risk_report(risk_report)
        if _risk_errors:
            console.print(f"[yellow]⚠ Boundary [risk_flagging]: {_risk_errors} — retrying[/]")
            client._current_agent = "risk_flagging_retry"
            risk_report = risk_agent.run(analysis, raw_data, client, news_report=news_report)
            client._current_agent = None
            _risk_errors2 = boundary_checks.check_risk_report(risk_report)
            if _risk_errors2:
                console.print(f"[dim]Retry still has issues: {_risk_errors2}[/]")

        state.save("risk_report", risk_report)

    print_risk_summary(risk_report)

    # ── Agent 5: Memo Generation ────────────────────────────────────────────
    if args.resume and state.completed("memo"):
        console.print("[dim]Resuming: memo ← session checkpoint[/]")
        memo = state.load("memo")
    else:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as p:
            task = p.add_task("Generating DD memo (GPT-4o reasoning)...", total=None)
            client._current_agent = "memo_generation"
            memo = memo_agent.run(analysis, risk_report, raw_data, client,
                                  news_report=news_report)
            client._current_agent = None
            p.update(task, description="Memo generation complete", completed=True)

        # Boundary sensor — memo must be a non-empty string
        if not memo or not isinstance(memo, str):
            console.print("[yellow]⚠ Boundary [memo_generation]: empty/invalid memo — retrying[/]")
            client._current_agent = "memo_generation_retry"
            memo = memo_agent.run(analysis, risk_report, raw_data, client,
                                  news_report=news_report)
            client._current_agent = None

        state.save("memo", memo)

    # ── Shared timestamp for all output files ────────────────────────────────────
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in firm_name)[:40]

    # ── Agent 6: IC Scorecard ──────────────────────────────────────────────
    if args.resume and state.completed("scorecard"):
        console.print("[dim]Resuming: scorecard ← session checkpoint[/]")
        scorecard = state.load("scorecard")
    else:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as p:
            task = p.add_task("Generating IC Scorecard (GPT-4o reasoning)...", total=None)
            client._current_agent = "ic_scorecard"
            scorecard = scorecard_agent.run(analysis, risk_report, raw_data, client,
                                            news_report=news_report)
            client._current_agent = None
            p.update(task, description="IC Scorecard complete", completed=True)

        # Boundary sensor
        _sc_errors = boundary_checks.check_scorecard(scorecard)
        if _sc_errors:
            console.print(f"[yellow]⚠ Boundary [ic_scorecard]: {_sc_errors} — retrying[/]")
            client._current_agent = "ic_scorecard_retry"
            scorecard = scorecard_agent.run(analysis, risk_report, raw_data, client,
                                            news_report=news_report)
            client._current_agent = None
            _sc_errors2 = boundary_checks.check_scorecard(scorecard)
            if _sc_errors2:
                console.print(f"[dim]Retry still has issues: {_sc_errors2}[/]")

        state.save("scorecard", scorecard)

    rec       = scorecard.get("recommendation", "UNKNOWN")
    overall   = scorecard.get("overall_score", "—")
    conf      = scorecard.get("confidence", "—")
    rec_color = {"PROCEED": "green", "REQUEST MORE INFO": "yellow", "PASS": "red"}.get(rec, "white")
    console.print(f"\n[bold {rec_color}]IC Recommendation: {rec}[/]  "
                  f"(Score: {overall}/10 · Confidence: {conf})")
    if scorecard.get("recommendation_summary"):
        console.print(f"[dim]{scorecard['recommendation_summary']}[/]")

    # ── Fact Checker ──────────────────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as p:
        task = p.add_task("Fact-checking memo (deterministic + narrative)...", total=None)
        client._current_agent = "fact_checker"
        verification = fact_checker_agent.run(
            analysis, risk_report, raw_data, scorecard, memo, client,
        )
        client._current_agent = None
        p.update(task, description="Fact check complete", completed=True)

    # Auto-retry memo if FAIL-level issues found
    if verification["summary"]["failures"] > 0:
        console.print(
            f"[yellow]Fact checker found {verification['summary']['failures']} "
            f"failure(s) — re-generating memo...[/]"
        )
        client._current_agent = "memo_generation_retry"
        memo = memo_agent.run(
            analysis, risk_report, raw_data, client,
            news_report=news_report,
        )
        client._current_agent = "fact_checker_retry"
        re_verification = fact_checker_agent.run(
            analysis, risk_report, raw_data, scorecard, memo, client,
        )
        client._current_agent = None
        # Bug #8: normalize check names before comparing — LLM may rephrase
        # names between runs ("AUM Consistency Check" vs "AUM Cross-Check").
        fixed = [
            c["check"] for c in verification["checks"]
            if c["status"] == "FAIL"
            and next(
                (r for r in re_verification["checks"]
                 if _normalize_check_name(r["check"]) == _normalize_check_name(c["check"])),
                {},
            ).get("status") != "FAIL"
        ]
        re_verification["retry_triggered"] = True
        re_verification["failures_fixed_on_retry"] = fixed
        verification = re_verification

    # Print trust score
    ts_color = {"HIGH": "green", "MEDIUM": "yellow", "LOW": "red"}.get(
        verification["trust_label"], "white"
    )
    console.print(
        f"\n[bold {ts_color}]Trust Score: {verification['trust_score']}/100 "
        f"({verification['trust_label']})[/] — "
        f"{verification['summary']['passed']} passed, "
        f"{verification['summary']['warnings']} warnings, "
        f"{verification['summary']['failures']} failures"
    )
    if verification.get("retry_triggered"):
        console.print(
            f"[dim]Auto-retry fixed: {verification['failures_fixed_on_retry']}[/]"
        )

    # ── DRAFT gate: refuse to serve LOW-trust memos as IC-ready ──────────
    if _is_trust_low(verification):
        console.print(
            "\n[bold red]DRAFT GATE:[/] Trust score is LOW — memo will be saved as DRAFT.\n"
            "IC Scorecard, Research Director, and Comparables will be skipped."
        )
        draft_ts = datetime.now().isoformat()
        memo = _build_draft_header(verification["trust_score"], draft_ts) + memo

        # Save as DRAFT
        base = Path(args.output_dir)
        base.mkdir(parents=True, exist_ok=True)
        draft_path = base / f"DRAFT_{ts}_{safe_name}_DD_MEMO.md"
        draft_path.write_text(memo, encoding="utf-8")

        # Still save raw data, analysis, risk report for review
        (base / f"{ts}_{safe_name}_raw_data.json").write_text(
            json.dumps(raw_data, indent=2, default=str), encoding="utf-8"
        )
        (base / f"{ts}_{safe_name}_analysis.json").write_text(
            json.dumps(analysis, indent=2, default=str), encoding="utf-8"
        )
        (base / f"{ts}_{safe_name}_risk_report.json").write_text(
            json.dumps(risk_report, indent=2, default=str), encoding="utf-8"
        )
        (base / f"{ts}_{safe_name}_verification.json").write_text(
            json.dumps(verification, indent=2, default=str), encoding="utf-8"
        )
        if news_report:
            (base / f"{ts}_{safe_name}_news_report.json").write_text(
                json.dumps(news_report, indent=2, default=str), encoding="utf-8"
            )

        console.print(Panel(
            f"[bold yellow]DRAFT memo saved.[/]\n"
            f"Path: [cyan]{draft_path}[/]\n"
            f"Trust: {verification['trust_score']}/100 (LOW)\n"
            f"Action: Manual review required before IC submission.",
            title="Draft — Not IC-Ready",
            expand=False,
        ))
        return  # Exit pipeline — do not run scorecard, director, comparables

    # ── Save outputs ──────────────────────────────────────────────────────────
    memo_path = save_outputs(
        firm_name, raw_data, analysis, risk_report, memo, args.output_dir,
        ts=ts, safe_name=safe_name,
    )
    if news_report:
        (Path(args.output_dir) / f"{ts}_{safe_name}_news_report.json").write_text(
            json.dumps(news_report, indent=2, default=str), encoding="utf-8"
        )
    (Path(args.output_dir) / f"{ts}_{safe_name}_ic_scorecard.json").write_text(
        json.dumps(scorecard, indent=2, default=str), encoding="utf-8"
    )
    (Path(args.output_dir) / f"{ts}_{safe_name}_verification.json").write_text(
        json.dumps(verification, indent=2, default=str), encoding="utf-8"
    )

    # ── Agent 7: Comparables ────────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as p:
        task = p.add_task("Finding comparable managers (IAPD)...", total=None)
        comparables = comparables_agent.run(
            firm_name=firm_name,
            adv_summary=raw_data.get("adv_summary", {}),
            raw_data=raw_data,
        )
        p.update(task, description=f"Comparables complete — {len(comparables.get('peers', []))} peers found", completed=True)

    # ── Agent 8: Research Director ────────────────────────────────────────────
    if args.resume and state.completed("director_review"):
        console.print("[dim]Resuming: director_review ← session checkpoint[/]")
        director_review = state.load("director_review")
    else:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as p:
            task = p.add_task("Research Director review (GPT-4o reasoning)...", total=None)
            client._current_agent = "research_director"
            director_review = director_agent.run(
                analysis, risk_report, raw_data, scorecard, client,
                news_report=news_report,
            )
            client._current_agent = None
            p.update(task, description="Director review complete", completed=True)

        # Boundary sensor
        _dr_errors = boundary_checks.check_director_review(director_review)
        if _dr_errors:
            console.print(f"[yellow]⚠ Boundary [research_director]: {_dr_errors} — retrying[/]")
            client._current_agent = "research_director_retry"
            director_review = director_agent.run(
                analysis, risk_report, raw_data, scorecard, client,
                news_report=news_report,
            )
            client._current_agent = None
            _dr_errors2 = boundary_checks.check_director_review(director_review)
            if _dr_errors2:
                console.print(f"[dim]Retry still has issues: {_dr_errors2}[/]")

        state.save("director_review", director_review)

    verdict = director_review.get("verdict", "UNKNOWN")
    revised = director_review.get("revised_recommendation", "")
    verdict_color = {"CONFIRMED": "green", "UPGRADED": "blue",
                     "DOWNGRADED": "red", "INCONCLUSIVE": "yellow"}.get(verdict, "white")
    console.print(f"\n[bold {verdict_color}]Director Verdict: {verdict}[/]  "
                  f"→ {revised}")
    if director_review.get("director_commentary"):
        console.print(f"[dim]{director_review['director_commentary']}[/]")

    (Path(args.output_dir) / f"{ts}_{safe_name}_comparables.json").write_text(
        json.dumps(comparables, indent=2, default=str), encoding="utf-8"
    )
    (Path(args.output_dir) / f"{ts}_{safe_name}_director_review.json").write_text(
        json.dumps(director_review, indent=2, default=str), encoding="utf-8"
    )

    # ── Harness trace: save + print per-agent cost/latency summary ────────────
    trace = client.get_trace()
    if trace:
        trace_path = Path(args.output_dir) / f"{ts}_{safe_name}_trace.json"
        trace_path.write_text(json.dumps(trace, indent=2, default=str), encoding="utf-8")

        trace_table = Table(title="Agent Trace", show_lines=True)
        trace_table.add_column("Agent", style="cyan", width=22)
        trace_table.add_column("Model", width=10)
        trace_table.add_column("Prompt tok", justify="right", width=11)
        trace_table.add_column("Completion tok", justify="right", width=14)
        trace_table.add_column("Total tok", justify="right", width=10)
        trace_table.add_column("Latency ms", justify="right", width=11)
        for row in trace:
            trace_table.add_row(
                row.get("agent") or "—",
                row.get("model") or "—",
                str(row.get("prompt_tokens") or "—"),
                str(row.get("completion_tokens") or "—"),
                str(row.get("total_tokens") or "—"),
                str(row.get("latency_ms") or "—"),
            )
        console.print(trace_table)

    console.print(Panel(
        f"[bold green]Done.[/]\n"
        f"Memo saved to: [cyan]{memo_path}[/]\n"
        f"JSON outputs in: [cyan]{memo_path.parent}/[/]",
        title="Complete",
        expand=False,
    ))

    # Print memo to console
    console.print("\n" + "─" * 80)
    console.print(memo)


if __name__ == "__main__":
    main()
