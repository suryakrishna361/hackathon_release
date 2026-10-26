"""
Webhook listener — Step 6
Receives GitHub push events and triggers the agent pipeline.
Run with: python pipeline/webhook_listener.py
"""
import os
import hashlib
import hmac
import threading
import json
from flask import Flask, request, jsonify

app = Flask(__name__)

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "release-guardian-secret")


def verify_github_signature(payload_bytes: bytes, signature_header: str) -> bool:
    """Verify the request actually came from GitHub."""
    if not signature_header:
        return False
    mac = hmac.new(WEBHOOK_SECRET.encode(), payload_bytes, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature_header)


def extract_push_info(payload: dict) -> dict:
    """Pull the relevant fields out of the GitHub push payload."""
    return {
        "ref":          payload.get("ref", ""),               # e.g. "refs/heads/candidate"
        "branch":       payload.get("ref", "").split("/")[-1], # e.g. "candidate"
        "before_sha":   payload.get("before", ""),
        "after_sha":    payload.get("after", ""),
        "pusher":       payload.get("pusher", {}).get("name", "unknown"),
        "commits":      payload.get("commits", []),
        "repo":         payload.get("repository", {}).get("full_name", ""),
        "commit_message": payload.get("head_commit", {}).get("message", ""),
        "modified_files": payload.get("head_commit", {}).get("modified", []),
    }


def run_pipeline_async(push_info: dict):
    """Run in a background thread so the webhook returns 202 immediately."""
    try:
        print(f"\n[Webhook] Push detected on '{push_info['branch']}' branch")
        print(f"[Webhook] Commit: {push_info['commit_message']}")
        print(f"[Webhook] Files changed: {push_info['modified_files']}")
        print("[Webhook] Starting agent pipeline...\n")

        # Import here to avoid circular imports once orchestrator is built
        from pipeline.orchestrator import run_pipeline
        run_pipeline(push_info)

    except ImportError:
        # Orchestrator not built yet — print a placeholder
        print("[Webhook] Orchestrator not ready yet — pipeline stub called")
        print(f"[Webhook] Would run pipeline for: {json.dumps(push_info, indent=2)}")
    except Exception as e:
        print(f"[Webhook] Pipeline error: {e}")


@app.route("/webhook", methods=["POST"])
def github_webhook():
    # Verify signature
    sig = request.headers.get("X-Hub-Signature-256", "")
    if not verify_github_signature(request.data, sig):
        print("[Webhook] Signature verification failed — rejected")
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.json
    if not payload:
        return jsonify({"error": "Empty payload"}), 400

    push_info = extract_push_info(payload)

    # Only trigger on candidate branch pushes
    if push_info["branch"] == "candidate":
        thread = threading.Thread(target=run_pipeline_async, args=(push_info,))
        thread.daemon = True
        thread.start()
        return jsonify({"status": "pipeline started", "branch": push_info["branch"]}), 202

    print(f"[Webhook] Ignoring push to '{push_info['branch']}' branch")
    return jsonify({"status": "ignored", "branch": push_info["branch"]}), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "webhook-listener"})


@app.route("/trigger", methods=["POST"])
def manual_trigger():
    """
    Demo shortcut — trigger the pipeline without a real GitHub push.
    POST /trigger with JSON: {"branch": "candidate", "message": "test push"}
    Useful during demo if ngrok isn't set up yet.
    """
    body = request.json or {}
    push_info = {
        "ref":            "refs/heads/candidate",
        "branch":         body.get("branch", "candidate"),
        "before_sha":     "main",
        "after_sha":      "candidate",
        "pusher":         "demo",
        "commits":        [],
        "repo":           "release-guardian",
        "commit_message": body.get("message", "refactor: rename PAYMENT_TIMEOUT_MS to PAYMENT_TIMEOUT"),
        "modified_files": ["services/payment-service/main.py"],
    }
    thread = threading.Thread(target=run_pipeline_async, args=(push_info,))
    thread.daemon = True
    thread.start()
    return jsonify({"status": "pipeline triggered manually", "push_info": push_info}), 202


if __name__ == "__main__":
    port = int(os.getenv("PIPELINE_PORT", "5000"))
    print(f"[Webhook] Listening on http://localhost:{port}")
    print(f"[Webhook] GitHub webhook URL: http://localhost:{port}/webhook")
    print(f"[Webhook] Manual trigger URL: http://localhost:{port}/trigger")
    app.run(host="0.0.0.0", port=port, debug=False)
