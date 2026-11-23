# ===================================================================
# session_middleware.py - HTML parse xatosidan himoya
# Telegram "can't parse entities" deb rad etsa (masalan foydalanuvchi
# matnida buzuq < > belgilar bo'lsa), xabar yo'qolmasligi uchun teglarsiz
# oddiy matn sifatida qayta yuboriladi.
# ===================================================================

from __future__ import annotations

import html
import logging
import re

from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest

_log = logging.getLogger("stars.parse")
_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def _plain(value: str) -> str:
    return html.unescape(_TAG_RE.sub("", value))


class ParseFallbackMiddleware(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        try:
            return await make_request(bot, method)
        except TelegramBadRequest as exc:
            if "parse entities" not in str(exc):
                raise
            update: dict = {"parse_mode": None}
            for field in ("text", "caption"):
                value = getattr(method, field, None)
                if isinstance(value, str):
                    update[field] = _plain(value)
            if not hasattr(method, "parse_mode"):
                raise
            _log.warning("HTML parse xatosi, oddiy matn bilan qayta yuborildi: %s", exc)
            return await make_request(bot, method.model_copy(update=update))
