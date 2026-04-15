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
import os
import sys
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
from tools.llm_client    import make_client
from tools.reconciliation import run_all as reconcile_sources

load_dotenv()
console = Console()


def validate_env() -> str:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        console.print("[bold red]Error:[/] ANTHROPIC_API_KEY not set. Add it to .env")
        sys.exit(1)
    return key


def save_outputs(firm_name: str, raw_data: dict, analysis: dict,
                 risk_report: dict, memo: str, output_dir: str):
    """Save all agent outputs to timestamped files."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in firm_name)[:40]
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
        help="Only run data ingestion, skip Claude analysis",
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
    args = parser.parse_args()

    api_key = validate_env()
    client  = make_client(api_key)
    fred_key = None if args.no_fred else os.getenv("FRED_API_KEY")

    tavily_key = os.getenv("TAVILY_API_KEY")

    console.print(Panel(
        f"[bold]AI Alternatives Research Associate[/]\n"
        f"Target: [cyan]{args.firm}[/]\n"
        f"Model: OpenAI GPT-4o\n"
        f"Sources: IAPD · SEC EDGAR · {'FRED' if not args.no_fred else 'FRED skipped'}"
        f" · {'News (' + ('Tavily' if tavily_key else 'DuckDuckGo') + ')' if not args.no_news else 'News skipped'}",
        title="Starting Analysis",
        expand=False,
    ))

    # ── Agent 1: Data Ingestion ───────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as p:
        task = p.add_task("Ingesting data from EDGAR / IAPD / FRED...", total=None)
        raw_data = ingestion_agent.run(args.firm, fred_api_key=fred_key)
        p.update(task, description="Data ingestion complete", completed=True)

    firm_name = (
        raw_data.get("adv_summary", {}).get("firm_name")
        or raw_data.get("search_results", [{}])[0].get("firm_name", args.firm)
        if raw_data.get("search_results")
        else args.firm
    )

    if raw_data["errors"]:
        console.print(f"\n[yellow]Ingestion warnings:[/] {raw_data['errors']}")

    if args.raw_only:
        out = Path(args.output_dir) / f"raw_{firm_name}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(raw_data, indent=2, default=str))
        console.print(f"\nRaw data saved to: {out}")
        return

    # ── Agent 2: Fund Analysis ────────────────────────────────────────────────

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as p:
        task = p.add_task("Running fund analysis (GPT-4o reasoning)...", total=None)
        analysis = analysis_agent.run(raw_data, client)
        p.update(task, description="Fund analysis complete", completed=True)

    # Cross-source reconciliation
    recon_results = reconcile_sources(analysis, raw_data)
    raw_data["reconciliation"] = recon_results
    for r in recon_results:
        icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗", "SKIP": "–"}.get(r["status"], "?")
        console.print(f"  [dim]{icon} {r['check']}: {r['status']} — {r['detail'][:80]}...[/dim]"
                      if len(r["detail"]) > 80 else
                      f"  [dim]{icon} {r['check']}: {r['status']} — {r['detail']}[/dim]")

    # ── Agent 3: News Research (Karpathy autoresearch) ────────────────────────
    news_report = None
    if not args.no_news:
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                      console=console) as p:
            task = p.add_task(
                f"Deep news research ({args.news_rounds} rounds, "
                f"{'Tavily' if tavily_key else 'DuckDuckGo'})...",
                total=None,
            )
            news_report = news_agent.run(
                firm_name=firm_name,
                analysis=analysis,
                client=client,
                tavily_api_key=tavily_key,
                max_rounds=args.news_rounds,
            )
            p.update(task, description=(
                f"News research complete — "
                f"{news_report['research_rounds']} rounds, "
                f"{news_report['total_sources']} sources"
            ), completed=True)

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

    # ── Agent 4: Risk Flagging ────────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as p:
        task = p.add_task("Running risk flagging (GPT-4o reasoning)...", total=None)
        risk_report = risk_agent.run(analysis, raw_data, client, news_report=news_report)
        p.update(task, description="Risk flagging complete", completed=True)

    print_risk_summary(risk_report)

    # ── Agent 5: Memo Generation ──────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as p:
        task = p.add_task("Generating DD memo (GPT-4o reasoning)...", total=None)
        memo = memo_agent.run(analysis, risk_report, raw_data, client,
                              news_report=news_report)
        p.update(task, description="Memo generation complete", completed=True)

    # ── Agent 6: IC Scorecard ─────────────────────────────────────────────────
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as p:
        task = p.add_task("Generating IC Scorecard (GPT-4o reasoning)...", total=None)
        scorecard = scorecard_agent.run(analysis, risk_report, raw_data, client,
                                        news_report=news_report)
        p.update(task, description="IC Scorecard complete", completed=True)

    rec       = scorecard.get("recommendation", "UNKNOWN")
    overall   = scorecard.get("overall_score", "—")
    conf      = scorecard.get("confidence", "—")
    rec_color = {"PROCEED": "green", "REQUEST MORE INFO": "yellow", "PASS": "red"}.get(rec, "white")
    console.print(f"\n[bold {rec_color}]IC Recommendation: {rec}[/]  "
                  f"(Score: {overall}/10 · Confidence: {conf})")
    if scorecard.get("recommendation_summary"):
        console.print(f"[dim]{scorecard['recommendation_summary']}[/]")

    # ── Save outputs ──────────────────────────────────────────────────────────
    memo_path = save_outputs(
        firm_name, raw_data, analysis, risk_report, memo, args.output_dir
    )
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in firm_name)[:40]
    if news_report:
        news_path = Path(args.output_dir) / f"{ts}_{safe_name}_news_report.json"
        news_path.write_text(json.dumps(news_report, indent=2, default=str), encoding="utf-8")
    scorecard_path = Path(args.output_dir) / f"{ts}_{safe_name}_ic_scorecard.json"
    scorecard_path.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")

    # ── Agent 7: Comparables ──────────────────────────────────────────────────
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
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as p:
        task = p.add_task("Research Director review (GPT-4o reasoning)...", total=None)
        director_review = director_agent.run(
            analysis, risk_report, raw_data, scorecard, client,
            news_report=news_report,
        )
        p.update(task, description="Director review complete", completed=True)

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
