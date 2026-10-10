"""SQLite access with Python's built-in sqlite3 module (no ORM)."""

import sqlite3
from pathlib import Path

# We import the module (not "settings" directly) so the path is read at call time.
# This lets the tests point the app to a temporary database.
from app import config


def get_connection() -> sqlite3.Connection:
    """Open a connection to the database file set in SQLITE_PATH."""
    path = Path(config.settings.SQLITE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    # Rows behave like dicts: row["name"] instead of row[1].
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    """Create the tables if they do not exist yet."""
    connection = get_connection()
    try:
        with connection:  # commits the transaction at the end
            connection.execute(
            """
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    price_cents INTEGER NOT NULL,
                    shipping_cents INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    is_demo INTEGER NOT NULL DEFAULT 1
                )
                """
            )
    finally:
        connection.close()


def count_products() -> int:
    """Return how many products are in the database."""
    connection = get_connection()
    try:
        return connection.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    finally:
        connection.close()
