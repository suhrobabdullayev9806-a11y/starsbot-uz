# ===================================================================
# handlers/buy.py - STARS SOTIB OLISH (step-by-step)
# Paket tanlash → To'lov usuli → To'lov → Stars yetkazib berish
# ===================================================================

from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from src.app import App
from src.assets import package_photo, send_smart_photo
from src.handlers._helpers import (
    edit_or_send,
    notify_admins_content,
    notify_all_admins,
    notify_payments_channel,
    user_ref,
)
from src.handlers.states import BuyFlow
from src.i18n import t
from src.keyboards import admin_orders_kb, back_kb, buy_packages_kb, main_menu_kb, paid_button_kb, payment_method_kb
from src.utils import prices_text

router = Router(name="buy")


async def _safe_notify_payments(bot, app, order_id: int) -> None:
    """To'lovlar kanali xabarini fon task sifatida — xatolarni yutadi."""
    try:
        await notify_payments_channel(bot, app, order_id)
    except Exception:  # noqa: BLE001
        pass


async def _safe_notify_admins(bot, text: str, app, kb=None) -> None:
    """Adminlarga xabarni fon task sifatida — xatolarni yutadi."""
    try:
        await notify_all_admins(bot, text, app, kb)
    except Exception:  # noqa: BLE001
        pass


async def _safe_notify_admins_media(bot, media_kind: str, file_id: str, caption: str,
                                    app, kb=None) -> None:
    """Chekni media TURIGA qarab adminlarga universal yetkazadi.

    Endi chek rasm-png(RASM)/skrinshot-document/video/animatsiya qilib
    yuborilganiga qarab mos usulda adminga boradi — Tomon retry va log
    `notify_admins_content` ichida. Faqat eski imzo (photo) chaqiruvlari
    uchun imzo o'zgartirildi — `notify_admins_content` ga qarang.
    """
    try:
        await notify_admins_content(bot, media_kind, file_id, caption, app, kb)
    except Exception:  # noqa: BLE001
        pass


async def _lang(app: App, user_id: int) -> str:
    return (await app.users.get(user_id) or {}).get("language", "uz")


async def _buy_packages(app: App) -> dict[int, float]:
    """Xarid paketlari: agar 1⭐ narxi sozlangan bo'lsa — minimal 50 dan
    100gacha o'sadigan qator; aks holda eski narxlar jadvali."""
    star_price = await app.settings.get_star_price()
    if star_price > 0:
        min_stars = await app.settings.get_min_stars()
        out: dict[int, float] = {}
        for mult in (1, 2, 3, 5, 10):
            amount = min_stars * mult
            if amount <= 100000:
                out[amount] = round(star_price * amount, 2)
        return out
    return await app.settings.get_prices() or app.cfg.default_prices


async def _prices_html(app: App) -> str:
    star_price = await app.settings.get_star_price()
    if star_price > 0:
        min_stars = await app.settings.get_min_stars()
        lines = "\n".join(
            f"⭐ <b>{a}</b> Stars  →  {float(p):,.0f} so'm"
            for a, p in sorted((await _buy_packages(app)).items())
        )
        return f"💎 1 ⭐ = <b>{star_price:,.0f} so'm</b> (min {min_stars}⭐)\n{lines}"
    prices = await app.settings.get_prices() or app.cfg.default_prices
    percent = await app.settings.get_percent()
    return prices_text(prices, percent)


@router.callback_query(F.data == "menu:buy")
async def show_packages(cb: CallbackQuery, app: App) -> None:
    """Paketlar ro'yxati (star_price bo'yicha, minimal 50)."""
    lang = await _lang(app, cb.from_user.id)
    prices = await _buy_packages(app)
    sum_bal = await app.users.balance_sum(cb.from_user.id)
    await edit_or_send(cb, 
        t(lang, "buy_choose", prices=await _prices_html(app), balance=f"{sum_bal:,.0f}"),
        reply_markup=buy_packages_kb(lang, prices, webapp_url=app.cfg.webapp_base_url),
    )


@router.callback_query(F.data == "menu:pricing")
async def show_pricing(cb: CallbackQuery, app: App) -> None:
    """Narxlar jadvali."""
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb, 
        t(lang, "pricing_text", prices=await _prices_html(app)),
        reply_markup=back_kb(lang, "menu:main"),
    )


