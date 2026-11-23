# ===================================================================
# handlers/wallet.py - HISOB (SO'MDA) VA STARS BALANSI
#  - Hisob: naqd pul (so'm) — karta / online orqali to'ldiriladi
#  - Stars: so'm hisobdan sotib olinadi (buy.py)
#  - Sof so'm, stars, statistika va tarix
# ===================================================================

from __future__ import annotations

import asyncio
import logging
import re

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.app import App
from src.handlers._helpers import (
    edit_or_send,
    notify_admins_media,
    notify_all_admins,
    notify_payments_channel,
    user_ref,
)
from src.handlers.states import TopupFlow
from src.i18n import t
from src.keyboards import (
    admin_orders_kb,
    topup_amounts_kb,
    topup_cancel_kb,
    topup_kb,
    topup_pay_kb,
    topup_result_kb,
    wallet_kb,
)
from src.utils import format_amount, progress_bar

router = Router(name="wallet")

_total_cap = 100.0  # stars progress bar to'lishi uchun shartli me'yor


async def _safe_pay_channel(bot, app, order_id: int) -> None:
    try:
        await notify_payments_channel(bot, app, order_id)
    except Exception:  # noqa: BLE001
        pass


async def _safe_admins(bot, text: str, app, kb=None) -> None:
    try:
        await notify_all_admins(bot, text, app, kb)
    except Exception:  # noqa: BLE001
        pass


async def _safe_admins_media(bot, photo_id: str, caption: str, app, kb=None) -> None:
    try:
        await notify_admins_media(bot, photo_id, caption, app, kb)
    except Exception:  # noqa: BLE001
        pass


async def _lang(app: App, user_id: int) -> str:
    return (await app.users.get(user_id) or {}).get("language", "uz")


def _fmt(value: float) -> str:
    """So'm miqdorini chiroyli formatda yozadi: 100 000"""
    return f"{value:,.0f}"


def _parse_sum(text: str) -> int | None:
    """Matndan faqat sonni oladi (bo'sh joy/kursa belgisi bo'lmaydi)."""
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    return int(digits) if digits else None


@router.callback_query(F.data == "menu:wallet")
async def show_wallet(cb: CallbackQuery, app: App) -> None:
    """Asosiy hisob ko'rinishi (so'm + stars)."""
    lang = await _lang(app, cb.from_user.id)
    user = await app.users.get(cb.from_user.id) or {}
    sum_bal = float(user.get("balance_sum", 0))
    bal = float(user.get("balance_stars", 0))
    totals = await app.users.totals(cb.from_user.id)
    prog = progress_bar(bal, _total_cap)
    await edit_or_send(cb,
        t(lang, "wallet_title",
          sum=_fmt(sum_bal),
          balance=format_amount(bal), progress=prog,
          bought=format_amount(float(totals.get("bought", 0))),
          sold=format_amount(float(totals.get("sold", 0))),
          gifted=format_amount(float(totals.get("gifted", 0)))),
        reply_markup=wallet_kb(lang),
    )


def _sp(value: float) -> str:
    """100000 -> '100 000' (topup matnlari uchun)."""
    return f"{value:,.0f}".replace(",", " ")


def _tx_from_order(order: dict) -> str:
    m = re.match(r"tx:([a-z0-9]+)", str(order.get("note") or ""))
    return m.group(1) if m else "—"


async def notify_topup_result(bot, app: App, order: dict, outcome: str, reason: str) -> None:
    """Avto-to'lov yakuni (fon tekshiruvidan): foydalanuvchiga tugmali xabar."""
    user_id = int(order["user_id"])
    lang = await _lang(app, user_id)
    amount = _sp(float(order.get("price_amount") or 0))
    tx = _tx_from_order(order)
    if outcome == "done":
        balance = _sp(await app.users.balance_sum(user_id))
        text = t(lang, "topup_ok", amount=amount, balance=balance)
        kb = topup_result_kb(lang, True)
    else:
        text = t(lang, f"topup_fail_{reason}", amount=amount, tx=tx)
        if text == f"topup_fail_{reason}":
            text = t(lang, "topup_fail_generic")
        kb = topup_result_kb(lang, False)
    try:
        await bot.send_message(user_id, text, reply_markup=kb)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("stars.topup").warning("topup xabari yuborilmadi (%s): %s", user_id, exc)
    if outcome == "done":
        asyncio.create_task(_safe_pay_channel(bot, app, int(order["id"])))


