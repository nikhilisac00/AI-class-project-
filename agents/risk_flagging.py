"""
Risk Flagging Agent
Scans structured analysis for red flags an LP due diligence team would care about.
All flags are derived from data — no fabricated risk signals.
"""

import json
import anthropic


SYSTEM_PROMPT = """You are a risk analyst at an institutional LP (endowment/pension/family office).
Your job is to identify red flags and areas requiring follow-up in an investment adviser's profile.

CRITICAL RULES:
1. Flags must cite specific evidence from the provided data. No generic risks.
2. If data is missing/null, flag that as a data gap — not as a risk itself.
3. Use severity levels: HIGH / MEDIUM / LOW based on LP fiduciary standards.
4. Do not invent risks. Do not speculate beyond what the data shows.
5. Keep it factual. IC teams act on these flags."""


def run(analysis: dict, raw_data: dict, client: anthropic.Anthropic) -> dict:
    """
    Produce a structured risk flags report.

    Args:
        analysis: Output from fund_analysis.run()
        raw_data: Original ingested data
        client:   Anthropic client

    Returns:
        risk_report dict
    """
    user_message = f"""
Review the following investment adviser analysis and identify risk flags for LP due diligence.

<analysis>
{json.dumps(analysis, indent=2, default=str)}
</analysis>

<raw_data_errors>
{json.dumps(raw_data.get("errors", []), indent=2)}
</raw_data_errors>

Return ONLY a JSON object:
{{
  "overall_risk_tier": "HIGH / MEDIUM / LOW — based on flags found",
  "flags": [
    {{
      "category": "one of: Regulatory | Concentration | Key Person | Fee/Structure | Disclosure | Data Gap | Operational",
      "severity": "HIGH / MEDIUM / LOW",
      "finding": "specific factual observation from the data",
      "evidence": "quote or reference the exact data field/value that supports this",
      "lp_action": "recommended next step for the diligence team"
    }}
  ],
  "clean_items": [
    "list of areas that appear clean based on available data (with caveat if limited data)"
  ],
  "critical_data_gaps": [
    "list of fields that are null/missing but would be material to LP decision"
  ],
  "overall_commentary": "2-3 sentence factual summary for IC memo. No fluff."
}}

Categories to check (flag only if there is actual evidence):
- Regulatory disclosures / disciplinary history
- Key person concentration (ownership %, number of advisers)
- AUM relative to team size
- Fee structure anomalies
- Missing material disclosures
- Registration gaps or lapses
- Macro environment risks for this strategy type
"""

    print("[Risk Flagging] Calling Claude (extended thinking)...")
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=6000,
        thinking={
            "type": "enabled",
            "budget_tokens": 4000,
        },
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    result_text = ""
    for block in response.content:
        if block.type == "text":
            result_text = block.text.strip()
            break

    if result_text.startswith("```"):
        lines = result_text.split("\n")
        result_text = "\n".join(lines[1:-1])

    try:
        risk_report = json.loads(result_text)
    except json.JSONDecodeError as e:
        print(f"[Risk Flagging] JSON parse error: {e}")
        risk_report = {"raw_response": result_text, "parse_error": str(e)}

    return risk_report
