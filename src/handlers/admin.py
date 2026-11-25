# ===================================================================
# handlers/admin.py - ADMIN PANELI (Telegram'da, WebAppga muhtoj emas)
#  - Buyurtmalar, foydalanuvchilar, statistika
#  - Sozlamalar: narx, foiz, karta, kanal
#  - Akkauntlar va giftlar, reklama, VIP, bot holati
# ===================================================================

from __future__ import annotations

import asyncio
import dataclasses
import html
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.app import App
from src.handlers._helpers import edit_or_send, user_ref
from src.handlers.states import AdminFlow
from src.i18n import status_label, t
from src.keyboards import (
    admin_accounts_kb,
    admin_gift_kb,
    admin_manage_kb,
    admin_nft_kb,
    admin_menu_kb,
    admin_orders_kb,
    admin_settings_kb,
)
from src.telethon_login import (
    can_request_code,
    clear_pending_login,
    confirm_password,
    get_flood_wait,
    get_pending_login,
    request_code,
    resend_code,
    set_pending_login,
    sign_in,
)


def _fmt_seconds(seconds: int) -> str:
    """Sekundni qulay matnga o'giradi: '1 soat', '22 soat' va h.k."""
    if seconds <= 0:
        return "hozir"
    if seconds < 3600:
        return f"{max(seconds // 60, 1)} daqiqa"
    return f"{seconds // 3600} soat"
from src.nft_parser import NftInfo, NftUrlError, fetch_nft
from src.utils import format_amount, parse_price_input

router = Router(name="admin")


async def _is_admin(app: App, user_id: int) -> bool:
    return await app.is_admin(user_id)


async def _lang(app: App, user_id: int) -> str:
    return (await app.users.get(user_id) or {}).get("language", "uz")


# ---------------------------------------------------------------
# Paneldan kirish va asosiy menyu
# ---------------------------------------------------------------

@router.message(Command("admin"))
async def admin_cmd(message: Message, app: App) -> None:
    if not await _is_admin(app, message.from_user.id):
        await message.answer("⛔️")
        return
    lang = await _lang(app, message.from_user.id)
    active = await app.settings.bot_active()
    await message.answer(t(lang, "admin_panel"), reply_markup=admin_menu_kb(lang, active))


