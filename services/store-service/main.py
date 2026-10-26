import os
import time
import requests
from collections import deque
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Store Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8001")

# ── In-memory metrics ──
_latencies = deque(maxlen=200)
_errors = [0]
_total = [0]


# ── Models ──
class CartItem(BaseModel):
    product_id: int
    quantity: int


class CheckoutRequest(BaseModel):
    items: List[CartItem]
    customer_email: str
    card_number: str = "4111111111111111"


# ── Hardcoded product catalog ──
PRODUCTS = [
    {"id": 1, "name": "Wireless Headphones",    "price": 79.99,  "stock": 50, "category": "Electronics"},
    {"id": 2, "name": "Running Shoes",           "price": 119.99, "stock": 30, "category": "Footwear"},
    {"id": 3, "name": "Stainless Water Bottle",  "price": 24.99,  "stock": 100,"category": "Accessories"},
    {"id": 4, "name": "Mechanical Keyboard",     "price": 149.99, "stock": 20, "category": "Electronics"},
    {"id": 5, "name": "Yoga Mat",                "price": 39.99,  "stock": 45, "category": "Fitness"},
]


# ── Routes ──
@app.get("/", response_class=HTMLResponse)
def store_ui():
    html_path = os.path.join(os.path.dirname(__file__), "index.html")
    with open(html_path, encoding="utf-8") as f:
        return f.read()

@app.get("/api/info")
def root():
    return {"service": "store-service", "version": "v1", "status": "running"}


@app.get("/products")
def list_products():
    return {"products": PRODUCTS, "total": len(PRODUCTS)}


@app.get("/products/{product_id}")
def get_product(product_id: int):
    product = next((p for p in PRODUCTS if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.post("/checkout")
def checkout(order: CheckoutRequest):
    start = time.time()
    _total[0] += 1

    # Calculate total amount
    total_amount = 0.0
    order_items = []
    for item in order.items:
        product = next((p for p in PRODUCTS if p["id"] == item.product_id), None)
        if not product:
            _errors[0] += 1
            raise HTTPException(status_code=400, detail=f"Product {item.product_id} not found")
        total_amount += product["price"] * item.quantity
        order_items.append({
            "product": product["name"],
            "quantity": item.quantity,
            "subtotal": product["price"] * item.quantity
        })

    # Call payment service
    try:
        payment_resp = requests.post(
            f"{PAYMENT_SERVICE_URL}/pay",
            json={
                "amount": round(total_amount, 2),
                "card_number": order.card_number,
                "customer_email": order.customer_email,
            },
            timeout=5.0,
        )
        duration_ms = (time.time() - start) * 1000
        _latencies.append(duration_ms)

        if payment_resp.status_code != 200:
            _errors[0] += 1
            return {"success": False, "error": "Payment declined", "code": payment_resp.status_code}

        payment_data = payment_resp.json()
        return {
            "success": True,
            "order_id": f"ORD-{int(time.time())}",
            "items": order_items,
            "total_amount": round(total_amount, 2),
            "payment": payment_data,
        }

    except requests.Timeout:
        duration_ms = (time.time() - start) * 1000
        _latencies.append(duration_ms)
        _errors[0] += 1
        return {"success": False, "error": "Payment service timeout"}

    except requests.ConnectionError:
        _errors[0] += 1
        return {"success": False, "error": "Payment service unreachable"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "store-service", "version": "v1"}


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
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
