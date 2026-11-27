# ===================================================================
# modules/gram.py - GRAM (TON) SOTIB OLISH MODULI
# Oqim:
#   1) Foydalanuvchi mini-appda Gram paketini tanlaydi va Gram hamyon
#      manzilini yoki Telegram @username'ini kiritadi
#   2) Narx so'mlik hisobdan yechiladi, 'gram' buyurtmasi yaratiladi
#   3) Adminga to'liq ma'lumot boradi: xaridor profili (@username + id),
#      qabul qiluvchi hamyon/profil, paket va narx
#   4) Admin Gram'ni yuborib «Tasdiqlash» bosadi; «Rad etish» pulni
#      xaridor hisobiga qaytaradi.
# Pul bilan bog'liq o'zgarishlar atomik: buyurtma ikki marta
# tasdiqlanmaydi va ikki marta qaytarilmaydi.
# ===================================================================

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta

from src.database import Database, SettingsRepo, now_iso
from src.modules.orders import OrdersModule
from src.modules.users import UsersModule
from src.schemas import PaymentResult
from src.utils import day_start, month_start, week_start

# Boshlang'ich paketlar. Narx — so'mda, admin panelda o'zgartiriladi.
# 1 Gram ≈ 13 000 so'm (bozor narxi ~12 100 so'm + kichik xizmat haqi).
# Admin istalgan paketni qo'shishi, narxini o'zgartirishi yoki o'chirishi mumkin.
DEFAULT_PACKAGES: list[tuple[float, float]] = [
    (1, 13_000),
    (5, 65_000),
    (10, 130_000),
    (25, 325_000),
    (50, 650_000),
    (100, 1_300_000),
]

# TON manzillari: EQ.../UQ.../kQ.../0Q... (48 belgi) yoki raw 0:hex / -1:hex
_TON_ADDR_RE = re.compile(r"^(?:EQ|UQ|kQ|0Q)[A-Za-z0-9_-]{46}$")
_TON_RAW_RE = re.compile(r"^(?:0|-1):[0-9a-fA-F]{64}$")
_TG_USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


def format_grams(value: object) -> str:
    """Gram miqdorini chiroyli ko'rsatadi: 1, 0.5, 1.25."""
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    if abs(v - round(v)) < 1e-9:
        return f"{int(round(v)):,}".replace(",", " ")
    return f"{v:,.4f}".rstrip("0").rstrip(".").replace(",", " ")


def normalize_wallet(raw: object) -> dict | None:
    """Gram qabul qiluvchisini tekshiradi.

    Qaytaradi: {"wallet": "...", "kind": "address"|"username"} yoki None.
    Qabul qilinadi:
      - TON manzili: EQ.../UQ.../kQ.../0Q... yoki 0:hex / -1:hex
      - Telegram @username (t.me/... ko'rinishida ham)
    """
    s = str(raw or "").strip()
    if not s:
        return None
    low = s.lower()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/", "telegram.me/"):
        if low.startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.strip().lstrip("@").strip()
    if not s:
        return None
    if _TON_RAW_RE.fullmatch(s):
        return {"wallet": s.lower(), "kind": "address"}
    if _TON_ADDR_RE.fullmatch(s):
        return {"wallet": s, "kind": "address"}
    if _TG_USER_RE.fullmatch(s):
        return {"wallet": "@" + s, "kind": "username"}
    return None


