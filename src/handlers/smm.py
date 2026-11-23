# ===================================================================
# handlers/smm.py - SMM NAKRUTKA (bot tomoni)
#  - "SMM Nakrutka" tugmasi mini-app (/smm) ni ochadi
#  - WEBAPP_BASE_URL sozlanmagan bo'lsa tushuntirish xabari
#  - Buyurtma natijasi (bajarildi / qisman / bekor) haqida xabar yuborish
# ===================================================================

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.app import App
from src.handlers._helpers import edit_or_send
from src.i18n import t
from src.keyboards import back_kb

router = Router(name="smm")
_log = logging.getLogger("stars.smm")


@router.callback_query(F.data == "menu:smm")
async def smm_menu_fallback(cb: CallbackQuery, app: App) -> None:
    lang = (await app.users.get(cb.from_user.id) or {}).get("language", "uz")
    await edit_or_send(cb, t(lang, "smm_no_webapp"), reply_markup=back_kb(lang))


async def notify_smm_result(bot, app: App, order: dict, outcome: str) -> None:
    """Buyurtma yakunlanganda foydalanuvchiga xabar (provayder xatosi 'failed' da xabarsiz:
    foydalanuvchi buni mini-appda darhol ko'radi)."""
    if bot is None or outcome == "failed":
        return
    lang = (await app.users.get(order["user_id"]) or {}).get("language", "uz")
    key = {"completed": "smm_done", "partial": "smm_partial", "canceled": "smm_canceled"}.get(outcome)
    if not key:
        return
    text = t(lang, key, name=html.escape(str(order["service_name"])), qty=f"{order['quantity']:,}",
             order_id=order["id"], refund=f"{float(order['refunded'] or 0):,.0f}")
    try:
        await bot.send_message(order["user_id"], text)
    except Exception as exc:  # noqa: BLE001
        _log.debug("smm xabar yuborilmadi: %s", exc)
