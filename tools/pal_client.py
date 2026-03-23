"""
PAL MCP Client
Wraps the PAL MCP server tools for use within the Python pipeline.

PAL runs as a stdio MCP server. This client spawns it as a subprocess
and communicates via the MCP JSON-RPC protocol.

If PAL is not available (server not found or import error), all functions
degrade gracefully — the pipeline continues without multi-model consensus.

PAL tools used:
  - thinkdeep: deep multi-step reasoning over risk flags
  - consensus:  multi-model validation of the memo draft
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

# Path to the local PAL server installation
PAL_SERVER_DIR = Path(os.getenv("PAL_SERVER_DIR", str(Path.home() / "pal-mcp-server")))
PAL_SERVER_SCRIPT = PAL_SERVER_DIR / "server.py"


def _pal_available() -> bool:
    return PAL_SERVER_SCRIPT.exists()


async def _call_pal_tool(tool_name: str, arguments: dict) -> str | None:
    """
    Spawn the PAL MCP server as a subprocess and call one tool via stdio.
    Returns the text content of the tool result, or None on failure.
    """
    if not _pal_available():
        print(f"[PAL] Server not found at {PAL_SERVER_SCRIPT}. Skipping.")
        return None

    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=sys.executable,
            args=[str(PAL_SERVER_SCRIPT)],
            env={**os.environ, "PYTHONPATH": str(PAL_SERVER_DIR)},
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)
                # Extract text from result content blocks
                for block in result.content:
                    if hasattr(block, "text"):
                        return block.text
                return None

    except Exception as e:
        print(f"[PAL] Tool call failed ({tool_name}): {e}")
        return None


def call_thinkdeep(problem: str, findings: str, model: str = "gemini-3-pro-preview") -> str | None:
    """
    Use PAL thinkdeep for multi-step deep reasoning on risk analysis.

    Args:
        problem:  Description of the analysis problem
        findings: Initial findings from the Claude risk agent
        model:    PAL model to use

    Returns:
        Extended reasoning text, or None if PAL unavailable
    """
    args = {
        "step": problem,
        "step_number": 1,
        "total_steps": 1,
        "next_step_required": False,
        "findings": findings,
        "hypothesis": "Risk flags identified by primary analysis require validation",
        "confidence": "medium",
        "thinking_mode": "high",
        "model": model,
        "focus_areas": ["regulatory risk", "key person risk", "fee structure", "data completeness"],
    }
    return asyncio.run(_call_pal_tool("thinkdeep", args))


def call_consensus(question: str, content: str,
                   model: str = "gemini-3-pro-preview") -> str | None:
    """
    Use PAL consensus to get a second-opinion validation of the memo.

    Args:
        question: The specific question to validate
        content:  The draft memo or risk report to review
        model:    PAL model for consensus

    Returns:
        Consensus validation text, or None if PAL unavailable
    """
    # Use PAL's chat tool for a focused validation review
    # (consensus tool calls multiple models internally)
    prompt = f"""You are validating an AI-generated investment due diligence memo.

QUESTION: {question}

CONTENT TO REVIEW:
{content}

Your job:
1. Identify any factual claims that appear unsupported or inconsistent
2. Flag any risk areas that may have been understated or overstated
3. Note any standard LP diligence items missing from the analysis
4. Rate the memo's reliability: HIGH / MEDIUM / LOW

Be specific. Reference exact sections. Do not rewrite the memo."""

    args = {
        "message": prompt,
        "model": model,
    }
    return asyncio.run(_call_pal_tool("chat", args))


def is_available() -> bool:
    """Return True if PAL MCP server is present and importable."""
    if not _pal_available():
        return False
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False
