"""
Docker/process tools — used by Agent 6 (Remediation)
Handles starting/stopping candidate service and verifying recovery.
Works both with Docker and plain Python processes (local dev).
"""
import os
import subprocess
import time
import requests

REPO_PATH      = os.getenv("REPO_PATH",      "C:/Users/VankadaraVenkataSuma/Desktop/Hackathon")
STABLE_URL     = os.getenv("STABLE_URL",     "http://localhost:8001")
CANDIDATE_URL  = os.getenv("CANDIDATE_URL",  "http://localhost:8002")
PID_FILE       = os.path.join(REPO_PATH, "data", "candidate_pid.txt")


def start_candidate() -> dict:
    """
    Start the candidate (v2) payment service on port 8002.
    Saves PID so stop_candidate() can kill it later.
    """
    candidate_main = os.path.join(REPO_PATH, "services", "payment-service", "main_v2.py")

    try:
        proc = subprocess.Popen(
            ["python", "-m", "uvicorn", "main_v2:app", "--port", "8002", "--host", "0.0.0.0"],
            cwd=os.path.join(REPO_PATH, "services", "payment-service"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Save PID for later
        os.makedirs(os.path.dirname(PID_FILE), exist_ok=True)
        with open(PID_FILE, "w") as f:
            f.write(str(proc.pid))

        time.sleep(3)  # give it time to start

        # Confirm it started
        try:
            resp = requests.get(f"{CANDIDATE_URL}/health", timeout=3)
            return {"success": True, "pid": proc.pid, "status": resp.json()}
        except Exception:
            return {"success": False, "pid": proc.pid, "error": "Started but not responding yet"}

    except Exception as e:
        return {"success": False, "error": str(e)}


def stop_candidate() -> dict:
    """
    Stop the candidate service.
    Tries Docker Compose first, falls back to killing by PID.
    """
    # Try Docker Compose first
    try:
        result = subprocess.run(
            ["docker-compose", "-f", "docker-compose.candidate.yml", "stop"],
            capture_output=True, text=True, cwd=REPO_PATH, timeout=15
        )
        if result.returncode == 0:
            return {"success": True, "method": "docker-compose", "output": result.stdout.strip()}
    except Exception:
        pass

    # Fall back to killing by saved PID
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())

            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            os.remove(PID_FILE)
            return {"success": True, "method": "pid-kill", "pid": pid}
        except Exception as e:
            return {"success": False, "error": f"PID kill failed: {str(e)}"}

    # Last resort: kill any process on port 8002
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if ":8002" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
                return {"success": True, "method": "port-kill", "pid": pid}
        return {"success": False, "error": "Could not find process on port 8002"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def verify_stable_healthy(retries: int = 3) -> dict:
    """
    Confirm the stable service is responding correctly after remediation.
    """
    for attempt in range(retries):
        try:
            health = requests.get(f"{STABLE_URL}/health", timeout=3).json()
            metrics = requests.get(f"{STABLE_URL}/metrics", timeout=3).json()

            if health.get("status") == "ok":
                return {
                    "healthy": True,
                    "version": health.get("version", "v1"),
                    "error_rate": metrics.get("error_rate", 0),
                    "p95_latency_ms": metrics.get("p95_latency_ms", 0),
                    "message": "Stable service is healthy and responding normally.",
                }
        except Exception:
            time.sleep(2)

    return {"healthy": False, "message": "Stable service is not responding after remediation."}


def record_incident(context_dict: dict) -> dict:
    """Append the release outcome to incidents.json for future Agent 1 lookups."""
    import json

    incidents_file = os.path.join(REPO_PATH, "data", "incidents.json")
    try:
        with open(incidents_file) as f:
            incidents = json.load(f)
    except Exception:
        incidents = []

    new_incident = {
        "id": f"INC-{len(incidents) + 100:03d}",
        "date": time.strftime("%Y-%m-%d"),
        "service": ",".join(context_dict.get("affected_services", [])),
        "change_type": "config_rename",
        "description": context_dict.get("suspected_failure", "Unknown failure"),
        "risk_level": context_dict.get("risk_level", "unknown"),
        "rollout_strategy": context_dict.get("rollout_strategy", "unknown"),
        "candidate_degraded": context_dict.get("candidate_is_degrading", False),
        "diagnosis_confidence": context_dict.get("diagnosis_confidence", 0),
        "remediation": context_dict.get("remediation_taken", "none"),
        "recovery_verified": context_dict.get("recovery_verified", False),
    }
    incidents.append(new_incident)

    with open(incidents_file, "w") as f:
        json.dump(incidents, f, indent=2)

    return {"success": True, "incident_id": new_incident["id"], "total_incidents": len(incidents)}
