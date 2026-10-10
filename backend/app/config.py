"""Application settings, read from the .env file at the project root.

Secrets (PayPal secret, Gemini key) are only read here and never printed.
Missing keys do not crash the server: they are simply empty for now.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# backend/app/config.py -> parents[2] is the project root (Projet-Hackathon/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load variables from Projet-Hackathon/.env (if the file exists).
# Variables already set in the environment are kept (override=False).
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    """All the settings the backend needs, in one place."""

    PAYPAL_CLIENT_ID: str
    PAYPAL_CLIENT_SECRET: str
    PAYPAL_API_BASE: str
    AI_MODE: str
    GEMINI_API_KEY: str
    SQLITE_PATH: str
    FRONTEND_ORIGIN: str

    def __repr__(self) -> str:
        # Never show secret values, even by accident (for example in a debug print).
        return (
            f"Settings(PAYPAL_API_BASE={self.PAYPAL_API_BASE!r}, AI_MODE={self.AI_MODE!r}, "
            f"SQLITE_PATH={self.SQLITE_PATH!r}, FRONTEND_ORIGIN={self.FRONTEND_ORIGIN!r}, "
            "secrets=<hidden>)"
        )


def _resolve_sqlite_path(value: str) -> str:
    """A relative SQLite path (like "backend/app.db") is relative to the project root."""
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


def load_settings() -> Settings:
    """Read the environment variables and apply default values."""
    return Settings(
        PAYPAL_CLIENT_ID=os.getenv("PAYPAL_CLIENT_ID", ""),
        PAYPAL_CLIENT_SECRET=os.getenv("PAYPAL_CLIENT_SECRET", ""),
        PAYPAL_API_BASE=os.getenv("PAYPAL_API_BASE") or "https://api-m.sandbox.paypal.com",
        AI_MODE=os.getenv("AI_MODE") or "mock",
        GEMINI_API_KEY=os.getenv("GEMINI_API_KEY", ""),
        SQLITE_PATH=_resolve_sqlite_path(os.getenv("SQLITE_PATH") or "backend/app.db"),
        FRONTEND_ORIGIN=os.getenv("FRONTEND_ORIGIN") or "http://localhost:5173",
    )


# The single settings object used by the rest of the app.
settings = load_settings()
