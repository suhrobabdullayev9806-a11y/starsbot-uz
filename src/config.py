# ===================================================================
# config.py - Bot konfiguratsiyasi
# .env faylidan (yoki muhit o'zgaruvchilaridan) barcha sozlamalarni
# yuklaydi. Pydantic orqali tiplar va qiymatlar tekshiriladi.
# ===================================================================

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

# .env faylini loyiha ildizidan yuklash
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _int_env(name: str, default: int) -> int:
    try:
        return int((os.getenv(name) or "").strip() or default)
    except ValueError:
        return default


class Settings(BaseModel):
    """Barcha bot sozlamalari bitta joyda to'plangan."""

    # --- Asosiy ---
    bot_token: str = Field(min_length=5)
    admin_ids: list[int]
    super_admin_id: int

    # --- Majburiy obuna kanali ---
    required_channel: str = ""
    required_channel_id: int | None = None

    # --- To'lovlar ---
    payments_provider_token: str = ""
    payment_card: str = ""
    payment_card_holder: str = ""

    # --- Avto-to'lov (karta -> tranzaksiya ID tekshiruvi) ---
    # Bank bildirishnomalarini qabul qilish yo'llari (kamida bittasi kerak):
    #  1) webhook: SMS-forwarder va h.k.  -> POST /api/bank/notify (X-Bank-Secret)
    #  2) Telethon: bank bildirishnoma boti (masalan CardXabar) yozuvlarini o'qish
    bank_webhook_secret: str = ""
    bank_session: str = ""          # alohida Telethon StringSession (gift akkauntidan boshqa!)
    bank_source_chats: list[str] = Field(default_factory=list)
    bank_auto: bool = False         # faqat /bankadd orqali qo'lda kiritilsa ham avto rejim
    topup_min: int = 5000
    topup_max: int = 10_000_000
    topup_verify_timeout: int = 600  # sekund: shundan keyin topilmasa bekor qilinadi

    # --- API (@Apilarimbot) ---
    stars_api_base_url: str = ""
    stars_api_key: str = ""
    api_callback_secret: str = ""

    # --- Ma'lumotlar bazasi ---
    db_path: str = "data/stars.db"

    # --- WebApp ---
    webapp_host: str = "0.0.0.0"
    webapp_port: int = 8080
    # Mini-App/Buy WebApp ochiladigan OMMAVIY https URL (mijozlarga
    # web_app tugmasi orqali beriladi). Masalan: https://bot.example.com
    webapp_base_url: str = ""

    # Dastlabki narxlar (adminga ularni o'zgartirishga ruxsat bor)
    default_prices: dict[int, float] = Field(
        default_factory=lambda: {15: 3.0, 30: 5.0, 50: 8.0, 100: 15.0}
    )
    # Vositachi foizi (baholash/foiz: narxni hisoblashda)
    default_percent: float = 0.0

    def is_super_admin(self, user_id: int) -> bool:
        """Super admin (barcha huquqlar) ekanligini tekshiradi."""
        return user_id == self.super_admin_id

    def is_admin(self, user_id: int) -> bool:
        """Foydalanuvchi adminlar ro'yxatida ekanligini tekshiradi."""
        return user_id in self.admin_ids or self.is_super_admin(user_id)

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, value: object) -> list[int]:
        """ADMIN_IDS='u1,u2' kabi stringni listga aylantiradi."""
        if isinstance(value, str):
            return [int(x.strip()) for x in value.split(",") if x.strip()]
        if isinstance(value, (list, tuple)):
            return [int(x) for x in value]
        return []

    @classmethod
    def from_env(cls) -> "Settings":
        """Muhit o'zgaruvchilaridan Settings obyektini quradi.

        Render uchun:
          - PORT (Render beradi) WEBAPP_PORT dan ustun turadi;
          - WEBAPP_BASE_URL bo'sh bo'lsa RENDER_EXTERNAL_URL ishlatiladi.
        """
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN muhit o'zgaruvchisi belgilanmagan!")
        admin_raw = os.getenv("ADMIN_IDS", "").strip()
        if not admin_raw:
            raise RuntimeError("ADMIN_IDS muhit o'zgaruvchisi bo'sh!")
        try:
            admin_ids = [int(x) for x in admin_raw.split(",") if x.strip()]
        except ValueError as exc:
            raise RuntimeError(
                "ADMIN_IDS noto'g'ri: faqat raqamlar, vergul bilan ajratilgan "
                "bo'lishi kerak (masalan: 123456789,987654321)"
            ) from exc
        if not admin_ids:
            raise RuntimeError("ADMIN_IDS bo'sh!")

        super_raw = os.getenv("SUPER_ADMIN_ID", "").strip()
        try:
            super_admin = int(super_raw) if super_raw else admin_ids[0]
        except ValueError as exc:
            raise RuntimeError("SUPER_ADMIN_ID raqam bo'lishi kerak!") from exc

        channel = os.getenv("REQUIRED_CHANNEL", "").lstrip("@").strip()
        channel_id = os.getenv("REQUIRED_CHANNEL_ID", "").strip()

        port_raw = (os.getenv("PORT") or os.getenv("WEBAPP_PORT") or "8080").strip()
        try:
            port = int(port_raw)
        except ValueError as exc:
            raise RuntimeError(f"PORT/WEBAPP_PORT noto'g'ri: {port_raw!r}") from exc

        base_url = (
            os.getenv("WEBAPP_BASE_URL", "").strip()
            or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        ).rstrip("/")

        try:
            percent = float(os.getenv("DEFAULT_PERCENT", "0") or 0)
        except ValueError:
            percent = 0.0

        return cls(
            bot_token=token,
            admin_ids=admin_ids,
            super_admin_id=super_admin,
            required_channel=channel,
            required_channel_id=int(channel_id) if channel_id else None,
            payments_provider_token=os.getenv("PAYMENTS_PROVIDER_TOKEN", ""),
            payment_card=os.getenv("PAYMENT_CARD", ""),
            payment_card_holder=os.getenv("PAYMENT_CARD_HOLDER", "").strip(),
            bank_webhook_secret=os.getenv("BANK_WEBHOOK_SECRET", "").strip(),
            bank_session=os.getenv("BANK_SESSION", "").strip(),
            bank_source_chats=[
                x.strip().lstrip("@") for x in os.getenv("BANK_SOURCE_CHATS", "").split(",")
                if x.strip()
            ],
            bank_auto=os.getenv("BANK_AUTO", "").strip().lower() in {"1", "true", "yes", "on"},
            topup_min=_int_env("TOPUP_MIN", 5000),
            topup_max=_int_env("TOPUP_MAX", 10_000_000),
            topup_verify_timeout=_int_env("TOPUP_VERIFY_TIMEOUT", 600),
            stars_api_base_url=os.getenv("STARS_API_BASE_URL", ""),
            stars_api_key=os.getenv("STARS_API_KEY", ""),
            api_callback_secret=os.getenv("API_CALLBACK_SECRET", ""),
            db_path=os.getenv("DB_PATH", "data/stars.db").strip() or "data/stars.db",
            webapp_host=os.getenv("WEBAPP_HOST", "0.0.0.0").strip() or "0.0.0.0",
            webapp_port=port,
            webapp_base_url=base_url,
            default_percent=percent,
        )


def load_settings() -> Settings:
    """Yagona Settings instansiyasini qaytaradi (singleton)."""
    if not hasattr(load_settings, "_cache"):
        load_settings._cache = Settings.from_env()
    return load_settings._cache