# ===================================================================
# tests/conftest.py - Testlar uchun umumiy fixture
# In-memory SQLite + App konteyner.
# ===================================================================

from __future__ import annotations

import pytest

from src.app import App
from src.config import Settings


def make_settings() -> Settings:
    return Settings(
        bot_token="123:TESTTOKEN",
        admin_ids=[111, 222],
        super_admin_id=111,
        required_channel="test_channel",
        db_path=":memory:",
        webapp_port=0,
    )


@pytest.fixture
async def app() -> App:
    a = App(make_settings(), db_path=":memory:")
    await a.connect()
    yield a
    await a.close()