# ===================================================================
# modules/gifts.py - GIFT MODULI
# Giftlar katalogi (admin nomi, narxi, soni bilan qo'shadi).
# Gift sotib olish so'mlik hisobdan to'lanadi va akkaunt (usersession)
# orqali oluvchiga avtomatik yetkaziladi.
# ===================================================================

from __future__ import annotations

from src.database import Database, now_iso
from src.modules.accounts import AccountsModule
from src.modules.orders import OrdersModule
from src.modules.users import UsersModule
from src.schemas import PaymentResult


class GiftsModule:
    """Giftlar katalogi va sotib olish."""

    def __init__(
        self,
        db: Database,
        orders: OrdersModule,
        users: UsersModule,
        accounts: AccountsModule,
    ):
        self.db = db
        self.orders = orders
        self.users = users
        self.accounts = accounts

    # ---------- Katalog CRUD ----------

    async def list_all(self) -> list[dict]:
        """Barcha giftlar (o'chirilganlari ham)."""
        return await self.db.fetch_all("SELECT * FROM gifts ORDER BY id DESC")

    async def list_active(self) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT * FROM gifts WHERE active = 1 ORDER BY id"
        )

    async def get(self, gift_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM gifts WHERE id = ?", (gift_id,))

    async def add(self, name: str, price: float, stars: float) -> int:
        """Yangi gift qo'shadi: nomi, narxi (so'm), stars soni."""
        return await self.db.execute(
            "INSERT INTO gifts(name, price, stars, active, created_at) "
            "VALUES(?, ?, ?, 1, ?)",
            (name[:200], round(float(price), 2), float(stars), now_iso()),
        )

    async def remove(self, gift_id: int) -> None:
        await self.db.execute("UPDATE gifts SET active = 0 WHERE id = ?", (gift_id,))

    # ---------- Sotib olish ----------

    async def purchase_gift(
        self, user_id: int, gift_id: int, recipient: str, kind: str = "phone"
    ) -> PaymentResult:
        """
        Gift sotib olish (so'mlik balansdan):
        1) Katalogdagi gift olinadi (nomi, narxi, stars)
        2) So'mlik balansdan price ayiriladi (yetarli bo'lmasa xato)
        3) Ulangan akkauntning session_data orqali gift yuboriladi
        recipient: "@username" yoki "+998901234567"; kind: username|phone
        """
        gift = await self.get(gift_id)
        if not gift or not gift.get("active"):
            return PaymentResult(ok=False, error="no_gift", order_id=None)
        price = round(float(gift["price"]), 2)
        if price <= 0:
            return PaymentResult(ok=False, error="no_price", order_id=None)
        amount = float(gift["stars"])
        name = gift["name"] or "Gift"
        note = f"{name} -> {recipient} ({kind})"
        order_id = await self.orders.create(
            user_id, "gift", amount, "sum", price_amount=price, note=note
        )

        bal = await self.users.sub_sum(
            user_id, price, f"gift purchase order#{order_id}", order_id
        )
        if bal < 0:
            await self.orders.update_status(order_id, "rejected", "insufficient balance")
            return PaymentResult(
                ok=False, error="insufficient_sum", order_id=order_id
            )

        delivery_ok, reason = await self.accounts.deliver_gift(amount, recipient, kind)
        if not delivery_ok:
            await self.orders.update_status(order_id, "failed", reason)
            # Muvaffaqiyatsiz bo'lsa pulni qaytaramiz
            await self.users.add_sum(
                user_id, price, f"gift refund order#{order_id}", order_id
            )
            if reason == "no_active_account":
                return PaymentResult(
                    ok=False, error="no_account", order_id=order_id
                )
            return PaymentResult(ok=False, error=reason, order_id=order_id)

        await self.orders.update_status(order_id, "done", "gift delivered")
        return PaymentResult(ok=True, balance=bal, order_id=order_id)

    async def apply_admin_gift(self, user_id: int, amount: float, add: bool = True) -> float | None:
        """
        Admin tomonidan balansga stars qo'shish/ayirish (⭐ balans).
        Qo'shilsa: balansga +, ayirilsa: balansdan -.
        Manfiy natijada None qaytaradi (yetarli emas).
        """
        if add:
            return await self.users.add_balance(
                user_id, amount, "admin gift add (+)", None
            )
        return await self.users.sub_balance(user_id, amount, "admin gift remove (-)", None)