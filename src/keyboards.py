# ===================================================================
# keyboards.py - Barcha inline tugmalar (NATIV RANGLI)
# Telegram 2026 dan inline tugmalar uchun haqiqiy fon ranglarini
# qo'llaydi (Bot API 'style' maydoni):
#   "danger"   -> QIZIL  (muhim/xavfli amallar)
#   "success"  -> YASHIL (tasdiqlash/muvaffaqiyat)
#   "primary"  -> KO'K   (navigatsiya/axborot)
# Eski klientlarda (2026-fevraldan avval) tugmalar oddiy ko'rinadi,
# lekin hamma xabarlarda emoji belgilar ham mavjud.
# Callback data formatlari:  <bo'lim>:<qiymat>
# ===================================================================

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.i18n import t

# Aiogram 'style' qiymatlari
RED = "danger"      # qizil fon
GREEN = "success"   # yashil fon
BLUE = "primary"    # ko'k fon

# Mini-App ochiladigan OMMAVIY HTTPS URL (main.py'da set_webapp_url orqali)
# Bo'sh bo'lsa "Stars olish" tugmasi inline oqimga o'tadi.
_WEBAPP_BASE_URL = ""


def set_webapp_url(url: str) -> None:
    """WEBAPP_BASE_URL ni o'rnatadi (bot startida chaqiriladi)."""
    global _WEBAPP_BASE_URL
    _WEBAPP_BASE_URL = (url or "").strip().rstrip("/")


def webapp_url() -> str:
    return _WEBAPP_BASE_URL


def btn(text: str, data: str, color: str = GREEN) -> InlineKeyboardButton:
    """Haqiqiy rangli (fonli) inline tugma yaratadi."""
    return InlineKeyboardButton(text=text, callback_data=data, style=color)


# ---------------------------------------------------------------
# Umumiy
# ---------------------------------------------------------------

def language_kb() -> InlineKeyboardMarkup:
    """Til tanlash tugmalari (Uz/En/Ru)."""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang:uz"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
    )
    return kb.as_markup()


