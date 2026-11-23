# ===================================================================
# modules/uc.py - PUBG MOBILE UC MODULI
# Oqim:
#   1) Foydalanuvchi mini-appda paket tanlaydi va PUBG ID kiritadi
#   2) Server nickname'ni aniqlaydi (admin sozlagan provayder orqali) va
#      foydalanuvchiga ko'rsatadi — noto'g'ri ID'ga UC ketib qolmasin
#   3) Narx so'mlik balansdan yechiladi, 'uc' buyurtmasi yaratiladi
#   4) Adminga ariza boradi (PUBG ID + nickname + paket). Admin UC'ni o'zi
#      yuboradi va «Tasdiqlash» bosadi; «Rad etish» pulni qaytaradi.
# Pul bilan bog'liq har bir o'tish "UPDATE ... WHERE status IN (...)" bilan
# atomik: bitta buyurtma ikki marta tasdiqlanmaydi va ikki marta qaytarilmaydi.
# ===================================================================

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from src.database import Database, SettingsRepo, now_iso
from src.modules.orders import OrdersModule
from src.modules.users import UsersModule
from src.schemas import PaymentResult
from src.utils import day_start, month_start, week_start

# PUBG Mobile standart UC paketlari. Narxlar BOSHLANG'ICH (1 UC ≈ 230 so'm),
# admin panelda o'zgartiriladi.
DEFAULT_PACKAGES: list[tuple[int, int, float]] = [
    (60, 0, 14_000),
    (325, 0, 75_000),
    (660, 0, 152_000),
    (1800, 0, 414_000),
    (3850, 0, 886_000),
    (8100, 0, 1_863_000),
]

_PUBG_ID_RE = re.compile(r"^\d{5,14}$")
_NICK_FALLBACK_KEYS = ("nickname", "nick", "name", "player_name", "playerName", "username")

# (url, headers) -> (http_status, json yoki None).  Testlarda almashtiriladi.
Fetcher = Callable[[str, dict], Awaitable["tuple[int, object | None]"]]


def normalize_pubg_id(raw: object) -> str | None:
    """Faqat raqamlar (5–14 ta). Bo'shliq/tire olib tashlanadi. Noto'g'ri bo'lsa None."""
    s = re.sub(r"[\s\-_]", "", str(raw or ""))
    return s if _PUBG_ID_RE.match(s) else None


def clean_nickname(raw: object) -> str:
    """Nickname'ni xavfsiz matnga keltiradi (boshqaruv belgilari olinadi, 40 belgigacha)."""
    s = re.sub(r"[\x00-\x1f\x7f]", "", str(raw or "")).strip()
    return s[:40]


def _dig(data: object, path: str) -> object | None:
    """'data.player.nickname' yoki 'items.0.name' yo'li bo'yicha qiymatni oladi."""
    cur = data
    for part in [p for p in path.split(".") if p]:
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
        if cur is None:
            return None
    return cur


def extract_nickname(data: object, path: str = "nickname") -> str | None:
    """Provayder javobidan nickname'ni topadi (avval sozlangan yo'l, so'ng umumiy kalitlar)."""
    val = _dig(data, path) if path else None
    if val is None and isinstance(data, dict):
        for holder in (data, data.get("data") if isinstance(data.get("data"), dict) else {}):
            for k in _NICK_FALLBACK_KEYS:
                if isinstance(holder, dict) and holder.get(k):
                    val = holder[k]
                    break
            if val:
                break
    if isinstance(val, (str, int)) and str(val).strip():
        return clean_nickname(val)
    return None


async def _http_fetch(url: str, headers: dict) -> tuple[int, object | None]:
    import httpx

    async with httpx.AsyncClient(timeout=8, follow_redirects=False) as c:
        r = await c.get(url, headers=headers)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, None


