# ===================================================================
# handlers/post_stars.py - POSTGA STARS OLISH
# Foydalanuvchi: paket (stars soni) -> post havolasi -> xulosa ->
#   ✅ Tasdiqlash / ❌ Bekor qilish.
# Tasdiqlashda summa admin paneldagi 1⭐ narxiga ko'ra so'm hisobidan
# yechib olinadi; pul yetarli bo'lmasa foydalanuvchiga xabar beriladi.
# ===================================================================

from __future__ import annotations

import asyncio
import html
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.types import CallbackQuery, Message

from src.app import App
from src.handlers._helpers import edit_or_send, notify_all_admins, notify_payments_channel, user_ref
from src.handlers.states import PostStarsFlow
from src.i18n import t
from src.keyboards import back_kb, post_stars_confirm_kb, post_stars_packages_kb

router = Router(name="post_stars")

_LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/(?:c/\d+|[A-Za-z0-9_]{3,32})/\d+"
)


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


async def _lang(app: App, user_id: int) -> str:
    return (await app.users.get(user_id) or {}).get("language", "uz")


async def _post_packages(app: App) -> dict[int, float]:
    """Postga stars paketlari: post 1⭐ narxi bo'yicha (min * 1/2/3/5/10)."""
    post_price = await app.settings.get_post_price()
    if post_price <= 0:
        return {}
    min_stars = await app.settings.get_post_min_stars()
    out: dict[int, float] = {}
    for mult in (1, 2, 3, 5, 10):
        amount = min_stars * mult
        if amount <= 100000:
            out[amount] = round(post_price * amount, 2)
    return out


def _extract_link(text: str) -> str | None:
    m = _LINK_RE.search(text or "")
    return m.group(0) if m else None


