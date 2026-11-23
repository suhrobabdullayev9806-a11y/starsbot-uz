# ===================================================================
# security.py - Xavfsizlik qatlami
#  - Authorization (admin huquqlari)
#  - Authentication (API callback maxfiy kalit)
#  - Himoyalangan ma'lumotlarni maxfiylashtirish
#  - Kiruvchi matnlarni tekshirish (sanitization)
# ===================================================================

from __future__ import annotations

import base64
import hashlib
import hmac
import re

from src.config import Settings

# SQL 'anastesi' (injection) uchun xavfli belgilar
_INJECTION_PATTERN = re.compile(r"['\";]|--|/\*|\\x")


def is_super_admin(user_id: int, cfg: Settings) -> bool:
    """Super admin (barcha huquqlar) ekanligini tekshiradi."""
    return user_id == cfg.super_admin_id


def is_admin(user_id: int, cfg: Settings) -> bool:
    """Foydalanuvchi adminlar ro'yxatida ekanligini tekshiradi."""
    return user_id in cfg.admin_ids or is_super_admin(user_id, cfg)


def safe_text(text: str | None, max_len: int = 200) -> str:
    """Matnni xavfsizlashtiradi: uzunlikni cheklaydi, match qiladi."""
    if text is None:
        return ""
    text = str(text)
    if len(text) > max_len:
        text = text[:max_len]
    # Boshqarish belgilarini olib tashlash
    return "".join(ch for ch in text if ch.isprintable())


def safe_amount(value: object) -> float:
    """Narx/balans qiymatini tekshiradi va musbat san'atga keltiradi."""
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError):
        raise ValueError("Noto'g'ri son")
    if amount < 0:
        raise ValueError("Manfiy qiymat ruxsat etilmaydi")
    if amount > 1_000_000_000:
        raise ValueError("Juda katta qiymat")
    return amount


def verify_callback_signature(secret: str, payload: str, signature: str) -> bool:
    """API webhook so'rovini HMAC-SHA256 imzosi bilan tekshiradi."""
    if not secret or not signature:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def sha256_hex(value: str) -> str:
    """Maxfiy qiymatlarni saqlashdan oldin qoraytirish."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fernet(bot_token: str):
    """Kalit bot_token dan deterministik hosil qilinadi (Fernet AES128)."""
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(hashlib.sha256(bot_token.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(plain: str, bot_token: str) -> str:
    """Maxfiy qiymatni Fernet bilan shifrlaydi (masalan session_string)."""
    if not plain:
        return ""
    return _fernet(bot_token).encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str, bot_token: str) -> str:
    """Shifrlangan qiymatni ochadi. Noto'g'ri/zarar bo'lsa '' qaytaradi."""
    if not token:
        return ""
    try:
        return _fernet(bot_token).decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""


def looks_like_injection(text: str) -> bool:
    """Ehtimoliy SQL-injection naqshini aniqlaydi."""
    return bool(_INJECTION_PATTERN.search(text or ""))


def admin_chat_id(user_id: int, cfg: Settings) -> int:
    """Admin chat id sifatida super admin yoki birinchi adminni qaytaradi."""
    return user_id if is_admin(user_id, cfg) else cfg.admin_ids[0]