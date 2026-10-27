"""
Demo Replay Mode
─────────────────
Step 1 (do tonight):  python pipeline/demo_replay.py --record
  → Runs the real pipeline once, saves result to data/demo_snapshot.json

Step 2 (during demo): python pipeline/demo_replay.py --replay
  → Reads the snapshot and replays all agent decisions with 2-second delays
  → Total demo time: ~15 seconds, looks identical to a live run

The dashboard picks up the replayed events via the same SSE queue.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import json
import time
import queue
import threading

SNAPSHOT_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "demo_snapshot.json")

AGENT_LABELS = [
    "Agent 1 — Change Analysis",
    "Agent 2 — CI Validation",
    "Agent 3 — Rollout Decision",
    "Agent 4 — Runtime Monitor",
    "Agent 5 — Failure Diagnosis",
    "Agent 6 — Autonomous Remediation",
]


# ── RECORD ────────────────────────────────────────────────────────────────────

def record():
    """Run the real pipeline and save a snapshot for later replay."""
    print("\n[Demo] Recording live pipeline run — this will take a few minutes...")
    print("[Demo] Snapshot will be saved to data/demo_snapshot.json\n")

    from pipeline.orchestrator import run_pipeline
    ctx = run_pipeline()

    snapshot = ctx.to_dict()
    os.makedirs(os.path.dirname(SNAPSHOT_FILE), exist_ok=True)
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(snapshot, f, indent=2)

    print(f"\n[Demo] ✓ Snapshot saved → {SNAPSHOT_FILE}")
    print("[Demo] Run with --replay tomorrow for a 15-second demo.")
    return snapshot


# ── REPLAY ────────────────────────────────────────────────────────────────────

def replay(event_queue: "queue.Queue | None" = None, delay: float = 2.0):
    """
    Replay a recorded snapshot through the dashboard SSE queue.
    Animates each agent completing one by one with `delay` seconds between.
    """
    if not os.path.exists(SNAPSHOT_FILE):
        print(f"[Demo] No snapshot found at {SNAPSHOT_FILE}")
        print("[Demo] Run with --record first.")
        return

    with open(SNAPSHOT_FILE) as f:
        ctx = json.load(f)

    def emit(event: str, data: dict):
        msg = json.dumps({"event": event, "data": data})
        if event_queue:
            event_queue.put(msg)
        print(f"  [{event}]")

    print("\n[Demo] Starting replay...")
    emit("pipeline_start", {"ref": "candidate", "ts": time.time()})
    time.sleep(0.5)

    # Determine which agents actually ran
    agents_ran = []
    if ctx.get("affected_services"):
        agents_ran.append(0)  # Agent 1
    if ctx.get("tests_passed") is not None:
        agents_ran.append(1)  # Agent 2
    if ctx.get("rollout_strategy"):
        agents_ran.append(2)  # Agent 3
    if ctx.get("stable_p95_ms") is not None:
        agents_ran.append(3)  # Agent 4
    if ctx.get("likely_cause"):
        agents_ran.append(4)  # Agent 5
    if ctx.get("remediation_status"):
        agents_ran.append(5)  # Agent 6

    for idx in agents_ran:
        label = AGENT_LABELS[idx]
        print(f"\n  ▶ {label}")
        emit("agent_start", {"agent": label})
        time.sleep(delay)
        emit("agent_done",  {"agent": label, "context": ctx})
        time.sleep(0.3)

        # Early exit gates (mirror orchestrator logic)
        if idx == 2 and not ctx.get("promotion_allowed", True):
            emit("pipeline_blocked", {"reason": ctx.get("strategy_reasoning", "")})
            print("\n[Demo] Pipeline blocked — deployment denied.")
            return

        if idx == 3 and not ctx.get("candidate_degrading", False):
            emit("pipeline_healthy", {"summary": "Candidate passed all checks"})
            print("\n[Demo] Candidate healthy — no remediation needed.")
            return

    # Final status
    recovered = ctx.get("recovery_verified", False)
    status = "REMEDIATED" if recovered else "DEGRADED"
    emit("pipeline_complete", {"status": status, "context": ctx})
    print(f"\n[Demo] ✓ Replay complete — {status}")


# ── STANDALONE (terminal-only replay, no dashboard) ──────────────────────────

def replay_terminal(delay: float = 2.0):
    """Print a coloured terminal replay without needing the dashboard."""
    if not os.path.exists(SNAPSHOT_FILE):
        print(f"[Demo] No snapshot found. Run --record first.")
        return

    with open(SNAPSHOT_FILE) as f:
        ctx = json.load(f)

    SEP = "=" * 60
    def banner(text):
        print(f"\n{SEP}\n  {text}\n{SEP}")

    banner("AUTONOMOUS RELEASE GUARDIAN — DEMO REPLAY")
    time.sleep(1)

    agent_data = [
        ("Agent 1 — Change Analysis",
         f"Risk: {ctx.get('risk_level','?').upper()}  |  {ctx.get('suspected_failure','')}"),
        ("Agent 2 — CI Validation",
         f"Tests passed: {ctx.get('tests_passed')}  |  Warnings: {ctx.get('validation_warnings',[])}"),
        ("Agent 3 — Rollout Decision",
         f"Strategy: {ctx.get('rollout_strategy','?').upper()}  |  Allowed: {ctx.get('promotion_allowed')}"),
        ("Agent 4 — Runtime Monitor",
         f"Stable p95={ctx.get('stable_p95_ms')}ms  Cand p95={ctx.get('candidate_p95_ms')}ms  "
         f"Degrading: {ctx.get('candidate_degrading')}"),
        ("Agent 5 — Failure Diagnosis",
         f"{ctx.get('likely_cause','')}  →  {ctx.get('recommended_action','')}"),
        ("Agent 6 — Remediation",
         f"Status: {ctx.get('remediation_status','')}  |  Recovery verified: {ctx.get('recovery_verified')}"),
    ]

    for label, detail in agent_data:
        banner(label)
        print(f"  {detail}")
        time.sleep(delay)

        if "Rollout" in label and not ctx.get("promotion_allowed", True):
            print("\n  BLOCKED — deployment denied.")
            return
        if "Monitor" in label and not ctx.get("candidate_degrading", False):
            print("\n  CANDIDATE HEALTHY — no rollback needed.")
            return

    recovered = ctx.get("recovery_verified", False)
    banner("PIPELINE COMPLETE — " + ("✓ AUTONOMOUS ROLLBACK SUCCESSFUL" if recovered else "⚠ MANUAL REVIEW NEEDED"))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "--help"
    delay = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0

    if mode == "--record":
        record()
    elif mode == "--replay":
        replay_terminal(delay=delay)
    elif mode == "--replay-dashboard":
        # Used by dashboard when demo mode is triggered
        from pipeline.orchestrator import set_event_queue
        q: queue.Queue = queue.Queue()
        set_event_queue(q)
        replay(event_queue=q, delay=delay)
    else:
        print(__doc__)
