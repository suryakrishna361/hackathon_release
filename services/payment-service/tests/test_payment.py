"""
Payment service tests — intentionally do NOT test env var rename scenarios.
This is the coverage gap that Agent 2 detects and flags.
Tests pass on both master and candidate — the bug slips through to agents.
"""
import os
import pytest

os.environ.setdefault("PAYMENT_TIMEOUT_MS", "500")

from fastapi.testclient import TestClient
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "payment-service"


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "payment-service" in data["service"]
    assert "timeout_ms" in data


def test_payment_request_accepted():
    response = client.post("/pay", json={
        "amount": 49.99,
        "card_number": "4111111111111111",
        "customer_email": "test@example.com",
    })
    assert response.status_code == 200
    data = response.json()
    assert "success" in data


def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "error_rate" in data
    assert "p95_latency_ms" in data
