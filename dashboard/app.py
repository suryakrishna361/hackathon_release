"""
Dashboard — real-time pipeline monitor
FastAPI + Server-Sent Events (SSE) streams agent decisions to the browser.
Run with: python dashboard/app.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import json
import queue
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn

app = FastAPI(title="Release Guardian Dashboard")

# ── shared event queue ────────────────────────────────────────────────────────
# The orchestrator writes to this; SSE clients read from it.
_event_queue: queue.Queue = queue.Queue()
_pipeline_running = False
_last_context: dict = {}


def _queue_put(event: str, data: dict):
    _event_queue.put(json.dumps({"event": event, "data": data}))


# ── HTML UI ───────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ── SSE stream ────────────────────────────────────────────────────────────────
@app.get("/events")
async def event_stream():
    """Server-Sent Events endpoint — browser connects here for live updates."""
    def generate():
        # Send current state immediately on connect
        yield f"data: {json.dumps({'event': 'connected', 'data': {'running': _pipeline_running, 'context': _last_context}})}\n\n"
        while True:
            try:
                msg = _event_queue.get(timeout=30)
                yield f"data: {msg}\n\n"
            except queue.Empty:
                # heartbeat to keep connection alive
                yield f"data: {json.dumps({'event': 'heartbeat', 'data': {}})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── manual trigger ────────────────────────────────────────────────────────────
@app.post("/run")
async def trigger_pipeline():
    """Trigger the full live pipeline from the dashboard UI."""
    global _pipeline_running, _last_context

    if _pipeline_running:
        return {"status": "already_running"}

    def _run():
        global _pipeline_running, _last_context
        _pipeline_running = True

        from pipeline.orchestrator import run_pipeline, set_event_queue
        set_event_queue(_event_queue)

        try:
            ctx = run_pipeline()
            _last_context = ctx.to_dict()
        except Exception as e:
            _event_queue.put(json.dumps({"event": "pipeline_error", "data": {"error": str(e)}}))
        finally:
            _pipeline_running = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"status": "started"}


@app.post("/demo")
async def trigger_demo():
    """Replay a pre-recorded pipeline run (fast, ~15 seconds). Use for demos."""
    global _pipeline_running

    if _pipeline_running:
        return {"status": "already_running"}

    def _run():
        global _pipeline_running
        _pipeline_running = True
        try:
            from pipeline.demo_replay import replay
            replay(event_queue=_event_queue, delay=2.0)
        except Exception as e:
            _event_queue.put(json.dumps({"event": "pipeline_error", "data": {"error": str(e)}}))
        finally:
            _pipeline_running = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return {"status": "demo_started"}


@app.get("/status")
async def status():
    return {"running": _pipeline_running, "context": _last_context}


# ── GitHub poller ─────────────────────────────────────────────────────────────
@app.post("/poller/start")
async def poller_start():
    from pipeline.github_poller import start_polling

    def _pipeline_fn(ref):
        from pipeline.orchestrator import run_pipeline, set_event_queue
        set_event_queue(_event_queue)
        run_pipeline(ref)

    return start_polling(_pipeline_fn)


@app.post("/poller/stop")
async def poller_stop():
    from pipeline.github_poller import stop_polling
    return stop_polling()


@app.get("/poller/status")
async def poller_status():
    from pipeline.github_poller import get_status
    return get_status()


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "5001"))
    print(f"[Dashboard] http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