@router.callback_query(F.data == "topup:choose")
async def topup_choose(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Hisobni so'mda to'ldirish usullari."""
    await state.clear()
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb, t(lang, "wallet_topup"), reply_markup=topup_kb(lang))


@router.callback_query(F.data == "topup:card")
async def topup_card_start(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Karta orqali (avto) — summani tanlash."""
    await state.clear()
    lang = await _lang(app, cb.from_user.id)
    lo, hi = app.cfg.topup_min, app.cfg.topup_max
    await edit_or_send(
        cb, t(lang, "topup_pick", min=_sp(lo), max=_sp(hi)),
        reply_markup=topup_amounts_kb(lang, lo, hi),
    )


@router.callback_query(F.data == "topup:auto")
async def topup_api_start(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Online (API) orqali so'm to'ldirish."""
    lang = await _lang(app, cb.from_user.id)
    await state.set_state(TopupFlow.wait_sum)
    await state.update_data(topup_method="api")
    await edit_or_send(
        cb, t(lang, "topup_sum_prompt", min=_sp(app.cfg.topup_min), max=_sp(app.cfg.topup_max)),
        reply_markup=topup_cancel_kb(lang),
    )


@router.callback_query(F.data == "topup:other")
async def topup_other(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    lang = await _lang(app, cb.from_user.id)
    await state.set_state(TopupFlow.wait_sum)
    await state.update_data(topup_method="card")
    await edit_or_send(
        cb, t(lang, "topup_sum_prompt", min=_sp(app.cfg.topup_min), max=_sp(app.cfg.topup_max)),
        reply_markup=topup_cancel_kb(lang),
    )


async def _show_pay_details(target, app: App, state: FSMContext, lang: str, value: int) -> None:
    """Karta rekvizitlari + 'To'ladim' tugmasi."""
    card = (await app.settings.payment_card() or app.cfg.payment_card or "").strip()
    holder = (await app.settings.payment_card_holder() or app.cfg.payment_card_holder or "").strip()
    if not card:
        await edit_or_send(target, t(lang, "topup_no_card"), reply_markup=topup_cancel_kb(lang))
        return
    await state.set_state(None)
    await state.update_data(topup_sum=value, topup_method="card")
    await edit_or_send(
        target,
        t(lang, "topup_card_pay", amount=_sp(value), card=card,
          holder=holder or t(lang, "topup_card_pay_noholder")),
        reply_markup=topup_pay_kb(lang),
    )


@router.callback_query(F.data.startswith("topup:amt:"))
async def topup_amount_chosen(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    lang = await _lang(app, cb.from_user.id)
    try:
        value = int(cb.data.split(":")[2])
    except (IndexError, ValueError):
        return
    if not app.cfg.topup_min <= value <= app.cfg.topup_max:
        await cb.answer("⚠️", show_alert=True)
        return
    await _show_pay_details(cb, app, state, lang, value)


@router.message(StateFilter(TopupFlow.wait_sum))
async def topup_sum_received(message: Message, app: App, state: FSMContext) -> None:
    """Qo'lda yozilgan summa: API -> avtomatik, karta -> rekvizitlar."""
    lang = await _lang(app, message.from_user.id)
    value = _parse_sum(message.text or "")
    lo, hi = app.cfg.topup_min, app.cfg.topup_max
    if not value or not lo <= value <= hi:
        await message.answer(t(lang, "topup_sum_bad", min=_sp(lo), max=_sp(hi)),
                             reply_markup=topup_cancel_kb(lang))
        return
    data = await state.get_data()
    method = data.get("topup_method", "card")

    if method == "api":
        order_id = await app.payments.create_intent(
            message.from_user.id, "topup", 0, "api", price=float(value)
        )
        await message.answer(t(lang, "api_order_creating"))
        result = await app.payments.submit_api_payment(order_id, message.from_user.id, value)
        if result.ok:
            new_bal = await app.payments.complete_successful(order_id, message.from_user.id, value)
            asyncio.create_task(_safe_pay_channel(message.bot, app, order_id))
            await message.answer(
                t(lang, "topup_api_success", balance=_sp(new_bal)),
                reply_markup=topup_result_kb(lang, True),
            )
        else:
            await message.answer(t(lang, "api_order_failed"),
                                 reply_markup=topup_result_kb(lang, False))
        await state.clear()
        return

    await _show_pay_details(message, app, state, lang, value)


@router.callback_query(F.data == "topup:paid")
async def topup_paid(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """'To'ladim' bosildi: tranzaksiya ID sini so'raymiz."""
    lang = await _lang(app, cb.from_user.id)
    data = await state.get_data()
    value = data.get("topup_sum")
    if not value:
        await edit_or_send(cb, t(lang, "wallet_topup"), reply_markup=topup_kb(lang))
        return
    await state.set_state(TopupFlow.wait_txid)
    await edit_or_send(cb, t(lang, "topup_ask_txid", amount=_sp(value)),
                       reply_markup=topup_cancel_kb(lang))


@router.callback_query(F.data == "topup:cancel")
async def topup_cancel(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    await state.clear()
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(
        cb, t(lang, "topup_cancelled") + "\n\n" + t(lang, "wallet_topup"),
        reply_markup=topup_kb(lang),
    )


@router.message(StateFilter(TopupFlow.wait_txid))
async def topup_txid_received(message: Message, app: App, state: FSMContext) -> None:
    """Tranzaksiya ID keldi: bot tekshiradi -> to'g'ri bo'lsa balansga qo'shadi, bo'lmasa bekor."""
    lang = await _lang(app, message.from_user.id)
    data = await state.get_data()
    value = data.get("topup_sum")
    if not value:
        await state.clear()
        await message.answer(t(lang, "wallet_topup"), reply_markup=topup_kb(lang))
        return
    tx_raw = (message.text or "").strip()
    if not tx_raw:
        await message.answer(t(lang, "topup_txid_bad"), reply_markup=topup_cancel_kb(lang))
        return

    res = await app.bank.submit(message.from_user.id, float(value), tx_raw)
    status, reason = res["status"], res["reason"]
    amount = _sp(value)

    if status == "rejected" and reason in ("bad_tx", "bad_amount", "amount_range"):
        await message.answer(t(lang, "topup_txid_bad"), reply_markup=topup_cancel_kb(lang))
        return  # state saqlanadi: qayta yuborishi mumkin

    await state.clear()
    tx = (res.get("order_id") and _tx_from_order(await app.orders.get(res["order_id"]) or {})) \
        or re.sub(r"[^a-z0-9]", "", tx_raw.lower())

    if status == "done":
        asyncio.create_task(_safe_pay_channel(message.bot, app, res["order_id"]))
        await message.answer(
            t(lang, "topup_ok", amount=amount, balance=_sp(res["balance_sum"])),
            reply_markup=topup_result_kb(lang, True),
        )
    elif status == "pending":
        await message.answer(t(lang, "topup_checking", tx=tx, amount=amount))
    elif status == "manual":
        user = await app.users.get(message.from_user.id) or {}
        asyncio.create_task(_safe_admins(
            message.bot,
            t("uz", "topup_sent_admin", uid=message.from_user.id, user=user_ref(user),
              amount=amount, proof=tx),
            app, admin_orders_kb("uz", res["order_id"]),
        ))
        await message.answer(t(lang, "topup_manual_sent", tx=tx, amount=amount),
                             reply_markup=topup_result_kb(lang, True))
    else:
        text = t(lang, f"topup_fail_{reason}", amount=amount, tx=tx)
        if text == f"topup_fail_{reason}":
            text = t(lang, "topup_fail_generic")
        await message.answer(text, reply_markup=topup_result_kb(lang, False))


@router.callback_query(F.data == "wallet:history")
async def wallet_history(cb: CallbackQuery, app: App) -> None:
    """Transaksiyalar tarixi."""
    lang = await _lang(app, cb.from_user.id)
    rows = await app.users.history(cb.from_user.id, 12)
    if not rows:
        await edit_or_send(cb,
            t(lang, "wallet_history", history=t(lang, "tx_none")),
            reply_markup=wallet_kb(lang),
        )
        return
    lines = []
    for r in rows:
        sign = "➕" if r["type"] == "credit" else "➖"
        lines.append(f"{sign} <b>{format_amount(float(r['amount']))}</b> · {r['reason']}")
    await edit_or_send(cb,
        t(lang, "wallet_history", history="\n".join(lines)),
        reply_markup=wallet_kb(lang),
    )