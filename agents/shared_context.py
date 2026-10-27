"""
ReleaseContext — Step 8
The shared state object that travels through all 6 agents.
Each agent reads from it and writes back to it.
The orchestrator passes it down the chain.
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ReleaseContext:
    # ── Identity ──
    release_id: str = field(default_factory=lambda: f"release-{str(uuid.uuid4())[:8]}")
    candidate_version: str = "v2"
    stable_version: str = "v1"
    created_at: float = field(default_factory=time.time)
    repo_path: str = "C:/Users/VankadaraVenkataSuma/Desktop/Hackathon"

    # ── Agent 1: Change & Impact Analysis ──
    affected_services: List[str] = field(default_factory=list)
    risk_level: str = "unknown"          # low / medium / high
    suspected_failure: str = ""
    risk_reasoning: List[str] = field(default_factory=list)
    risk_confidence: float = 0.0
    git_diff_summary: str = ""

    # ── Agent 2: CI & Environment Validation ──
    tests_passed: bool = False
    config_compatible: bool = True
    missing_env_vars: List[str] = field(default_factory=list)
    renamed_env_vars: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    validation_recommendation: str = ""  # block / guarded / proceed

    # ── Agent 3: Rollout Decision ──
    rollout_strategy: str = "pending"    # blocked / synthetic_canary / canary / blue_green / full
    promotion_allowed: bool = False
    strategy_reasoning: str = ""

    # ── Agent 4: Runtime Monitor (updated each monitoring cycle) ──
    stable_p95_ms: float = 0.0
    stable_p50_ms: float = 0.0
    stable_error_rate: float = 0.0
    stable_total_requests: int = 0
    candidate_p95_ms: float = 0.0
    candidate_p50_ms: float = 0.0
    candidate_error_rate: float = 0.0
    candidate_total_requests: int = 0
    synthetic_stable_success_rate: float = 0.0
    synthetic_candidate_success_rate: float = 0.0
    synthetic_stable_avg_latency_ms: float = 0.0
    synthetic_candidate_avg_latency_ms: float = 0.0
    monitoring_cycles_completed: int = 0

    # ── Agent 5: Runtime Diagnosis ──
    candidate_is_degrading: bool = False
    diagnosis_confidence: float = 0.0
    likely_cause: str = ""
    diagnosis_evidence: List[str] = field(default_factory=list)
    predicted_impact: str = ""           # low / medium / high
    recommended_action: str = ""         # continue / stop_promotion / rollback

    # ── Agent 6: Remediation ──
    remediation_taken: str = ""
    remediation_status: str = "pending"  # pending / completed / failed
    recovery_verified: bool = False
    recovery_notes: str = ""

    # ── Shared decision log (all agents write here) ──
    decision_log: List[dict] = field(default_factory=list)

    def log(self, agent: str, message: str, level: str = "info"):
        """Any agent can call this to record a decision or observation."""
        entry = {
            "agent": agent,
            "message": message,
            "level": level,
            "timestamp": time.time(),
        }
        self.decision_log.append(entry)
        # Also print to terminal so you can watch in real time
        icons = {"info": "→", "warning": "⚠", "action": "★", "error": "✗"}
        icon = icons.get(level, "→")
        print(f"  [{agent}] {icon} {message}")

    def to_dict(self) -> dict:
        """Serialize for dashboard display or incident recording."""
        return {
            "release_id": self.release_id,
            "candidate_version": self.candidate_version,
            "stable_version": self.stable_version,
            "risk_level": self.risk_level,
            "suspected_failure": self.suspected_failure,
            "risk_reasoning": self.risk_reasoning,
            "rollout_strategy": self.rollout_strategy,
            "runtime": {
                "stable_p95_ms": self.stable_p95_ms,
                "candidate_p95_ms": self.candidate_p95_ms,
                "stable_error_rate": self.stable_error_rate,
                "candidate_error_rate": self.candidate_error_rate,
                "synthetic_stable_success_rate": self.synthetic_stable_success_rate,
                "synthetic_candidate_success_rate": self.synthetic_candidate_success_rate,
            },
            "diagnosis": {
                "candidate_is_degrading": self.candidate_is_degrading,
                "confidence": self.diagnosis_confidence,
                "likely_cause": self.likely_cause,
                "evidence": self.diagnosis_evidence,
                "recommended_action": self.recommended_action,
            },
            "remediation": {
                "action": self.remediation_taken,
                "status": self.remediation_status,
                "recovery_verified": self.recovery_verified,
            },
            "decision_log": self.decision_log,
        }
