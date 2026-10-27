"""
GitHub API tools — used by Agent 2 to read GitHub Actions CI results.
"""
import os
import time
import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO  = os.getenv("GITHUB_REPO",  "suryakrishna361/hackathon_release")
BASE_URL     = "https://api.github.com"


def _headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }


def get_latest_commit(branch: str = "candidate") -> dict:
    """Get the latest commit SHA and message on a branch."""
    url = f"{BASE_URL}/repos/{GITHUB_REPO}/branches/{branch}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=10)
        if resp.status_code == 200:
            data   = resp.json()
            commit = data.get("commit", {})
            return {
                "sha":     commit.get("sha", ""),
                "message": commit.get("commit", {}).get("message", ""),
                "author":  commit.get("commit", {}).get("author", {}).get("name", ""),
                "date":    commit.get("commit", {}).get("author", {}).get("date", ""),
            }
        return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"error": str(e)}


def get_workflow_run_status(commit_sha: str) -> dict:
    """Find the GitHub Actions run for a specific commit SHA."""
    url = f"{BASE_URL}/repos/{GITHUB_REPO}/actions/runs"
    try:
        resp = requests.get(url, headers=_headers(), params={"head_sha": commit_sha}, timeout=10)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}

        runs = resp.json().get("workflow_runs", [])
        if not runs:
            return {"status": "not_found", "message": "No workflow run found for this commit yet"}

        run = runs[0]
        return {
            "run_id":     run.get("id"),
            "status":     run.get("status"),      # queued | in_progress | completed
            "conclusion": run.get("conclusion"),  # success | failure | cancelled | None
            "name":       run.get("name"),
            "url":        run.get("html_url"),
            "created_at": run.get("created_at"),
        }
    except Exception as e:
        return {"error": str(e)}


def wait_for_workflow(commit_sha: str, timeout_seconds: int = 300) -> dict:
    """Poll every 10s until the workflow completes or timeout is reached."""
    start = time.time()
    while time.time() - start < timeout_seconds:
        result = get_workflow_run_status(commit_sha)

        if "error" in result:
            return result

        if result.get("status") == "not_found":
            time.sleep(10)
            continue

        if result.get("status") == "completed":
            return result

        # Still running — print status and keep polling
        elapsed = int(time.time() - start)
        print(f"    [github] Workflow {result.get('status')} … {elapsed}s elapsed")
        time.sleep(10)

    return {"status": "timeout", "message": f"Workflow did not complete within {timeout_seconds}s"}


def get_workflow_jobs(run_id: int) -> str:
    """Get job-level pass/fail details for a workflow run."""
    url = f"{BASE_URL}/repos/{GITHUB_REPO}/actions/runs/{run_id}/jobs"
    try:
        resp = requests.get(url, headers=_headers(), timeout=10)
        if resp.status_code != 200:
            return f"HTTP {resp.status_code}"

        jobs  = resp.json().get("jobs", [])
        lines = []
        for job in jobs:
            status = job.get("conclusion") or job.get("status")
            lines.append(f"Job: {job.get('name')} → {status}")
            for step in job.get("steps", []):
                step_status = step.get("conclusion") or step.get("status")
                lines.append(f"  Step: {step.get('name')} → {step_status}")

        return "\n".join(lines) if lines else "No jobs found"
    except Exception as e:
        return f"Failed: {str(e)}"