@router.callback_query(F.data == "admin:main")
async def admin_menu(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    active = await app.settings.bot_active()
    await edit_or_send(cb, t(lang, "admin_panel"), reply_markup=admin_menu_kb(lang, active))


@router.callback_query(F.data == "admin:toggle")
async def admin_toggle(cb: CallbackQuery, app: App) -> None:
    """Botni aktiv/nofaol qilish."""
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    now_active = await app.admin.toggle_bot()
    await edit_or_send(cb, 
        t(lang, "admin_toggled", status=t(lang, "admin_bot_active")
          if now_active else t(lang, "admin_bot_inactive")),
        reply_markup=admin_menu_kb(lang, now_active),
    )


# ---------------------------------------------------------------
# Buyurtmalar
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:orders")
async def admin_orders(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    pending = await app.orders.pending()
    if not pending:
        await edit_or_send(cb, 
            t(lang, "admin_orders_none"),
            reply_markup=admin_menu_kb(lang, await app.settings.bot_active()),
        )
        return
    # Har bir buyurtma uchun alohida xabar
    await edit_or_send(cb, t(lang, "admin_orders_pending", orders="") + "⏳")
    for o in pending[:10]:
        buyer = await app.users.get(o["user_id"]) or {}
        txt = (
            f"<b>#{o['id']}</b> · {user_ref(buyer)}\n"
            f"⭐ {o['stars_amount']} · {status_label(lang, o['status'])}\n"
            f"💰 {o['payment_method']} · 📝 {o['note'][:120]}"
        )
        await cb.message.answer(txt, reply_markup=admin_orders_kb(lang, o["id"]))


# ---------------------------------------------------------------
# Foydalanuvchilar
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:users")
async def admin_users(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    total = await app.users.count()
    await edit_or_send(cb, t(lang, "admin_users_count", total=total))
    await state.set_state(AdminFlow.wait_user_id)


@router.message(StateFilter(AdminFlow.wait_user_id))
async def admin_user_info(message: Message, app: App, state: FSMContext) -> None:
    """Foydalanuvchi ID bo'yicha ma'lumot."""
    if not await _is_admin(app, message.from_user.id):
        return
    lang = await _lang(app, message.from_user.id)
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer(t(lang, "admin_invalid_format"))
        return
    user = await app.users.get(uid) or {}
    if not user:
        await message.answer("❌ Foydalanuvchi topilmadi")
        await state.clear()
        return
    totals = await app.users.totals(uid)
    await message.answer(
        f"👤 <b>{user_ref(user)}</b>\n"
        f"ID: <code>{uid}</code>\n"
        f"🌐 Til: {user.get('language')}\n"
        f"⭐ Balans: {format_amount(float(user.get('balance_stars', 0)))}\n"
        f"💵 Hisob: {format_amount(float(user.get('balance_sum', 0)))} so'm\n"
        f"📊 Sotib olingan: {format_amount(float(totals.get('bought', 0)))}\n"
        f"🎁 Giftlar: {format_amount(float(totals.get('gifted', 0)))}",
    )
    await state.clear()


# ---------------------------------------------------------------
# Statistika
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:stats")
async def admin_stats(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    s = await app.admin.stats()
    text = (
        f"📆 <b>Kunlik</b>: {format_amount(float(s['daily']['sold_stars']))} ⭐ | "
        f"{format_amount(float(s['daily']['sold_sum']))} so'm | {s['daily']['count']} ta\n"
        f"🗓 <b>Haftalik</b>: {format_amount(float(s['weekly']['sold_stars']))} ⭐ | "
        f"{format_amount(float(s['weekly']['sold_sum']))} so'm | {s['weekly']['count']} ta\n"
        f"📅 <b>Oylik</b>: {format_amount(float(s['monthly']['sold_stars']))} ⭐ | "
        f"{format_amount(float(s['monthly']['sold_sum']))} so'm | {s['monthly']['count']} ta\n"
        f"👥 Foydalanuvchilar: <b>{s['users']}</b>"
    )
    await edit_or_send(cb, text, reply_markup=admin_menu_kb(lang, await app.settings.bot_active()))


# ---------------------------------------------------------------
# Sozlamalar: narxlar, karta, kanal
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:settings")
async def admin_settings(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    api_url, api_key = await app.settings.get_stars_api()
    api_status = (
        f"✅ <code>{api_url}</code>"
        if api_url else "⛔️ O'rnatilmagan (.env zaxira: "
        f"{app.cfg.stars_api_base_url or '—'}"
        + (f")" if not api_url and app.cfg.stars_api_base_url else ")")
    )
    card = await app.settings.payment_card() or "—"
    channel, ch_id = await app.settings.get_channel()
    pay_ch, pay_id = await app.settings.get_payment_channel()
    prices = await app.settings.get_prices() or app.cfg.default_prices
    star_price = await app.settings.get_star_price()
    gift_price = await app.settings.get_gift_price()
    post_price = await app.settings.get_post_price()
    min_stars = await app.settings.get_min_stars()
    txt = (
        f"⚙️ <b>Sozlamalar</b>\n"
        f"💎 Stars 1 ⭐ narxi: <b>{star_price:,.0f} so'm</b>\n"
        f"🎁 Gift 1 ⭐ narxi: <b>{gift_price:,.0f} so'm</b>\n"
        f"📝 Post 1 ⭐ narxi: <b>{post_price:,.0f} so'm</b>\n"
        f"▫️ Minimal: <b>{min_stars} ⭐</b>\n"
        f"▫️ Narxlar: {', '.join(f'{k}⭐={v}so`m' for k, v in sorted(prices.items()))}\n"
        f"▫️ Karta: <code>{card}</code>\n"
        f"▫️ Kanal: @{channel or '—'}\n"
        f"▫️ To'lovlar kanali: @{pay_ch or '—'}\n"
        f"▫️ Stars API: {api_status}"
    )
    await edit_or_send(cb, txt, reply_markup=admin_settings_kb(lang))


@router.callback_query(F.data == "admin:set_pic")
async def admin_set_pic(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Bosh menyu rasmini (banner) o'rnatish."""
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, "📷 Bosh menyuga chiqadigan yangi <b>banner rasm</b>ni yuboring.")
    await state.set_state(AdminFlow.wait_pic)


@router.message(StateFilter(AdminFlow.wait_pic), F.photo)
async def save_pic(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    bdir = Path(__file__).resolve().parent.parent.parent / "assets" / "images"
    try:
        bdir.mkdir(parents=True, exist_ok=True)
        dest = bdir / "banner.png"
        await message.bot.download(message.photo[-1], destination=dest)
        await message.answer("✅ Yangi banner o'rnatildi! /start da ko'rinadi.")
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"❌ Rasmni saqlashda xatolik: {exc}")
    await state.clear()


@router.callback_query(F.data == "admin:set_prices")
async def admin_set_prices(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    current = await app.settings.get_prices()
    tpl = "Hozirgi: " + ", ".join(f"{k}={v}" for k, v in sorted(current.items()))
    await edit_or_send(cb, 
        t(lang, "admin_send_new_price") + "\n\n" + tpl
    )
    await state.set_state(AdminFlow.wait_prices)


@router.message(StateFilter(AdminFlow.wait_prices))
async def save_prices(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    lang = await _lang(app, message.from_user.id)
    prices = parse_price_input(message.text or "")
    if prices is None:
        await message.answer(t(lang, "admin_invalid_format"))
        return
    await app.admin.set_prices(prices)
    await message.answer(t(lang, "admin_price_updated"))
    await state.clear()


@router.callback_query(F.data == "admin:set_star_price")
async def admin_set_star_price(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """1 star narxini sozlash (so'm). Buy narx = stars * star_price."""
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    current = await app.settings.get_star_price()
    min_stars = await app.settings.get_min_stars()
    await edit_or_send(cb,
        "💎 <b>Stars 1 ⭐ narxini</b> yuboring (so'mda).\n"
        "Masalan: <code>200</code> → 50⭐ = 10 000 so'm, 100⭐ = 20 000 so'm.\n\n"
        f"Hozirgi: {current:,.0f} so'm"
        f" | Minimal: {min_stars} ⭐"
    )
    await state.set_state(AdminFlow.wait_star_price)


@router.callback_query(F.data == "admin:set_gift_price")
async def admin_set_gift_price(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Gift uchun alohida 1 star narxini sozlash (so'm)."""
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    current = await app.settings.get_gift_price()
    await edit_or_send(cb,
        "🎁 <b>Gift 1 ⭐ narxini</b> yuboring (so'mda).\n"
        "Bu narx gift oqimi uchun alohida havolanadi.\n"
        "Agar o'rnatmagan bo'lsangiz, Stars narxi ishlatiladi.\n\n"
        f"Hozirgi: {current:,.0f} so'm"
    )
    await state.set_state(AdminFlow.wait_gift_price)


@router.callback_query(F.data == "admin:set_post_price")
async def admin_set_post_price(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Post uchun alohida 1 star narxini sozlash (so'm)."""
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    current = await app.settings.get_post_price()
    await edit_or_send(cb,
        "📝 <b>Post 1 ⭐ narxini</b> yuboring (so'mda).\n"
        "Bu narx postga stars oqimi uchun alohida havolanadi.\n"
        "Agar o'rnatmagan bo'lsangiz, Stars narxi ishlatiladi.\n\n"
        f"Hozirgi: {current:,.0f} so'm"
    )
    await state.set_state(AdminFlow.wait_post_price)


@router.callback_query(F.data == "admin:set_post_min_stars")
async def admin_set_post_min_stars(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Postga yuboriladigan minimal stars sonini sozlash."""
    if not await _is_admin(app, cb.from_user.id):
        return
    current = await app.settings.get_post_min_stars()
    fallback = await app.settings.get_min_stars()
    extra = "" if current == fallback else f"  (umumiy: {fallback})"
    await edit_or_send(cb,
        "📝 <b>Postga minimal ⭐ sonini</b> yuboring.\n"
        "Buyurtma shu miqdordan kam bo'lishi mumkin emas.\n\n"
        f"Hozirgi: {current} ⭐{extra}"
    )
    await state.set_state(AdminFlow.wait_post_min_stars)


@router.message(StateFilter(AdminFlow.wait_star_price))
async def save_star_price(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    raw = (message.text or "").strip().replace(" ", "").replace("so'm", "").replace("som", "")
    try:
        val = float(raw)
    except ValueError:
        await message.answer("❌ Narx raqam bo'lishi kerak. Masalan: <code>200</code>")
        return
    if val <= 0:
        await message.answer("❌ Narx 0 dan katta bo'lishi kerak.")
        return
    await app.admin.set_star_price(val)
    min_stars = await app.settings.get_min_stars()
    await message.answer(
        f"✅ 1 ⭐ narxi saqlandi: <b>{val:,.0f} so'm</b>\n"
        f"📊 Endi: {min_stars}⭐ = {val * min_stars:,.0f} so'm\n"
        f"100⭐ = {val * 100:,.0f} so'm"
    )
    await state.clear()


async def _save_simple_price(message: Message, app: App, state: FSMContext,
                             *,
                             label: str, setter: str) -> None:
    """Gift/Post narxini saqlash (umumiy kod)."""
    if not await _is_admin(app, message.from_user.id):
        return
    raw = (message.text or "").strip().replace(" ", "").replace("so'm", "").replace("som", "")
    try:
        val = float(raw)
    except ValueError:
        await message.answer("❌ Narx raqam bo'lishi kerak. Masalan: <code>200</code>")
        return
    if val <= 0:
        await message.answer("❌ Narx 0 dan katta bo'lishi kerak.")
        return
    setter_fn = getattr(app.admin, setter)
    await setter_fn(val)
    await message.answer(
        f"✅ <b>{label}</b> 1 ⭐ narxi saqlandi: <b>{val:,.0f} so'm</b>"
    )
    await state.clear()


@router.message(StateFilter(AdminFlow.wait_gift_price))
async def save_gift_price(message: Message, app: App, state: FSMContext) -> None:
    await _save_simple_price(message, app, state, label="🎁 Gift", setter="set_gift_price")


@router.message(StateFilter(AdminFlow.wait_post_price))
async def save_post_price(message: Message, app: App, state: FSMContext) -> None:
    await _save_simple_price(message, app, state, label="📝 Post", setter="set_post_price")


@router.message(StateFilter(AdminFlow.wait_post_min_stars))
async def save_post_min_stars(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    raw = (message.text or "").strip().replace(" ", "").replace("⭐", "").replace("*", "")
    try:
        val = int(float(raw))
    except ValueError:
        await message.answer("❌ Minimal stars soni butun raqam bo'lishi kerak. Masalan: <code>50</code>")
        return
    if val <= 0:
        await message.answer("❌ Minimal 1 dan katta bo'lishi kerak.")
        return
    await app.admin.set_post_min_stars(val)
    await message.answer(f"✅ Postga minimal stars saqlandi: <b>{val} ⭐</b>")
    await state.clear()


@router.callback_query(F.data == "admin:set_card")
async def admin_set_card(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(
        cb,
        "💳 <b>Karta ma'lumotini yuboring</b>\n\n"
        "Format (2 qator yoki | bilan):\n"
        "<code>9860 1234 5678 9012\nIsm Familiya</code>\n"
        "yoki: <code>9860 1234 5678 9012 | Ism Familiya</code>\n\n"
        "Karta egasining ismi mini-app va botdagi to'lov oynasida ko'rinadi.")
    await state.set_state(AdminFlow.wait_card)


@router.message(StateFilter(AdminFlow.wait_card))
async def save_card(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    raw = (message.text or "").strip()
    parts = [x.strip() for x in raw.replace("|", "\n").splitlines() if x.strip()]
    if not parts:
        await message.answer("⚠️ Karta raqamini yuboring.")
        return
    card = parts[0][:32]
    holder = " ".join(parts[1:])[:60]
    await app.admin.set_card(card)
    await app.settings.set_payment_card_holder(holder)
    await message.answer(
        f"✅ Karta saqlandi\n💳 <code>{card}</code>\n👤 {holder or '—'}")
    await state.clear()


@router.message(Command("bankadd"))
async def cmd_bankadd(message: Message, app: App) -> None:
    """Admin: bank kirim xabarini qo'lda kiritadi (SMS/CardXabar matnini nusxalab).

    Foydalanish: /bankadd <bank xabari matni>   yoki xabarga javob sifatida /bankadd
    """
    if not await _is_admin(app, message.from_user.id):
        return
    text = (message.text or "").partition(" ")[2].strip()
    if not text and message.reply_to_message:
        text = message.reply_to_message.text or message.reply_to_message.caption or ""
    if not text:
        await message.answer(
            "ℹ️ Foydalanish:\n<code>/bankadd ➕ 50 000.00 UZS ... Ref: 4821937465</code>\n"
            "yoki bank xabariga javob sifatida /bankadd yozing.")
        return
    res = await app.bank.ingest(text, "admin")
    if not res.get("ok"):
        await message.answer("⚠️ Xabardan summa ajratib bo'lmadi (UZS / so'm bilan yozilgan bo'lishi kerak).")
    elif not res.get("stored"):
        await message.answer("ℹ️ Saqlanmadi (chiqim yoki avval kiritilgan xabar).")
    else:
        await message.answer(f"✅ Kirim saqlandi: <b>{res['amount']:,.0f}</b> so'm. "
                             "Kutayotgan to'lovlar qayta tekshirildi.")


@router.callback_query(F.data == "admin:set_channel")
async def admin_set_channel(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, "📢 Kanal username yoki linkini yuboring:\nMasalan: @my_channel")
    await state.set_state(AdminFlow.wait_channel)


@router.message(StateFilter(AdminFlow.wait_channel))
async def save_channel(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    text = message.text.strip()
    # Username yoki linkdan nomni ajratib olamiz
    username = text.rstrip("/").split("/")[-1].lstrip("@")
    # chat_id ni aniqlashga harakat qilamiz
    chat_id = ""
    try:
        chat = await message.bot.get_chat(f"@{username}")
        chat_id = str(chat.id)
    except Exception:  # noqa: BLE001
        pass
    await app.admin.set_channel(username, chat_id)
    await message.answer(
        f"✅ Kanal sozlandi: @{username}"
        + (f"\nID: {chat_id}" if chat_id else "\n⚠️ Botni kanalga admin qiling!")
    )
    await state.clear()


@router.callback_query(F.data == "admin:set_pay_channel")
async def admin_set_pay_channel(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Buyurtmalar kanali sozlash (barcha buyurtmalar shu yerga yoziladi)."""
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb,
        "🛒 To'lovlar kanali username yoki linkini yuboring:\n"
        "Masalan: @payments_channel\n\n"
        "⚠️ Bot bu kanalga admin bo'lishi shart!"
    )
    await state.set_state(AdminFlow.wait_pay_channel)


@router.message(StateFilter(AdminFlow.wait_pay_channel))
async def save_pay_channel(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    text = message.text.strip()
    username = text.rstrip("/").split("/")[-1].lstrip("@")
    if not username:
        await message.answer("❌ Noto'g'ri username")
        return
    chat_id = ""
    try:
        chat = await message.bot.get_chat(f"@{username}")
        chat_id = str(chat.id)
    except Exception:  # noqa: BLE001
        pass
    await app.settings.set_payment_channel(username, chat_id)
    await message.answer(
        f"✅ To'lovlar kanali sozlandi: @{username}\n"
        f"Endi barcha yangi buyurtmalar shu kanalga yuboriladi."
        + (f"\nID: {chat_id}" if chat_id else "\n⚠️ Botni kanalga admin qiling!")
    )
    await state.clear()


@router.callback_query(F.data == "admin:clear_pay_channel")
async def admin_clear_pay_channel(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await app.settings.clear_payment_channel()
    await edit_or_send(cb, "🗑 To'lovlar kanali o'chirildi.")


# ---------------------------------------------------------------
# Stars API (url va api key)
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:set_api")
async def admin_set_api(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb,
        "🤖 <b>Stars API URL</b> nii yuboring:\n"
        "Masalan: <code>https://api.apilarimbot.uz</code>\n"
        "Bekor qilish: /admin"
    )
    await state.set_state(AdminFlow.wait_api_url)


@router.message(StateFilter(AdminFlow.wait_api_url))
async def save_api_url(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    url = (message.text or "").strip().rstrip("/")
    if not url.startswith("http://") and not url.startswith("https://"):
        await message.answer("❌ URL http(s):// bilan boshlanishi kerak")
        return
    await state.update_data(api_url=url)
    await message.answer("🔑 Endi <b>API kalitini</b> yuboring:")
    await state.set_state(AdminFlow.wait_api_key)


@router.message(StateFilter(AdminFlow.wait_api_key))
async def save_api_key(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    data = await state.get_data()
    key = (message.text or "").strip()
    if not key:
        await message.answer("❌ Kalit bo'sh bo'lishi mumkin emas")
        return
    await app.settings.set_stars_api(data.get("api_url", ""), key)
    await message.answer("✅ Stars API o'rnatildi.\n"
                         "Endi @Apilarimbot to'lovlari ushbu API orqali ishlaydi.")
    await state.clear()


@router.callback_query(F.data == "admin:clear_api")
async def admin_clear_api(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await app.settings.clear_stars_api()
    await edit_or_send(cb, "🗑 Stars API o'chirildi (endilikda .env zaxirasidan foydalaniladi).")


# ---------------------------------------------------------------
# Gift boshqaruv
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:gifts")
async def admin_gifts(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb, t(lang, "admin_gifts"), reply_markup=admin_gift_kb(lang))


@router.callback_query(F.data == "admin:gift_add")
async def admin_gift_add(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, "🎁 <b>Gift nomini</b> yuboring:\n"
                           "Masalan: <code>Premium</code>")
    await state.set_state(AdminFlow.wait_gift_name)


@router.message(StateFilter(AdminFlow.wait_gift_name))
async def gift_name(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ Nom bo'sh bo'lishi mumkin emas.")
        return
    await state.update_data(gift_name=name[:200])
    await message.answer(f"💲 <b>{name}</b> narxini (so'mda) yuboring:\n"
                         "Masalan: <code>12000</code>")
    await state.set_state(AdminFlow.wait_gift_narxi)


@router.message(StateFilter(AdminFlow.wait_gift_narxi))
async def gift_narxi(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    raw = (message.text or "").strip().replace(" ", "").replace("so'm", "").replace("som", "")
    try:
        price = float(raw)
    except ValueError:
        await message.answer("❌ Narx raqam bo'lishi kerak. Masalan: <code>12000</code>")
        return
    if price <= 0:
        await message.answer("❌ Narx 0 dan katta bo'lishi kerak.")
        return
    await state.update_data(gift_price=price)
    await message.answer("⭐ <b>Soni (nechta stars)</b> yuboring:\n"
                         "Masalan: <code>100</code>")
    await state.set_state(AdminFlow.wait_gift_soni)


@router.message(StateFilter(AdminFlow.wait_gift_soni))
async def gift_soni(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    raw = (message.text or "").strip()
    try:
        stars = float(raw.replace(",", "."))
    except ValueError:
        await message.answer("❌ Soni raqam bo'lishi kerak. Masalan: <code>100</code>")
        return
    if stars <= 0:
        await message.answer("❌ Soni 0 dan katta bo'lishi kerak.")
        return
    data = await state.get_data()
    gift_id = await app.gifts.add(data.get("gift_name", "Gift"), data["gift_price"], stars)
    await message.answer(
        f"✅ <b>Gift qo'shildi!</b>\n"
        f"#️⃣ ID: <b>#{gift_id}</b>\n"
        f"🎁 Nomi: <b>{data.get('gift_name', '')}</b>\n"
        f"💰 Narxi: <b>{data['gift_price']:,.0f} so'm</b>\n"
        f"⭐ Soni: <b>{stars:,.0f} Stars</b>"
    )
    await state.clear()


@router.callback_query(F.data == "admin:gift_list")
async def admin_gift_list(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    gifts = await app.gifts.list_all()
    if not gifts:
        await edit_or_send(cb, "📄 Giftlar yo'q.", reply_markup=admin_gift_kb("uz"))
        return
    lines = []
    for g in gifts:
        active = "🟢" if g["active"] else "🔴"
        lines.append(
            f"{active} <b>#{g['id']}</b> {g['name']} — "
            f"{float(g['price']):,.0f} so'm / {float(g['stars']):,.0f}⭐"
        )
    await edit_or_send(cb, "📄 <b>Giftlar</b>\n\n" + "\n".join(lines),
                       reply_markup=admin_gift_kb("uz"))


@router.callback_query(F.data == "admin:gift_del")
async def admin_gift_del(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, "🗑 O'chiriladigan <b>gift ID sini</b> yuboring:\n"
                           "Masalan: <code>2</code>")
    await state.set_state(AdminFlow.wait_gift_delete)


@router.message(StateFilter(AdminFlow.wait_gift_delete))
async def gift_delete_id(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    try:
        gift_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Noto'g'ri ID")
        return
    gift = await app.gifts.get(gift_id)
    if not gift:
        await message.answer("❌ Gift topilmadi.")
        return
    await app.gifts.remove(gift_id)
    await message.answer(f"✅ <b>{gift['name']}</b> (#{gift_id}) o'chirildi.")
    await state.clear()


@router.callback_query(F.data == "admin:gift_sub")
async def admin_gift_sub(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await state.update_data(gift_add=False)
    await edit_or_send(cb, "➖ Foydalanuvchi ID sini yuboring (balansdan stars ayirish):")
    await state.set_state(AdminFlow.wait_gift_user)


@router.message(StateFilter(AdminFlow.wait_gift_user))
async def gift_user_id(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Noto'g'ri ID")
        return
    await state.update_data(gift_user_id=uid)
    await message.answer("💲 Miqdorni (stars) yuboring:")
    await state.set_state(AdminFlow.wait_gift_amount)


@router.message(StateFilter(AdminFlow.wait_gift_amount))
async def gift_amount(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("❌ Son kiriting")
        return
    data = await state.get_data()
    result = await app.gifts.apply_admin_gift(data["gift_user_id"], amount, data.get("gift_add", True))
    if result is None:
        await message.answer("❌ Yetarli balans yo'q")
    else:
        await message.answer(f"✅ Yangi balans: {format_amount(result)} ⭐")
    await state.clear()


# ---------------------------------------------------------------
# Akkauntlar
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:accounts")
async def admin_accounts(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb, t(lang, "admin_accounts"), reply_markup=admin_accounts_kb(lang))


@router.callback_query(F.data == "admin:acct_list")
async def admin_acct_list(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    rows = await app.accounts.list_all()
    if not rows:
        await edit_or_send(cb, "📄 Akkauntlar yo'q.")
        return
    text = "\n".join(
        f"<b>#{r['id']}</b> {r['title']} · {'✅' if r['status'] == 'active' else '⛔️'}"
        f"{' · 🔒 session' if r.get('session_data') else ' · ⚠️ sessionsiz'}"
        for r in rows
    )
    await edit_or_send(cb, text)


@router.callback_query(F.data == "admin:acct_add")
async def admin_acct_add(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, 
        "➕ Akkaunt session string (Telethon) yuboring.\n"
        "Masalan: <code>1BQANOTEuMTAu... (StringSession)</code>\n"
        "Bu qiymat Fernet bilan shifrlanib saqlanadi."
    )
    await state.set_state(AdminFlow.wait_acct_session)


@router.message(StateFilter(AdminFlow.wait_acct_session))
async def acct_session(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    await state.update_data(session=message.text or "")
    await message.answer("🔖 Akkaunt nomini yozing:")
    await state.set_state(AdminFlow.wait_acct_title)


@router.message(StateFilter(AdminFlow.wait_acct_title))
async def acct_title(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    data = await state.get_data()
    session = data.get("session", "")
    if not session:
        await message.answer("❌ Session string kiritilmagan.")
        return
    await message.answer("⏳ Session tekshirilmoqda...")
    ok, msg = await app.accounts._sender.test_session(session)
    if not ok:
        await message.answer(
            f"❌ Session yaroqsiz: <code>{msg}</code>\n"
            "To'g'ri StringSession olish uchun <b>📲 Login orqali ulash</b>ni ishlating."
        )
        await state.clear()
        return
    await app.accounts.add(message.text[:100], session)
    await message.answer(f"✅ Akkaunt ulandi ({msg})")
    await state.clear()


# ---------------------------------------------------------------
# Login orqali akkaunt ulash (telefon raqam + kod, session 'ssiz)
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:acct_login")
async def acct_login_start(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb,
        "📲 <b>Login orqali ulash</b>\n\n"
        "Telegram kodini o'chirilgan yoki ishlayotgan telefonga yuboramiz. "
        "Bosqichlar:\n"
        "1️⃣ Telefon raqamingizni kiriting (masalan <code>+998901234567</code>)\n"
        "2️⃣ Telegramga kelgan tasdiqlash kodini yuborasiz\n"
        "3️⃣ (agar yoqilgan bo'lsa) 2FA parolni yuborasiz\n"
        "4️⃣ Akkaunt avtomatik ulanadi\n\n"
        "⚠️ Botdan (userbot) foydalanish Telegram qoidalariga zid bo'lishi mumkin.\n"
        "🎨 Boshqa hisobga kirishda avval chiqib ketish EHTIYOT bo'ladi."
    )
    await state.set_state(AdminFlow.wait_acct_phone)


@router.message(StateFilter(AdminFlow.wait_acct_phone))
async def acct_login_phone(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    phone = (message.text or "").strip()
    if not phone.replace("+", "").isdigit() or len(phone.replace("+", "")) < 7:
        await message.answer("❌ Telefon raqam noto'g'ri. Masalan: <code>+998901234567</code>")
        return
    # Raqam Telegram tomonidan bloklangan bo'lsa — oldindan ogohlantiramiz.
    flood = get_flood_wait(phone)
    if flood > 0:
        await message.answer(
            f"⛔ Bu raqam Telegram tomonidan <b>{_fmt_seconds(flood)}</b> bloklangan "
            "(juda ko'p kod so'rovi). Blok tugagach qaytadan urining.\n"
            "Boshqa raqam ulash mumkin."
        )
        return
    # Agar shu raqam uchun hali amalda kod (pending login) bo'lsa —
    # YANGI kod yuborilmaydi (u oldingisini bekor qiladi), o'sha kod
    # kutib turadi. "Bittada kirish" uchun shu zarur.
    pending = get_pending_login(phone)
    if pending:
        sess_p, hash_p = pending
        await state.update_data(
            acct_temp_session=sess_p,
            acct_phone=phone,
            acct_phone_hash=hash_p,
        )
        await message.answer(
            "✅ Shu raqam uchun <b>kod hali amalda</b> — yangisi yuborilmadi.\n"
            "Telegram'dagi <b>eng oxirgi</b> kodni yozib yuboring.\n\n"
            "Bekor qilish: /admin"
        )
        await state.set_state(AdminFlow.wait_acct_code)
        return
    await message.answer("⏳ Kod yuborilmoqda...")
    state_data = await state.get_data()
    temp_session = state_data.get("acct_temp_session", "")
    # Birinchi marta yangi session, aks holda oldingi temp session davom etadi
    ok, msg, temp_session2, phone_hash = await request_code(phone)
    if not ok:
        flood = get_flood_wait(phone)
        if flood > 0 or "FLOOD_WAIT" in msg:
            await message.answer(
                f"⛔ Telegram bu raqamni bloklagan ({_fmt_seconds(flood)}). "
                "Blok tugagach qaytadan urining.\nBoshqa raqam ulash mumkin."
            )
            return
        await message.answer(f"❌ Kod yuborilmadi: {_login_error_uz(msg)}")
        return
    temp_session = temp_session2 or temp_session
    if phone_hash:
        set_pending_login(phone, temp_session, phone_hash)
    await state.update_data(
        acct_temp_session=temp_session,
        acct_phone=phone,
        acct_phone_hash=phone_hash,
    )
    await message.answer(
        "✅ Kod yuborildi! Telegram akkauntning o'ziga (Telegram ilovasi) kelgan "
        "<b>5 xonali kodni</b> yuboring.\n\n"
        "Bekor qilish: /admin"
    )
    await state.set_state(AdminFlow.wait_acct_code)


@router.message(StateFilter(AdminFlow.wait_acct_code))
async def acct_login_code(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    data = await state.get_data()
    phone = data.get("acct_phone", "")
    temp_session = data.get("acct_temp_session", "")
    phone_hash = data.get("acct_phone_hash", "")
    # Telegram kodni "12 345" yoki "123-45" ko'rinishida yuborishi mumkin —
    # faqat raqamlarni olib qolamiz.
    code = "".join(ch for ch in (message.text or "") if ch.isdigit())
    if not (4 <= len(code) <= 6):
        await message.answer("❌ Kod raqamdan iborat (5-6 xonali) bo'lishi kerak.")
        return
    ok, msg, final_session, need_password = await sign_in(
        temp_session, phone, code, phone_hash
    )
    if need_password:
        await state.update_data(acct_temp_session=final_session)
        await message.answer(
            "🔒 Bu akkauntda <b>ikkita bosqichli tekshiruv (2FA)</b> yoqilgan.\n"
            "Telegram parolini yuboring:"
        )
        await state.set_state(AdminFlow.wait_acct_password)
        return
    if not ok:
        if "expired" in (msg or "").lower():
            # Kod eskirgan — pending'ni tozalaymiz (u allaqachon yaroqsiz),
            # keyin cooldown tugashini kutib, YANGI kod so'raymiz.
            clear_pending_login(phone)
            can_wait, wait_s = can_request_code(phone)
            if not can_wait and wait_s > 0:
                await message.answer(
                    f"⏳ Kod eskirgan edi. {int(wait_s) + 3} soniyadan so'ng "
                    "yangi kod so'raladi — iltimos kuting..."
                )
                await asyncio.sleep(wait_s + 3)
            ok2, msg2, sess2, hash2 = await request_code(phone)
            if ok2:
                if hash2:
                    set_pending_login(phone, sess2, hash2)
                await state.update_data(
                    acct_temp_session=sess2,
                    acct_phone=phone,
                    acct_phone_hash=hash2,
                )
                await message.answer(
                    "⏳ Oldingi kod eskirgan edi.\n"
                    "Telegram'ga <b>YANGI kod</b> yuborildi — "
                    "aynan <b>eng oxirgi</b> kodni tezda yozib yuboring:"
                )
                return
            await state.clear()
            await message.answer(
                "❌ Kod eskirgan va yangi kod ham yuborilmadi: "
                f"{_login_error_uz(msg2)}\n\n"
                "Boshlash uchun /admin → Akkauntlar → 📲 Login orqali ulash."
            )
            return
        msg_uz = _login_error_uz(msg)
        await message.answer(f"❌ Kirish amalga oshmadi: {msg_uz}")
        return
    clear_pending_login(phone)
    await _save_logged_in_account(message, app, final_session, phone)
    await state.clear()


@router.message(StateFilter(AdminFlow.wait_acct_password))
async def acct_login_password(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    data = await state.get_data()
    phone = data.get("acct_phone", "")
    temp_session = data.get("acct_temp_session", "")
    password = (message.text or "").strip()
    if not password:
        await message.answer("❌ Parol bo'sh bo'lishi mumkin emas.")
        return
    ok, msg, final_session = await confirm_password(temp_session, password)
    if not ok:
        await message.answer(f"❌ Parol noto'g'ri: {msg}")
        return
    await _save_logged_in_account(message, app, final_session, phone)
    await state.clear()


def _login_error_uz(msg: str) -> str:
    """Telethon sign_in xatosini foydalanuvchi tushunadigan tilga o'giradi."""
    low = (msg or "").lower()
    if low.startswith("cooldown:"):
        try:
            s = int(msg.split(":")[1])
        except (ValueError, IndexError):
            s = 30
        return f"Juda tez so'radi — {s} soniya kutib, qaytadan urinib ko'ring."
    if low.startswith("flood_wait:"):
        try:
            s = int(msg.split(":")[1])
        except (ValueError, IndexError):
            s = 25
        return (
            f"Telegram urinishlarni chekladi (FloodWait {s}s). "
            f"{s} soniya kuting va qaytadan urining."
        )
    if "invalid code" in low or "code_invalid" in low:
        return "Kod noto'g'ri. Telegram'dan yangi kodni yozib yuboring."
    if "expired" in low or "code_expired" in low:
        return "Kod eskirgan. Boshlash uchun /admin va qaytadan 'Login orqali ulash'."
    if "flood" in low:
        return "Urinishlar ko'p bo'ldi — bir necha daqiqa kutib qaytadan urinib ko'ring."
    if "too_many" in low or "phone_number_unoccupied" in low:
        return "Bu raqam Telegram'da mavjud emas yoki urinish cheklangan."
    if "password" in low:
        return "2FA parol kerak — parolni yuboring."
    if "session" in low:
        return "Session buzilgan. Qaytadan 'Login orqali ulash'ni boshlang."
    return f"<code>{msg[:140]}</code>"


async def _save_logged_in_account(message: Message, app: App, session: str, phone: str) -> None:
    """Kirish muvaffaqiyatli bo'lgach akkauntni saqlaydi va test qiladi."""
    if not session:
        await message.answer("❌ Session bo'sh — qaytadan urinib ko'ring.")
        return
    await message.answer("⏳ Akkaunt tekshirilmoqda...")
    ok, msg = await app.accounts._sender.test_session(session)
    if not ok:
        await message.answer(f"❌ Session tekshiruvidan o'tmadi: <code>{msg}</code>")
        return
    await app.accounts.add(phone, session)
    text = f"✅ <b>Akkaunt ulandi!</b> ({phone})\n🔌 Test: ✅ {msg}"
    await message.answer(text)


@router.callback_query(F.data == "admin:acct_del")
async def admin_acct_del(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, "❌ O'chiriladigan akkaunt ID sini yuboring:")
    await state.set_state(AdminFlow.wait_acct_delete)


@router.callback_query(F.data == "admin:acct_test")
async def admin_acct_test(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, "🔌 Test qilinadigan akkaunt ID sini yuboring:")
    await state.set_state(AdminFlow.wait_acct_test)


@router.message(StateFilter(AdminFlow.wait_acct_test))
async def acct_test_run(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    try:
        aid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Noto'g'ri ID")
        return
    await message.answer("⏳ Tekshirilmoqda...")
    ok, msg = await app.accounts.test_connection(aid)
    await message.answer(
        f"{'✅' if ok else '❌'} Akkaunt #{aid}: <code>{msg}</code>"
    )
    await state.clear()


@router.message(StateFilter(AdminFlow.wait_acct_delete))
async def acct_delete(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    try:
        await app.accounts.remove(int(message.text.strip()))
        await message.answer("✅ Akkaunt o'chirildi")
    except (ValueError, Exception):  # noqa: BLE001
        await message.answer("❌ ID topilmadi")
    await state.clear()


# ---------------------------------------------------------------
# Reklama (broadcast)
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, 
        "📣 Reklama xabarini yuboring. Barcha foydalanuvchilarga jo'natiladi."
    )
    await state.set_state(AdminFlow.wait_broadcast)


@router.message(StateFilter(AdminFlow.wait_broadcast), F.text)
async def broadcast_send(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    users = await app.db.fetch_all("SELECT id FROM users")
    sent = 0
    for u in users:
        try:
            await message.bot.send_message(u["id"], message.text, disable_web_page_preview=True)
            sent += 1
        except Exception:  # noqa: BLE001
            continue
    await message.answer(f"✅ Reklama yuborildi: {sent}/{len(users)}")
    await state.clear()


# ---------------------------------------------------------------
# FAQ (admin javob sahifasi)
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:faq")
async def admin_faq(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb, t(lang, "faq", admin="admin"))


# ---------------------------------------------------------------
# Adminlarni boshqarish (qo'shish / ro'yxat / o'chirish)
# ---------------------------------------------------------------

@router.callback_query(F.data == "admin:admins")
async def admin_admins_menu(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb,
        "👥 <b>Admin boshqarish</b>\n\n"
        "Bu yerdan yangi admin qo'shish yoki o'chirish mumkin.",
        reply_markup=admin_manage_kb(lang),
    )


@router.callback_query(F.data == "admin:admin_list")
async def admin_admin_list(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    ids = list(app.cfg.admin_ids)
    if app.cfg.super_admin_id and app.cfg.super_admin_id not in ids:
        ids.append(app.cfg.super_admin_id)
    extra = await app.settings.get_extra_admins()
    lines = []
    for uid in ids:
        lines.append(f"🔹 <b>{uid}</b> (asosiy)")
    for uid in extra:
        if uid not in ids:
            lines.append(f"➕ <b>{uid}</b> (DB)")
    text = "📄 <b>Adminlar ro'yxati</b>\n\n" + "\n".join(lines) if lines else "🙅 Adminlar yo'q"
    await edit_or_send(cb, text, reply_markup=admin_manage_kb(lang))


@router.callback_query(F.data == "admin:admin_add")
async def admin_admin_add(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    await state.update_data(admin_action="add")
    await edit_or_send(cb,
        "➕ Yangi admin bo'ladigan foydalanuvchi <b>ID</b>sini yuboring.\n"
        "Misol: <code>123456789</code>\n\n"
        "ID bilmayapsizmi? Foydalanuvchi botga /start bosib, siz admin:users orqali ko'rasiz.",
        reply_markup=admin_manage_kb(lang),
    )
    await state.set_state(AdminFlow.wait_admin_user)


@router.callback_query(F.data == "admin:admin_del")
async def admin_admin_del(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    lang = await _lang(app, cb.from_user.id)
    await state.update_data(admin_action="del")
    await edit_or_send(cb,
        "➖ O'chiriladigan adminning <b>ID</b>sini yuboring.\n"
        "Misol: <code>123456789</code>\n\n"
        "Asosiy (.env) adminlarini shu yerdan o'chirib bo'lmaydi — ularni faqat "
        "super admin (github .env) orqali boshqaradi.",
        reply_markup=admin_manage_kb(lang),
    )
    await state.set_state(AdminFlow.wait_admin_user)


@router.message(StateFilter(AdminFlow.wait_admin_user))
async def admin_admin_apply(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    lang = await _lang(app, message.from_user.id)
    data = await state.get_data()
    action = data.get("admin_action", "add")
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer(t(lang, "admin_invalid_format"))
        return
    if action == "add":
        ok = await app.settings.add_extra_admin(uid)
        if ok:
            await message.answer(f"✅ <b>{uid}</b> endi admin! Endi unga barcha buyurtma va "
                                 f"to'lov xabarlari ham boradi.")
        else:
            await message.answer(f"ℹ️ <b>{uid}</b> allaqachon admin ro'yxatida.")
    else:
        if uid in app.cfg.admin_ids or uid == app.cfg.super_admin_id:
            await message.answer("⛔️ Asosiy/super adminni bu yerdan o'chirib bo'lmaydi.")
        else:
            ok = await app.settings.remove_extra_admin(uid)
            await message.answer(f"✅ <b>{uid}</b> adminlikdan o'chirildi." if ok
                                 else f"ℹ️ <b>{uid}</b> DB adminlarida topilmadi.")
    await state.clear()


# ---------------------------------------------------------------
# NFT boshqaruv: URL yuboriladi -> rasm/model/backdrop/symbol avtomatik,
# keyin admin narxni (so'm) kiritadi. Mini-app'dagi "NFT olish" shu ro'yxatni ko'rsatadi.
# ---------------------------------------------------------------

def _nft_card(nft: NftInfo | dict, price: float | None = None) -> str:
    """NFT haqida chiroyli matn (admin ko'rishi uchun)."""
    g = (lambda k: nft[k]) if isinstance(nft, dict) else (lambda k: getattr(nft, k))
    lines = [f"🖼 <b>{html.escape(str(g('name')))} #{g('number')}</b>"]
    for icon, label, key in (("🎭", "Model", "model"), ("🎨", "Backdrop", "backdrop"),
                             ("🔣", "Symbol", "symbol")):
        val = g(key)
        lines.append(f"{icon} {label}: <b>{html.escape(val) if val else '—'}</b>")
    price = price if price is not None else (float(nft["price"]) if isinstance(nft, dict) else None)
    if price is not None:
        lines.append(f"💰 Narxi: <b>{price:,.0f} so'm</b>")
    lines.append(f"🔗 {html.escape(str(g('url')))}")
    return "\n".join(lines)


async def _send_nft_preview(message: Message, image: str, text: str) -> None:
    """Rasm bilan yuboradi; rasm ochilmasa oddiy matn."""
    if image:
        try:
            await message.answer_photo(image, caption=text)
            return
        except Exception:  # noqa: BLE001
            pass
    await message.answer(text, disable_web_page_preview=True)


@router.callback_query(F.data == "admin:nfts")
async def admin_nfts(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await state.clear()
    lang = await _lang(app, cb.from_user.id)
    n = len([x for x in await app.nft.list_all() if x["status"] == "active"])
    await edit_or_send(cb, f"{t(lang, 'admin_nft')}\n\nSotuvda: <b>{n}</b> ta",
                       reply_markup=admin_nft_kb(lang))


@router.callback_query(F.data == "admin:nft_add")
async def admin_nft_add(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, "🖼 <b>NFT havolasini</b> yuboring:\n"
                           "Masalan: <code>https://t.me/nft/PlushPepe-1234</code>\n\n"
                           "Rasm, Model, Backdrop va Symbol avtomatik aniqlanadi.")
    await state.set_state(AdminFlow.wait_nft_url)


@router.message(StateFilter(AdminFlow.wait_nft_url))
async def nft_url_received(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    try:
        info = await fetch_nft(message.text or "")
    except NftUrlError:
        await message.answer("❌ Havola noto'g'ri. Format: <code>https://t.me/nft/PlushPepe-1234</code>")
        return
    dup = await app.nft.find_by_slug(info.slug)
    if dup:
        await message.answer(f"⚠️ Bu NFT allaqachon qo'shilgan (ID: <b>#{dup['id']}</b>).")
        return
    await state.update_data(nft=dataclasses.asdict(info))
    note = ""
    if not info.found_page:
        note = ("\n\n⚠️ Telegram sahifasi o'qilmadi — rasm standart manzildan olindi, "
                "Model/Backdrop/Symbol bo'sh qoldi. Baribir davom ettirsangiz bo'ladi.")
    await _send_nft_preview(message, info.image, _nft_card(info))
    await message.answer("💲 Endi <b>narxini (so'mda)</b> yuboring:\n"
                         "Masalan: <code>150000</code>" + note)
    await state.set_state(AdminFlow.wait_nft_price)


@router.message(StateFilter(AdminFlow.wait_nft_price))
async def nft_price_received(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    try:
        price = parse_nft_price(message.text or "")
    except ValueError:
        await message.answer("❌ Narx raqam bo'lishi kerak va 0 dan katta. Masalan: <code>150000</code>")
        return
    data = await state.get_data()
    raw = data.get("nft")
    if not raw:
        await state.clear()
        await message.answer("❌ Ma'lumot yo'qoldi, qaytadan boshlang.", reply_markup=admin_nft_kb("uz"))
        return
    info = NftInfo(**raw)
    if await app.nft.find_by_slug(info.slug):
        await state.clear()
        await message.answer("⚠️ Bu NFT allaqachon qo'shilgan.", reply_markup=admin_nft_kb("uz"))
        return
    nft_id = await app.nft.add(info, price)
    await state.clear()
    await message.answer(f"✅ <b>NFT qo'shildi!</b> (ID: <b>#{nft_id}</b>)\n\n" + _nft_card(info, price),
                         reply_markup=admin_nft_kb("uz"), disable_web_page_preview=True)


def parse_nft_price(raw: str) -> float:
    """'150 000', '150000 so'm', '150,000' -> 150000.0 (0 yoki manfiy bo'lsa ValueError)."""
    cleaned = (raw or "").lower().replace("so'm", "").replace("som", "").replace("сум", "")
    cleaned = cleaned.replace(" ", "").replace("\u00a0", "").replace(",", "")
    price = float(cleaned)
    if price <= 0 or price != price or price > 10**10:
        raise ValueError("bad price")
    return price


_NFT_STATUS = {"active": "🟢", "reserved": "🟡", "sold": "✅"}


@router.callback_query(F.data == "admin:nft_list")
async def admin_nft_list(cb: CallbackQuery, app: App) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    items = await app.nft.list_all()
    if not items:
        await edit_or_send(cb, "📄 NFT'lar yo'q.", reply_markup=admin_nft_kb("uz"))
        return
    lines = [
        f"{_NFT_STATUS.get(n['status'], '•')} <b>#{n['id']}</b> {html.escape(n['name'])} "
        f"#{n['number']} — {float(n['price']):,.0f} so'm"
        for n in items[:40]
    ]
    legend = "\n\n🟢 sotuvda · 🟡 buyurtmada · ✅ sotilgan"
    await edit_or_send(cb, "📄 <b>NFT'lar</b>\n\n" + "\n".join(lines) + legend,
                       reply_markup=admin_nft_kb("uz"))


@router.callback_query(F.data == "admin:nft_del")
async def admin_nft_del(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, "🗑 O'chiriladigan <b>NFT ID sini</b> yuboring:\nMasalan: <code>2</code>")
    await state.set_state(AdminFlow.wait_nft_delete)


@router.message(StateFilter(AdminFlow.wait_nft_delete))
async def nft_delete_id(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    try:
        nft_id = int((message.text or "").strip().lstrip("#"))
    except ValueError:
        await message.answer("❌ Noto'g'ri ID")
        return
    nft = await app.nft.get(nft_id)
    if not nft or nft["status"] == "deleted":
        await message.answer("❌ NFT topilmadi.")
        return
    if not await app.nft.remove(nft_id):
        await message.answer("⚠️ Bu NFT buyurtmada yoki sotilgan — o'chirib bo'lmaydi.")
        await state.clear()
        return
    await message.answer(f"✅ <b>{html.escape(nft['name'])} #{nft['number']}</b> (#{nft_id}) o'chirildi.",
                         reply_markup=admin_nft_kb("uz"))
    await state.clear()


@router.callback_query(F.data == "admin:nft_price")
async def admin_nft_price(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, cb.from_user.id):
        return
    await edit_or_send(cb, "💲 Narxi o'zgartiriladigan <b>NFT ID sini</b> yuboring:")
    await state.set_state(AdminFlow.wait_nft_edit_id)


@router.message(StateFilter(AdminFlow.wait_nft_edit_id))
async def nft_edit_id(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    try:
        nft_id = int((message.text or "").strip().lstrip("#"))
    except ValueError:
        await message.answer("❌ Noto'g'ri ID")
        return
    nft = await app.nft.get(nft_id)
    if not nft or nft["status"] == "deleted":
        await message.answer("❌ NFT topilmadi.")
        return
    await state.update_data(nft_edit_id=nft_id)
    await message.answer(f"{_nft_card(nft)}\n\n💲 Yangi narxni (so'mda) yuboring:",
                         disable_web_page_preview=True)
    await state.set_state(AdminFlow.wait_nft_edit_price)


@router.message(StateFilter(AdminFlow.wait_nft_edit_price))
async def nft_edit_price(message: Message, app: App, state: FSMContext) -> None:
    if not await _is_admin(app, message.from_user.id):
        return
    try:
        price = parse_nft_price(message.text or "")
    except ValueError:
        await message.answer("❌ Narx raqam bo'lishi kerak va 0 dan katta.")
        return
    nft_id = (await state.get_data()).get("nft_edit_id")
    await state.clear()
    if nft_id and await app.nft.set_price(int(nft_id), price):
        await message.answer(f"✅ Narx yangilandi: <b>{price:,.0f} so'm</b>",
                             reply_markup=admin_nft_kb("uz"))
    else:
        await message.answer("❌ NFT topilmadi.", reply_markup=admin_nft_kb("uz"))
