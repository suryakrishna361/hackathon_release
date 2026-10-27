"""
Docker build / push / pull / container management tools.
Used by the orchestrator (build step) and Agents 4 & 6.
"""
import os
import subprocess
import time
import requests

REPO_PATH          = os.getenv("REPO_PATH", "C:/Users/VankadaraVenkataSuma/Desktop/Hackathon")
DOCKERHUB_USERNAME = os.getenv("DOCKERHUB_USERNAME", "surya361")


def build_image(service: str, tag: str) -> dict:
    """Build a Docker image. Uses Dockerfile.v2 for the candidate tag."""
    service_path = os.path.join(REPO_PATH, "services", service)
    dockerfile   = "Dockerfile.v2" if tag == "candidate" else "Dockerfile"
    image_name   = f"{DOCKERHUB_USERNAME}/{service}:{tag}"

    try:
        result = subprocess.run(
            ["docker", "build", "-f", dockerfile, "-t", image_name, "."],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=service_path, timeout=180,
        )
        if result.returncode == 0:
            return {"success": True, "image": image_name, "output": result.stdout[-500:]}
        return {"success": False, "image": image_name, "error": result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Docker build timed out (180s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def push_image(service: str, tag: str) -> dict:
    """Push a Docker image to Docker Hub."""
    image_name = f"{DOCKERHUB_USERNAME}/{service}:{tag}"
    try:
        result = subprocess.run(
            ["docker", "push", image_name],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180,
        )
        if result.returncode == 0:
            return {"success": True, "image": image_name}
        return {"success": False, "image": image_name, "error": result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Docker push timed out (180s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def pull_image(service: str, tag: str) -> dict:
    """Pull a Docker image from Docker Hub."""
    image_name = f"{DOCKERHUB_USERNAME}/{service}:{tag}"
    try:
        result = subprocess.run(
            ["docker", "pull", image_name],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        if result.returncode == 0:
            return {"success": True, "image": image_name}
        return {"success": False, "image": image_name, "error": result.stderr[-300:]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def start_container(service: str, tag: str, port: int, name: str) -> dict:
    """Start a Docker container, mapping external port → internal 8001."""
    image_name = f"{DOCKERHUB_USERNAME}/{service}:{tag}"

    # Remove existing container with same name silently
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    try:
        result = subprocess.run(
            ["docker", "run", "-d", "-p", f"{port}:8001", "--name", name, image_name],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        if result.returncode == 0:
            time.sleep(3)  # let the container initialise
            container_id = result.stdout.strip()[:12]
            return {"success": True, "container_id": container_id, "name": name, "port": port}
        return {"success": False, "error": result.stderr[-300:]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def stop_container(name: str) -> dict:
    """Stop and remove a Docker container."""
    try:
        subprocess.run(["docker", "stop", name], capture_output=True, timeout=15)
        subprocess.run(["docker", "rm",   name], capture_output=True, timeout=10)
        return {"success": True, "stopped": name}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_container_logs(name: str, lines: int = 50) -> str:
    """Fetch recent stdout/stderr logs from a running container."""
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(lines), name],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        return (result.stdout + result.stderr) or "(no logs)"
    except Exception as e:
        return f"Failed to get logs: {str(e)}"
