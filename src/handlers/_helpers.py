# ===================================================================
# handlers/_helpers.py - Umumiy yordamchi funksiyalar
# Obuna tekshirish, user formati, moderator xabarlari va h.k.
# ===================================================================

from __future__ import annotations

import asyncio
import html
import logging

from aiogram import Bot
from aiogram.types import CallbackQuery, Message

from src.config import Settings
from src.i18n import t

_log = logging.getLogger("stars.notify")


async def is_subscribed(bot: Bot, user_id: int, channel: str, channel_id: str | None) -> bool:
    """Foydalanuvchi majburiy kanalga obuna bo'lganini tekshiradi."""
    from src.subscription import check_member

    return await check_member(bot, user_id, channel, channel_id)


def user_ref(user: dict) -> str:
    """Foydalanuvchini HTML formatda ko'rsatadi (bot parse_mode=HTML)."""
    username = user.get("username") or ""
    if username:
        return "@" + html.escape(str(username))
    first = html.escape(str(user.get("first_name") or user.get("id", "")))
    return f'<a href="tg://user?id={int(user["id"])}">{first}</a>'


async def notify_admins(bot: Bot, text: str, cfg: Settings, kb=None) -> None:
    """Barcha adminlarga xabar jo'natadi (.env ADMIN_IDS + super admin)."""
    for admin_id in cfg.admin_ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001
            continue
    if cfg.super_admin_id and cfg.super_admin_id not in cfg.admin_ids:
        try:
            await bot.send_message(cfg.super_admin_id, text, reply_markup=kb,
                                   disable_web_page_preview=True)
        except Exception:  # noqa: BLE001
            pass


async def notify_all_admins(bot: Bot, text: str, app, kb=None) -> None:
    """Barcha adminlarga xabar jo'natadi — .env adminlari + DB'da qo'shilganlar."""
    extra = await app.settings.get_extra_admins()
    seen = set()
    ids = list(app.cfg.admin_ids)
    if app.cfg.super_admin_id:
        ids.append(app.cfg.super_admin_id)
    for admin_id in ids + extra:
        if admin_id in seen:
            continue
        seen.add(admin_id)
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001
            continue


async def notify_admins_content(bot: Bot, media_kind: str, file_id: str, caption: str,
                               app, kb=None) -> None:
    """Chekni media TURIGA qarab barcha adminlarga yetkazadi.

    Endi chek rasm/video/fayl(png-skrinshot)/animatsiya qilib yuborilganiga
    qarab mos holyalik usulda (retry + log bilan) adminga boradi.

    Retry: DNS vaqtincha uzilganda, flood limitida va boshqa tarmoq xatolarida
    har bir adminga alohida 3 marta qayta urinadi; hammasi ham ishlamasa
    `ERROR` log'ga yoziladi — chek hech qachon izsiz yo'qolmaydi.
    """
    kind_sender = {
        "photo": bot.send_photo,
        "video": bot.send_video,
        "document": bot.send_document,
        "animation": bot.send_animation,
    }
    sender = kind_sender.get(media_kind)
    if not sender:
        _log.warning("noma'lum chek media turi: %s", media_kind)
        return

    extra = await app.settings.get_extra_admins()
    seen: set[int] = set()
    ids: list[int] = list(app.cfg.admin_ids)
    if app.cfg.super_admin_id:
        ids.append(app.cfg.super_admin_id)
    for admin_id in ids + extra:
        if admin_id in seen:
            continue
        seen.add(admin_id)
        try:
            # Tarmoq vaqtinchalik uzilganda ham chek yetkazilishi uchun retry
            for attempt in range(3):
                try:
                    await sender(
                        admin_id, file_id, caption=caption, reply_markup=kb)
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 2:
                        raise
                    _log.warning("chek retry %d media=%s admin=%s: %s",
                                 attempt + 1, media_kind, admin_id, exc)
                    await asyncio.sleep(1.5)
        except Exception as exc:  # noqa: BLE001
            _log.error("chek adminga yetkazilmadi admin=%s media=%s: %s",
                       admin_id, media_kind, exc)


async def notify_admins_media(bot: Bot, photo_id: str, caption: str, app, kb=None) -> None:
    """ESKI imzo (rasm) — universal `notify_admins_content` ga yo'naltiradi."""
    await notify_admins_content(bot, "photo", photo_id, caption, app, kb)


_STATUS_HEAD = {
    "pending": "🆕 <b>YANGI BUYURTMA</b>",
    "processing": "🔄 <b>BUYURTMA JARAYONDA</b>",
    "done": "✅ <b>BUYURTMA BAJARILDI</b>",
    "rejected": "❌ <b>BUYURTMA RAD ETILDI</b>",
    "failed": "⚠️ <b>BUYURTMA XATO</b>",
}


async def _channel_target(app) -> str:
    username, chat_id = await app.settings.get_payment_channel()
    return chat_id or (f"@{username}" if username else "")


