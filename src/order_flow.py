# ===================================================================
# order_flow.py - Buyurtmani tasdiqlash / rad etish (BOT va MINI-APP umumiy)
# Bir xil mantiq: Telegram tugmalari ham, admin mini-app ham shuni chaqiradi.
# ===================================================================

from __future__ import annotations

import asyncio
import logging

from src.i18n import t

_log = logging.getLogger("stars.orders")


async def _pay_channel(bot, app, order_id: int) -> None:
    try:
        from src.handlers._helpers import notify_payments_channel

        await notify_payments_channel(bot, app, order_id)
    except Exception as exc:  # noqa: BLE001
        _log.debug("to'lovlar kanali: %s", exc)


async def _tell(bot, user_id: int, text: str) -> None:
    if bot is None:
        return
    try:
        await bot.send_message(user_id, text)
    except Exception:  # noqa: BLE001
        pass


async def decide_order(app, bot, order_id: int, approve: bool) -> tuple[bool, str]:
    """Buyurtma bo'yicha qaror. Qaytaradi: (ok, xabar)."""
    order = await app.orders.get(order_id)
    if not order:
        return False, "order_not_found"
    if order["status"] not in ("pending", "processing"):
        return False, f"already_{order['status']}"
    uid = order["user_id"]
    lang = (await app.users.get(uid) or {}).get("language", "uz")
    typ = order["type"]
    amount = float(order["stars_amount"] or 0)

    if typ == "nft":
        from src.handlers.nft import finish_nft_order

        done = await finish_nft_order(bot, app, order, approve=approve)
        if done and approve:
            asyncio.create_task(_pay_channel(bot, app, order_id))
        return done, "ok" if done else "already_processed"

    if typ == "uc":
        from src.handlers.uc import finish_uc_order

        done = await finish_uc_order(bot, app, order, approve=approve)
        if done and approve:
            asyncio.create_task(_pay_channel(bot, app, order_id))
        return done, "ok" if done else "already_processed"

    if typ == "gram":
        from src.handlers.gram import finish_gram_order

        done = await finish_gram_order(bot, app, order, approve=approve)
        if done and approve:
            asyncio.create_task(_pay_channel(bot, app, order_id))
        return done, "ok" if done else "already_processed"

    if not approve:
        await app.admin.reject_order(order_id, "admin rejected")
        await _tell(bot, uid, t(lang, "order_rejected_user", order_id=order_id))
        return True, "ok"

    if typ == "post_stars":
        ok, reason = await app.admin.confirm_post_stars(order_id, amount)
        await _tell(bot, uid, t(lang, "post_approved_user", amount=amount) if ok
                    else t(lang, "post_approval_failed", reason=reason))
        if ok:
            asyncio.create_task(_pay_channel(bot, app, order_id))
        return ok, reason
    if typ == "buy":
        await app.payments.approve_card_order(order_id, uid, amount)
        await _tell(bot, uid, t(lang, "api_order_success", amount=amount))
    elif typ == "topup":
        await app.payments.approve_card_order(order_id, uid, 0)
        await _tell(bot, uid, t(lang, "topup_enough",
                                balance=f"{float(order['price_amount']):,.0f}"))
    else:  # gift
        await app.payments.approve_card_order(order_id, uid, amount)
        await _tell(bot, uid, t(lang, "gift_sent", amount=amount, name="Gift", balance=0))
    asyncio.create_task(_pay_channel(bot, app, order_id))
    return True, "ok"
