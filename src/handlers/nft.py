# ===================================================================
# handlers/nft.py - NFT OLISH (foydalanuvchi tomoni + buyurtma jarayoni)
#  - "NFT olish" tugmasi: mini-app ochadi (/nft)
#  - Yangi NFT buyurtmasi haqida adminlarga xabar (rasm + tugmalar)
#  - Admin "Tasdiqlash" -> NFT yetkazildi / "Rad etish" -> pul qaytariladi
# ===================================================================

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.app import App
from src.handlers._helpers import edit_or_send, notify_all_admins, user_ref
from src.i18n import t
from src.keyboards import admin_orders_kb, nft_open_kb

router = Router(name="nft")
_log = logging.getLogger("stars.nft")


async def _lang(app: App, user_id: int) -> str:
    return (await app.users.get(user_id) or {}).get("language", "uz")


@router.callback_query(F.data == "menu:nft")
async def nft_menu_fallback(cb: CallbackQuery, app: App) -> None:
    """WEBAPP_BASE_URL sozlanmagan bo'lsa: mini-app yo'qligini tushuntiradi."""
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb, t(lang, "nft_no_webapp"), reply_markup=nft_open_kb(lang))


def recipient_of(order: dict | None) -> str:
    """Buyurtma izohidan oluvchi akkauntni ajratadi (… -> @user (id:1) | url)."""
    note = str((order or {}).get("note", ""))
    if "->" in note:
        return note.split("->", 1)[1].split("|")[0].strip() or "—"
    return "—"


async def send_safe(bot, chat_id: int, text: str) -> bool:
    """Xabarni yuboradi; HTML xato bersa oddiy matn bilan qayta urinadi."""
    if bot is None:
        return False
    try:
        await bot.send_message(chat_id, text)
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("xabar yuborilmadi chat=%s: %s", chat_id, exc)
    try:
        import re as _re
        await bot.send_message(chat_id, _re.sub(r"<[^>]+>", "", text), parse_mode=None)
        return True
    except Exception as exc:  # noqa: BLE001
        _log.warning("oddiy matn ham yuborilmadi chat=%s: %s", chat_id, exc)
        return False


def nft_title(nft: dict | None, order: dict | None = None) -> str:
    if nft:
        return f"{nft['name']} #{nft['number']}"
    return str((order or {}).get("note", "NFT")).split("->")[0].strip() or "NFT"


async def notify_nft_order(bot, app: App, order_id: int) -> None:
    """Yangi NFT buyurtmasi: adminlarga rasm + [Tasdiqlash/Rad etish] tugmalari."""
    order = await app.orders.get(order_id)
    nft = await app.nft.by_order(order_id) if order else None
    if not order or not nft:
        return
    buyer = await app.users.get(order["user_id"]) or {}
    traits = "\n".join(
        f"{icon} {label}: <b>{html.escape(nft[key])}</b>"
        for icon, label, key in (("🎭", "Model", "model"), ("🎨", "Backdrop", "backdrop"),
                                 ("🔣", "Symbol", "symbol")) if nft.get(key)
    )
    text = (
        f"🖼 <b>YANGI NFT BUYURTMA №{order_id}</b>\n"
        f"👤 {user_ref(buyer) if buyer else order['user_id']} (id: <code>{order['user_id']}</code>)\n"
        f"🎁 <b>{html.escape(nft_title(nft))}</b>\n"
        + (traits + "\n" if traits else "")
        + f"📬 Yetkazish: <b>{html.escape(recipient_of(order))}</b>\n"
        + f"💰 Narx: <b>{float(order['price_amount']):,.0f} so'm</b> (hisobdan yechildi)\n"
        f"🔗 {html.escape(nft['url'])}\n\n"
        "NFT'ni xaridorga yuboring, so'ng «Tasdiqlash» ni bosing. "
        "«Rad etish» pulni qaytaradi va NFT'ni yana sotuvga chiqaradi."
    )
    kb = admin_orders_kb("uz", order_id)
    extra = await app.settings.get_extra_admins()
    ids: list[int] = []
    for a in [*app.cfg.admin_ids, app.cfg.super_admin_id, *extra]:
        if a and a not in ids:
            ids.append(a)
    for admin_id in ids:
        try:
            if nft.get("image"):
                try:
                    await bot.send_photo(admin_id, nft["image"], caption=text, reply_markup=kb)
                    continue
                except Exception:  # noqa: BLE001  rasm yuborilmasa matn bilan
                    pass
            await bot.send_message(admin_id, text, reply_markup=kb, disable_web_page_preview=True)
        except Exception as exc:  # noqa: BLE001
            _log.warning("nft buyurtma adminga yetmadi admin=%s: %s", admin_id, exc)


async def finish_nft_order(bot, app: App, order: dict, approve: bool) -> bool:
    """
    Admin qarori: approve=True -> NFT yetkazildi; False -> pul qaytariladi.
    Foydalanuvchiga xabar yuboradi. Qaytaradi: amal bajarilganmi (ikki marta emas).
    """
    order_id = order["id"]
    nft = await app.nft.by_order(order_id)
    title = nft_title(nft, order)
    u_lang = await _lang(app, order["user_id"])
    if approve:
        if not await app.nft.complete(order_id):
            return False
        msg = t(u_lang, "nft_order_done", title=html.escape(title), order_id=order_id)
    else:
        if not await app.nft.cancel(order_id):
            return False
        msg = t(u_lang, "nft_order_rejected", title=html.escape(title), order_id=order_id,
                price=f"{float(order['price_amount']):,.0f}")
    if approve:
        msg += f"\n📬 {html.escape(recipient_of(order))}"
    await send_safe(bot, order["user_id"], msg)
    return True


async def notify_buyer_accepted(bot, app: App, order_id: int) -> None:
    """Xaridorga: buyurtma qabul qilindi (admin tasdiqlashini kutmoqda)."""
    order = await app.orders.get(order_id)
    nft = await app.nft.by_order(order_id) if order else None
    if not order:
        return
    await send_safe(
        bot, order["user_id"],
        f"🧾 <b>Buyurtma qabul qilindi</b> №{order_id}\n"
        f"🖼 <b>{html.escape(nft_title(nft, order))}</b>\n"
        f"📬 {html.escape(recipient_of(order))}\n\n"
        "Admin tasdiqlagach sizga xabar keladi.")
