"""
payment-service v1 — STABLE
Reads PAYMENT_TIMEOUT_MS correctly. Processes payments reliably.
"""
import os
import time
import random
from collections import deque
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Payment Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# v1 reads the CORRECT env var name
TIMEOUT_MS = int(os.getenv("PAYMENT_TIMEOUT_MS", "500"))

# ── In-memory metrics ──
_latencies = deque(maxlen=200)
_errors = [0]
_total = [0]


class PaymentRequest(BaseModel):
    amount: float
    card_number: str
    customer_email: str


@app.get("/")
def root():
    return {"service": "payment-service", "version": "v1", "timeout_ms": TIMEOUT_MS}


@app.post("/pay")
def process_payment(payment: PaymentRequest):
    start = time.time()
    _total[0] += 1

    # Simulate processing time (realistic: 150-300ms)
    processing_time = random.uniform(0.15, 0.30)
    time.sleep(processing_time)

    duration_ms = (time.time() - start) * 1000
    _latencies.append(duration_ms)

    # Simulate 2% random failures (normal production rate)
    if random.random() < 0.02:
        _errors[0] += 1
        return {"success": False, "error": "Card declined"}

    return {
        "success": True,
        "transaction_id": f"TXN-{int(time.time())}-{random.randint(1000, 9999)}",
        "amount_charged": payment.amount,
        "last4": payment.card_number[-4:],
        "processing_time_ms": round(duration_ms, 2),
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "payment-service", "version": "v1"}


@app.get("/metrics")
def metrics():
    times = sorted(_latencies)
    p95 = times[int(len(times) * 0.95)] if times else 0.0
    p50 = times[int(len(times) * 0.50)] if times else 0.0
    return {
        "p95_latency_ms": round(p95, 2),
        "p50_latency_ms": round(p50, 2),
        "error_rate": round(_errors[0] / max(_total[0], 1), 4),
        "total_requests": _total[0],
        "error_count": _errors[0],
        "version": "v1",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
