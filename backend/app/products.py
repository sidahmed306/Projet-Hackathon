"""GET /api/products: list products from the demo catalog (docs/api.md, section b)."""

from typing import Optional

from fastapi import APIRouter

from app.db import get_connection
from app.errors import ApiError
from app.money import from_cents, to_cents

router = APIRouter()


def product_to_json(row) -> dict:
    """Turn a database row into the API shape (amounts as "749.00" strings)."""
    return {
        "id": row["id"],
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "price": from_cents(row["price_cents"]),
        "shipping": from_cents(row["shipping_cents"]),
        "currency": row["currency"],
        "is_demo": bool(row["is_demo"]),
    }


@router.get("/api/products")
def list_products(category: Optional[str] = None, max_price: Optional[str] = None) -> list[dict]:
    """Return products, cheapest first. Both filters are optional."""
    # Build the SQL query step by step. Values are passed as "?" parameters,
    # never pasted into the SQL text (this prevents SQL injection).
    sql = "SELECT * FROM products WHERE 1 = 1"
    params = []

    # " Laptop " and "LAPTOP" are treated like "laptop".
    category = (category or "").strip().lower()
    if category:
        sql += " AND category = ?"
        params.append(category)

    if max_price:
        try:
            max_price_cents = to_cents(max_price)
        except ValueError as error:
            raise ApiError("VALIDATION_ERROR", f"max_price: {error}", 400) from None
        sql += " AND price_cents <= ?"
        params.append(max_price_cents)

    sql += " ORDER BY price_cents, id"

    connection = get_connection()
    try:
        rows = connection.execute(sql, params).fetchall()
    finally:
        connection.close()
    return [product_to_json(row) for row in rows]