def main_menu_kb(lang: str) -> InlineKeyboardMarkup:
    """Asosiy menyu - minimalist UI, tugmalar yonma-yon (2 ta/qator)."""
    kb = InlineKeyboardBuilder()

    def _webapp(text: str, url: str, color: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(
            text=text, web_app=WebAppInfo(url=url), style=color)

    topup = btn(t(lang, "menu_topup"), "topup:choose", GREEN)
    buy = (_webapp(t(lang, "menu_buy"), f"{_WEBAPP_BASE_URL}/app", RED)
           if _WEBAPP_BASE_URL else btn(t(lang, "menu_buy"), "menu:buy", RED))
    kb.row(topup, buy)

    nft = (_webapp(t(lang, "menu_nft"), f"{_WEBAPP_BASE_URL}/nft", GREEN)
           if _WEBAPP_BASE_URL else btn(t(lang, "menu_nft"), "menu:nft", GREEN))
    gram = (_webapp(t(lang, "menu_gram"), f"{_WEBAPP_BASE_URL}/gram", BLUE)
            if _WEBAPP_BASE_URL else btn(t(lang, "menu_gram"), "menu:gram", BLUE))
    kb.row(nft, gram)

    smm = (_webapp(t(lang, "menu_smm"), f"{_WEBAPP_BASE_URL}/smm", BLUE)
           if _WEBAPP_BASE_URL else btn(t(lang, "menu_smm"), "menu:smm", BLUE))
    uc = (_webapp(t(lang, "menu_uc"), f"{_WEBAPP_BASE_URL}/uc", RED)
          if _WEBAPP_BASE_URL else btn(t(lang, "menu_uc"), "menu:uc", RED))
    kb.row(smm, uc)

    kb.row(btn(t(lang, "menu_wallet"), "menu:wallet", BLUE),
           btn(t(lang, "menu_gift"), "menu:gift", GREEN))
    kb.row(btn(t(lang, "menu_subscribe"), "menu:post_stars", BLUE),
           btn(t(lang, "menu_pricing"), "menu:pricing", BLUE))
    kb.row(btn(t(lang, "menu_stats"), "menu:stats", GREEN),
           btn(t(lang, "menu_help"), "menu:faq", GREEN))
    kb.row(btn("🌐", "lang:change", RED))
    return kb.as_markup()


def back_kb(lang: str, target: str = "menu:main") -> InlineKeyboardMarkup:
    """'◀️ Orqaga' tugmasi - har bir bo'limdan chiqish."""
    kb = InlineKeyboardBuilder()
    kb.row(btn(t(lang, "back"), target, RED))
    return kb.as_markup()


def check_subscribe_kb(lang: str, channel: str = "",
                       channels: list[dict] | None = None) -> InlineKeyboardMarkup:
    """Majburiy obuna: har bir kanalga o'tish + tekshirish."""
    kb = InlineKeyboardBuilder()
    items: list[dict] = []
    if channels is not None:
        items = [c for c in channels if isinstance(c, dict)]
    elif channel:
        items = [{"username": channel}]
    for c in items:
        username = str(c.get("username") or "").lstrip("@").strip()
        chat_id = str(c.get("chat_id") or "").strip()
        title = str(c.get("title") or "").strip() or (f"@{username}" if username else "")
        if username:
            url = f"https://t.me/{username}"
        elif chat_id.startswith("-100"):
            url = f"https://t.me/c/{chat_id[4:]}"
        else:
            continue
        label = t(lang, "sub_join") if len(items) == 1 else f"📢 {title or 'Kanal'}"
        kb.row(InlineKeyboardButton(text=label[:64], url=url, style=BLUE))
    kb.row(btn(t(lang, "check_subscribe"), "check:sub", GREEN))
    return kb.as_markup()


# ---------------------------------------------------------------
# Sotib olish (buy)
# ---------------------------------------------------------------

def buy_packages_kb(
    lang: str,
    packages: dict[int, float],
    webapp_url: str = "",
) -> InlineKeyboardMarkup:
    """Paketlarni tanlash - 2 ta/qator (yonma-yon)."""
    kb = InlineKeyboardBuilder()
    for amount in sorted(packages):
        kb.button(text=t(lang, "buy_package").format(amount=amount),
                  callback_data=f"buy:{amount}", style=RED)
    if webapp_url:
        kb.row(InlineKeyboardButton(
            text="🛍 " + ("Mini-App orqali sotib olish" if lang == "uz" else "Buy via Mini-App"),
            web_app=WebAppInfo(url=f"{webapp_url}/app"),
            style=GREEN,
        ))
    kb.button(text=t(lang, "buy_from_balance"), callback_data="buy:from_balance", style=BLUE)
    kb.button(text=t(lang, "back"), callback_data="menu:main", style=RED)
    kb.adjust(2)  # hamma tugmalar yonma-yon (2 tadan)
    return kb.as_markup()


def _wide_row(kb: InlineKeyboardBuilder, text: str, data: str, color: str = BLUE) -> None:
    kb.row(InlineKeyboardButton(text=text, callback_data=data, style=color))


def payment_method_kb(lang: str, amount: int) -> InlineKeyboardMarkup:
    """To'lov usuli tanlash — karta|API yonma-yon, balans to'liq en."""
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "method_card"), callback_data=f"method:{amount}:card", style=BLUE)
    kb.button(text=t(lang, "method_api"), callback_data=f"method:{amount}:api", style=GREEN)
    kb.button(text=t(lang, "method_balance"), callback_data=f"method:{amount}:balance", style=RED)
    kb.button(text=t(lang, "back"), callback_data="menu:buy", style=RED)
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def paid_button_kb(lang: str, amount: int) -> InlineKeyboardMarkup:
    """'To'lov qildim' tugmasi."""
    kb = InlineKeyboardBuilder()
    kb.row(btn(t(lang, "card_paid"), f"paid:{amount}", GREEN))
    kb.row(btn(t(lang, "back"), "menu:buy", RED))
    return kb.as_markup()