async def notify_payments_channel(bot: Bot, app, order_id: int) -> None:
    """Buyurtma haqida buyurtmalar kanaliga xabar jo'natadi (sozlangan bo'lsa).

    Admin panel: Sozlamalar -> Buyurtmalar kanali.
    """
    order = await app.orders.get(order_id)
    if not order:
        return
    target = await _channel_target(app)
    if not target:
        return
    try:
        user = await app.users.get(order["user_id"]) or {}
        uid = order["user_id"]
        uname = html.escape(str(user.get("username") or user.get("first_name") or uid))
        if user and not user.get("username"):
            uname = f'<a href="tg://user?id={uid}">{uname}</a>'
        else:
            uname = "@" + uname
        type_map = {
            "buy": "🛒 Sotib olish",
            "gift": "🎁 Gift",
            "post_stars": "📝 Postga stars",
            "topup": "💰 Hisob to'ldirish (so'm)",
            "nft": "🖼 NFT",
            "uc": "🎮 PUBG UC",
            "gram": "🪙 Gram (TON)",
        }
        stars = float(order["stars_amount"])
        bio = (f"<b>{int(stars)} ⭐</b>" if stars and order["type"] not in ("nft", "uc", "gram") else
               f"<b>{float(order['price_amount']):,.0f} so'm</b>")
        head = _STATUS_HEAD.get(str(order["status"]), "🆕 <b>BUYURTMA</b>")
        text = (
            f"{head} №{order['id']}\n"
            f"👤 <b>{uname}</b> (id: <code>{uid}</code>)\n"
            f"📦 Tur: {type_map.get(order['type'], order['type'])} — {bio}\n"
            f"💰 Narx: <b>{float(order['price_amount']):,.0f}</b> so'm\n"
            f"💳 Usul: <code>{order['payment_method']}</code>\n"
            f"🕓 Vaqt: <code>{order['created_at']}</code>\n"
        )
        if order.get("note"):
            text += f"📝 {html.escape(str(order['note'])[:120])}\n"
        text += f"📌 Status: <b>{order['status']}</b>"
        await bot.send_message(target, text, disable_web_page_preview=True)
    except Exception:  # noqa: BLE001
        pass


async def notify_smm_channel(bot: Bot, app, order: dict, event: str = "new") -> None:
    """SMM buyurtmasi (yangi yoki yakuniy holat) haqida buyurtmalar kanaliga yozadi."""
    target = await _channel_target(app)
    if not target or not order:
        return
    try:
        uid = int(order["user_id"])
        user = await app.users.get(uid) or {}
        uname = html.escape(str(user.get("username") or user.get("first_name") or uid))
        if user and not user.get("username"):
            uname = f'<a href="tg://user?id={uid}">{uname}</a>'
        else:
            uname = "@" + uname
        if event == "new":
            head = "🆕 <b>YANGI SMM BUYURTMA</b>"
        elif event == "completed":
            head = "✅ <b>SMM BUYURTMA BAJARILDI</b>"
        elif event == "partial":
            head = "⚠️ <b>SMM BUYURTMA QISMAN BAJARILDI</b>"
        elif event in ("canceled", "failed"):
            head = "❌ <b>SMM BUYURTMA BEKOR QILINDI</b>"
        else:
            head = "🔄 <b>SMM BUYURTMA</b>"
        text = (
            f"{head} №{order['id']}\n"
            f"👤 <b>{uname}</b> (id: <code>{uid}</code>)\n"
            f"🚀 {html.escape(str(order['service_name']))}\n"
            f"🔢 Miqdor: <b>{int(order['quantity']):,}</b> ta\n"
            f"🔗 <code>{html.escape(str(order['link'])[:180])}</code>\n"
            f"💰 Narx: <b>{float(order['price']):,.0f}</b> so'm\n"
            f"🕓 Vaqt: <code>{order['created_at']}</code>\n"
            f"📌 Status: <b>{html.escape(str(order.get('status') or ''))}</b>"
        )
        if order.get("provider_order"):
            text += f"\n🆔 Provayder: <code>{html.escape(str(order['provider_order'])[:60])}</code>"
        if float(order.get("refunded") or 0) > 0:
            text += f"\n💸 Qaytarilgan: <b>{float(order['refunded']):,.0f}</b> so'm"
        await bot.send_message(target, text, disable_web_page_preview=True)
    except Exception:  # noqa: BLE001
        pass


async def answer(msg: Message, key: str, lang: str, kb=None, **kwargs) -> None:
    """Xabar yuborish yordamchisi."""
    text = t(lang, key, **kwargs)
    await msg.answer(text, reply_markup=kb, disable_web_page_preview=True)


async def edit_ok(cb: CallbackQuery, key: str, lang: str, kb=None, **kwargs) -> None:
    """Mavjud xabarni yangilash yordamchisi."""
    text = t(lang, key, **kwargs)
    try:
        await cb.message.edit_text(text, reply_markup=kb, disable_web_page_preview=True)
    except Exception:  # noqa: BLE001
        await cb.answer()


async def edit_or_send(cb: CallbackQuery, text: str, reply_markup=None,
                       disable_web_page_preview: bool = True) -> None:
    """
    Xabarni tahrirlaydi. Agar xabar media (rasm) bo'lsa, edit qilib
    bo'lmaydi — eski xabarni o'chirib yangi (matn) xabar jo'natadi.
    Bu bannerli menyular va bosqichli jarayonlar uchun zarur.
    """
    if isinstance(cb, Message):   # oddiy xabar (matn kiritilgandan keyin): yangi xabar yuboramiz
        try:
            await cb.answer(text, reply_markup=reply_markup,
                            disable_web_page_preview=disable_web_page_preview)
        except Exception:  # noqa: BLE001
            pass
        return
    try:
        await cb.message.edit_text(text, reply_markup=reply_markup,
                                   disable_web_page_preview=disable_web_page_preview)
        return
    except Exception:  # noqa: BLE001
        pass
    try:
        await cb.message.delete()
    except Exception:  # noqa: BLE001
        pass
    try:
        await cb.message.answer(text, reply_markup=reply_markup,
                                disable_web_page_preview=disable_web_page_preview)
    except Exception:  # noqa: BLE001
        pass