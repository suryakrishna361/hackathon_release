"""
Agent 3 — Rollout Strategy Decision
Reads Agent 1 and Agent 2 output from context and decides:
  - whether to allow promotion at all
  - which deployment strategy to use (canary / blue-green / block)
No external tools needed — this agent reasons purely from prior agents' evidence.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import anthropic
from agents.base import extract_json
from agents.shared_context import ReleaseContext

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """You are a deployment strategy AI. You receive a risk assessment and a
CI validation report, and you decide whether and how to deploy the candidate.

Deployment strategy guidelines:
- block: risk=critical OR tests_passed=False with renamed env vars → DO NOT deploy
- canary: risk=high OR any validation warnings → deploy to 10% traffic, monitor closely
- blue-green: risk=medium → deploy alongside stable, switch traffic only after health verified
- direct: risk=low AND tests_passed=True AND no warnings → standard rolling deploy

Output ONLY this JSON:
{
  "rollout_strategy": "canary|blue-green|direct|block",
  "promotion_allowed": true,
  "strategy_reasoning": "2-3 sentences explaining your choice"
}
"""


def run(ctx: ReleaseContext) -> ReleaseContext:
    ctx.log("agent3", "Deciding rollout strategy...")

    client = anthropic.Anthropic()

    # Build a summary from prior agents' findings (no tool calls needed)
    summary = f"""
Risk Assessment (Agent 1):
  - Affected services: {ctx.affected_services}
  - Risk level: {ctx.risk_level}
  - Suspected failure: {ctx.suspected_failure}
  - Risk reasoning: {ctx.risk_reasoning}
  - Confidence: {ctx.risk_confidence:.0%}

CI Validation (Agent 2):
  - Tests passed: {ctx.tests_passed}
  - Config compatible: {ctx.config_compatible}
  - Missing env vars: {ctx.missing_env_vars}
  - Renamed env vars: {ctx.renamed_env_vars}
  - Warnings: {ctx.validation_warnings}

Based on this evidence, decide the rollout strategy. Output ONLY the JSON.
"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": summary}],
    )

    raw = ""
    for block in response.content:
        if hasattr(block, "text"):
            raw += block.text

    result = extract_json(raw)

    ctx.rollout_strategy    = result.get("rollout_strategy", "block")
    ctx.promotion_allowed   = result.get("promotion_allowed", False)
    ctx.strategy_reasoning  = result.get("strategy_reasoning", "")

    ctx.log("agent3", f"Strategy: {ctx.rollout_strategy} | Promotion allowed: {ctx.promotion_allowed}")
    ctx.log("agent3", ctx.strategy_reasoning)
    return ctx
