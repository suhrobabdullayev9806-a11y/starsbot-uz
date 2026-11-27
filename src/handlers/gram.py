# ===================================================================
# handlers/gram.py - GRAM (TON) SOTIB OLISH
#  - "Gram olish" tugmasi: mini-app ochadi (/gram)
#  - Yangi Gram buyurtmasi haqida adminlarga to'liq ma'lumot:
#    xaridor profili (@username + id), Gram hamyon manzili / @username,
#    paket va narx + [Tasdiqlash/Rad etish]
#  - Admin "Tasdiqlash" -> Gram yuborildi / "Rad etish" -> pul qaytariladi
#  - Admin menyusida "Gram statistikasi"
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
from src.keyboards import admin_orders_kb, back_kb, gram_open_kb
from src.modules.gram import format_grams

router = Router(name="gram")
_log = logging.getLogger("stars.gram")


async def _lang(app: App, user_id: int) -> str:
    return (await app.users.get(user_id) or {}).get("language", "uz")


def _money(v: float) -> str:
    return f"{float(v):,.0f}".replace(",", " ")


def _buyer(order: dict) -> str:
    username = order.get("buyer_username") or order.get("username") or ""
    if username:
        return "@" + html.escape(str(username))
    name = html.escape(str(order.get("buyer_first_name") or order["user_id"]))
    return f'<a href="tg://user?id={int(order["user_id"])}">{name}</a>'


def gram_title(order: dict) -> str:
    return f"{format_grams(order.get('grams'))} Gram"


def wallet_kind_label(kind: str) -> str:
    return "Telegram profil (@username)" if kind == "username" else "TON Gram hamyoni"


@router.callback_query(F.data == "menu:gram")
async def gram_menu_fallback(cb: CallbackQuery, app: App) -> None:
    """WEBAPP_BASE_URL sozlanmagan bo'lsa: mini-app yo'qligini tushuntiradi."""
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb, t(lang, "gram_no_webapp"), reply_markup=gram_open_kb(lang))


async def notify_gram_order(bot, app: App, order_id: int) -> None:
    """Yangi Gram buyurtmasi: adminlarga to'liq ma'lumot + qaror tugmalari."""
    o = await app.gram.get_order(order_id)
    if not o:
        return
    buyer = _buyer(o)
    profile_line = f"👤 Xaridor: {buyer} (id: <code>{o['user_id']}</code>)"
    text = (
        f"🪙 <b>YANGI GRAM BUYURTMA №{order_id}</b>\n"
        f"{profile_line}\n"
        f"🪙 Paket: <b>{html.escape(gram_title(o))}</b>\n"
        f"👛 Qabul qiluvchi: <code>{html.escape(str(o['wallet']))}</code>\n"
        f"🏷 Tur: <b>{wallet_kind_label(str(o.get('wallet_kind') or ''))}</b>\n"
        f"💰 Narx: <b>{_money(o['price'])} so'm</b> (hisobdan yechildi)\n"
        f"🕓 Vaqt: <code>{html.escape(str(o.get('ordered_at') or ''))}</code>\n\n"
        "Gram'ni shu manzilga/profilga yuboring, so'ng «Tasdiqlash» ni bosing. "
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
            _log.warning("gram buyurtma adminga yetmadi admin=%s: %s", admin_id, exc)
    from src.handlers._helpers import notify_payments_channel

    await notify_payments_channel(bot, app, order_id)


async def notify_buyer_accepted(bot, app: App, order_id: int) -> None:
    """Xaridorga: buyurtma qabul qilindi (admin yuborishini kutmoqda)."""
    o = await app.gram.get_order(order_id)
    if not o:
        return
    lang = await _lang(app, o["user_id"])
    await send_safe(bot, o["user_id"], t(
        lang, "gram_order_accepted", order_id=order_id,
        title=html.escape(gram_title(o)), wallet=html.escape(str(o["wallet"]))))


async def finish_gram_order(bot, app: App, order: dict, approve: bool) -> bool:
    """
    Admin qarori: approve=True -> Gram yuborildi; False -> pul qaytariladi.
    Foydalanuvchiga xabar yuboradi. Qaytaradi: amal bajarilganmi.
    """
    order_id = order["id"]
    o = await app.gram.get_order(order_id) or {"grams": 0, "wallet": "—"}
    lang = await _lang(app, order["user_id"])
    title = html.escape(gram_title(o))
    if approve:
        if not await app.gram.complete(order_id):
            return False
        msg = t(lang, "gram_order_done", title=title, order_id=order_id,
                wallet=html.escape(str(o["wallet"])))
    else:
        if not await app.gram.cancel(order_id):
            return False
        msg = t(lang, "gram_order_rejected", title=title, order_id=order_id,
                price=_money(order["price_amount"]))
    await send_safe(bot, order["user_id"], msg)
    return True


@router.callback_query(F.data == "admin:gram")
async def admin_gram_stats(cb: CallbackQuery, app: App) -> None:
    """Admin menyusi: Gram statistikasi (to'liq boshqaruv — admin mini-appda)."""
    if not await app.is_admin(cb.from_user.id):
        await cb.answer("⛔️ Ruxsat yo'q")
        return
    s = await app.gram.stats()
    p = s["periods"]

    def line(label: str, d: dict) -> str:
        return (f"{label}: <b>{int(d['orders'])}</b> ta · "
                f"<b>{format_grams(d['grams'])}</b> Gram · "
                f"<b>{_money(d['revenue'])}</b> so'm")

    text = (
        "🪙 <b>Gram statistikasi</b>\n\n"
        + line("Bugun", p["today"]) + "\n" + line("Hafta", p["week"]) + "\n"
        + line("Oy", p["month"]) + "\n" + line("Jami", p["all"]) + "\n\n"
        f"⏳ Kutilayotgan: <b>{int(s['pending']['c'])}</b> ta "
        f"({_money(s['pending']['s'])} so'm)\n"
        f"❌ Rad etilgan: <b>{int(s['rejected'])}</b> ta\n"
        f"🧾 O'rtacha chek: <b>{_money(s['avg_order'])}</b> so'm\n\n"
        "⚙️ Paketlar va narxlarni <b>Admin mini-app → Gram</b> bo'limida boshqaring."
    )
    if s["top_packages"]:
        text += "\n\n🏆 <b>Top paketlar</b>\n" + "\n".join(
            f"• {format_grams(r['grams'])} Gram — {int(r['orders'])} ta"
            for r in s["top_packages"])
    if s["top_buyers"]:
        text += "\n\n👑 <b>Top xaridorlar</b>\n" + "\n".join(
            f"• {('@' + r['username']) if r['username'] else html.escape(str(r['first_name'] or r['user_id']))}"
            f" — {_money(r['revenue'])} so'm ({int(r['orders'])} ta)"
            for r in s["top_buyers"])
    lang = await _lang(app, cb.from_user.id)
    await edit_or_send(cb, text, reply_markup=back_kb(lang, "admin:main"))
