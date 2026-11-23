# ===================================================================
# handlers/uc.py - PUBG UC OLISH (foydalanuvchi tomoni + buyurtma jarayoni)
#  - "UC olish" tugmasi: mini-app ochadi (/uc)
#  - Yangi UC buyurtmasi haqida adminlarga xabar (PUBG ID + nickname + tugmalar)
#  - Admin "Tasdiqlash" -> UC yuborildi / "Rad etish" -> pul qaytariladi
#  - Admin menyusida "UC statistikasi"
# ===================================================================

from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.app import App
from src.handlers._helpers import edit_or_send
from src.handlers.nft import send_safe
from src.i18n import t
from src.keyboards import admin_orders_kb, back_kb, uc_open_kb

router = Router(name="uc")
_log = logging.getLogger("stars.uc")


async def _lang(app: App, user_id: int) -> str:
    return (await app.users.get(user_id) or {}).get("language", "uz")


def _money(v: float) -> str:
    return f"{float(v):,.0f}".replace(",", " ")


def _buyer(order: dict) -> str:
    if order.get("username"):
        return "@" + html.escape(str(order["username"]))
    name = html.escape(str(order.get("first_name") or order["user_id"]))
    return f'<a href="tg://user?id={int(order["user_id"])}">{name}</a>'


def uc_title(order: dict) -> str:
    total = int(order["uc"]) + int(order.get("bonus") or 0)
    return f"{total:,} UC".replace(",", " ")


@router.callback_query(F.data == "menu:uc")
async def uc_menu_fallback(cb: CallbackQuery, app: App) -> None:
    """WEBAPP_BASE_URL sozlanmagan bo'lsa: mini-app yo'qligini tushuntiradi."""
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb, t(lang, "uc_no_webapp"), reply_markup=uc_open_kb(lang))


async def notify_uc_order(bot, app: App, order_id: int) -> None:
    """Yangi UC buyurtmasi: adminlarga PUBG ID + nickname + [Tasdiqlash/Rad etish]."""
    o = await app.uc.get_order(order_id)
    if not o:
        return
    nick_line = (f"🎮 Nickname: <b>{html.escape(o['nickname'])}</b> ✅\n" if o["nickname"]
                 else "🎮 Nickname: <i>aniqlanmadi — ID ni diqqat bilan tekshiring</i>\n")
    text = (
        f"🎮 <b>YANGI UC BUYURTMA №{order_id}</b>\n"
        f"👤 {_buyer(o)} (id: <code>{o['user_id']}</code>)\n"
        f"💎 Paket: <b>{html.escape(uc_title(o))}</b>"
        + (f" (shundan bonus: {int(o['bonus'])})" if o["bonus"] else "") + "\n"
        f"🆔 PUBG ID: <code>{html.escape(o['pubg_id'])}</code>\n"
        + nick_line
        + f"💰 Narx: <b>{_money(o['price'])} so'm</b> (hisobdan yechildi)\n\n"
        "UC'ni shu ID ga yuboring, so'ng «Tasdiqlash» ni bosing. "
        "«Rad etish» pulni xaridorga qaytaradi."
    )
    kb = admin_orders_kb("uz", order_id)
    extra = await app.settings.get_extra_admins()
    ids: list[int] = []
    for a in [*app.cfg.admin_ids, app.cfg.super_admin_id, *extra]:
        if a and a not in ids:
            ids.append(a)
    for admin_id in ids:
        try:
            await bot.send_message(admin_id, text, reply_markup=kb, disable_web_page_preview=True)
        except Exception as exc:  # noqa: BLE001
            _log.warning("uc buyurtma adminga yetmadi admin=%s: %s", admin_id, exc)


async def notify_buyer_accepted(bot, app: App, order_id: int) -> None:
    """Xaridorga: buyurtma qabul qilindi (admin yuborishini kutmoqda)."""
    o = await app.uc.get_order(order_id)
    if not o:
        return
    lang = await _lang(app, o["user_id"])
    await send_safe(bot, o["user_id"], t(
        lang, "uc_order_accepted", order_id=order_id, title=html.escape(uc_title(o)),
        pubg_id=html.escape(o["pubg_id"]), nick=html.escape(o["nickname"] or "—")))


async def finish_uc_order(bot, app: App, order: dict, approve: bool) -> bool:
    """
    Admin qarori: approve=True -> UC yuborildi; False -> pul qaytariladi.
    Foydalanuvchiga xabar yuboradi. Qaytaradi: amal bajarilganmi (ikki marta emas).
    """
    order_id = order["id"]
    o = await app.uc.get_order(order_id) or {"uc": 0, "bonus": 0, "pubg_id": "—", "nickname": ""}
    lang = await _lang(app, order["user_id"])
    title = html.escape(uc_title(o))
    if approve:
        if not await app.uc.complete(order_id):
            return False
        msg = t(lang, "uc_order_done", title=title, order_id=order_id,
                pubg_id=html.escape(o["pubg_id"]), nick=html.escape(o["nickname"] or "—"))
    else:
        if not await app.uc.cancel(order_id):
            return False
        msg = t(lang, "uc_order_rejected", title=title, order_id=order_id,
                price=_money(order["price_amount"]))
    await send_safe(bot, order["user_id"], msg)
    return True


@router.callback_query(F.data == "admin:uc")
async def admin_uc_stats(cb: CallbackQuery, app: App) -> None:
    """Admin menyusi: UC statistikasi (to'liq boshqaruv — admin mini-appda)."""
    if not await app.is_admin(cb.from_user.id):
        await cb.answer("⛔️ Ruxsat yo'q")
        return
    s = await app.uc.stats()
    p = s["periods"]

    def line(label: str, d: dict) -> str:
        return (f"{label}: <b>{int(d['orders'])}</b> ta · <b>{int(d['uc']):,}</b> UC · "
                f"<b>{_money(d['revenue'])}</b> so'm").replace(",", " ")

    text = (
        "🎮 <b>UC statistikasi</b>\n\n"
        + line("Bugun", p["today"]) + "\n" + line("Hafta", p["week"]) + "\n"
        + line("Oy", p["month"]) + "\n" + line("Jami", p["all"]) + "\n\n"
        f"⏳ Kutilayotgan: <b>{int(s['pending']['c'])}</b> ta "
        f"({_money(s['pending']['s'])} so'm)\n"
        f"❌ Rad etilgan: <b>{int(s['rejected'])}</b> ta\n"
        f"🧾 O'rtacha chek: <b>{_money(s['avg_order'])}</b> so'm"
    )
    if s["top_packages"]:
        text += "\n\n🏆 <b>Top paketlar</b>\n" + "\n".join(
            f"• {int(r['uc']):,} UC — {int(r['orders'])} ta".replace(",", " ")
            for r in s["top_packages"])
    if s["top_buyers"]:
        text += "\n\n👑 <b>Top xaridorlar</b>\n" + "\n".join(
            f"• {('@' + r['username']) if r['username'] else html.escape(str(r['first_name'] or r['user_id']))}"
            f" — {_money(r['revenue'])} so'm ({int(r['orders'])} ta)"
            for r in s["top_buyers"])
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb, text, reply_markup=back_kb(lang, "admin:main"))
