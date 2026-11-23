# ===================================================================
# handlers/extras.py - STATISTIKA VA FAQ MENYUSI
# ===================================================================

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from src.app import App
from src.handlers._helpers import edit_or_send
from src.i18n import t
from src.keyboards import back_kb
from src.utils import format_amount

router = Router(name="extras")


async def _lang(app: App, user_id: int) -> str:
    return (await app.users.get(user_id) or {}).get("language", "uz")


@router.callback_query(F.data == "menu:stats")
async def show_stats(cb: CallbackQuery, app: App) -> None:
    """Foydalanuvchi shaxsiy statistikasi."""
    lang = await _lang(app, cb.from_user.id)
    user = await app.users.get(cb.from_user.id) or {}
    totals = await app.users.totals(cb.from_user.id)
    bal = float(user.get("balance_stars", 0))
    sum_bal = float(user.get("balance_sum", 0))
    txt = (
        t(lang, "wallet_title",
          sum=f"{sum_bal:,.0f}",
          balance=format_amount(bal),
          progress="▱▱▱▱▱▱▱▱▱▱",
          bought=format_amount(float(totals.get("bought", 0))),
          sold=format_amount(float(totals.get("sold", 0))),
          gifted=format_amount(float(totals.get("gifted", 0))))
    )
    await edit_or_send(cb, txt, reply_markup=back_kb(lang, "menu:main"))


@router.callback_query(F.data == "menu:faq")
async def show_faq(cb: CallbackQuery, app: App) -> None:
    """FAQ / Yordam bo'limi."""
    lang = await _lang(app, cb.from_user.id)
    admin_name = "@" + (app.cfg.required_channel or "admin")
    await edit_or_send(cb, 
        t(lang, "faq", admin=admin_name),
        reply_markup=back_kb(lang, "menu:main"),
    )