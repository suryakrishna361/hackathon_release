"""
Git tools — used by Agent 1 (Change Analysis)
These are the Python functions behind the tool definitions given to Claude.
"""
import os
import subprocess

REPO_PATH = os.getenv("REPO_PATH", "C:/Users/VankadaraVenkataSuma/Desktop/Hackathon")


def read_git_diff(base_branch: str = "master", candidate_branch: str = "candidate") -> str:
    """Get the full diff between stable and candidate branch."""
    try:
        result = subprocess.run(
            ["git", "diff", f"{base_branch}..{candidate_branch}"],
            capture_output=True, text=True, cwd=REPO_PATH
        )
        if result.returncode != 0:
            return f"Error reading diff: {result.stderr}"
        return result.stdout if result.stdout.strip() else "No differences found between branches."
    except Exception as e:
        return f"Git diff failed: {str(e)}"


def read_changed_files(base_branch: str = "master", candidate_branch: str = "candidate") -> str:
    """List just the file names that changed."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_branch}..{candidate_branch}"],
            capture_output=True, text=True, cwd=REPO_PATH
        )
        return result.stdout.strip() or "No files changed."
    except Exception as e:
        return f"Failed: {str(e)}"


def read_commit_messages(branch: str = "candidate", count: int = 5) -> str:
    """Get recent commit messages on the candidate branch."""
    try:
        result = subprocess.run(
            ["git", "log", branch, f"-{count}", "--pretty=format:%h %s"],
            capture_output=True, text=True, cwd=REPO_PATH
        )
        return result.stdout.strip() or "No commits found."
    except Exception as e:
        return f"Failed: {str(e)}"


def read_file_contents(file_path: str, branch: str = "candidate") -> str:
    """Read a specific file from a branch."""
    try:
        result = subprocess.run(
            ["git", "show", f"{branch}:{file_path}"],
            capture_output=True, text=True, cwd=REPO_PATH
        )
        if result.returncode != 0:
            return f"File not found on branch {branch}: {file_path}"
        return result.stdout
    except Exception as e:
        return f"Failed: {str(e)}"


def compare_env_vars(service: str = "payment-service") -> str:
    """
    Compare environment variable usage between v1 (master) and v2 (candidate).
    Greps for os.getenv calls in both versions of the service.
    """
    try:
        v1 = subprocess.run(
            ["git", "show", f"master:services/{service}/main.py"],
            capture_output=True, text=True, cwd=REPO_PATH
        ).stdout

        v2 = subprocess.run(
            ["git", "show", f"candidate:services/{service}/main.py"],
            capture_output=True, text=True, cwd=REPO_PATH
        ).stdout

        # Extract os.getenv lines from both
        v1_envs = [line.strip() for line in v1.splitlines() if "os.getenv" in line]
        v2_envs = [line.strip() for line in v2.splitlines() if "os.getenv" in line]

        result = []
        result.append(f"=== {service} env var usage ===")
        result.append("\n[master / v1]:")
        result.extend(f"  {e}" for e in v1_envs)
        result.append("\n[candidate / v2]:")
        result.extend(f"  {e}" for e in v2_envs)

        # Find removed/added env vars (simple line diff)
        removed = set(v1_envs) - set(v2_envs)
        added = set(v2_envs) - set(v1_envs)
        if removed:
            result.append(f"\nREMOVED from v2: {list(removed)}")
        if added:
            result.append(f"ADDED in v2:     {list(added)}")
        if not removed and not added:
            result.append("\nNo env var changes detected.")

        return "\n".join(result)
    except Exception as e:
        return f"Failed to compare env vars: {str(e)}"
