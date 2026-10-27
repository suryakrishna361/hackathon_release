"""
Pipeline Orchestrator
Runs all 6 agents in sequence, passing ReleaseContext through each one.
Called by the webhook listener (or directly for demo).
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import json
import time

from agents.shared_context import ReleaseContext
from agents import (
    agent1_change_analysis,
    agent2_ci_validation,
    agent3_rollout_decision,
    agent4_runtime_monitor,
    agent5_diagnosis,
    agent6_remediation,
)
from tools.docker_build_tools import build_image, push_image

# ── optional SSE event stream ────────────────────────────────────────────────
# The dashboard subscribes to this queue for real-time updates.
import queue
_event_queue: "queue.Queue | None" = None

def set_event_queue(q: queue.Queue):
    global _event_queue
    _event_queue = q

def _emit(event: str, data: dict):
    if _event_queue:
        _event_queue.put(json.dumps({"event": event, "data": data}))


def _banner(text: str):
    width = 60
    print("\n" + "=" * width)
    print(f"  {text}")
    print("=" * width)


def run_pipeline(trigger_ref: str = "candidate") -> ReleaseContext:
    ctx = ReleaseContext()
    ctx.log("orchestrator", f"Pipeline triggered for ref: {trigger_ref}")
    _emit("pipeline_start", {"ref": trigger_ref, "ts": time.time()})

    steps = [
        ("Agent 1 — Change Analysis",       agent1_change_analysis),
        ("Agent 2 — CI Validation",          agent2_ci_validation),
        ("Agent 3 — Rollout Decision",       agent3_rollout_decision),
        ("Agent 4 — Runtime Monitor",        agent4_runtime_monitor),
    ]

    for label, module in steps:
        _banner(label)
        _emit("agent_start", {"agent": label})
        try:
            ctx = module.run(ctx)
            _emit("agent_done", {"agent": label, "context": ctx.to_dict()})
        except Exception as exc:
            ctx.log("orchestrator", f"{label} failed: {exc}", level="error")
            _emit("agent_error", {"agent": label, "error": str(exc)})

        # ── after Agent 2: build & push candidate Docker image ───────────────
        if label.startswith("Agent 2") and ctx.tests_passed:
            _banner("Docker Build — building candidate image")
            _emit("docker_build_start", {"service": "payment-service"})
            build_result = build_image("payment-service", "candidate")
            ctx.log("orchestrator", f"Docker build: {build_result}")
            if build_result.get("success"):
                push_result = push_image("payment-service", "candidate")
                ctx.log("orchestrator", f"Docker push: {push_result}")
                _emit("docker_build_done", {"image": build_result.get("image"), "pushed": push_result.get("success")})
            else:
                ctx.log("orchestrator", "Docker build failed — continuing with risk analysis", level="warn")

        # ── early exit gates ─────────────────────────────────────────────────
        if label.startswith("Agent 3") and not ctx.promotion_allowed:
            _banner("PIPELINE BLOCKED — promotion denied by Agent 3")
            ctx.log("orchestrator", "Deployment blocked. Reason: " + ctx.strategy_reasoning)
            _emit("pipeline_blocked", {"reason": ctx.strategy_reasoning})
            return ctx

        if label.startswith("Agent 4") and not ctx.candidate_degrading:
            _banner("PIPELINE COMPLETE — candidate is healthy, no remediation needed")
            ctx.log("orchestrator", "Candidate is healthy. Pipeline complete.")
            _emit("pipeline_healthy", {"summary": "Candidate passed all checks"})
            return ctx

    # ── only reach here if candidate IS degrading ─────────────────────────
    for label, module in [
        ("Agent 5 — Failure Diagnosis",   agent5_diagnosis),
        ("Agent 6 — Autonomous Remediation", agent6_remediation),
    ]:
        _banner(label)
        _emit("agent_start", {"agent": label})
        try:
            ctx = module.run(ctx)
            _emit("agent_done", {"agent": label, "context": ctx.to_dict()})
        except Exception as exc:
            ctx.log("orchestrator", f"{label} failed: {exc}", level="error")
            _emit("agent_error", {"agent": label, "error": str(exc)})

    status = "REMEDIATED" if ctx.recovery_verified else "DEGRADED (manual review needed)"
    _banner(f"PIPELINE COMPLETE — {status}")
    ctx.log("orchestrator", f"Final status: {status}")
    _emit("pipeline_complete", {"status": status, "context": ctx.to_dict()})

    print("\n── Final decision log ──")
    for entry in ctx.decision_log:
        ts = entry.get("ts", "")
        ag = entry.get("agent", "")
        msg = entry.get("message", "")
        lvl = entry.get("level", "info").upper()
        print(f"[{ts}] [{ag}] [{lvl}] {msg}")

    return ctx


if __name__ == "__main__":
    result = run_pipeline()
    print("\n── Context snapshot ──")
    print(json.dumps(result.to_dict(), indent=2))
