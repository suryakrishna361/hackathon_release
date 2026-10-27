"""
Synthetic canary — used by Agent 4 (Runtime Monitor)
Sends real HTTP requests to both stable and candidate services,
compares the results. No real user traffic involved.
"""
import os
import time
import requests

STABLE_URL    = os.getenv("STABLE_URL",    "http://localhost:8001")
CANDIDATE_URL = os.getenv("CANDIDATE_URL", "http://localhost:8002")

TEST_PAYLOAD = {
    "amount": 99.99,
    "card_number": "4111111111111111",
    "customer_email": "canary-test@release-guardian.internal",
}


def run_single_transaction(url: str, timeout: float = 5.0) -> dict:
    """Send one payment request and record the result."""
    start = time.time()
    try:
        resp = requests.post(f"{url}/pay", json=TEST_PAYLOAD, timeout=timeout)
        latency_ms = (time.time() - start) * 1000
        data = resp.json()
        return {
            "success":    resp.status_code == 200 and data.get("success", False),
            "latency_ms": round(latency_ms, 2),
            "status_code": resp.status_code,
            "response":   data,
        }
    except requests.Timeout:
        latency_ms = (time.time() - start) * 1000
        return {"success": False, "latency_ms": round(latency_ms, 2), "status_code": 504, "response": {"error": "timeout"}}
    except requests.ConnectionError:
        return {"success": False, "latency_ms": 0, "status_code": 0, "response": {"error": "connection refused"}}
    except Exception as e:
        return {"success": False, "latency_ms": 0, "status_code": 0, "response": {"error": str(e)}}


def run_synthetic_comparison(n: int = 5) -> dict:
    """
    Run n transactions against both services and compare.
    Returns structured result an agent can reason over.
    """
    print(f"  [Canary] Running {n} transactions against stable (:{8001}) and candidate (:{8002})...")

    stable_results    = [run_single_transaction(STABLE_URL)    for _ in range(n)]
    candidate_results = [run_single_transaction(CANDIDATE_URL) for _ in range(n)]

    stable_successes    = sum(1 for r in stable_results    if r["success"])
    candidate_successes = sum(1 for r in candidate_results if r["success"])

    stable_latencies    = [r["latency_ms"] for r in stable_results    if r["latency_ms"] > 0]
    candidate_latencies = [r["latency_ms"] for r in candidate_results if r["latency_ms"] > 0]

    stable_avg_ms    = sum(stable_latencies)    / len(stable_latencies)    if stable_latencies    else 0
    candidate_avg_ms = sum(candidate_latencies) / len(candidate_latencies) if candidate_latencies else 0

    stable_success_rate    = stable_successes    / n
    candidate_success_rate = candidate_successes / n

    # Simple degradation flag: candidate success rate dropped by more than 20%
    # or latency more than doubled
    candidate_degraded = (
        candidate_success_rate < stable_success_rate - 0.2
        or (stable_avg_ms > 0 and candidate_avg_ms > stable_avg_ms * 2)
    )

    result = {
        "transactions_per_service": n,
        "stable": {
            "success_rate":    round(stable_success_rate, 3),
            "avg_latency_ms":  round(stable_avg_ms, 2),
            "successes":       stable_successes,
            "failures":        n - stable_successes,
        },
        "candidate": {
            "success_rate":    round(candidate_success_rate, 3),
            "avg_latency_ms":  round(candidate_avg_ms, 2),
            "successes":       candidate_successes,
            "failures":        n - candidate_successes,
        },
        "candidate_degraded": candidate_degraded,
        "summary": _build_summary(
            stable_success_rate, candidate_success_rate,
            stable_avg_ms, candidate_avg_ms, candidate_degraded
        ),
    }

    print(f"  [Canary] Stable:    {stable_successes}/{n} ok, avg {stable_avg_ms:.0f}ms")
    print(f"  [Canary] Candidate: {candidate_successes}/{n} ok, avg {candidate_avg_ms:.0f}ms")
    print(f"  [Canary] Degraded:  {candidate_degraded}")

    return result


def _build_summary(s_rate, c_rate, s_ms, c_ms, degraded) -> str:
    parts = []
    if c_rate < s_rate - 0.2:
        parts.append(
            f"Candidate success rate dropped to {c_rate*100:.0f}% vs stable {s_rate*100:.0f}%."
        )
    if s_ms > 0 and c_ms > s_ms * 2:
        parts.append(
            f"Candidate latency {c_ms:.0f}ms is {c_ms/s_ms:.1f}x the stable {s_ms:.0f}ms."
        )
    if not parts:
        parts.append("Candidate and stable performing comparably.")
    return " ".join(parts)
