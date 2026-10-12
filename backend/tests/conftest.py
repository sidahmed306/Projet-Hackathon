"""Shared test setup.

Every test runs with a fresh temporary SQLite database, so the tests
NEVER touch the real backend/app.db.
"""

import dataclasses

import httpx
import pytest

from app import config


@pytest.fixture(autouse=True)
def temporary_database(tmp_path, monkeypatch):
    test_settings = dataclasses.replace(config.settings, SQLITE_PATH=str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "settings", test_settings)
    yield test_settings.SQLITE_PATH


@pytest.fixture(autouse=True)
def block_real_paypal(monkeypatch):
    """Safety net: no test may ever call the real PayPal.

    Any PayPal request that a test did not mock fails immediately.
    """
    from app import paypal_client

    def refuse(request):
        raise AssertionError(f"Test tried to call the real PayPal: {request.method} {request.url.path}")

    monkeypatch.setattr(paypal_client, "_transport", httpx.MockTransport(refuse))
    paypal_client._token_cache.clear()
    yield
    paypal_client._token_cache.clear()