class UcModule:
    """UC paketlari, nickname aniqlash, sotib olish va statistika."""

    CACHE_TTL = 600  # nickname keshi (sekund)

    def __init__(self, db: Database, orders: OrdersModule, users: UsersModule,
                 settings: SettingsRepo, fetcher: Fetcher | None = None):
        self.db = db
        self.orders = orders
        self.users = users
        self.settings = settings
        self._fetch: Fetcher = fetcher or _http_fetch
        self._locks: dict[int, asyncio.Lock] = {}
        self._cache: dict[str, tuple[float, dict]] = {}

    # ---------- Boshlang'ich paketlar ----------

    async def ensure_defaults(self) -> None:
        """Birinchi ishga tushishda standart paketlarni qo'shadi (bir marta)."""
        if await self.settings.get("uc_seeded", "") == "1":
            return
        row = await self.db.fetch_one("SELECT COUNT(*) AS c FROM uc_packages")
        if not (row or {}).get("c"):
            for i, (uc, bonus, price) in enumerate(DEFAULT_PACKAGES):
                await self.add_package(uc, price, bonus, sort=i)
        await self.settings.set("uc_seeded", "1")

    # ---------- Paketlar ----------

    async def get_package(self, package_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM uc_packages WHERE id = ?", (package_id,))

    async def list_active(self) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT * FROM uc_packages WHERE active = 1 AND price > 0 ORDER BY sort, uc")

    async def list_all(self) -> list[dict]:
        return await self.db.fetch_all("SELECT * FROM uc_packages ORDER BY sort, uc")

    async def add_package(self, uc: int, price: float, bonus: int = 0, sort: int | None = None) -> int:
        uc, bonus = int(uc), max(0, int(bonus))
        if uc <= 0 or uc > 1_000_000:
            raise ValueError("bad_uc")
        if float(price) <= 0:
            raise ValueError("bad_price")
        if sort is None:
            row = await self.db.fetch_one("SELECT COALESCE(MAX(sort), -1) + 1 AS s FROM uc_packages")
            sort = int((row or {}).get("s", 0))
        return await self.db.execute(
            "INSERT INTO uc_packages(uc, bonus, price, active, sort, created_at) "
            "VALUES(?, ?, ?, 1, ?, ?)",
            (uc, bonus, round(float(price), 2), sort, now_iso()))

    async def update_package(self, package_id: int, **fields) -> bool:
        sets, args = [], []
        for k, v in fields.items():
            if v is None or k not in ("uc", "bonus", "price", "active", "sort"):
                continue
            if k == "price":
                v = round(float(v), 2)
                if v <= 0:
                    raise ValueError("bad_price")
            elif k == "active":
                v = 1 if v else 0
            else:
                v = int(v)
                if (k == "uc" and v <= 0) or (k in ("bonus",) and v < 0):
                    raise ValueError("bad_uc")
            sets.append(f"{k} = ?")
            args.append(v)
        if not sets:
            return False
        rc = await self.db.execute_rc(
            f"UPDATE uc_packages SET {', '.join(sets)} WHERE id = ?", (*args, package_id))
        return rc > 0

    async def delete_package(self, package_id: int) -> bool:
        """Buyurtma tarixi paketdan mustaqil (nusxa saqlanadi), shuning uchun o'chirish xavfsiz."""
        return await self.db.execute_rc("DELETE FROM uc_packages WHERE id = ?", (package_id,)) > 0

    # ---------- Nickname aniqlash ----------

    async def lookup(self, pubg_id: str) -> dict:
        """PUBG ID bo'yicha nickname.

        Qaytaradi: {"status": "found"|"not_found"|"unavailable", "nickname": str}
          found       — nickname aniqlandi
          not_found   — provayder bunday o'yinchi yo'qligini aytdi (HTTP 404 yoki bo'sh nom)
          unavailable — tekshiruv sozlanmagan yoki provayder javob bermadi
        """
        pid = normalize_pubg_id(pubg_id)
        if not pid:
            return {"status": "not_found", "nickname": "", "reason": "bad_id"}
        cached = self._cache.get(pid)
        if cached and time.monotonic() - cached[0] < self.CACHE_TTL:
            return cached[1]

        cfg = await self.settings.get_uc()
        url = cfg["lookup_url"].strip()
        if not url or "{id}" not in url or not url.lower().startswith(("http://", "https://")):
            return {"status": "unavailable", "nickname": "", "reason": "not_configured"}
        url = url.replace("{id}", pid).replace("{key}", cfg["lookup_key"])
        headers = {"Accept": "application/json", "User-Agent": "uc-bot/1.0"}
        if cfg["lookup_key"]:
            headers["Authorization"] = f"Bearer {cfg['lookup_key']}"
            headers["X-API-Key"] = cfg["lookup_key"]
        try:
            status, data = await self._fetch(url, headers)
        except Exception:  # noqa: BLE001  tarmoq/timeout
            return {"status": "unavailable", "nickname": "", "reason": "network"}

        if status == 404:
            res = {"status": "not_found", "nickname": "", "reason": "provider_404"}
        elif status != 200 or data is None:
            return {"status": "unavailable", "nickname": "", "reason": f"http_{status}"}
        else:
            nick = extract_nickname(data, cfg["lookup_path"])
            if nick:
                res = {"status": "found", "nickname": nick, "reason": ""}
            elif _dig(data, cfg["lookup_path"]) == "":
                res = {"status": "not_found", "nickname": "", "reason": "empty_name"}
            else:
                return {"status": "unavailable", "nickname": "", "reason": "bad_response"}
        if len(self._cache) > 2000:
            self._cache.clear()
        self._cache[pid] = (time.monotonic(), res)
        return res

    # ---------- Sotib olish ----------

    def _lock(self, user_id: int) -> asyncio.Lock:
        return self._locks.setdefault(user_id, asyncio.Lock())

    async def purchase(self, user_id: int, package_id: int, pubg_id: str) -> PaymentResult:
        """Balansdan yechadi va 'uc' buyurtmasini yaratadi.

        Xato kodlari: disabled, no_package, bad_pubg_id, player_not_found, nick_required,
        duplicate, insufficient_sum.  Muvaffaqiyatda result.order_id, result.balance.
        """
        cfg = await self.settings.get_uc()
        if not cfg["enabled"]:
            return PaymentResult(ok=False, error="disabled")
        pkg = await self.get_package(package_id)
        if not pkg or not pkg["active"] or float(pkg["price"]) <= 0:
            return PaymentResult(ok=False, error="no_package")
        pid = normalize_pubg_id(pubg_id)
        if not pid:
            return PaymentResult(ok=False, error="bad_pubg_id")

        info = await self.lookup(pid)
        if info["status"] == "not_found":
            return PaymentResult(ok=False, error="player_not_found")
        if cfg["require_nick"] and info["status"] != "found":
            return PaymentResult(ok=False, error="nick_required")
        nick, verified = (info["nickname"], 1) if info["status"] == "found" else ("", 0)

        price = round(float(pkg["price"]), 2)
        total_uc = int(pkg["uc"]) + int(pkg["bonus"] or 0)
        async with self._lock(user_id):
            # Bir xil buyurtmani tasodifan ikki marta yubormaslik (qo'sh bosish)
            since = (datetime.now() - timedelta(seconds=15)).isoformat(timespec="seconds")
            dup = await self.db.fetch_one(
                "SELECT 1 AS x FROM uc_orders u JOIN orders o ON o.id = u.order_id "
                "WHERE u.user_id = ? AND u.package_id = ? AND u.pubg_id = ? "
                "AND o.created_at >= ? AND o.status IN ('pending','processing','done')",
                (user_id, package_id, pid, since))
            if dup:
                return PaymentResult(ok=False, error="duplicate")
            if await self.users.balance_sum(user_id) + 1e-9 < price:
                return PaymentResult(ok=False, error="insufficient_sum")

            note = f"{total_uc} UC | PUBG ID {pid}" + (f" | {nick}" if nick else "")
            order_id = await self.orders.create(
                user_id, "uc", 0, "sum", price_amount=price, note=note)
            bal = await self.users.sub_sum(user_id, price, f"uc purchase order#{order_id}", order_id)
            if bal < 0:
                await self.orders.update_status(order_id, "rejected", "insufficient balance")
                return PaymentResult(ok=False, error="insufficient_sum", order_id=order_id)
            await self.db.execute(
                "INSERT INTO uc_orders(order_id, user_id, package_id, uc, bonus, price, pubg_id, "
                " nickname, verified, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (order_id, user_id, package_id, int(pkg["uc"]), int(pkg["bonus"] or 0), price,
                 pid, nick, verified, now_iso()))
        return PaymentResult(ok=True, order_id=order_id, balance=bal)

    # ---------- Admin qarori ----------

    async def get_order(self, order_id: int) -> dict | None:
        """Buyurtma + UC tafsiloti (+ xaridor ismi)."""
        return await self.db.fetch_one(
            "SELECT u.*, o.status, o.created_at AS ordered_at, o.updated_at, "
            " us.username, us.first_name "
            "FROM uc_orders u JOIN orders o ON o.id = u.order_id "
            "LEFT JOIN users us ON us.id = u.user_id WHERE u.order_id = ?", (order_id,))

    async def complete(self, order_id: int) -> bool:
        """Admin UC'ni yubordi: buyurtma 'done'. Ikkinchi marta ishlamaydi."""
        rc = await self.db.execute_rc(
            "UPDATE orders SET status = 'done', updated_at = ? "
            "WHERE id = ? AND type = 'uc' AND status IN ('pending','processing')",
            (now_iso(), order_id))
        return rc > 0

    async def cancel(self, order_id: int) -> dict | None:
        """Buyurtmani bekor qiladi va pulni qaytaradi (faqat kutilayotgan, bir marta)."""
        order = await self.orders.get(order_id)
        if not order or order["type"] != "uc":
            return None
        rc = await self.db.execute_rc(
            "UPDATE orders SET status = 'rejected', updated_at = ? "
            "WHERE id = ? AND status IN ('pending','processing')",
            (now_iso(), order_id))
        if rc == 0:
            return None
        await self.users.add_sum(order["user_id"], float(order["price_amount"]),
                                 f"uc refund order#{order_id}", order_id)
        return order

    # ---------- Ro'yxatlar ----------

    async def user_history(self, user_id: int, limit: int = 10) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT u.order_id, u.uc, u.bonus, u.price, u.pubg_id, u.nickname, o.status, "
            " o.created_at FROM uc_orders u JOIN orders o ON o.id = u.order_id "
            "WHERE u.user_id = ? ORDER BY u.order_id DESC LIMIT ?", (user_id, limit))

    async def last_pubg_id(self, user_id: int) -> str:
        row = await self.db.fetch_one(
            "SELECT pubg_id FROM uc_orders WHERE user_id = ? ORDER BY order_id DESC LIMIT 1",
            (user_id,))
        return (row or {}).get("pubg_id", "")

    async def list_orders(self, status: str = "", q: str = "", limit: int = 60) -> list[dict]:
        """Admin ro'yxati. status: 'pending' | 'done' | 'rejected' | ''. q: PUBG ID / nick / user ID."""
        where, args = [], []
        if status == "pending":
            where.append("o.status IN ('pending','processing')")
        elif status:
            where.append("o.status = ?")
            args.append(status)
        q = (q or "").strip().lstrip("@")
        if q:
            where.append("(u.pubg_id LIKE ? OR u.nickname LIKE ? OR CAST(u.user_id AS TEXT) = ? "
                         "OR us.username LIKE ?)")
            args += [f"%{q}%", f"%{q}%", q, f"%{q}%"]
        sql = (
            "SELECT u.order_id, u.user_id, u.uc, u.bonus, u.price, u.pubg_id, u.nickname, "
            " u.verified, o.status, o.created_at, o.updated_at, us.username, us.first_name "
            "FROM uc_orders u JOIN orders o ON o.id = u.order_id "
            "LEFT JOIN users us ON us.id = u.user_id"
            + (" WHERE " + " AND ".join(where) if where else "")
            + " ORDER BY u.order_id DESC LIMIT ?")
        return await self.db.fetch_all(sql, (*args, max(1, min(int(limit), 200))))

    # ---------- Statistika ----------

    async def _range(self, since_iso: str) -> dict:
        row = await self.db.fetch_one(
            "SELECT COUNT(*) AS orders, COALESCE(SUM(u.uc + u.bonus), 0) AS uc, "
            " COALESCE(SUM(u.price), 0) AS revenue, COUNT(DISTINCT u.user_id) AS buyers "
            "FROM uc_orders u JOIN orders o ON o.id = u.order_id "
            "WHERE o.status = 'done' AND o.created_at >= ?", (since_iso,))
        return row or {"orders": 0, "uc": 0, "revenue": 0, "buyers": 0}

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
            "SELECT COUNT(*) AS c, COALESCE(SUM(u.price), 0) AS s, COALESCE(SUM(u.uc + u.bonus), 0) AS uc "
            "FROM uc_orders u JOIN orders o ON o.id = u.order_id "
            "WHERE o.status IN ('pending','processing')")
        rejected = await self.db.fetch_one(
            "SELECT COUNT(*) AS c FROM uc_orders u JOIN orders o ON o.id = u.order_id "
            "WHERE o.status = 'rejected'")
        top_packages = await self.db.fetch_all(
            "SELECT (u.uc + u.bonus) AS uc, COUNT(*) AS orders, SUM(u.price) AS revenue "
            "FROM uc_orders u JOIN orders o ON o.id = u.order_id WHERE o.status = 'done' "
            "GROUP BY (u.uc + u.bonus) ORDER BY orders DESC, uc DESC LIMIT 6")
        top_buyers = await self.db.fetch_all(
            "SELECT u.user_id, MAX(us.username) AS username, MAX(us.first_name) AS first_name, "
            " COUNT(*) AS orders, SUM(u.uc + u.bonus) AS uc, SUM(u.price) AS revenue "
            "FROM uc_orders u JOIN orders o ON o.id = u.order_id "
            "LEFT JOIN users us ON us.id = u.user_id WHERE o.status = 'done' "
            "GROUP BY u.user_id ORDER BY revenue DESC LIMIT 5")
        since14 = (day_start(now) - timedelta(days=13)).isoformat()
        rows = await self.db.fetch_all(
            "SELECT substr(o.created_at, 1, 10) AS d, COUNT(*) AS orders, SUM(u.price) AS revenue, "
            " SUM(u.uc + u.bonus) AS uc FROM uc_orders u JOIN orders o ON o.id = u.order_id "
            "WHERE o.status = 'done' AND o.created_at >= ? GROUP BY d", (since14,))
        by_day = {r["d"]: r for r in rows}
        daily = []
        for i in range(13, -1, -1):
            d = (day_start(now) - timedelta(days=i)).date().isoformat()
            r = by_day.get(d, {})
            daily.append({"date": d, "orders": r.get("orders", 0) or 0,
                          "revenue": r.get("revenue", 0) or 0, "uc": r.get("uc", 0) or 0})
        avg = periods["all"]["revenue"] / periods["all"]["orders"] if periods["all"]["orders"] else 0
        return {
            "periods": periods,
            "pending": pending, "rejected": (rejected or {}).get("c", 0),
            "avg_order": round(avg, 2),
            "top_packages": top_packages, "top_buyers": top_buyers, "daily": daily,
        }
