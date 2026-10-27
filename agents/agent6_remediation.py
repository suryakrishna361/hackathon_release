"""
Agent 6 — Autonomous Remediation
Takes the action recommended by Agent 5 without human intervention.
Tools: stop_candidate, verify_stable_healthy, record_incident
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import anthropic
from agents.base import run_agent_loop, extract_json
from agents.shared_context import ReleaseContext
from tools.docker_tools import verify_stable_healthy, record_incident
from tools.docker_build_tools import stop_container, start_container, pull_image

def stop_candidate():
    return stop_container("payment-candidate")

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """You are an autonomous remediation AI. You have been given a diagnosis and
a recommended action. You must execute the remediation WITHOUT human intervention.

Available remediations:
- rollback: Stop the candidate service. Verify the stable service is healthy. Record the incident.
- fix_config: Also stop candidate (config fixes require a new deploy — flag this).
- monitor: Do NOT stop candidate; just record the incident for review.
- escalate: Stop candidate as a precaution and record with high-priority flag.

Steps for rollback (most common):
1. Call stop_candidate() to terminate the broken deployment.
2. Call verify_stable_healthy() to confirm stable is still serving correctly.
3. Call record_incident() with the full context so future agents can learn from this.

Output ONLY this JSON:
{
  "remediation_taken": "description of what you did",
  "remediation_status": "success|partial|failed",
  "recovery_verified": true
}
"""

TOOLS = [
    {
        "name": "stop_candidate",
        "description": "Stop the candidate (v2) payment service. Executes the rollback.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "verify_stable_healthy",
        "description": "Confirm the stable service is healthy and serving traffic after rollback.",
        "input_schema": {
            "type": "object",
            "properties": {
                "retries": {"type": "integer", "default": 3},
            },
        },
    },
    {
        "name": "record_incident",
        "description": "Write the full release outcome to incidents.json for future learning.",
        "input_schema": {
            "type": "object",
            "properties": {
                "context_dict": {
                    "type": "object",
                    "description": "The full release context as a dict.",
                },
            },
            "required": ["context_dict"],
        },
    },
]


def _execute_tool(name: str, inputs: dict) -> str:
    dispatch = {
        "stop_candidate":       lambda **kw: str(stop_candidate()),
        "verify_stable_healthy": verify_stable_healthy,
        "record_incident":      lambda context_dict, **kw: str(record_incident(context_dict)),
    }
    fn = dispatch.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    return str(fn(**inputs))


def run(ctx: ReleaseContext) -> ReleaseContext:
    ctx.log("agent6", f"Starting remediation — action: {ctx.recommended_action}...")

    client = anthropic.Anthropic()

    user_prompt = f"""Execute the remediation.

Diagnosis summary:
- Root cause: {ctx.likely_cause}
- Recommended action: {ctx.recommended_action}
- Confidence: {ctx.diagnosis_confidence:.0%}
- Evidence: {ctx.diagnosis_evidence}

Full context for incident record:
{ctx.to_dict()}

Take the appropriate action now and output your JSON report.
"""

    raw = run_agent_loop(
        client=client,
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tools=TOOLS,
        tool_executor=_execute_tool,
    )

    result = extract_json(raw)

    ctx.remediation_taken   = result.get("remediation_taken", "")
    ctx.remediation_status  = result.get("remediation_status", "failed")
    ctx.recovery_verified   = result.get("recovery_verified", False)

    ctx.log("agent6", f"Remediation status: {ctx.remediation_status}")
    ctx.log("agent6", f"Recovery verified: {ctx.recovery_verified}")
    ctx.log("agent6", ctx.remediation_taken)
    return ctx
