# ===================================================================
# subscription.py - MAJBURIY OBUNA
# - check_member(): foydalanuvchi kanal a'zosimi
# - SubscriptionGuard: natijani qisqa muddat keshlaydi (Telegram API ni
#   har tugma bosilganda urmaslik uchun)
# - SubscriptionMiddleware: HAR BIR xabar va tugma bosishda tekshiradi
#   (faqat /start da emas), obuna bo'lmaganlarga kanal tugmasi chiqadi.
# Adminlar tekshiruvdan ozod.
# ===================================================================

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message

log = logging.getLogger("stars.sub")

_CACHE_TTL = 120.0          # obunani "ok" deb eslab qolish (sekund)
_WARN_EVERY = 600.0         # tekshirib bo'lmasa logga ogohlantirish chastotasi

# Obuna bo'lmagan foydalanuvchi ham bosa oladigan tugmalar
_ALLOWED_CALLBACKS = ("check:sub", "lang:")


async def check_member(bot: Bot, user_id: int, channel: str, channel_id: str | None) -> bool:
    """True = a'zo (yoki tekshirib bo'lmaydi). Kanal sozlanmagan bo'lsa True."""
    if not channel and not channel_id:
        return True
    chat_id: Any = channel_id if channel_id else f"@{channel}"
    try:
        chat_id = int(chat_id)
    except (TypeError, ValueError):
        pass
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except Exception as exc:  # noqa: BLE001
        # Bot kanalda admin emas / kanal topilmadi: foydalanuvchini bloklamaymiz,
        # lekin adminga ko'rinishi uchun ogohlantiramiz.
        SubscriptionGuard.warn(f"obunani tekshirib bo'lmadi ({chat_id}): {exc}")
        return True
    if member.status in ("member", "administrator", "creator"):
        return True
    # "restricted" holati: kanalda qolgan, lekin cheklangan
    return member.status == "restricted" and bool(getattr(member, "is_member", False))


async def missing_channels(bot: Bot, user_id: int, channels: list[dict]) -> list[dict]:
    """Obuna bo'lmagan kanallar ro'yxati. Tekshirib bo'lmaydigan kanal o'tkaziladi."""
    missing: list[dict] = []
    for c in channels or []:
        username = str(c.get("username") or "").lstrip("@")
        chat_id = str(c.get("chat_id") or "")
        if await check_member(bot, user_id, username, chat_id or None):
            continue
        missing.append(c)
    return missing


class SubscriptionGuard:
    _last_warn = 0.0

    def __init__(self) -> None:
        self._ok_until: dict[int, float] = {}

    @classmethod
    def warn(cls, msg: str) -> None:
        now = time.monotonic()
        if now - cls._last_warn > _WARN_EVERY:
            cls._last_warn = now
            log.warning("%s — botni kanalga ADMIN qilib qo'shing!", msg)

    async def ok(self, app, bot: Bot | None, user_id: int) -> bool:
        if bot is None or await app.is_admin(user_id):
            return True
        channels = await app.settings.get_channels()
        if not channels:
            return True
        if self._ok_until.get(user_id, 0.0) > time.monotonic():
            return True
        if not await missing_channels(bot, user_id, channels):
            self._ok_until[user_id] = time.monotonic() + _CACHE_TTL
            if len(self._ok_until) > 50_000:
                self._ok_until.clear()
            return True
        self._ok_until.pop(user_id, None)
        return False

    def forget(self, user_id: int) -> None:
        self._ok_until.pop(user_id, None)


class SubscriptionMiddleware(BaseMiddleware):
    """Obuna bo'lmaganlarga hech narsani ochmaydi (kanal + 'Tekshirish' tugmalari chiqadi)."""

    def __init__(self, guard: SubscriptionGuard):
        self.guard = guard

    async def __call__(self, handler: Callable[[Any, dict], Awaitable[Any]],
                       event: Any, data: dict) -> Any:
        app = data.get("app")
        user = data.get("event_from_user")
        if app is None or user is None or user.is_bot:
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            if (event.data or "").startswith(_ALLOWED_CALLBACKS):
                return await handler(event, data)
            if event.message is not None and event.message.chat.type != "private":
                return await handler(event, data)
        elif isinstance(event, Message):
            if event.chat.type != "private":
                return await handler(event, data)
            if (event.text or "").startswith("/start"):
                return await handler(event, data)   # start.py o'zi ko'rsatadi
        else:
            return await handler(event, data)

        if await self.guard.ok(app, data.get("bot"), user.id):
            return await handler(event, data)

        # --- obuna yo'q: so'rov to'xtatiladi ---
        from src.i18n import t
        from src.keyboards import check_subscribe_kb

        lang = (await app.users.get(user.id) or {}).get("language", "uz")
        channels = await app.settings.get_channels()
        label = ", ".join(
            "@" + str(c.get("username")) for c in channels if c.get("username")) or "—"
        if len(channels) > 1:
            text = t(lang, "start_not_subscribed_multi", channels=label)
        else:
            text = t(lang, "start_not_subscribed", channel=label)
        kb = check_subscribe_kb(lang, channels=channels)
        try:
            if isinstance(event, CallbackQuery):
                await event.answer("📢", show_alert=False)
                if event.message is not None:
                    await event.message.answer(text, reply_markup=kb)
            else:
                await event.answer(text, reply_markup=kb)
        except Exception:  # noqa: BLE001
            pass
        return None
