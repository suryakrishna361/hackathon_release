"""
Store service tests.
"""
import os
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_products_list():
    response = client.get("/products")
    assert response.status_code == 200
    data = response.json()
    assert "products" in data
    assert len(data["products"]) > 0


def test_product_detail():
    response = client.get("/products/1")
    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "price" in data


def test_product_not_found():
    response = client.get("/products/9999")
    assert response.status_code == 404


def test_api_info():
    response = client.get("/api/info")
    assert response.status_code == 200
    assert response.json()["service"] == "store-service"
