# ===================================================================
# handlers/start.py - START / TIL / ASOSIY MENYU / OBUNA
# ===================================================================

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from src.app import App
from src.assets import menu_banner, send_smart_photo
from src.handlers._helpers import edit_or_send
from src.i18n import t
from src.keyboards import check_subscribe_kb, language_kb, main_menu_kb

router = Router(name="start")


async def render_main_menu(target, app: App, lang: str, user: dict) -> None:
    """
    Bosh menyuni chiroyli ko'rsatadi:
    - banner rasm (mavjud bo'lsa) + caption + yonma-yon tugmalar
    - rasm yetishmasa oddiy matn
    Rasm file_id keshlanadi — birinchi marta upload, keyingilari instant.
    """
    text = t(lang, "start", first=(user.get("first_name") or "friend"))
    kb = main_menu_kb(lang)
    banner = menu_banner()
    if banner:
        sent = await send_smart_photo(target, banner, text, kb)
        if sent is not None:
            return

    sends_new = isinstance(target, CallbackQuery)
    if sends_new:
        try:
            await target.message.delete()
        except Exception:  # noqa: BLE001
            pass
        try:
            await target.message.answer(text, reply_markup=kb)
        except Exception:  # noqa: BLE001
            pass
    else:
        await target.answer(text, reply_markup=kb)


@router.message(CommandStart())
async def cmd_start(message: Message, app: App) -> None:
    """Botga 'Start' berilganda ishlaydi."""
    bot_active = await app.settings.bot_active()

    user, created = await app.users.get_or_create(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.first_name or "",
        "uz",
    )

    # Bot o'chirilgan bo'lsa (admin tomonidan) — admin o'zi kirsa ko'radi
    if not bot_active and not await app.is_admin(message.from_user.id):
        await message.answer(t(user.get("language", "uz"), "start_bot_inactive"))
        return

    lang = user.get("language") or "uz"

    # Obuna tekshiruvi (barcha majburiy kanallar)
    channels = await app.settings.get_channels()
    if channels:
        from src.subscription import missing_channels

        missing = await missing_channels(message.bot, message.from_user.id, channels)
        if missing:
            label = ", ".join(
                "@" + str(c.get("username")) for c in channels if c.get("username")) or "—"
            text = (t(lang, "start_not_subscribed_multi", channels=label)
                    if len(channels) > 1 else
                    t(lang, "start_not_subscribed", channel=label))
            await message.answer(text, reply_markup=check_subscribe_kb(lang, channels=channels))
            return

    await render_main_menu(message, app, lang, user)


@router.callback_query(F.data == "check:sub")
async def check_subscription(cb: CallbackQuery, app: App) -> None:
    """Obunani tekshirish tugmasi."""
    lang = (await app.users.get(cb.from_user.id) or {}).get("language", "uz")
    channels = await app.settings.get_channels()
    if channels:
        from src.subscription import missing_channels

        missing = await missing_channels(cb.bot, cb.from_user.id, channels)
        if missing:
            label = ", ".join(
                "@" + str(c.get("username")) for c in missing if c.get("username")) or "—"
            await cb.answer(t(lang, "start_not_subscribed", channel=label), show_alert=True)
            return
    user = await app.users.get(cb.from_user.id) or {}
    await app.users.set_subscribed(cb.from_user.id, True)
    app.sub_guard.forget(cb.from_user.id)
    await render_main_menu(cb, app, lang, user)


@router.callback_query(F.data == "menu:main")
async def go_main_menu(cb: CallbackQuery, app: App) -> None:
    """Asosiy menyuga qaytish."""
    lang = (await app.users.get(cb.from_user.id) or {}).get("language", "uz")
    user = await app.users.get(cb.from_user.id) or {}
    await render_main_menu(cb, app, lang, user)


@router.callback_query(F.data == "lang:change")
async def change_lang(cb: CallbackQuery) -> None:
    """Tilni o'zgartirish menyusi."""
    await edit_or_send(cb, "🌐 <b>Select language / Tilni tanlang</b>",
                               reply_markup=language_kb())


@router.callback_query(F.data.startswith("lang:"))
async def set_lang(cb: CallbackQuery, app: App) -> None:
    """Tanlangan tilni saqlash."""
    lang = cb.data.split(":")[1]
    if lang not in ("uz", "en", "ru"):
        return
    await app.users.set_language(cb.from_user.id, lang)
    user = await app.users.get(cb.from_user.id) or {}
    await cb.answer("✅ OK")
    await render_main_menu(cb, app, lang, user)


# /lang qo'shimcha buyruq
@router.message(Command("lang"))
async def cmd_lang(message: Message) -> None:
    await message.answer("🌐 <b>Select language / Tilni tanlang</b>",
                         reply_markup=language_kb())