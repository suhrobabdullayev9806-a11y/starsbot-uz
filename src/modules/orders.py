# ===================================================================
# modules/orders.py - BUYURTMALAR MODULI
# Stars sotib olish, gift, post-stars buyurtmalarini yaratish,
# statusini boshqarish va admin tasdiqlash jarayoni.
# ===================================================================

from __future__ import annotations

from src.database import Database, now_iso
from src.models import OrderStatus


class OrdersModule:
    """Buyurtmalar CRUD va holat xodimlari."""

    def __init__(self, db: Database):
        self.db = db

    async def create(
        self,
        user_id: int,
        order_type: str,
        stars_amount: float,
        payment_method: str,
        price_amount: float = 0.0,
        note: str = "",
    ) -> int:
        """Yangi buyurtma yaratadi va uning ID-sini qaytaradi."""
        now = now_iso()
        return await self.db.execute(
            "INSERT INTO orders(user_id, type, stars_amount, price_amount, "
            " payment_method, status, note, created_at, updated_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                order_type,
                stars_amount,
                price_amount,
                payment_method,
                OrderStatus.PENDING.value,
                note[:500],
                now,
                now,
            ),
        )

    async def get(self, order_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM orders WHERE id = ?", (order_id,))

    async def update_status(
        self, order_id: int, status: str, note: str | None = None
    ) -> None:
        """Buyurtma statusini yangilaydi."""
        if note is None:
            await self.db.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE id = ?",
                (status, now_iso(), order_id),
            )
        else:
            await self.db.execute(
                "UPDATE orders SET status = ?, note = ?, updated_at = ? WHERE id = ?",
                (status, note[:500], now_iso(), order_id),
            )

    async def set_api_ref(self, order_id: int, api_ref: str) -> None:
        """API tomonidagi mos referensni saqlaydi."""
        await self.db.execute("UPDATE orders SET api_ref = ? WHERE id = ?", (api_ref, order_id))

    async def add_delivered(self, order_id: int, amount: float) -> None:
        """Yetkazilgan stars summasini qo'shib turaadi."""
        await self.db.execute(
            "UPDATE orders SET total_stars_delivered = total_stars_delivered + ? WHERE id = ?",
            (amount, order_id),
        )

    async def pending(self) -> list[dict]:
        """Admin tasdig'ini kutayotgan buyurtmalar."""
        return await self.db.fetch_all(
            "SELECT * FROM orders WHERE status IN ('pending','processing') "
            "ORDER BY id DESC LIMIT 25"
        )

    async def user_orders(self, user_id: int, limit: int = 10) -> list[dict]:
        """Foydalanuvchining oxirgi buyurtmalari."""
        return await self.db.fetch_all(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )

    async def by_api_ref(self, api_ref: str) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM orders WHERE api_ref = ?", (api_ref,))

    # --- Statistika so'rovlari ---
    async def stats_range(self, since_iso: str) -> dict:
        """Ma'lum muddatdagi sotuvlar statistikasi."""
        row = await self.db.fetch_one(
            "SELECT "
            "  COALESCE(SUM(stars_amount), 0) AS sold_stars, "
            "  COALESCE(SUM(price_amount), 0) AS sold_sum, "
            "  COUNT(*) AS count "
            "FROM orders "
            "WHERE created_at >= ? AND type = 'buy' "
            "  AND status IN ('approved','done')",
            (since_iso,),
        )
        return row or {"sold_stars": 0, "sold_sum": 0, "count": 0}

    async def all_orders(self, limit: int = 50) -> list[dict]:
        return await self.db.fetch_all("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))