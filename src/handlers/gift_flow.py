# ===================================================================
# handlers/gift_flow.py - GIFT OLISH VA BERISH
#  - Admin gift katalogini qo'shadi (nomi, narxi, soni)
#  - Foydalanuvchi gift tanlaydi, so'mlik hisobdan to'laydi
#  - Qabul qiluvchi @username / telefon raqam kiritadi
#  - Akkaunt orqali avtomatik yetkaziladi
# ===================================================================

from __future__ import annotations

import asyncio

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from src.app import App
from src.handlers._helpers import edit_or_send, notify_payments_channel
from src.handlers.states import GiftFlow
from src.i18n import t
from src.keyboards import gift_catalog_kb, gift_kb, main_menu_kb
from src.utils import parse_recipient

router = Router(name="gift")


async def _safe_pay_channel(bot, app, order_id: int) -> None:
    try:
        await notify_payments_channel(bot, app, order_id)
    except Exception:  # noqa: BLE001
        pass


async def _lang(app: App, user_id: int) -> str:
    return (await app.users.get(user_id) or {}).get("language", "uz")


@router.callback_query(F.data == "menu:gift")
async def gift_menu(cb: CallbackQuery, app: App) -> None:
    lang = await _lang(app, cb.from_user.id)
    sum_bal = await app.users.balance_sum(cb.from_user.id)
    await edit_or_send(cb,
        t(lang, "gift_menu", balance=f"{sum_bal:,.0f}"),
        reply_markup=gift_kb(lang),
    )


@router.callback_query(F.data == "gift:buy")
async def gift_buy(cb: CallbackQuery, app: App) -> None:
    """Gift katalogi (admin qo'shgan giftlar nomi + narxi bilan)."""
    lang = await _lang(app, cb.from_user.id)
    gifts = await app.gifts.list_active()
    if not gifts:
        await edit_or_send(cb, t(lang, "gift_empty"), reply_markup=gift_kb(lang))
        return
    await edit_or_send(cb,
        t(lang, "gift_choose_catalog"),
        reply_markup=gift_catalog_kb(lang, gifts),
    )


@router.callback_query(F.data == "gift:send")
async def gift_send(cb: CallbackQuery, app: App) -> None:
    """Gift yuborish ham katalogdan tanlanadi."""
    await gift_buy(cb, app)


@router.callback_query(F.data.startswith("giftbuy:"))
async def gift_pack(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Gift tanlandi — narx ko'rsatilib @username/telefon so'raladi."""
    lang = await _lang(app, cb.from_user.id)
    try:
        gift_id = int(cb.data.split(":")[1])
    except ValueError:
        return
    gift = await app.gifts.get(gift_id)
    if not gift or not gift.get("active"):
        await cb.answer("❌ Gift topilmadi")
        return
    await state.update_data(gift_id=gift_id, gift_name=gift["name"],
                            gift_price=float(gift["price"]), gift_stars=float(gift["stars"]))
    await edit_or_send(
        cb,
        t(lang, "gift_need_phone",
          name=gift["name"], price=f"{float(gift['price']):,.0f}",
          stars=f"{float(gift['stars']):,.0f}"),
    )
    await state.set_state(GiftFlow.wait_phone)


@router.message(StateFilter(GiftFlow.wait_phone))
async def gift_phone_received(message: Message, app: App, state: FSMContext) -> None:
    """@username yoki telefon raqam qabul qilinganda gift sotib olinadi."""
    lang = await _lang(app, message.from_user.id)
    recipient = parse_recipient(message.text or "")
    if not recipient:
        await message.answer(t(lang, "invalid_phone"))
        return
    data = await state.get_data()
    gift_id = data.get("gift_id")
    if not gift_id:
        await message.answer("❌ Gift tanlanmagan. /start")
        await state.clear()
        return

    rtype, rvalue = recipient
    result = await app.gifts.purchase_gift(
        message.from_user.id, int(gift_id), rvalue, rtype
    )
    if result.ok:
        asyncio.create_task(_safe_pay_channel(message.bot, app, result.order_id))
        await message.answer(
            t(lang, "gift_sent",
              name=data.get("gift_name", "Gift"),
              amount=int(data.get("gift_stars", 0)),
              balance=int(result.balance or 0)),
            reply_markup=main_menu_kb(lang),
        )
    elif result.error == "insufficient_sum":
        await message.answer(
            t(lang, "insufficient_sum",
              balance=int(await app.users.balance_sum(message.from_user.id)),
              need=f"{int(data.get('gift_price', 0)):,.0f}"),
            reply_markup=main_menu_kb(lang),
        )
    elif result.error == "no_price":
        await message.answer(t(lang, "no_price"), reply_markup=main_menu_kb(lang))
    elif result.error == "no_account":
        await message.answer(
            "⚠️ Akkaunt ulanishi talab qilinadi (gift yetkazish). /start\n"
            "Admin: panel → Akkauntlar → 📲 Login orqali ulash",
            reply_markup=main_menu_kb(lang),
        )
    else:
        await message.answer(
            f"⚠️ Gift yuborilmadi: <code>{result.error}</code>",
            reply_markup=main_menu_kb(lang),
        )
    await state.clear()