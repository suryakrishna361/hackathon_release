"""
Metrics tools — used by Agent 4 (Runtime Monitor)
Fetches live metrics from the running services.
"""
import os
import subprocess
import requests

STABLE_URL   = os.getenv("STABLE_URL",    "http://localhost:8001")
CANDIDATE_URL = os.getenv("CANDIDATE_URL", "http://localhost:8002")


def get_metrics_stable() -> dict:
    """Fetch metrics from the stable payment-service (port 8001)."""
    try:
        resp = requests.get(f"{STABLE_URL}/metrics", timeout=3)
        return resp.json()
    except requests.ConnectionError:
        return {"error": "stable service unreachable", "p95_latency_ms": 0, "error_rate": 0}
    except Exception as e:
        return {"error": str(e)}


def get_metrics_candidate() -> dict:
    """Fetch metrics from the candidate payment-service (port 8002)."""
    try:
        resp = requests.get(f"{CANDIDATE_URL}/metrics", timeout=3)
        return resp.json()
    except requests.ConnectionError:
        return {"error": "candidate service unreachable — may not be started yet"}
    except Exception as e:
        return {"error": str(e)}


def check_health_stable() -> dict:
    """Health check on stable service."""
    try:
        resp = requests.get(f"{STABLE_URL}/health", timeout=3)
        return resp.json()
    except Exception:
        return {"status": "unreachable"}


def check_health_candidate() -> dict:
    """Health check on candidate service."""
    try:
        resp = requests.get(f"{CANDIDATE_URL}/health", timeout=3)
        return resp.json()
    except Exception:
        return {"status": "unreachable"}


def read_service_logs(service_name: str = "payment-service", lines: int = 30) -> str:
    """
    Read recent logs from a running Docker container.
    Falls back to a message if Docker isn't running.
    """
    try:
        result = subprocess.run(
            ["docker", "logs", service_name, "--tail", str(lines)],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout + result.stderr
        return output.strip() if output.strip() else "No logs available."
    except FileNotFoundError:
        return "Docker not available — services running locally without containers."
    except subprocess.TimeoutExpired:
        return "Log fetch timed out."
    except Exception as e:
        return f"Log fetch failed: {str(e)}"


def compare_metrics_summary() -> dict:
    """
    One-shot comparison of stable vs candidate — used by Agent 5.
    Returns a human-readable summary alongside raw numbers.
    """
    stable    = get_metrics_stable()
    candidate = get_metrics_candidate()

    if "error" in stable or "error" in candidate:
        return {
            "stable": stable,
            "candidate": candidate,
            "comparison": "Cannot compare — one or both services unreachable."
        }

    s_p95   = stable.get("p95_latency_ms", 0)
    c_p95   = candidate.get("p95_latency_ms", 0)
    s_err   = stable.get("error_rate", 0)
    c_err   = candidate.get("error_rate", 0)

    latency_delta = c_p95 - s_p95
    error_delta   = c_err - s_err

    summary_parts = []
    if latency_delta > 500:
        summary_parts.append(
            f"Candidate p95 latency is {latency_delta:.0f}ms HIGHER than stable ({c_p95:.0f}ms vs {s_p95:.0f}ms)."
        )
    elif latency_delta < -100:
        summary_parts.append(
            f"Candidate p95 latency is {abs(latency_delta):.0f}ms LOWER than stable — improvement detected."
        )
    else:
        summary_parts.append(f"Latency within normal range (delta: {latency_delta:.0f}ms).")

    if error_delta > 0.05:
        summary_parts.append(
            f"Candidate error rate is {c_err*100:.1f}% vs stable {s_err*100:.1f}% — ELEVATED."
        )
    else:
        summary_parts.append(f"Error rates comparable (candidate: {c_err*100:.1f}%, stable: {s_err*100:.1f}%).")

    return {
        "stable":    stable,
        "candidate": candidate,
        "delta": {
            "latency_ms": round(latency_delta, 2),
            "error_rate": round(error_delta, 4),
        },
        "summary": " ".join(summary_parts),
    }
