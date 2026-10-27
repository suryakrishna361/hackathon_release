"""
CI tools — used by Agent 2 (CI & Environment Validation)
"""
import os
import subprocess

REPO_PATH = os.getenv("REPO_PATH", "C:/Users/VankadaraVenkataSuma/Desktop/Hackathon")


def run_tests(service: str = "payment-service") -> str:
    """Run pytest on a service. Returns test output."""
    service_path = os.path.join(REPO_PATH, "services", service)
    tests_path = os.path.join(service_path, "tests")

    if not os.path.exists(tests_path):
        return (
            f"No tests directory found at {tests_path}.\n"
            "This means there are NO automated tests for this service.\n"
            "Coverage gap: config key changes are untested."
        )

    try:
        result = subprocess.run(
            ["python", "-m", "pytest", tests_path, "-v", "--tb=short"],
            capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=service_path, timeout=30
        )
        output = result.stdout + result.stderr
        return output if output.strip() else "Tests ran but produced no output."
    except subprocess.TimeoutExpired:
        return "Tests timed out after 30 seconds."
    except Exception as e:
        return f"Failed to run tests: {str(e)}"


def check_env_var_coverage(service: str = "payment-service") -> str:
    """
    Check which env vars the candidate code reads,
    and whether any test covers them.
    """
    service_path = os.path.join(REPO_PATH, "services", service)
    candidate_main = os.path.join(service_path, "main_v2.py")
    main_file = candidate_main if os.path.exists(candidate_main) else os.path.join(service_path, "main.py")

    try:
        with open(main_file) as f:
            source = f.read()

        import re
        env_vars = re.findall(r'os\.getenv\(["\']([^"\']+)["\']', source)

        tests_path = os.path.join(service_path, "tests")
        covered = []
        uncovered = []

        for var in env_vars:
            if os.path.exists(tests_path):
                # Check if any test file references this env var
                found = False
                for fname in os.listdir(tests_path):
                    if fname.endswith(".py"):
                        with open(os.path.join(tests_path, fname)) as tf:
                            if var in tf.read():
                                found = True
                                break
                (covered if found else uncovered).append(var)
            else:
                uncovered.append(var)

        lines = [f"Env vars read by {service} candidate:"]
        for v in env_vars:
            status = "✓ covered by tests" if v in covered else "✗ NOT covered by any test"
            lines.append(f"  {v}: {status}")

        if uncovered:
            lines.append(f"\nUncovered env vars: {uncovered}")
            lines.append("If any of these were renamed or removed, tests would not catch it.")

        return "\n".join(lines)

    except Exception as e:
        return f"Failed to check env var coverage: {str(e)}"


def compare_configs(service: str = "payment-service") -> str:
    """
    Compare the Docker Compose env vars for stable vs candidate.
    Flags vars present in stable but missing from candidate deployment.
    """
    import re

    stable_compose = os.path.join(REPO_PATH, "docker-compose.yml")
    candidate_compose = os.path.join(REPO_PATH, "docker-compose.candidate.yml")

    try:
        with open(stable_compose) as f:
            stable_text = f.read()
        with open(candidate_compose) as f:
            candidate_text = f.read()

        stable_vars    = re.findall(r"- ([A-Z_]+)=", stable_text)
        candidate_vars = re.findall(r"- ([A-Z_]+)=", candidate_text)

        missing = set(stable_vars) - set(candidate_vars)
        added   = set(candidate_vars) - set(stable_vars)

        lines = ["Deployment config comparison (docker-compose):"]
        lines.append(f"  Stable vars:    {stable_vars}")
        lines.append(f"  Candidate vars: {candidate_vars}")
        if missing:
            lines.append(f"\n  MISSING from candidate: {list(missing)}")
            lines.append("  These env vars are in stable deploy but NOT in candidate deploy.")
        if added:
            lines.append(f"\n  NEW in candidate: {list(added)}")
        if not missing and not added:
            lines.append("\n  No differences in deployment config.")

        return "\n".join(lines)

    except Exception as e:
        return f"Failed to compare configs: {str(e)}"