# ---------------------------------------------------------------
# Balans
# ---------------------------------------------------------------

_TOPUP_LABELS = {"uz": "Hisobni to'ldirish", "en": "Top up", "ru": "Пополнить"}
_HISTORY_LABELS = {"uz": "Hisob harakati", "en": "History", "ru": "История"}


def wallet_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(btn("💳 " + _TOPUP_LABELS.get(lang, _TOPUP_LABELS["uz"]), "topup:choose", GREEN))
    kb.row(btn("📜 " + _HISTORY_LABELS.get(lang, _HISTORY_LABELS["uz"]), "wallet:history", BLUE))
    kb.row(btn(t(lang, "back"), "menu:main", RED))
    return kb.as_markup()


TOPUP_PRESETS = (10_000, 20_000, 50_000, 100_000, 200_000, 500_000)


def _sp(value: float) -> str:
    """100000 -> '100 000'"""
    return f"{value:,.0f}".replace(",", " ")


def topup_kb(lang: str) -> InlineKeyboardMarkup:
    """So'mda hisob to'ldirish usullari."""
    kb = InlineKeyboardBuilder()
    if _WEBAPP_BASE_URL:
        kb.row(InlineKeyboardButton(
            text=t(lang, "topup_btn_app"),
            web_app=WebAppInfo(url=f"{_WEBAPP_BASE_URL}/app?tab=topup"),
            style=GREEN,
        ))
    kb.row(btn(t(lang, "topup_btn_card"), "topup:card", GREEN if not _WEBAPP_BASE_URL else BLUE))
    kb.row(btn(t(lang, "topup_btn_api"), "topup:auto", BLUE))
    kb.row(btn(t(lang, "back"), "menu:wallet", RED))
    return kb.as_markup()


def topup_amounts_kb(lang: str, lo: int = 5000, hi: int = 10_000_000) -> InlineKeyboardMarkup:
    """Tayyor summalar (2 tadan) + boshqa summa."""
    kb = InlineKeyboardBuilder()
    for v in TOPUP_PRESETS:
        if lo <= v <= hi:
            kb.button(text=f"{_sp(v)} so'm" if lang == "uz" else f"{_sp(v)} UZS" if lang == "en"
                      else f"{_sp(v)} сум", callback_data=f"topup:amt:{v}", style=BLUE)
    kb.adjust(2)
    kb.row(btn(t(lang, "topup_btn_other"), "topup:other", GREEN))
    kb.row(btn(t(lang, "back"), "topup:choose", RED))
    return kb.as_markup()


def topup_pay_kb(lang: str, auto: bool = False, order_id: int = 0) -> InlineKeyboardMarkup:
    """Rekvizitlar ostidagi tugmalar.

    auto=True: noyob summa bo'yicha avto-to'lov — tranzaksiya ID so'ralmaydi,
    faqat holatni tekshirish tugmasi ko'rsatiladi.
    """
    kb = InlineKeyboardBuilder()
    if auto and order_id:
        kb.row(btn(t(lang, "topup_btn_check"), f"topup:check:{order_id}", GREEN))
    else:
        kb.row(btn(t(lang, "topup_btn_paid"), "topup:paid", GREEN))
    kb.row(btn(t(lang, "topup_btn_cancel"), "topup:cancel", RED))
    return kb.as_markup()


def topup_cancel_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(btn(t(lang, "topup_btn_cancel"), "topup:cancel", RED))
    return kb.as_markup()


def topup_result_kb(lang: str, ok: bool) -> InlineKeyboardMarkup:
    """To'lov natijasidan keyingi tugmalar."""
    kb = InlineKeyboardBuilder()
    if ok:
        if _WEBAPP_BASE_URL:
            kb.row(InlineKeyboardButton(
                text=t(lang, "topup_btn_buy"), web_app=WebAppInfo(url=f"{_WEBAPP_BASE_URL}/app"),
                style=GREEN))
        else:
            kb.row(btn(t(lang, "topup_btn_buy"), "menu:buy", GREEN))
        kb.row(btn(t(lang, "topup_btn_wallet"), "menu:wallet", BLUE))
    else:
        kb.row(btn(t(lang, "topup_btn_retry"), "topup:card", GREEN))
        kb.row(btn(t(lang, "topup_btn_wallet"), "menu:wallet", BLUE))
    kb.row(btn(t(lang, "back"), "menu:main", RED))
    return kb.as_markup()


