"""
payment-service v2 — CANDIDATE
Refactored config keys to use shorter names for consistency.
New feature: /refund endpoint for partial and full refunds.
"""
import os
import time
import random
from collections import deque
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Payment Service", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config: renamed PAYMENT_TIMEOUT_MS → PAYMENT_TIMEOUT for consistency
TIMEOUT_MS = int(os.getenv("PAYMENT_TIMEOUT", "0"))

# ── In-memory metrics ──
_latencies = deque(maxlen=200)
_errors = [0]
_total = [0]


class PaymentRequest(BaseModel):
    amount: float
    card_number: str
    customer_email: str


class RefundRequest(BaseModel):
    transaction_id: str
    amount: float
    reason: str = "customer_request"


@app.get("/")
def root():
    return {"service": "payment-service", "version": "v2", "timeout_ms": TIMEOUT_MS}


@app.post("/pay")
def process_payment(payment: PaymentRequest):
    start = time.time()
    _total[0] += 1

    # TIMEOUT_MS is 0 because PAYMENT_TIMEOUT is not set in the environment
    if TIMEOUT_MS == 0:
        time.sleep(3.0)
        duration_ms = (time.time() - start) * 1000
        _latencies.append(duration_ms)
        _errors[0] += 1
        return {"success": False, "error": "Payment processor timeout", "timeout_ms": TIMEOUT_MS}

    processing_time = random.uniform(0.15, 0.30)
    time.sleep(processing_time)
    duration_ms = (time.time() - start) * 1000
    _latencies.append(duration_ms)

    return {
        "success": True,
        "transaction_id": f"TXN-{int(time.time())}-{random.randint(1000, 9999)}",
        "amount_charged": payment.amount,
        "last4": payment.card_number[-4:],
        "processing_time_ms": round(duration_ms, 2),
    }


@app.post("/refund")
def process_refund(refund: RefundRequest):
    start = time.time()
    _total[0] += 1

    # Same bug: TIMEOUT_MS is 0 — refunds also timeout
    if TIMEOUT_MS == 0:
        time.sleep(3.0)
        duration_ms = (time.time() - start) * 1000
        _latencies.append(duration_ms)
        _errors[0] += 1
        return {"success": False, "error": "Refund processor timeout", "timeout_ms": TIMEOUT_MS}

    processing_time = random.uniform(0.10, 0.20)
    time.sleep(processing_time)
    duration_ms = (time.time() - start) * 1000
    _latencies.append(duration_ms)

    return {
        "success": True,
        "refund_id": f"REF-{int(time.time())}-{random.randint(1000, 9999)}",
        "transaction_id": refund.transaction_id,
        "amount_refunded": refund.amount,
        "reason": refund.reason,
        "processing_time_ms": round(duration_ms, 2),
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "payment-service", "version": "v2"}


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
        "version": "v2",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
