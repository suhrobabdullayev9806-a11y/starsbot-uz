# ===================================================================
# assets.py - Paket rasmlariga yo'l (assets/images/)
# Admin o'z rasmlarini qo'ysa shu papkaga tashlaydi; bot avtomatik
# o'qiydi. Rasm topilmasa None qaytadi (bot rasmsiz ishlaydi).
#
# TEZLIK: rasm har safar Telegram'ga qayta yuklanmasligi uchun
# file_id keshlanadi. Birinchi yuborishda upload bo'ladi, keyingi
# barcha menyular instant (file_id bilan).
# ===================================================================

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiogram.types import FSInputFile, Message

_IMAGES = Path(__file__).resolve().parent.parent / "assets" / "images"

# Pastga: fayl yo'li -> yuborilgan rasmning file_id (global, botiga bog'liq)
_PHOTO_CACHE: dict[str, str] = {}


def package_photo(amount: int) -> str | None:
    """Berilgan paket uchun rasm yo'lini qaytaradi (mavjud bo'lsa)."""
    candidates = [
        _IMAGES / f"star_{amount}.png",
        _IMAGES / f"star_{amount}.jpg",
        _IMAGES / f"{amount}.png",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def menu_banner() -> str | None:
    """Bosh menyu banneri (logo rasm) — 'chiroyli' start ko'rinishi."""
    for name in ("banner.png", "banner.jpg", "logo.png"):
        path = _IMAGES / name
        if path.exists():
            return str(path)
    return None


def package_photo_id_map(bot, amount: int) -> str | None:
    """Ixtiyoriy: bir marta jo'natilib, file_id eslab qolinadigan cache."""
    return cached_photo_id(menu_banner() or "")


def cached_photo_id(path: str) -> str | None:
    """Keshda rasmning file_id i bo'lsa qaytaradi."""
    return _PHOTO_CACHE.get(path)


def remember_photo_id(path: str, file_id: str) -> None:
    """Yuborilgan rasmning file_id ini eslab qoladi."""
    if path and file_id:
        _PHOTO_CACHE[path] = file_id


async def send_smart_photo(
    target: Any,  # Message yoki CallbackQuery
    path: str,
    caption: str,
    reply_markup=None,
) -> Message | None:
    """
    Rasmni keshlangani bilan yoki keshlanmagani bilan yuboradi.
    - agar file_id keshda bo'lsa: file_id -> tez (upload yo'q)
    - bo'lmasa: FSInputFile -> upload va file_id ni eslab qoladi
    Qaytaradi: yuborilgan Message (None agar muvaffaqiyatsiz).
    """
    if not path or not Path(path).exists():
        return None
    found_id = cached_photo_id(path)
    photo: Any = found_id or FSInputFile(path)
    try:
        if target.__class__.__name__ == "CallbackQuery":
            cid = getattr(target, "message", None)
            await cid.delete()
            sent = await cid.answer_photo(
                photo, caption=caption, reply_markup=reply_markup
            )
        else:
            sent = await target.answer_photo(
                photo, caption=caption, reply_markup=reply_markup
            )
    except Exception:  # noqa: BLE001
        return None
    if not found_id and getattr(sent, "photo", None):
        remember_photo_id(path, sent.photo[-1].file_id)
    return sent