# ---------------------------------------------------------------
# Gift
# ---------------------------------------------------------------

def gift_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=t(lang, "gift_buy"), callback_data="gift:buy", style=GREEN)
    kb.button(text=t(lang, "gift_send"), callback_data="gift:send", style=BLUE)
    kb.button(text=t(lang, "back"), callback_data="menu:main", style=RED)
    kb.adjust(2, 1)  # buy va send yonma-yon, orqaga to'liq en
    return kb.as_markup()


def gift_catalog_kb(lang: str, gifts: list[dict]) -> InlineKeyboardMarkup:
    """Gift katalogi: admin qo'shgan giftlar (nomi + narxi)."""
    kb = InlineKeyboardBuilder()
    for g in gifts:
        kb.button(
            text=f"🎁 {g['name']} — {float(g['price']):,.0f} so'm",
            callback_data=f"giftbuy:{g['id']}",
            style=GREEN,
        )
    kb.button(text=t(lang, "back"), callback_data="menu:gift", style=RED)
    kb.adjust(1)
    return kb.as_markup()


def gift_pack_kb(lang: str, packages: dict[int, float]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for amount in sorted(packages):
        kb.button(text="🎁 " + t(lang, "buy_package").format(amount=amount),
                  callback_data=f"giftpack:{amount}", style=GREEN)
    kb.button(text=t(lang, "back"), callback_data="menu:gift", style=RED)
    kb.adjust(2, 1)
    return kb.as_markup()


# ---------------------------------------------------------------
# Postga stars
# ---------------------------------------------------------------

def post_stars_packages_kb(lang: str, packages: dict[int, float]) -> InlineKeyboardMarkup:
    """Postga stars: qancha stars kerakligini tanlash (2 ta/qator)."""
    kb = InlineKeyboardBuilder()
    for amount in sorted(packages):
        kb.button(
            text=t(lang, "buy_package").format(amount=amount),
            callback_data=f"postpkg:{amount}",
            style=BLUE,
        )
    kb.button(text=t(lang, "post_custom_amount"), callback_data="postpkg:custom", style=GREEN)
    kb.button(text=t(lang, "back"), callback_data="menu:main", style=RED)
    kb.adjust(2, 1)
    return kb.as_markup()


def post_stars_confirm_kb(lang: str) -> InlineKeyboardMarkup:
    """Xulosa ko'rsatilgach: ✅ Tasdiqlash / ❌ Bekor qilish."""
    kb = InlineKeyboardBuilder()
    kb.row(btn(t(lang, "post_confirm"), "post:confirm", GREEN))
    kb.row(btn(t(lang, "post_cancel"), "post:cancel", RED))
    return kb.as_markup()


# ---------------------------------------------------------------
# Admin
# ---------------------------------------------------------------

def admin_menu_kb(lang: str, bot_active: bool) -> InlineKeyboardMarkup:
    """Admin menyusi: tugmalar 2 tadan yonma-yon (joylashuv ixcham)."""
    kb = InlineKeyboardBuilder()
    buttons: list[InlineKeyboardButton] = []
    if _WEBAPP_BASE_URL:
        buttons.append(InlineKeyboardButton(
            text="🛠 " + ("Admin mini-app" if lang != "ru" else "Админ мини-app"),
            web_app=WebAppInfo(url=f"{_WEBAPP_BASE_URL}/admin"), style=GREEN))
    buttons += [
        btn(t(lang, "admin_orders"), "admin:orders", BLUE),
        btn(t(lang, "admin_users"), "admin:users", BLUE),
        btn(t(lang, "admin_stats"), "admin:stats", GREEN),
        btn(t(lang, "admin_settings"), "admin:settings", BLUE),
        btn("👥 " + ("Admin boshqarish" if lang == "uz" else "Manage admins"),
            "admin:admins", BLUE),
        btn(t(lang, "admin_accounts"), "admin:accounts", GREEN),
        btn(t(lang, "admin_gifts"), "admin:gifts", RED),
        btn(t(lang, "admin_nft"), "admin:nfts", GREEN),
        btn(t(lang, "admin_uc"), "admin:uc", RED),
        btn(t(lang, "admin_gram"), "admin:gram", BLUE),
        btn(t(lang, "admin_broadcast"), "admin:broadcast", BLUE),
        btn(t(lang, "admin_faq"), "admin:faq", BLUE),
        btn(t(lang, "admin_toggle"), "admin:toggle", RED),
    ]
    for i in range(0, len(buttons), 2):
        kb.row(*buttons[i:i + 2])
    kb.row(btn(t(lang, "back"), "menu:main", RED))
    return kb.as_markup()


def admin_manage_kb(lang: str) -> InlineKeyboardMarkup:
    """Admin boshqarish: qo'shish / ro'yxat / o'chirish."""
    def _l(uz: str, en: str) -> str:
        return uz if lang == "uz" else en
    kb = InlineKeyboardBuilder()
    kb.row(btn("➕ " + _l("Admin qo'shish", "Add admin"), "admin:admin_add", GREEN),
           btn("📄 " + _l("Adminlar ro'yxati", "Admin list"), "admin:admin_list", BLUE))
    kb.row(btn("➖ " + _l("Admin o'chirish", "Remove admin"), "admin:admin_del", RED),
           btn(t(lang, "back"), "admin:main", RED))
    return kb.as_markup()


def admin_settings_kb(lang: str) -> InlineKeyboardMarkup:
    def _l(uz: str, en: str) -> str:
        return uz if lang == "uz" else en
    kb = InlineKeyboardBuilder()
    kb.row(btn("📷 " + _l("Rasm o'rnatish", "Set image"), "admin:set_pic", GREEN),
           btn("💎 " + _l("Stars 1⭐ narxi", "Stars 1⭐ price"), "admin:set_star_price", GREEN))
    kb.row(btn("🎁 " + _l("Gift 1⭐ narxi", "Gift 1⭐ price"), "admin:set_gift_price", GREEN),
           btn("📝 " + _l("Post 1⭐ narxi", "Post 1⭐ price"), "admin:set_post_price", GREEN))
    kb.row(btn("📝 " + _l("Post minimal ⭐", "Post minimum ⭐"), "admin:set_post_min_stars", GREEN),
           btn("💵 " + _l("Narxlar", "Prices"), "admin:set_prices", BLUE))
    kb.row(btn("💳 " + _l("Karta", "Card"), "admin:set_card", BLUE),
           btn("📢 " + _l("Majburiy kanal", "Required channel"), "admin:set_channel", BLUE))
    kb.row(btn("🛒 " + _l("To'lovlar kanali", "Payments channel"), "admin:set_pay_channel", BLUE),
           btn("🗑 " + _l("Kanalni o'chirish", "Remove channel"), "admin:clear_pay_channel", RED))
    kb.row(btn("🤖 " + _l("Stars API o'rnatish", "Set Stars API"), "admin:set_api", GREEN),
           btn("🗑 " + _l("Stars API o'chirish", "Remove Stars API"), "admin:clear_api", RED))
    kb.row(btn(t(lang, "back"), "admin:main", RED))
    return kb.as_markup()


def admin_orders_kb(lang: str, order_id: int) -> InlineKeyboardMarkup:
    """Buyurtmani qabul qilish / rad etish."""
    kb = InlineKeyboardBuilder()
    kb.row(btn(t(lang, "approve_button"), f"order:approve:{order_id}", GREEN),
           btn(t(lang, "reject_button"), f"order:reject:{order_id}", RED))
    kb.row(btn(t(lang, "back"), "admin:orders", RED))
    return kb.as_markup()


def admin_gift_kb(lang: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(btn("➕ " + ("Gift qo'shish" if lang == "uz" else "Add gift"), "admin:gift_add", GREEN),
           btn("📄 " + ("Ro'yxat" if lang == "uz" else "List"), "admin:gift_list", BLUE))
    kb.row(btn("❌ " + ("O'chirish" if lang == "uz" else "Remove"), "admin:gift_del", RED),
           btn("➖ " + ("Balansdan ayirish" if lang == "uz" else "Subtract balance"), "admin:gift_sub", RED))
    kb.row(btn(t(lang, "back"), "admin:main", RED))
    return kb.as_markup()


def admin_nft_kb(lang: str) -> InlineKeyboardMarkup:
    """Admin: NFT boshqarish (URL + narx bilan qo'shish)."""
    def _l(uz: str, en: str) -> str:
        return uz if lang == "uz" else en
    kb = InlineKeyboardBuilder()
    kb.row(btn("➕ " + _l("NFT qo'shish (URL)", "Add NFT (URL)"), "admin:nft_add", GREEN),
           btn("📄 " + _l("Ro'yxat", "List"), "admin:nft_list", BLUE))
    kb.row(btn("💲 " + _l("Narxini o'zgartirish", "Change price"), "admin:nft_price", BLUE),
           btn("❌ " + _l("O'chirish", "Remove"), "admin:nft_del", RED))
    kb.row(btn(t(lang, "back"), "admin:main", RED))
    return kb.as_markup()


def nft_open_kb(lang: str) -> InlineKeyboardMarkup:
    """Foydalanuvchiga: NFT mini-appini ochish tugmasi."""
    kb = InlineKeyboardBuilder()
    if _WEBAPP_BASE_URL:
        kb.row(InlineKeyboardButton(
            text=t(lang, "menu_nft"), web_app=WebAppInfo(url=f"{_WEBAPP_BASE_URL}/nft"),
            style=GREEN))
    kb.row(btn(t(lang, "back"), "menu:main", RED))
    return kb.as_markup()


def uc_open_kb(lang: str) -> InlineKeyboardMarkup:
    """Foydalanuvchiga: UC mini-appini ochish tugmasi."""
    kb = InlineKeyboardBuilder()
    if _WEBAPP_BASE_URL:
        kb.row(InlineKeyboardButton(
            text=t(lang, "menu_uc"), web_app=WebAppInfo(url=f"{_WEBAPP_BASE_URL}/uc"),
            style=RED))
    kb.row(btn(t(lang, "back"), "menu:main", RED))
    return kb.as_markup()


def gram_open_kb(lang: str) -> InlineKeyboardMarkup:
    """Foydalanuvchiga: Gram mini-appini ochish tugmasi."""
    kb = InlineKeyboardBuilder()
    if _WEBAPP_BASE_URL:
        kb.row(InlineKeyboardButton(
            text=t(lang, "menu_gram"), web_app=WebAppInfo(url=f"{_WEBAPP_BASE_URL}/gram"),
            style=BLUE))
    kb.row(btn(t(lang, "back"), "menu:main", RED))
    return kb.as_markup()


def admin_accounts_kb(lang: str) -> InlineKeyboardMarkup:
    def _l(uz: str, en: str) -> str:
        return uz if lang == "uz" else en
    kb = InlineKeyboardBuilder()
    kb.row(btn("📲 " + _l("Login orqali ulash", "Connect via login"), "admin:acct_login", GREEN),
           btn("➕ " + _l("Session string", "Session string"), "admin:acct_add", BLUE))
    kb.row(btn("🔌 " + _l("Test ulanish", "Test connection"), "admin:acct_test", BLUE),
           btn("📄 " + _l("Ro'yxat", "List"), "admin:acct_list", BLUE))
    kb.row(btn("❌ " + _l("Akkaunt o'chirish", "Remove account"), "admin:acct_del", RED),
           btn(t(lang, "back"), "admin:main", RED))
    return kb.as_markup()