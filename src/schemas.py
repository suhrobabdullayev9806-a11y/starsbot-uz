# ===================================================================
# schemas.py - Modullar orasidagi ichki ma'lumot strukturalari
# To'lov natijalari va intenentlari uchun Pydantic modellar.
# ===================================================================

from __future__ import annotations

from pydantic import BaseModel


class PaymentIntent(BaseModel):
    """To'lov intenti: buyurtma yaratish ma'lumotlari."""

    user_id: int
    order_id: int
    amount: float
    method: str
    price: float = 0.0


class PaymentResult(BaseModel):
    """To'lov amaliyoti natijasi."""

    ok: bool
    order_id: int | None = None
    balance: float | None = None
    pending: bool = False
    error: str = ""