class GramModule:
    """Gram paketlari, sotib olish, admin qarori va statistika."""

    def __init__(self, db: Database, orders: OrdersModule, users: UsersModule,
                 settings: SettingsRepo):
        self.db = db
        self.orders = orders
        self.users = users
        self.settings = settings
        self._locks: dict[int, asyncio.Lock] = {}

    # ---------- Boshlang'ich paketlar ----------

    async def ensure_defaults(self) -> None:
        """Birinchi ishga tushishda standart paketlarni qo'shadi (bir marta)."""
        if await self.settings.get("gram_seeded", "") == "1":
            return
        row = await self.db.fetch_one("SELECT COUNT(*) AS c FROM gram_packages")
        if not (row or {}).get("c"):
            for i, (grams, price) in enumerate(DEFAULT_PACKAGES):
                await self.add_package(grams, price, sort=i)
        await self.settings.set("gram_seeded", "1")

    # ---------- Paketlar ----------

    async def get_package(self, package_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM gram_packages WHERE id = ?", (package_id,))

    async def list_active(self) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT * FROM gram_packages WHERE active = 1 AND price > 0 ORDER BY sort, grams")

    async def list_all(self) -> list[dict]:
        return await self.db.fetch_all("SELECT * FROM gram_packages ORDER BY sort, grams")

    async def add_package(self, grams: float, price: float, sort: int | None = None) -> int:
        grams = round(float(grams), 4)
        if grams <= 0 or grams > 1_000_000:
            raise ValueError("bad_grams")
        if float(price) <= 0:
            raise ValueError("bad_price")
        if sort is None:
            row = await self.db.fetch_one("SELECT COALESCE(MAX(sort), -1) + 1 AS s FROM gram_packages")
            sort = int((row or {}).get("s", 0))
        return await self.db.execute(
            "INSERT INTO gram_packages(grams, price, active, sort, created_at) "
            "VALUES(?, ?, 1, ?, ?)",
            (grams, round(float(price), 2), sort, now_iso()))

    async def update_package(self, package_id: int, **fields) -> bool:
        sets, args = [], []
        for k, v in fields.items():
            if v is None or k not in ("grams", "price", "active", "sort"):
                continue
            if k == "price":
                v = round(float(v), 2)
                if v <= 0:
                    raise ValueError("bad_price")
            elif k == "active":
                v = 1 if v else 0
            elif k == "grams":
                v = round(float(v), 4)
                if v <= 0:
                    raise ValueError("bad_grams")
            else:
                v = int(v)
            sets.append(f"{k} = ?")
            args.append(v)
        if not sets:
            return False
        rc = await self.db.execute_rc(
            f"UPDATE gram_packages SET {', '.join(sets)} WHERE id = ?", (*args, package_id))
        return rc > 0

    async def delete_package(self, package_id: int) -> bool:
        """Buyurtma tarixi paketdan mustaqil (nusxa saqlanadi), o'chirish xavfsiz."""
        return await self.db.execute_rc(
            "DELETE FROM gram_packages WHERE id = ?", (package_id,)) > 0

    # ---------- Sotib olish ----------

    def _lock(self, user_id: int) -> asyncio.Lock:
        return self._locks.setdefault(user_id, asyncio.Lock())

    async def purchase(self, user_id: int, package_id: int, wallet: str,
                       username: str = "") -> PaymentResult:
        """Balansdan yechadi va 'gram' buyurtmasini yaratadi.

        Xato kodlari: disabled, no_package, bad_wallet, duplicate,
        insufficient_sum.  Muvaffaqiyatda result.order_id, result.balance.
        """
        cfg = await self.settings.get_gram()
        if not cfg["enabled"]:
            return PaymentResult(ok=False, error="disabled")
        pkg = await self.get_package(package_id)
        if not pkg or not pkg["active"] or float(pkg["price"]) <= 0:
            return PaymentResult(ok=False, error="no_package")
        dest = normalize_wallet(wallet)
        if not dest:
            return PaymentResult(ok=False, error="bad_wallet")

        price = round(float(pkg["price"]), 2)
        grams = round(float(pkg["grams"]), 4)
        user = await self.users.get(user_id) or {}
        buyer = str(user.get("username") or username or "").strip().lstrip("@")
        async with self._lock(user_id):
            # Qo'sh bosishdan himoya: 15 sekund ichida bir xil buyurtma.
            since = (datetime.now() - timedelta(seconds=15)).isoformat(timespec="seconds")
            dup = await self.db.fetch_one(
                "SELECT 1 AS x FROM gram_orders g JOIN orders o ON o.id = g.order_id "
                "WHERE g.user_id = ? AND g.package_id = ? AND lower(g.wallet) = lower(?) "
                "AND o.created_at >= ? AND o.status IN ('pending','processing','done')",
                (user_id, package_id, dest["wallet"], since))
            if dup:
                return PaymentResult(ok=False, error="duplicate")
            if await self.users.balance_sum(user_id) + 1e-9 < price:
                return PaymentResult(ok=False, error="insufficient_sum")

            note = f"{format_grams(grams)} Gram | {dest['wallet']}"
            if buyer:
                note += f" | @{buyer}"
            order_id = await self.orders.create(
                user_id, "gram", 0, "sum", price_amount=price, note=note)
            bal = await self.users.sub_sum(user_id, price, f"gram purchase order#{order_id}", order_id)
            if bal < 0:
                await self.orders.update_status(order_id, "rejected", "insufficient balance")
                return PaymentResult(ok=False, error="insufficient_sum", order_id=order_id)
            await self.db.execute(
                "INSERT INTO gram_orders(order_id, user_id, package_id, grams, price, wallet, "
                " wallet_kind, username, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (order_id, user_id, package_id, grams, price, dest["wallet"],
                 dest["kind"], buyer, now_iso()))
        return PaymentResult(ok=True, order_id=order_id, balance=bal)

    # ---------- Admin qarori ----------

    async def get_order(self, order_id: int) -> dict | None:
        """Buyurtma + Gram tafsiloti (+ xaridor ismi va profili)."""
        return await self.db.fetch_one(
            "SELECT g.*, o.status, o.created_at AS ordered_at, o.updated_at, "
            " us.username AS buyer_username, us.first_name AS buyer_first_name "
            "FROM gram_orders g JOIN orders o ON o.id = g.order_id "
            "LEFT JOIN users us ON us.id = g.user_id WHERE g.order_id = ?", (order_id,))

    async def complete(self, order_id: int) -> bool:
        """Admin Gram'ni yubordi: buyurtma 'done'. Ikkinchi marta ishlamaydi."""
        rc = await self.db.execute_rc(
            "UPDATE orders SET status = 'done', updated_at = ? "
            "WHERE id = ? AND type = 'gram' AND status IN ('pending','processing')",
            (now_iso(), order_id))
        return rc > 0

    async def cancel(self, order_id: int) -> dict | None:
        """Buyurtmani bekor qiladi va pulni qaytaradi (faqat kutilayotgan, bir marta)."""
        order = await self.orders.get(order_id)
        if not order or order["type"] != "gram":
            return None
        rc = await self.db.execute_rc(
            "UPDATE orders SET status = 'rejected', updated_at = ? "
            "WHERE id = ? AND status IN ('pending','processing')",
            (now_iso(), order_id))
        if rc == 0:
            return None
        await self.users.add_sum(order["user_id"], float(order["price_amount"]),
                                 f"gram refund order#{order_id}", order_id)
        return order

    # ---------- Ro'yxatlar ----------

    async def user_history(self, user_id: int, limit: int = 10) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT g.order_id, g.grams, g.price, g.wallet, g.wallet_kind, o.status, "
            " o.created_at FROM gram_orders g JOIN orders o ON o.id = g.order_id "
            "WHERE g.user_id = ? ORDER BY g.order_id DESC LIMIT ?", (user_id, limit))

    async def last_wallet(self, user_id: int) -> str:
        row = await self.db.fetch_one(
            "SELECT wallet FROM gram_orders WHERE user_id = ? ORDER BY order_id DESC LIMIT 1",
            (user_id,))
        return (row or {}).get("wallet", "")

    async def list_orders(self, status: str = "", q: str = "", limit: int = 60) -> list[dict]:
        """Admin ro'yxati. status: 'pending' | 'done' | 'rejected' | ''.
        q: hamyon, @username, xaridor username yoki user ID."""
        where, args = [], []
        if status == "pending":
            where.append("o.status IN ('pending','processing')")
        elif status:
            where.append("o.status = ?")
            args.append(status)
        q = (q or "").strip().lstrip("@")
        if q:
            where.append("(g.wallet LIKE ? OR g.username LIKE ? OR CAST(g.user_id AS TEXT) = ? "
                         "OR us.username LIKE ?)")
            args += [f"%{q}%", f"%{q}%", q, f"%{q}%"]
        sql = (
            "SELECT g.order_id, g.user_id, g.grams, g.price, g.wallet, g.wallet_kind, "
            " g.username, o.status, o.created_at, o.updated_at, "
            " us.username AS buyer_username, us.first_name AS buyer_first_name "
            "FROM gram_orders g JOIN orders o ON o.id = g.order_id "
            "LEFT JOIN users us ON us.id = g.user_id"
            + (" WHERE " + " AND ".join(where) if where else "")
            + " ORDER BY g.order_id DESC LIMIT ?")
        return await self.db.fetch_all(sql, (*args, max(1, min(int(limit), 200))))

    # ---------- Statistika ----------

    async def _range(self, since_iso: str) -> dict:
        row = await self.db.fetch_one(
            "SELECT COUNT(*) AS orders, COALESCE(SUM(g.grams), 0) AS grams, "
            " COALESCE(SUM(g.price), 0) AS revenue, COUNT(DISTINCT g.user_id) AS buyers "
            "FROM gram_orders g JOIN orders o ON o.id = g.order_id "
            "WHERE o.status = 'done' AND o.created_at >= ?", (since_iso,))
        return row or {"orders": 0, "grams": 0, "revenue": 0, "buyers": 0}

    async def stats(self) -> dict:
        """Admin statistikasi: davrlar, kutilayotganlar, top paketlar/xaridorlar, 14 kunlik grafik."""
        now = datetime.now()
        periods = {
            "today": await self._range(day_start(now).isoformat()),
            "week": await self._range(week_start(now).isoformat()),
            "month": await self._range(month_start(now).isoformat()),
            "all": await self._range("0000"),
        }
        pending = await self.db.fetch_one(
            "SELECT COUNT(*) AS c, COALESCE(SUM(g.price), 0) AS s, "
            " COALESCE(SUM(g.grams), 0) AS grams "
            "FROM gram_orders g JOIN orders o ON o.id = g.order_id "
            "WHERE o.status IN ('pending','processing')")
        rejected = await self.db.fetch_one(
            "SELECT COUNT(*) AS c FROM gram_orders g JOIN orders o ON o.id = g.order_id "
            "WHERE o.status = 'rejected'")
        top_packages = await self.db.fetch_all(
            "SELECT g.grams, COUNT(*) AS orders, SUM(g.price) AS revenue "
            "FROM gram_orders g JOIN orders o ON o.id = g.order_id WHERE o.status = 'done' "
            "GROUP BY g.grams ORDER BY orders DESC, g.grams DESC LIMIT 6")
        top_buyers = await self.db.fetch_all(
            "SELECT g.user_id, MAX(us.username) AS username, MAX(us.first_name) AS first_name, "
            " COUNT(*) AS orders, SUM(g.grams) AS grams, SUM(g.price) AS revenue "
            "FROM gram_orders g JOIN orders o ON o.id = g.order_id "
            "LEFT JOIN users us ON us.id = g.user_id WHERE o.status = 'done' "
            "GROUP BY g.user_id ORDER BY revenue DESC LIMIT 5")
        since14 = (day_start(now) - timedelta(days=13)).isoformat()
        rows = await self.db.fetch_all(
            "SELECT substr(o.created_at, 1, 10) AS d, COUNT(*) AS orders, SUM(g.price) AS revenue, "
            " SUM(g.grams) AS grams FROM gram_orders g JOIN orders o ON o.id = g.order_id "
            "WHERE o.status = 'done' AND o.created_at >= ? GROUP BY d", (since14,))
        by_day = {r["d"]: r for r in rows}
        daily = []
        for i in range(13, -1, -1):
            d = (day_start(now) - timedelta(days=i)).date().isoformat()
            r = by_day.get(d, {})
            daily.append({"date": d, "orders": r.get("orders", 0) or 0,
                          "revenue": r.get("revenue", 0) or 0, "grams": r.get("grams", 0) or 0})
        avg = periods["all"]["revenue"] / periods["all"]["orders"] if periods["all"]["orders"] else 0
        return {
            "periods": periods,
            "pending": pending, "rejected": (rejected or {}).get("c", 0),
            "avg_order": round(avg, 2),
            "top_packages": top_packages, "top_buyers": top_buyers, "daily": daily,
        }
