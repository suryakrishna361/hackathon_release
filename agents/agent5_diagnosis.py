"""
Agent 5 — Failure Diagnosis
When Agent 4 sees degradation, this agent digs deeper to identify the root cause
and recommend a remediation action.
Tools: read_service_logs, get_metrics_candidate, run_synthetic_comparison,
       compare_env_vars, read_file_contents, search_incident_history
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import anthropic
from agents.base import run_agent_loop, extract_json
from agents.shared_context import ReleaseContext
from tools.metrics_tools import get_metrics_candidate, read_service_logs
from tools.synthetic_canary import run_synthetic_comparison
from tools.git_tools import compare_env_vars, read_file_contents, search_incident_history

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """You are a failure-diagnosis AI. The runtime monitor has flagged the candidate
deployment as degrading. Your job is to determine the root cause.

Approach:
1. Read candidate logs — look for timeouts, exceptions, errors.
2. Run synthetic transactions again to observe the actual error pattern.
3. Compare env vars between stable and candidate — mismatches are the #1 cause of silent failures.
4. Read the candidate source file to understand how env vars are used.
5. Search incident history for similar failures.
6. Cross-reference with what Agent 1 suspected and what Agent 2 warned about.

Common patterns to look for:
- Env var renamed: code reads OLD_VAR_NAME but only NEW_VAR_NAME is in the environment
- Timeout set to 0 or negative: service sleeps then returns error
- Missing config: service falls back to unsafe default

Output ONLY this JSON:
{
  "candidate_is_degrading": true,
  "diagnosis_confidence": 0.0,
  "likely_cause": "concise description of root cause",
  "diagnosis_evidence": ["list", "of", "evidence", "items"],
  "recommended_action": "rollback|fix_config|monitor|escalate"
}
diagnosis_confidence is 0.0 – 1.0.
recommended_action must be one of the four values above.
"""

TOOLS = [
    {
        "name": "read_service_logs",
        "description": "Read recent logs from a service container.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "default": "payment-service-candidate"},
                "lines":   {"type": "integer", "default": 30},
            },
        },
    },
    {
        "name": "run_synthetic_comparison",
        "description": "Run more synthetic transactions to observe the failure pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "default": 3},
            },
        },
    },
    {
        "name": "get_metrics_candidate",
        "description": "Get current metrics from the candidate service.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "compare_env_vars",
        "description": "Compare os.getenv() calls between stable and candidate source.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "default": "payment-service"},
            },
        },
    },
    {
        "name": "read_file_contents",
        "description": "Read a specific file from a branch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "branch":    {"type": "string", "default": "candidate"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "search_incident_history",
        "description": "Search past incidents for patterns matching this failure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
]


def _execute_tool(name: str, inputs: dict) -> str:
    dispatch = {
        "read_service_logs":       read_service_logs,
        "run_synthetic_comparison": run_synthetic_comparison,
        "get_metrics_candidate":   lambda **kw: str(get_metrics_candidate()),
        "compare_env_vars":        compare_env_vars,
        "read_file_contents":      read_file_contents,
        "search_incident_history": search_incident_history,
    }
    fn = dispatch.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    return str(fn(**inputs))


def run(ctx: ReleaseContext) -> ReleaseContext:
    ctx.log("agent5", "Starting failure diagnosis...")

    client = anthropic.Anthropic()

    user_prompt = f"""The runtime monitor reports that the candidate deployment IS degrading.

Evidence from prior agents:
- Agent 1 suspected: '{ctx.suspected_failure}' (risk: {ctx.risk_level}, confidence: {ctx.risk_confidence:.0%})
- Agent 2 found renamed env vars: {ctx.renamed_env_vars}
- Agent 2 warnings: {ctx.validation_warnings}
- Agent 4 metrics:
    Stable  p95={ctx.stable_p95_ms}ms  error={ctx.stable_error_rate:.0%}  synth_ok={ctx.synthetic_success_rate_stable:.0%}
    Candidate p95={ctx.candidate_p95_ms}ms  error={ctx.candidate_error_rate:.0%}  synth_ok={ctx.synthetic_success_rate_candidate:.0%}

Dig into the root cause. Use the tools to gather more evidence, then output your JSON diagnosis.
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

    ctx.candidate_is_degrading  = result.get("candidate_is_degrading", True)
    ctx.diagnosis_confidence    = float(result.get("diagnosis_confidence", 0.0))
    ctx.likely_cause            = result.get("likely_cause", "Unknown")
    ctx.diagnosis_evidence      = result.get("diagnosis_evidence", [])
    ctx.recommended_action      = result.get("recommended_action", "rollback")

    ctx.log("agent5", f"Root cause: {ctx.likely_cause}")
    ctx.log("agent5", f"Recommended action: {ctx.recommended_action} (confidence {ctx.diagnosis_confidence:.0%})")
    return ctx