@router.callback_query(F.data == "menu:post_stars")
async def post_request_start(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """1-qadam: qancha stars kerakligi tanlanadi."""
    lang = await _lang(app, cb.from_user.id)
    packages = await _post_packages(app)
    if not packages:
        await cb.answer("❌")
        await edit_or_send(cb, t(lang, "post_no_price"), reply_markup=back_kb(lang, "menu:main"))
        return
    await state.set_state(PostStarsFlow.choose_package)
    await edit_or_send(cb, t(lang, "post_stars_request"),
                       reply_markup=post_stars_packages_kb(lang, packages))


@router.callback_query(F.data.startswith("postpkg:"))
async def post_package_chosen(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """2-qadam: stars soni tanlandi, post havolasi so'raladi."""
    lang = await _lang(app, cb.from_user.id)
    amount_raw = cb.data.split(":", 2)[1]
    if amount_raw == "custom":
        min_stars = await app.settings.get_post_min_stars()
        await state.set_state(PostStarsFlow.custom_amount)
        await edit_or_send(
            cb, t(lang, "post_stars_custom_prompt"),
            reply_markup=back_kb(lang, "menu:main"),
        )
        return
    try:
        amount = int(amount_raw)
    except ValueError:
        await cb.answer("❌")
        return
    packages = await _post_packages(app)
    if amount not in packages:
        await cb.answer("❌ Mavjud emas")
        return
    await state.update_data(amount=amount, price=packages[amount])
    await state.set_state(PostStarsFlow.wait_link)
    await edit_or_send(cb, t(lang, "post_stars_ask_link"),
                       reply_markup=back_kb(lang, "menu:main"))


@router.message(StateFilter(PostStarsFlow.custom_amount), F.text)
async def post_custom_amount(message: Message, app: App, state: FSMContext) -> None:
    """2-qadam (qo'lda): foydalanuvchi o'zi stars sonini kiritadi."""
    lang = await _lang(app, message.from_user.id)
    min_stars = await app.settings.get_post_min_stars()
    post_price = await app.settings.get_post_price()
    text = (message.text or "").replace(" ", "").replace(",", ".").strip()
    try:
        amount = int(float(text))
    except ValueError:
        await message.answer(t(lang, "post_stars_bad_amount", min_stars=min_stars))
        return
    if amount < min_stars or amount <= 0:
        await message.answer(t(lang, "post_stars_bad_amount", min_stars=min_stars))
        return
    if post_price <= 0:
        await message.answer(t(lang, "post_no_price"))
        return
    await state.update_data(amount=amount, price=round(post_price * amount, 2))
    await state.set_state(PostStarsFlow.wait_link)
    await message.answer(t(lang, "post_stars_ask_link"),
                         reply_markup=back_kb(lang, "menu:main"))


@router.message(StateFilter(PostStarsFlow.wait_link), F.text)
async def post_link_received(message: Message, app: App, state: FSMContext) -> None:
    """3-qadam: post havolasi qabul qilinib, xulosa ko'rsatiladi."""
    lang = await _lang(app, message.from_user.id)
    link = _extract_link(message.text)
    if not link:
        await message.answer(t(lang, "post_stars_bad_link"))
        return
    data = await state.get_data()
    amount = int(data.get("amount", 0))
    price = float(data.get("price", 0))
    balance = await app.users.balance_sum(message.from_user.id)
    await state.update_data(link=link)
    await state.set_state(PostStarsFlow.confirm)
    await message.answer(
        t(lang, "post_stars_summary",
          amount=amount, link=link, price=f"{price:,.0f}", balance=f"{balance:,.0f}"),
        reply_markup=post_stars_confirm_kb(lang),
    )


@router.callback_query(F.data == "post:confirm")
async def post_confirm(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Tasdiqlash: pul yechiladi va stars ulangan akkaunt orqali AVTOMATIK yuboriladi.

    Xato bo'lsa pul avtomatik qaytariladi, adminlarga sabab bilan xabar boradi.
    """
    lang = await _lang(app, cb.from_user.id)
    data = await state.get_data()
    amount = int(data.get("amount", 0))
    price = float(data.get("price", 0))
    link = data.get("link") or ""
    # Ikki marta bosishdan himoya: holat darhol tozalanadi
    await state.clear()
    if amount <= 0 or not link:
        await edit_or_send(cb, t(lang, "post_stars_request"),
                           reply_markup=back_kb(lang, "menu:main"))
        return

    user_id = cb.from_user.id
    balance = await app.users.balance_sum(user_id)
    if balance + 1e-9 < price:
        await edit_or_send(cb, t(lang, "post_insufficient", balance=f"{balance:,.0f}",
                                 need=f"{price:,.0f}"))
        return

    order_id = await app.orders.create(
        user_id, "post_stars", amount, "balance", price_amount=price, note=link
    )
    new_bal = await app.users.sub_sum(
        user_id, price, f"Postga stars (buyurtma #{order_id})", order_id
    )
    if new_bal < 0:
        await app.orders.update_status(order_id, "rejected", "insufficient balance")
        await edit_or_send(cb, t(lang, "post_insufficient", balance=f"{balance:,.0f}",
                                 need=f"{price:,.0f}"))
        return

    try:
        await cb.answer()
    except Exception:  # noqa: BLE001
        pass
    await edit_or_send(
        cb, t(lang, "post_processing", order_id=order_id, amount=amount, link=link)
    )

    # --- AVTOMATIK yetkazish (ulangan Telegram akkaunt orqali) ---
    res = await app.admin.deliver_post_stars(order_id)
    user = await app.users.get(user_id) or {}

    if res.get("already"):
        await edit_or_send(cb, t(lang, "post_processing", order_id=order_id, amount=amount, link=link),
                           reply_markup=back_kb(lang, "menu:main"))
        return
    if res["ok"]:
        await edit_or_send(
            cb,
            t(lang, "post_auto_ok", order_id=order_id, amount=amount,
              link=link, price=f"{price:,.0f}"),
            reply_markup=back_kb(lang, "menu:main"),
        )
        admin_text = t("uz", "post_admin_auto_ok", order_id=order_id,
                       user=user_ref(user), amount=amount, link=link)
        await _safe_pay_channel(cb.bot, app, order_id)
    else:
        await edit_or_send(
            cb,
            t(lang, "post_auto_failed", order_id=order_id,
              refunded=f"{res['refunded']:,.0f}",
              reason=html.escape(str(res["reason"])[:200])),
            reply_markup=back_kb(lang, "menu:main"),
        )
        reason = html.escape(str(res["reason"])[:300])
        admin_text = t("uz", "post_admin_auto_failed", order_id=order_id,
                       user=user_ref(user), amount=amount,
                       sent=f"{res['sent']:g}", link=link, reason=reason,
                       refunded=f"{res['refunded']:,.0f}")
    asyncio.create_task(_safe_admins(cb.bot, admin_text, app))


@router.callback_query(F.data == "post:cancel")
async def post_cancel(cb: CallbackQuery, app: App, state: FSMContext) -> None:
    """Bekor qilish: hech narsa yechilmaydi, pul foydalanuvchida qoladi."""
    lang = await _lang(app, cb.from_user.id)
    balance = await app.users.balance_sum(cb.from_user.id)
    await state.clear()
    await edit_or_send(cb, t(lang, "post_cancelled", balance=f"{balance:,.0f}"),
                       reply_markup=back_kb(lang, "menu:main"))


@router.callback_query(F.data.startswith("order:approve:"))
async def admin_approve_order(cb: CallbackQuery, app: App) -> None:
    """Admin: post-stars yoki karta buyurtmasini tasdiqlash."""
    if not await app.is_admin(cb.from_user.id):
        await cb.answer("⛔️ Ruxsat yo'q")
        return
    lang = await _lang(app, cb.from_user.id)
    order_id = int(cb.data.split(":")[2])
    order = await app.orders.get(order_id)
    if not order:
        return
    if order["status"] not in ("pending", "processing"):
        await cb.answer("⛔️ Buyurtma holati tasdiqlab bo'lmaydi")
        return

    if order["type"] == "nft":
        # NFT yetkazildi (xaridorga xabar yuboriladi, pul allaqachon yechilgan)
        from src.handlers.nft import finish_nft_order

        done = await finish_nft_order(cb.bot, app, order, approve=True)
        await edit_or_send(cb, t(lang, "admin_approved", order_id=order_id)
                           if done else "⛔️ Buyurtma allaqachon ko'rib chiqilgan")
        if done:
            asyncio.create_task(_safe_pay_channel(cb.bot, app, order_id))
        return

    if order["type"] == "uc":
        # UC admin tomonidan PUBG ID ga yuborildi (pul allaqachon yechilgan)
        from src.handlers.uc import finish_uc_order

        done = await finish_uc_order(cb.bot, app, order, approve=True)
        await edit_or_send(cb, t(lang, "admin_approved", order_id=order_id)
                           if done else "⛔️ Buyurtma allaqachon ko'rib chiqilgan")
        if done:
            asyncio.create_task(_safe_pay_channel(cb.bot, app, order_id))
        return

    amount = float(order["stars_amount"])
    u_lang = (await app.users.get(order["user_id"]) or {}).get("language", "uz")
    if order["type"] == "post_stars":
        ok, reason = await app.admin.confirm_post_stars(order_id, amount)
        if ok:
            await edit_or_send(cb, t(lang, "post_approved_user", amount=amount))
            to_user = t(u_lang, "post_approved_user", amount=amount)
        else:
            await edit_or_send(cb, t(lang, "post_approval_failed", reason=reason))
            to_user = t(u_lang, "post_approval_failed", reason=reason)
    elif order["type"] == "buy":
        await app.payments.approve_card_order(order_id, order["user_id"], amount)
        await edit_or_send(cb, t(lang, "admin_approved", order_id=order_id))
        to_user = t(u_lang, "api_order_success", amount=amount)
    elif order["type"] == "topup":
        # Hisobni so'mda to'ldirishni tasdiqlash: pul qo'shiladi va kanalga yoziladi
        await app.payments.approve_card_order(order_id, order["user_id"], 0)
        await edit_or_send(cb, t(lang, "admin_approved", order_id=order_id))
        to_user = t(u_lang, "topup_enough", balance=f"{float(order['price_amount']):,.0f}")
    else:  # gift
        await app.payments.approve_card_order(order_id, order["user_id"], amount)
        await edit_or_send(cb, t(lang, "admin_approved", order_id=order_id))
        to_user = t(u_lang, "gift_sent", amount=amount, name="Gift", balance=0)
    # To'lovlar kanaliga faqat yetkazilgandan KEYIN yoziladi (admin tasdiqlagach)
    asyncio.create_task(_safe_pay_channel(cb.bot, app, order_id))
    try:
        await cb.bot.send_message(order["user_id"], to_user)
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("order:reject:"))
async def admin_reject_order(cb: CallbackQuery, app: App) -> None:
    """Admin: buyurtmani rad etish (pul qo'shilmaydi, kanalga yozilmaydi)."""
    if not await app.is_admin(cb.from_user.id):
        await cb.answer("⛔️ Ruxsat yo'q")
        return
    lang = await _lang(app, cb.from_user.id)
    order_id = int(cb.data.split(":")[2])
    order = await app.orders.get(order_id)
    if not order:
        return
    if order["type"] == "nft":
        # Pul qaytariladi, NFT yana sotuvga chiqadi
        from src.handlers.nft import finish_nft_order

        done = await finish_nft_order(cb.bot, app, order, approve=False)
        await edit_or_send(cb, t(lang, "admin_rejected", order_id=order_id)
                           if done else "⛔️ Buyurtma allaqachon ko'rib chiqilgan")
        return
    if order["type"] == "uc":
        # Pul qaytariladi
        from src.handlers.uc import finish_uc_order

        done = await finish_uc_order(cb.bot, app, order, approve=False)
        await edit_or_send(cb, t(lang, "admin_rejected", order_id=order_id)
                           if done else "⛔️ Buyurtma allaqachon ko'rib chiqilgan")
        return
    await app.admin.reject_order(order_id, "admin rejected")
    await edit_or_send(cb, t(lang, "admin_rejected", order_id=order_id))
    # Foydalanuvchiga xabar: buyurtma bekor qilindi, pul qo'shilmadi
    u_lang = (await app.users.get(order["user_id"]) or {}).get("language", "uz")
    try:
        await cb.bot.send_message(
            order["user_id"],
            t(u_lang, "order_rejected_user", order_id=order_id),
        )
    except Exception:  # noqa: BLE001
        pass