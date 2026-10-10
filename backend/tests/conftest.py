"""Shared test setup.

Every test runs with a fresh temporary SQLite database, so the tests
NEVER touch the real backend/app.db.
"""

import dataclasses

import pytest

from app import config


@pytest.fixture(autouse=True)
def temporary_database(tmp_path, monkeypatch):
    test_settings = dataclasses.replace(config.settings, SQLITE_PATH=str(tmp_path / "test.db"))
    monkeypatch.setattr(config, "settings", test_settings)
    yield test_settings.SQLITE_PATH
