"""
Agent 4 — Runtime Monitor
Runs synthetic canary traffic against both stable and candidate,
reads live metrics, and decides if the candidate is degrading.
Tools: get_metrics_stable, get_metrics_candidate, check_health_stable,
       check_health_candidate, run_synthetic_comparison, compare_metrics_summary
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import anthropic
from agents.base import run_agent_loop, extract_json
from agents.shared_context import ReleaseContext
from tools.metrics_tools import (
    get_metrics_stable, get_metrics_candidate,
    check_health_stable, check_health_candidate,
    read_service_logs, compare_metrics_summary,
)
from tools.synthetic_canary import run_synthetic_comparison
from tools.docker_build_tools import pull_image, start_container, stop_container, get_container_logs

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """You are a runtime monitoring AI. Your job is to observe both the stable
and candidate services under real (synthetic) traffic and determine if the candidate is degrading.

Steps:
1. Check health of both services.
2. Run the synthetic canary (sends real HTTP requests to both).
3. Compare live metrics (p95 latency, error rate).
4. Read logs if you see anomalies.

Degradation thresholds:
- Error rate: candidate > stable by more than 20 percentage points
- Latency: candidate p95 > stable p95 × 2

Output ONLY this JSON when done:
{
  "stable_p95_ms": 0,
  "candidate_p95_ms": 0,
  "stable_error_rate": 0.0,
  "candidate_error_rate": 0.0,
  "synthetic_success_rate_stable": 0.0,
  "synthetic_success_rate_candidate": 0.0,
  "synthetic_avg_latency_stable_ms": 0,
  "synthetic_avg_latency_candidate_ms": 0,
  "candidate_degrading": false,
  "monitor_summary": "one-line summary of what you observed"
}
All floats 0.0–1.0 for rates, integers for ms.
"""

TOOLS = [
    {
        "name": "check_health_stable",
        "description": "Health check the stable payment service.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_health_candidate",
        "description": "Health check the candidate payment service.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_synthetic_comparison",
        "description": "Send synthetic transactions to both services and compare results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {"type": "integer", "default": 5, "description": "Number of transactions per service"},
            },
        },
    },
    {
        "name": "get_metrics_stable",
        "description": "Get live metrics (p95 latency, error rate) from the stable service.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_metrics_candidate",
        "description": "Get live metrics from the candidate service.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "compare_metrics_summary",
        "description": "One-shot human-readable comparison of stable vs candidate metrics.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_service_logs",
        "description": "Read recent logs from a service.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "default": "payment-service-candidate"},
                "lines":   {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "get_container_logs",
        "description": "Read recent Docker container logs by container name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":  {"type": "string", "default": "payment-candidate"},
                "lines": {"type": "integer", "default": 50},
            },
        },
    },
]


def _execute_tool(name: str, inputs: dict) -> str:
    dispatch = {
        "check_health_stable":          lambda **kw: str(check_health_stable()),
        "check_health_candidate":       lambda **kw: str(check_health_candidate()),
        "run_synthetic_comparison":     run_synthetic_comparison,
        "get_metrics_stable":           lambda **kw: str(get_metrics_stable()),
        "get_metrics_candidate":        lambda **kw: str(get_metrics_candidate()),
        "compare_metrics_summary":      lambda **kw: compare_metrics_summary(),
        "read_service_logs":            read_service_logs,
        "get_container_logs":           get_container_logs,
    }
    fn = dispatch.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    return str(fn(**inputs))


def run(ctx: ReleaseContext) -> ReleaseContext:
    ctx.log("agent4", "Starting runtime monitoring with synthetic canary...")

    # Pull candidate image and start container on port 8002
    ctx.log("agent4", "Pulling candidate Docker image...")
    pull_result = pull_image("payment-service", "candidate")
    ctx.log("agent4", f"Pull: {pull_result}")

    ctx.log("agent4", "Starting candidate container on port 8002...")
    start_result = start_container("payment-service", "candidate", 8002, "payment-candidate")
    ctx.log("agent4", f"Container started: {start_result}")

    client = anthropic.Anthropic()

    user_prompt = (
        f"Monitor the candidate deployment. Strategy chosen: {ctx.rollout_strategy}. "
        f"Agent 1 suspects: '{ctx.suspected_failure}'. "
        "Check health, run synthetic canary traffic, compare metrics. "
        "Output your JSON report."
    )

    raw = run_agent_loop(
        client=client,
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tools=TOOLS,
        tool_executor=_execute_tool,
    )

    result = extract_json(raw)

    # Always stop candidate container after monitoring
    ctx.log("agent4", "Stopping candidate container...")
    stop_container("payment-candidate")

    ctx.stable_p95_ms                    = result.get("stable_p95_ms", 0)
    ctx.candidate_p95_ms                 = result.get("candidate_p95_ms", 0)
    ctx.stable_error_rate                = float(result.get("stable_error_rate", 0.0))
    ctx.candidate_error_rate             = float(result.get("candidate_error_rate", 0.0))
    ctx.synthetic_success_rate_stable    = float(result.get("synthetic_success_rate_stable", 0.0))
    ctx.synthetic_success_rate_candidate = float(result.get("synthetic_success_rate_candidate", 0.0))
    ctx.synthetic_avg_latency_stable_ms  = result.get("synthetic_avg_latency_stable_ms", 0)
    ctx.synthetic_avg_latency_candidate_ms = result.get("synthetic_avg_latency_candidate_ms", 0)
    ctx.candidate_degrading              = result.get("candidate_degrading", False)

    summary = result.get("monitor_summary", "")
    ctx.log("agent4", summary or f"Candidate degrading: {ctx.candidate_degrading}")
    ctx.log("agent4", (
        f"Stable  — p95={ctx.stable_p95_ms}ms  error={ctx.stable_error_rate:.0%}  "
        f"synth_ok={ctx.synthetic_success_rate_stable:.0%}"
    ))
    ctx.log("agent4", (
        f"Candidate — p95={ctx.candidate_p95_ms}ms  error={ctx.candidate_error_rate:.0%}  "
        f"synth_ok={ctx.synthetic_success_rate_candidate:.0%}"
    ))
    return ctx
