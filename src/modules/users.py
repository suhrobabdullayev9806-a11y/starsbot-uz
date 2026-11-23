# ===================================================================
# modules/users.py - FOYDALANUVCHILAR MODULI
# Foydalanuvchilarni yaratish, yangilash, balans boshqaruvi.
# ===================================================================

from __future__ import annotations

from src.database import Database, now_iso


class UsersModule:
    """Foydalanuvchilar bilan ishlash (register, update, balance)."""

    def __init__(self, db: Database):
        self.db = db

    async def get(self, user_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))

    async def get_or_create(
        self,
        user_id: int,
        username: str = "",
        first_name: str = "",
        lang: str = "uz",
    ) -> tuple[dict, bool]:
        """Foydalanuvchini topadi yoki yangi yaratadi. (user, created) qaytaradi."""
        user = await self.get(user_id)
        if user:
            # Username/o'zgarishlarni yangilash
            changed = False
            if username and user.get("username") != username:
                user["username"] = username
                changed = True
            if first_name and user.get("first_name") != first_name:
                user["first_name"] = first_name
                changed = True
            if changed:
                await self.db.execute(
                    "UPDATE users SET username = ?, first_name = ? WHERE id = ?",
                    (user["username"], user["first_name"], user_id),
                )
            return user, False

        await self.db.execute(
            "INSERT OR IGNORE INTO users(id, username, first_name, language, created_at) "
            "VALUES(?, ?, ?, ?, ?)",
            (user_id, username[:32], first_name[:64], lang, now_iso()),
        )
        return await self.get(user_id) or {}, True

    async def set_language(self, user_id: int, lang: str) -> None:
        """Foydalanuvchi tilini o'rnatadi."""
        await self.db.execute("UPDATE users SET language = ? WHERE id = ?", (lang, user_id))

    async def set_subscribed(self, user_id: int, subscribed: bool = True) -> None:
        """Majburiy obuna holatini yangilaydi."""
        await self.db.execute(
            "UPDATE users SET subscribed = ? WHERE id = ?", (int(subscribed), user_id)
        )

    async def set_vip(self, user_id: int, is_vip: bool) -> None:
        """VIP holatini o'rnatadi."""
        await self.db.execute("UPDATE users SET is_vip = ? WHERE id = ?", (int(is_vip), user_id))

    async def is_vip(self, user_id: int) -> bool:
        user = await self.get(user_id)
        return bool(user and user.get("is_vip"))

    async def balance(self, user_id: int) -> float:
        user = await self.get(user_id)
        return float(user.get("balance_stars", 0)) if user else 0.0

    async def balance_sum(self, user_id: int) -> float:
        """So'mdagi hisob (naqd pul hamyon)."""
        user = await self.get(user_id)
        return float(user.get("balance_sum", 0)) if user else 0.0

    async def add_sum(self, user_id: int, amount: float, reason: str, order_id: int | None = None) -> float:
        """So'm hisobiga pul qo'shadi (hisob to'ldirish)."""
        amount = round(float(amount), 2)
        await self.db.execute(
            "UPDATE users SET balance_sum = balance_sum + ? WHERE id = ?",
            (amount, user_id),
        )
        await self._log_tx(user_id, order_id, amount, "credit", reason)
        return await self.balance_sum(user_id)

    async def sub_sum(self, user_id: int, amount: float, reason: str, order_id: int | None = None) -> float:
        """So'm hisobidan pul ayiradi (yetarli bo'lmasa -1.0 qaytaradi)."""
        amount = round(float(amount), 2)
        current = await self.balance_sum(user_id)
        if current + 1e-9 < amount:
            return -1.0
        await self.db.execute(
            "UPDATE users SET balance_sum = balance_sum - ? WHERE id = ?",
            (amount, user_id),
        )
        await self._log_tx(user_id, order_id, amount, "debit", reason)
        return await self.balance_sum(user_id)

    async def add_balance(self, user_id: int, amount: float, reason: str, order_id: int | None = None) -> float:
        """Balansga stars qo'shadi va transaksiya yozadi."""
        amount = round(float(amount), 2)
        await self.db.execute(
            "UPDATE users SET balance_stars = balance_stars + ? WHERE id = ?",
            (amount, user_id),
        )
        await self._log_tx(user_id, order_id, amount, "credit", reason)
        return await self.balance(user_id)

    async def sub_balance(self, user_id: int, amount: float, reason: str, order_id: int | None = None) -> float:
        """Balansdan stars ayiradi (yetarli bo'lmasa -1.0 qaytaradi)."""
        amount = round(float(amount), 2)
        current = await self.balance(user_id)
        if current + 1e-9 < amount:
            return -1.0
        await self.db.execute(
            "UPDATE users SET balance_stars = balance_stars - ? WHERE id = ?",
            (amount, user_id),
        )
        await self._log_tx(user_id, order_id, amount, "debit", reason)
        return await self.balance(user_id)

    async def _log_tx(
        self, user_id: int, order_id: int | None, amount: float, tx_type: str, reason: str
    ) -> None:
        await self.db.execute(
            "INSERT INTO transactions(user_id, order_id, amount, type, reason, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?)",
            (user_id, order_id, amount, tx_type, reason, now_iso()),
        )

    async def history(self, user_id: int, limit: int = 10) -> list[dict]:
        """Foydalanuvchining oxirgi transaksiyalari."""
        return await self.db.fetch_all(
            "SELECT type, amount, reason, created_at FROM transactions "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )

    async def totals(self, user_id: int) -> dict:
        """Sotilgan / sotib olingan / gift summasi."""
        row = await self.db.fetch_one(
            "SELECT "
            "  COALESCE(SUM(CASE WHEN type='credit' AND reason LIKE '%buy%' THEN amount END), 0) AS bought, "
            "  COALESCE(SUM(CASE WHEN type='debit'  AND reason LIKE '%buy%' THEN amount END), 0) AS sold, "
            "  COALESCE(SUM(CASE WHEN reason LIKE '%gift%' AND type='credit' THEN amount END), 0) AS gifted "
            "FROM transactions WHERE user_id = ?",
            (user_id,),
        )
        return row or {"bought": 0, "sold": 0, "gifted": 0}

    async def count(self) -> int:
        row = await self.db.fetch_one("SELECT COUNT(*) AS c FROM users")
        return int((row or {}).get("c", 0))
    async def search(self, q: str = "", limit: int = 30) -> list[dict]:
        """Admin mini-app: foydalanuvchi qidirish (ID, @username yoki ism)."""
        q = (q or "").strip().lstrip("@")
        limit = max(1, min(int(limit), 100))
        if not q:
            return await self.db.fetch_all(
                "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,))
        like = f"%{q}%"
        return await self.db.fetch_all(
            "SELECT * FROM users WHERE CAST(id AS TEXT) = ? OR username LIKE ? "
            "OR first_name LIKE ? ORDER BY created_at DESC LIMIT ?",
            (q, like, like, limit))
