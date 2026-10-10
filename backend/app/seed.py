"""Load the demo catalog (data/products.json) into the database.

Run it from backend/ with: python -m app.seed
Safe to run several times: a product with the same id is updated, never duplicated.
"""

import json
from pathlib import Path

from app.db import get_connection, init_db
from app.money import to_cents

PRODUCTS_FILE = Path(__file__).resolve().parent.parent / "data" / "products.json"

REQUIRED_FIELDS = ("id", "name", "category", "description", "price", "shipping", "currency")
ALLOWED_CATEGORIES = ("laptop", "headphones", "phone")


def load_products(path: Path = PRODUCTS_FILE) -> list[dict]:
    """Read the JSON file and check every product. Raises ValueError if something is wrong."""
    with open(path, encoding="utf-8") as file:
        products = json.load(file)

    seen_ids = set()
    rows = []
    for product in products:
        missing = [field for field in REQUIRED_FIELDS if field not in product]
        if missing:
            raise ValueError(f"Product {product.get('id', '?')} is missing: {', '.join(missing)}")
        if product["id"] in seen_ids:
            raise ValueError(f"Duplicate product id: {product['id']}")
        if product["category"] not in ALLOWED_CATEGORIES:
            raise ValueError(f"Product {product['id']} has an unknown category")
        if product["currency"] != "USD":
            raise ValueError(f"Product {product['id']} must use USD")
        seen_ids.add(product["id"])

        rows.append(
            {
                "id": product["id"],
                "name": product["name"],
                "category": product["category"],
                "description": product["description"],
                # to_cents raises ValueError for a bad amount.
                "price_cents": to_cents(product["price"]),
                "shipping_cents": to_cents(product["shipping"]),
                "currency": product["currency"],
            }
        )
    return rows


def seed_products() -> int:
    """Insert or update every product. Returns the number of products loaded."""
    rows = load_products()
    init_db()
    connection = get_connection()
    try:
        with connection:  # one transaction: all products or none
            connection.executemany(
                """
                INSERT INTO products
                    (id, name, category, description, price_cents, shipping_cents, currency, is_demo)
                VALUES
                    (:id, :name, :category, :description, :price_cents, :shipping_cents, :currency, 1)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    description = excluded.description,
                    price_cents = excluded.price_cents,
                    shipping_cents = excluded.shipping_cents,
                    currency = excluded.currency,
                    is_demo = 1
                """,
                rows,
            )
    finally:
        connection.close()
    return len(rows)


if __name__ == "__main__":
    count = seed_products()
    print(f"Seeded {count} demo products.")
