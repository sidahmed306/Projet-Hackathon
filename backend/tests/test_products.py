"""Tests for the demo catalog and GET /api/products (docs/api.md, section b)."""

import re
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.db import count_products
from app.main import app
from app.seed import seed_products

TWO_DECIMALS = re.compile(r"^\d+\.\d{2}$")


@pytest.fixture
def client():
    # "with" runs the app's startup (lifespan): create the table and seed the
    # temporary database prepared in conftest.py.
    with TestClient(app) as test_client:
        yield test_client


def test_tests_use_a_temporary_database():
    real_db = Path(__file__).resolve().parent.parent / "app.db"
    assert Path(config.settings.SQLITE_PATH) != real_db


def test_returns_all_12_products(client):
    response = client.get("/api/products")
    assert response.status_code == 200
    products = response.json()
    assert len(products) == 12
    assert len({p["id"] for p in products}) == 12


def test_sorted_by_price_lowest_first(client):
    prices = [Decimal(p["price"]) for p in client.get("/api/products").json()]
    assert prices == sorted(prices)


@pytest.mark.parametrize("category, expected", [("laptop", 5), ("headphones", 4), ("phone", 3)])
def test_category_filter(client, category, expected):
    products = client.get("/api/products", params={"category": category}).json()
    assert len(products) == expected
    assert all(p["category"] == category for p in products)


@pytest.mark.parametrize("category", ["laptop", "LAPTOP", " Laptop "])
def test_category_is_normalized(client, category):
    products = client.get("/api/products", params={"category": category}).json()
    assert len(products) == 5
    assert all(p["category"] == "laptop" for p in products)


def test_unknown_category_returns_empty_list(client):
    response = client.get("/api/products", params={"category": "car"})
    assert response.status_code == 200
    assert response.json() == []


def test_max_price_includes_exact_price(client):
    # prod_001 costs exactly 749.00: it must be included.
    products = client.get("/api/products", params={"max_price": "749.00"}).json()
    ids = [p["id"] for p in products]
    assert "prod_001" in ids
    assert all(Decimal(p["price"]) <= Decimal("749.00") for p in products)
    # prod_004 costs 799.00: it must be excluded.
    assert "prod_004" not in ids


def test_category_and_max_price_together(client):
    products = client.get("/api/products", params={"category": "laptop", "max_price": "800.00"}).json()
    assert [p["id"] for p in products] == ["prod_002", "prod_001", "prod_004"]


@pytest.mark.parametrize("bad_value", ["abc", "-5", "10.999"])
def test_invalid_max_price_returns_validation_error(client, bad_value):
    response = client.get("/api/products", params={"max_price": bad_value})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(response.json()["error"]["message"], str)


def test_amounts_are_strings_with_2_decimals(client):
    for product in client.get("/api/products").json():
        assert isinstance(product["price"], str) and TWO_DECIMALS.match(product["price"])
        assert isinstance(product["shipping"], str) and TWO_DECIMALS.match(product["shipping"])
        assert product["currency"] == "USD"


def test_every_product_is_demo(client):
    for product in client.get("/api/products").json():
        assert product["is_demo"] is True


def test_seeding_twice_does_not_create_duplicates(client):
    # The startup already seeded once. Seed two more times.
    seed_products()
    seed_products()
    assert count_products() == 12
    assert len(client.get("/api/products").json()) == 12

