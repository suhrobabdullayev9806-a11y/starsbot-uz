# ===================================================================
# models.py - Ma'lumotlar modellari (pydantic)
# Kiruvchi ma'lumotlarni tekshirish (data validation) bu yerda amalga
# oshiriladi. SQLite'dan kelgan qatorlar ham shu modellarga o'raladi.
# ===================================================================

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Lang(str, Enum):
    """Qo'llab-quvvatlanadigan tillar."""

    UZ = "uz"
    EN = "en"
    RU = "ru"


class OrderType(str, Enum):
    """Buyurtma turlari."""

    BUY = "buy"                # Stars sotib olish
    GIFT = "gift"              # Gift sotib olish
    POST_STARS = "post_stars"  # Postga stars olish
    TOPUP = "topup"            # Hisobni so'mda to'ldirish
    NFT = "nft"                # NFT sotib olish (mini-app)


class OrderStatus(str, Enum):
    """Buyurtma statuslari."""

    PENDING = "pending"        # Kutmoqda (admin tasdig'i / API)
    PROCESSING = "processing"  # API ishlamoqda
    APPROVED = "approved"      # Tasdiqlandi
    REJECTED = "rejected"      # Rad etildi
    DONE = "done"              # Yetkazildi
    CANCELED = "canceled"      # Bekor qilindi


class PaymentMethod(str, Enum):
    """To'lov usullari."""

    CARD = "card"          # Karta orqali (ruchka, admin tasdiqlaydi)
    API = "api"            # Online API to'lov (XTR / sandiq)
    BALANCE = "balance"    # Ichki balansdan


class UserModel(BaseModel):
    """Foydalanuvchi yozuvi."""

    id: int
    username: str = ""
    first_name: str = ""
    language: Lang = Lang.UZ
    balance_stars: float = Field(default=0, ge=0)
    balance_sum: float = Field(default=0, ge=0)
    is_vip: bool = False
    subscribed: bool = False
    created_at: datetime | None = None

    @field_validator("username")
    @classmethod
    def _clean_username(cls, v: str) -> str:
        # Xavfsizlik: username ichida maxsus belgilar bo'lmasin
        return "".join(ch for ch in v if ch.isalnum() or ch in "_")[:32]


class OrderModel(BaseModel):
    """Buyurtma yozuvi."""

    id: int
    user_id: int
    type: OrderType
    stars_amount: float
    total_stars_delivered: float = 0
    price_amount: float = 0
    payment_method: PaymentMethod = PaymentMethod.CARD
    status: OrderStatus = OrderStatus.PENDING
    api_ref: str = ""
    note: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TransactionModel(BaseModel):
    """Hisob harakati (transaksiya)."""

    id: int
    user_id: int
    order_id: int | None = None
    amount: float
    type: str  # credit | debit
    reason: str
    created_at: datetime | None = None


class AccountModel(BaseModel):
    """Ulangan akkaunt (gift yuborish uchun)."""

    id: int
    title: str
    session_data: str = ""
    status: str = "active"  # active | inactive
    created_at: datetime | None = None


class PurchaseRequest(BaseModel):
    """API (@Apilarimbot) ga yuboriladigan so'rov."""

    amount: int = Field(ge=1)
    user_id: int
    order_id: int
    reference: str

    @field_validator("amount")
    @classmethod
    def _amount_valid(cls, v: int) -> int:
        if v < 1 or v > 10000:
            raise ValueError("amount 1..10000 oralig'ida bo'lishi kerak")
        return v


class OrderCallback(BaseModel):
    """API dan qaytgan buyurtma holati (webhook)."""

    order_id: int
    status: OrderStatus
    reference: str = ""
    note: str = ""

    @field_validator("status")
    @classmethod
    def _status_valid(cls, v: OrderStatus) -> OrderStatus:
        allowed = {OrderStatus.DONE, OrderStatus.REJECTED, OrderStatus.PROCESSING}
        if v not in allowed:
            raise ValueError(f"Noto'g'ri status: {v}")
        return v