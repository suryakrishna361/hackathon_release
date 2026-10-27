"""
GitHub Poller — replaces ngrok/webhook for local dev.
Polls the candidate branch every 30s for new commits and auto-triggers the pipeline.
"""
import os
import sys
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from tools.github_tools import get_latest_commit

POLL_INTERVAL  = 30  # seconds
STATE_FILE     = os.path.join(os.path.dirname(__file__), "..", "data", "last_seen_commit.txt")

_stop_event    = threading.Event()
_poll_thread   = None
_last_sha      = None
_poller_status = {"running": False, "last_sha": None, "last_checked": None, "triggers": 0}


def _read_last_sha() -> str:
    try:
        with open(STATE_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def _write_last_sha(sha: str):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        f.write(sha)


def _poll_loop(pipeline_fn):
    global _last_sha
    _last_sha = _read_last_sha()
    print(f"  [poller] Started. Last known SHA: {_last_sha[:8] if _last_sha else 'none'}")

    while not _stop_event.is_set():
        try:
            commit = get_latest_commit("candidate")
            sha    = commit.get("sha", "")

            _poller_status["last_checked"] = time.strftime("%H:%M:%S")
            _poller_status["last_sha"]     = sha[:8] if sha else None

            if sha and sha != _last_sha:
                msg = commit.get("message", "")[:60]
                print(f"\n  [poller] New commit detected on candidate: {sha[:8]} — {msg}")
                print(f"  [poller] Auto-triggering pipeline...")

                _last_sha = sha
                _write_last_sha(sha)
                _poller_status["triggers"] += 1

                try:
                    pipeline_fn("candidate")
                except Exception as e:
                    print(f"  [poller] Pipeline error: {e}")
            else:
                print(f"  [poller] No new commits ({time.strftime('%H:%M:%S')})")

        except Exception as e:
            print(f"  [poller] Poll error: {e}")

        _stop_event.wait(POLL_INTERVAL)

    print("  [poller] Stopped.")


def start_polling(pipeline_fn):
    global _poll_thread
    if _poll_thread and _poll_thread.is_alive():
        return {"status": "already_running"}

    _stop_event.clear()
    _poller_status["running"] = True
    _poll_thread = threading.Thread(target=_poll_loop, args=(pipeline_fn,), daemon=True)
    _poll_thread.start()
    return {"status": "started", "interval_seconds": POLL_INTERVAL}


def stop_polling():
    _stop_event.set()
    _poller_status["running"] = False
    return {"status": "stopped"}


def get_status() -> dict:
    return {**_poller_status, "interval_seconds": POLL_INTERVAL}
