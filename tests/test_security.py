# ===================================================================
# test_security.py - Xavfsizlik funksiyalari
# ===================================================================

import pytest

from src.config import Settings
from src.security import (
    is_admin,
    is_super_admin,
    safe_amount,
    safe_text,
    sha256_hex,
    verify_callback_signature,
)


@pytest.fixture
def cfg() -> Settings:
    return Settings(bot_token="12345", admin_ids=[10, 20], super_admin_id=10)


def test_is_admin(cfg):
    assert is_admin(10, cfg) is True
    assert is_admin(20, cfg) is True
    assert is_admin(999, cfg) is False


def test_is_super_admin(cfg):
    assert is_super_admin(10, cfg) is True
    assert is_super_admin(20, cfg) is False


def test_safe_amount_ok():
    assert safe_amount("12.5") == 12.5
    assert safe_amount(0) == 0.0


def test_safe_amount_negative():
    with pytest.raises(ValueError):
        safe_amount(-5)


def test_safe_text_trim():
    assert len(safe_text("x" * 500)) <= 200


@pytest.mark.asyncio
async def test_verify_signature_roundtrip():
    secret = "s3cr3t"
    payload = '{"order_id": 5}'
    import hashlib
    import hmac

    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    assert verify_callback_signature(secret, payload, sig) is True
    assert verify_callback_signature(secret, payload, "bad") is False
    assert verify_callback_signature("", payload, sig) is False


def test_sha256_deterministic():
    assert sha256_hex("abc") == sha256_hex("abc")
    assert sha256_hex("abc") != sha256_hex("abd")