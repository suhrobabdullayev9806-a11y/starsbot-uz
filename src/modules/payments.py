# ===================================================================
# modules/payments.py - TO'LOVLAR MODULI
# To'lov usullari: karta (ruchka), online API, Telegram Stars (XTR)
# va ichki balans. Har bir to'lov buyurtma (order) bilan bog'lanadi.
# ===================================================================

from __future__ import annotations

from aiogram import Bot

from src.api_client import StarsApiClient
from src.modules.orders import OrdersModule
from src.modules.users import UsersModule
from src.schemas import PaymentIntent, PaymentResult


class PaymentsModule:
    """To'lov jarayonlarini boshqaradi."""

    def __init__(
        self,
        orders: OrdersModule,
        users: UsersModule,
        api: StarsApiClient,
    ):
        self.orders = orders
        self.users = users
        self.api = api

    async def create_intent(
        self,
        user_id: int,
        order_type: str,
        amount: float,
        method: str,
        price: float = 0.0,
        note: str = "",
    ) -> int:
        """To'lov intent (buyurtma) yaratadi."""
        return await self.orders.create(
            user_id=user_id,
            order_type=order_type,
            stars_amount=amount,
            payment_method=method,
            price_amount=price,
            note=note,
        )

    async def pay_from_balance(self, order_id: int, user_id: int, stars_amount: float, price: float = 0.0) -> PaymentResult:
        """
        So'm hisobidan (balance_sum) stars sotib olish.
        - Hisob yetarli bo'lsa: narx (so'm) ayirib olinadi, stars qo'shiladi.
        - Yetarli bo'lmasa xato qaytariladi.
        """
        price = round(float(price), 2)
        bal = await self.users.sub_sum(user_id, price, f"buy balance order#{order_id}", order_id)
        if bal < 0:
            await self.orders.update_status(order_id, "rejected", "insufficient balance")
            return PaymentResult(
                ok=False, error="insufficient",
                balance=await self.users.balance_sum(user_id),
            )
        await self.orders.update_status(order_id, "approved", "paid from balance")
        await self.orders.add_delivered(order_id, stars_amount)
        new_bal = await self.users.add_balance(
            user_id, stars_amount, f"buy deliver order#{order_id}", order_id
        )
        await self.orders.update_status(order_id, "done", "delivered")
        return PaymentResult(ok=True, balance=new_bal, order_id=order_id)

    async def demand(self, user_id: int, stars_amount: float, price: float, username: str = "") -> PaymentResult:
        """
        Mini-App buy: balansdan pul yechadi, buyurtma yaratadi, API orqali
        bajaradi (API sozlangan bo'lsa), stars hisobga yoziladi.
        (PayedFromBalance + API submit yagona oqimida.)
        Qaytaradi: PaymentResult(order_id, balance, error)
        """
        price = round(float(price), 2)
        order_id = await self.orders.create(
            user_id=user_id,
            order_type="buy",
            stars_amount=float(stars_amount),
            payment_method="api",
            price_amount=price,
            note=f"mini-app @{username.lstrip('@')}" if username else "mini-app",
        )
        bal = await self.users.sub_sum(
            user_id, price, f"buy mini order#{order_id}", order_id
        )
        if bal < 0:
            await self.orders.update_status(order_id, "rejected", "insufficient balance")
            return PaymentResult(
                ok=False, error="insufficient", order_id=order_id,
                balance=await self.users.balance_sum(user_id),
            )
        # API chaqirish (sozlangan bo'lsa) — real stars bajariladi
        api_error = ""
        if await self.api.enabled():
            try:
                req_ok = await self.api.purchase(
                    amount=int(stars_amount), user_id=user_id, order_id=order_id,
                    username=username,
                )
                if not req_ok:
                    api_error = "api_failed"
            except Exception as exc:  # noqa: BLE001
                api_error = f"api_error:{exc}"
        # Stars hisobga yozish (buyurtma usuli api, lekin ichki shartli)
        await self.orders.add_delivered(order_id, stars_amount)
        await self.users.add_balance(
            user_id, stars_amount, f"buy mini deliver order#{order_id}", order_id
        )
        note = "delivered" + (f"; {api_error}" if api_error else "")
        await self.orders.update_status(order_id, "done", note)
        return PaymentResult(
            ok=True, order_id=order_id,
            balance=await self.users.balance(user_id),
        )

    async def _credit(self, order: dict) -> float:
        """Buyurtma turiga qarab hisobga yozadi:
        - 'topup'  -> so'm hisobiga (balance_sum) narx qo'shiladi
        - boshqasi -> stars balansiga (balance_stars) stars qo'shiladi
        """
        user_id = order["user_id"]
        order_id = order["id"]
        if order["type"] == "topup":
            return await self.users.add_sum(
                user_id, float(order["price_amount"]),
                f"topup deliver order#{order_id}", order_id,
            )
        await self.users.add_balance(
            user_id, float(order["stars_amount"]),
            f"{order['type']} deliver order#{order_id}", order_id,
        )
        return await self.users.balance(user_id)

    async def submit_card_payment(self, order_id: int, user_id: int, proof_text: str) -> PaymentResult:
        """
        Karta orqali to'lov: buyurtma admin tasdig'iga yuboriladi.
        Tasdiqlangach modul funksiyasi orqali stars yetkaziladi.
        """
        await self.orders.update_status(order_id, "pending", proof_text[:500])
        return PaymentResult(ok=True, order_id=order_id, pending=True)

    async def submit_api_payment(self, order_id: int, user_id: int, amount: float) -> PaymentResult:
        """
        Online API (@Apilarimbot) orqali to'lov.
        API chaqiriladi; natija bo'yicha buyurtma yakunlanadi.
        """
        await self.orders.update_status(order_id, "processing", "api request")
        try:
            req_ok = await self.api.purchase(
                amount=int(amount), user_id=user_id, order_id=order_id
            )
        except Exception as exc:  # noqa: BLE001
            req_ok = False
        if req_ok:
            # API callback yetkazguncha vaqtinchalik kutish holati
            await self.orders.update_status(order_id, "processing", "api sent")
            return PaymentResult(ok=True, order_id=order_id, pending=True)
        await self.orders.update_status(order_id, "rejected", "api failed")
        return PaymentResult(ok=False, error="api_failed", order_id=order_id)

    async def complete_successful(self, order_id: int, user_id: int, amount: float) -> float:
        """API muvaffaqiyatli yakunlanganda hisobga yozish (topup -> so'm, buy -> stars)."""
        order = await self.orders.get(order_id) or {}
        if order.get("type") == "topup":
            await self.orders.update_status(order_id, "done", "api topup delivered")
            return await self.users.add_sum(
                user_id, float(order.get("price_amount", 0)),
                f"topup api deliver order#{order_id}", order_id,
            )
        await self.orders.update_status(order_id, "done", "api delivered")
        await self.orders.add_delivered(order_id, amount)
        return await self.users.add_balance(
            user_id, amount, f"api deliver order#{order_id}", order_id
        )

    async def approve_card_order(self, order_id: int, user_id: int, amount: float) -> float:
        """Admin karta buyurtmasini tasdiqlaganda hisobga yozish (topup -> so'm, buy -> stars)."""
        await self.orders.update_status(order_id, "approved", "admin approved")
        order = await self.orders.get(order_id) or {}
        if order.get("type") == "topup":
            return await self.users.add_sum(
                user_id, float(order.get("price_amount", 0)),
                f"topup deliver order#{order_id}", order_id,
            )
        await self.orders.add_delivered(order_id, amount)
        return await self.users.add_balance(
            user_id, amount, f"card deliver order#{order_id}", order_id
        )