@router.callback_query(F.data.startswith("buy:"))
async def choose_package(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Paket tanlangach to'lov usulini so'raydi (step-by-step 1-qadam)."""
    lang = await _lang(app, cb.from_user.id)
    amount_raw = cb.data.split(":", 2)[1]
    if amount_raw == "from_balance":
        await show_packages(cb, app)  # balansdan ham avval paket kerak
        return
    try:
        amount = int(amount_raw)
    except ValueError:
        await cb.answer("❌")
        return
    prices = await _buy_packages(app)
    if amount not in prices:
        await cb.answer("❌ Mavjud emas")
        return
    # Step-by-step: paket tanlandi, keyin to'lov usuli
    await state.set_state(BuyFlow.choose_package)
    await state.update_data(package=amount)
    text = t(lang, "buy_method", amount=amount) + "\n\n" + await _prices_html(app)
    photo = package_photo(amount)
    if photo:
        sent = await send_smart_photo(cb, photo, text, payment_method_kb(lang, amount))
        if sent is None:
            await edit_or_send(cb, text, reply_markup=payment_method_kb(lang, amount))
    else:
        await edit_or_send(cb, text, reply_markup=payment_method_kb(lang, amount))


@router.callback_query(F.data.startswith("method:"))
async def choose_method(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """To'lov usuli tanlangach (step-by-step 2-qadam) buyurtma yaratiladi."""
    lang = await _lang(app, cb.from_user.id)
    _, amount_s, method = cb.data.split(":")
    amount = int(amount_s)
    star_price = await app.settings.get_star_price()
    if star_price > 0:
        price = round(star_price * amount, 2)
        percent = 0.0
    else:
        prices = await app.settings.get_prices() or app.cfg.default_prices
        price = prices.get(amount, 0.0)
        percent = await app.settings.get_percent()
    final_price = round(price * (1 + percent / 100), 2) if price else 0.0

    if final_price <= 0:
        await edit_or_send(cb, t(lang, "no_price"))
        await state.clear()
        return

    order_id = await app.payments.create_intent(
        cb.from_user.id, "buy", amount, method, price=final_price
    )
    await state.update_data(pending_order_id=order_id)

    if method == "card":
        # ---- Karta (ruchka): admin tasdiqlaydi ----
        card = await app.settings.payment_card() or app.cfg.payment_card
        await state.set_state(BuyFlow.card_proof)
        await edit_or_send(cb, 
            t(lang, "card_pay_instructions", amount=amount, price=final_price, card=card),
            reply_markup=paid_button_kb(lang, amount),
        )
        return

    if method == "balance":
        # ---- So'm hisobidan to'lash: narx ayiriladi, stars qo'shiladi ----
        result = await app.payments.pay_from_balance(order_id, cb.from_user.id, amount, final_price)
        if result.ok:
            asyncio.create_task(_safe_notify_payments(cb.message.bot, app, order_id))
            await edit_or_send(cb, 
                t(lang, "balance_buy_ok",
                  price=f"{final_price:,.0f}", amount=amount, order_id=order_id,
                  balance=result.balance),
                reply_markup=main_menu_kb(lang),
            )
        else:
            await edit_or_send(cb, 
                t(lang, "insufficient_sum",
                  balance=f"{await app.users.balance_sum(cb.from_user.id):,.0f}",
                  need=f"{final_price:,.0f}"),
                reply_markup=back_kb(lang, "menu:buy"),
            )
        await state.clear()
        return

    if method == "api":
        # ---- Online API (@Apilarimbot): avtomatik ----
        await edit_or_send(cb, t(lang, "api_order_creating"))
        result = await app.payments.submit_api_payment(order_id, cb.from_user.id, amount)
        if result.ok:
            await app.payments.complete_successful(order_id, cb.from_user.id, amount)
            asyncio.create_task(_safe_notify_payments(cb.message.bot, app, order_id))
            await edit_or_send(cb, 
                t(lang, "api_order_success", amount=amount),
                reply_markup=main_menu_kb(lang),
            )
        else:
            await edit_or_send(cb, 
                t(lang, "api_order_failed"),
                reply_markup=main_menu_kb(lang),
            )
        await state.clear()
        return


@router.callback_query(F.data.startswith("paid:"))
async def paid_clicked(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """'To'lov qildim' — tasdiq matnini kutamiz (step-by-step 3-qadam)."""
    lang = await _lang(app, cb.from_user.id)
    data = await state.get_data()
    if not data.get("pending_order_id"):
        await cb.answer("❌")
        return
    await edit_or_send(cb, t(lang, "card_paid_note"))
    await state.set_state(BuyFlow.card_proof)


@router.message(StateFilter(BuyFlow.card_proof))
async def card_proof_received(message: Message, app: App, state: FSMContext) -> None:
    """Foydalanuvchi to'lov tasdig'ini yuborganida — adminlarga yuboriladi."""
    lang = await _lang(app, message.from_user.id)
    data = await state.get_data()
    order_id = data.get("pending_order_id")
    if not order_id:
        await message.answer("❌ Buyurtma topilmadi. /start ni bosing.")
        await state.clear()
        return

    user = await app.users.get(message.from_user.id) or {}
    proof = (
        f"💳 {message.text[:500] if message.text else '[Rasm tasdiq]'}\n\n"
        f"👤 {user_ref(user)}"
    )
    result = await app.payments.submit_card_payment(int(order_id), message.from_user.id, proof)
    if not result.ok:
        await message.answer(t(lang, "admin_invalid_format"))
        return

    # Adminlarga buyurtma + tasdiqlash tugmalari yuboriladi (fon task)
    order = await app.orders.get(int(order_id))
    if order:
        admin_text = t(lang, "admin_new_order",
                        order_id=order_id, user=user_ref(user), amount=order["stars_amount"],
                        method=order["payment_method"], note=order["note"])
        photo = message.photo[0] if message.photo else None
        if photo:
            asyncio.create_task(_safe_notify_admins_media(
                message.bot, photo.file_id, admin_text, app,
                admin_orders_kb(lang, int(order_id)),
            ))
        else:
            asyncio.create_task(_safe_notify_admins(
                message.bot, admin_text, app,
                admin_orders_kb(lang, int(order_id)),
            ))
    await message.answer(
        t(lang, "order_created_user", order_id=order_id,
          amount=order["stars_amount"] if order else "",
          method=order["payment_method"] if order else "card"))
    await state.clear()