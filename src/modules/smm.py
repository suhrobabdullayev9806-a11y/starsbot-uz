# ===================================================================
# modules/smm.py - SMM NAKRUTKA MODULI
#   * Xizmatlar katalogi (provayderdan import yoki qo'lda) + narx hisoblash
#   * Buyurtma: balansdan atomik yechish -> provayderga yuborish -> xatoda qaytarish
#   * Holat sinxronlash (processing -> completed/partial/canceled) + avtomatik qaytarish
#   * Foydalanuvchilarga API kalit berish (standart "v2" formatida)
# Pul bilan bog'liq har bir o'tish "UPDATE ... WHERE status IN (...)" bilan atomik:
# bir buyurtma ikki marta qaytarilmaydi va ikki marta yechilmaydi.
# ===================================================================

from __future__ import annotations

import hashlib
import math
import re
import secrets
import time
from typing import Awaitable, Callable

from src.database import Database, SettingsRepo, now_iso
from src.modules.users import UsersModule
from src.smm_client import SmmError, SmmProvider

PLATFORMS: dict[str, str] = {
    "telegram": "Telegram", "instagram": "Instagram", "tiktok": "TikTok",
    "youtube": "YouTube", "facebook": "Facebook", "x": "X (Twitter)", "other": "Boshqa",
}
_PLATFORM_RULES = [
    ("telegram", re.compile(r"telegram|\btg\b|t\.me", re.I)),
    ("instagram", re.compile(r"instagram|\big\b|insta\b|reels", re.I)),
    ("tiktok", re.compile(r"tik\s?tok", re.I)),
    ("youtube", re.compile(r"youtube|\byt\b|shorts", re.I)),
    ("facebook", re.compile(r"facebook|\bfb\b", re.I)),
    ("x", re.compile(r"twitter|\bx\.com\b|\bx\s+(?:followers|likes|views|retweets)|tweet", re.I)),
]
_LINK_RE = re.compile(r"^(https?://\S{3,480}|@[A-Za-z0-9_.]{2,64})$")

ACTIVE = ("pending", "processing")


def detect_platform(*texts: str) -> str:
    blob = " ".join(t for t in texts if t)
    for key, rx in _PLATFORM_RULES:
        if rx.search(blob):
            return key
    return "other"


def map_status(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("completed", "complete", "done", "success", "finished"):
        return "completed"
    if s == "partial":
        return "partial"
    if s in ("canceled", "cancelled", "refunded", "fail", "failed", "error", "rejected"):
        return "canceled"
    return "processing"  # pending / in progress / processing / running ...


def _int(v, d=0) -> int:
    try:
        return int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return d


def _float(v, d=0.0) -> float:
    try:
        return float(str(v).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return d


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class SmmModule:
    """Katalog, buyurtmalar, sinxronlash va API kalitlar."""

    def __init__(self, db: Database, users: UsersModule, settings: SettingsRepo,
                 provider: SmmProvider):
        self.db = db
        self.users = users
        self.settings = settings
        self.provider = provider
        # (order, outcome) -> bot orqali foydalanuvchiga xabar. outcome: completed|partial|canceled|failed
        self.on_result: Callable[[dict, str], Awaitable[None]] | None = None
        self._last_user_sync: dict[int, float] = {}
        self._provider_cache: tuple[float, list[dict]] | None = None

    # ------------------------------------------------------------------
    # Narx
    # ------------------------------------------------------------------
    @staticmethod
    def calc_price(price_per_1000: float, qty: int, min_price: float = 1.0) -> float:
        """Buyurtma narxi (so'm, butun songa yuqoriga yaxlitlanadi)."""
        raw = float(price_per_1000) * int(qty) / 1000.0
        return float(max(math.ceil(raw - 1e-9), math.ceil(min_price)))

    @staticmethod
    def auto_price(cost: float, rate: float, markup: float) -> float:
        return float(math.ceil(float(cost) * float(rate) * (1 + float(markup) / 100.0) - 1e-9))

    # ------------------------------------------------------------------
    # Katalog
    # ------------------------------------------------------------------
    async def get_service(self, service_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM smm_services WHERE id = ?", (service_id,))

    async def public_catalog(self) -> list[dict]:
        """Mijozga ko'rinadigan xizmatlar (provayder narxi/ID si YASHIRIN)."""
        rows = await self.db.fetch_all(
            "SELECT id, platform, category, name, description, price, min_qty, max_qty "
            "FROM smm_services WHERE active = 1 AND price > 0 AND provider_id != '' "
            "ORDER BY platform, category, sort, price, id")
        return rows

    async def list_services(self) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT * FROM smm_services ORDER BY platform, category, sort, id")

    async def admin_services(self, q: str = "", platform: str = "", limit: int = 100,
                             offset: int = 0) -> tuple[list[dict], int]:
        """Admin ro'yxati (qidiruv/platforma filtri bilan, sahifalab) + jami son."""
        where, args = [], []
        if q.strip():
            like = f"%{q.strip()}%"
            where.append("(name LIKE ? OR category LIKE ? OR provider_id = ?)")
            args += [like, like, q.strip()]
        if platform in PLATFORMS:
            where.append("platform = ?"); args.append(platform)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        total = (await self.db.fetch_one(f"SELECT COUNT(*) AS c FROM smm_services{w}", tuple(args)) or {}).get("c", 0)
        rows = await self.db.fetch_all(
            f"SELECT * FROM smm_services{w} ORDER BY platform, category, sort, id LIMIT ? OFFSET ?",
            (*args, max(1, min(int(limit), 300)), max(0, int(offset))))
        return rows, int(total)

    async def bulk(self, action: str, category: str = "", platform: str = "") -> int:
        """Kategoriya/platforma bo'yicha ommaviy yoqish, o'chirish, yo'q qilish."""
        where, args = [], []
        if category:
            where.append("category = ?"); args.append(category)
        if platform in PLATFORMS:
            where.append("platform = ?"); args.append(platform)
        if not where:
            return 0  # butun katalogga tasodifan tegmaslik uchun filtr majburiy
        w = " WHERE " + " AND ".join(where)
        if action in ("activate", "deactivate"):
            return await self.db.execute_rc(
                f"UPDATE smm_services SET active = ?{w}", (1 if action == "activate" else 0, *args))
        if action == "delete":
            return await self.db.execute_rc(f"DELETE FROM smm_services{w}", tuple(args))
        return 0

    async def add_service(self, *, name: str, category: str = "", platform: str = "",
                          provider_id: str = "", price: float = 0.0, cost: float = 0.0,
                          min_qty: int = 10, max_qty: int = 10000, description: str = "",
                          auto_price: bool = False, active: bool = True) -> int:
        name = name.strip()[:200]
        category = category.strip()[:120]
        platform = platform if platform in PLATFORMS else detect_platform(category, name)
        return await self.db.execute(
            "INSERT INTO smm_services(provider_id, platform, category, name, description, cost, "
            " price, auto_price, min_qty, max_qty, active, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(provider_id).strip()[:40], platform, category, name, description.strip()[:600],
             float(cost), float(price), int(auto_price), max(1, int(min_qty)),
             max(int(min_qty), int(max_qty)), int(active), now_iso()))

    async def update_service(self, service_id: int, **f) -> bool:
        sets, args = [], []
        for k in ("name", "category", "description", "provider_id"):
            if k in f and f[k] is not None:
                lim = {"name": 200, "category": 120, "description": 600, "provider_id": 40}[k]
                sets.append(f"{k} = ?"); args.append(str(f[k]).strip()[:lim])
        if f.get("platform") in PLATFORMS:
            sets.append("platform = ?"); args.append(f["platform"])
        if "price" in f and f["price"] is not None:
            p = float(f["price"])
            if p < 0:
                return False
            sets.append("price = ?"); args.append(p)
            sets.append("auto_price = 0")
        if "min_qty" in f and f["min_qty"] is not None:
            sets.append("min_qty = ?"); args.append(max(1, int(f["min_qty"])))
        if "max_qty" in f and f["max_qty"] is not None:
            sets.append("max_qty = ?"); args.append(max(1, int(f["max_qty"])))
        if "active" in f and f["active"] is not None:
            sets.append("active = ?"); args.append(int(bool(f["active"])))
        if "sort" in f and f["sort"] is not None:
            sets.append("sort = ?"); args.append(int(f["sort"]))
        if not sets:
            return False
        rc = await self.db.execute_rc(
            f"UPDATE smm_services SET {', '.join(sets)} WHERE id = ?", (*args, service_id))
        if rc and f.get("auto_price") is True:
            await self._reprice_one(service_id)
        return rc > 0

    async def _reprice_one(self, service_id: int) -> None:
        s = await self.settings.get_smm()
        svc = await self.get_service(service_id)
        if svc and float(svc["cost"]) > 0:
            await self.db.execute(
                "UPDATE smm_services SET price = ?, auto_price = 1 WHERE id = ?",
                (self.auto_price(svc["cost"], s["rate"], s["markup"]), service_id))

    async def delete_service(self, service_id: int) -> bool:
        # Buyurtmalar tarixi service_name ni o'zida saqlaydi, shuning uchun o'chirish xavfsiz
        rc = await self.db.execute_rc("DELETE FROM smm_services WHERE id = ?", (service_id,))
        return rc > 0

    async def reprice_all(self) -> int:
        """Kurs/ustama o'zgarganda avto-narxli xizmatlarni qayta hisoblaydi."""
        s = await self.settings.get_smm()
        rows = await self.db.fetch_all(
            "SELECT id, cost FROM smm_services WHERE auto_price = 1 AND cost > 0")
        data = [(self.auto_price(r["cost"], s["rate"], s["markup"]), r["id"]) for r in rows]
        if data:
            await self.db.execute_many("UPDATE smm_services SET price = ? WHERE id = ?", data)
        return len(data)

    # --- provayderdan import ---
    async def provider_categories(self, force: bool = False) -> list[dict]:
        """[{category, platform, count}] — provayder xizmatlari kategoriyalar bo'yicha."""
        raw = await self._provider_services(force)
        cats: dict[str, dict] = {}
        for x in raw:
            c = str(x.get("category") or "Boshqa").strip()
            e = cats.setdefault(c, {"category": c, "count": 0,
                                    "platform": detect_platform(c, str(x.get("name", "")))})
            e["count"] += 1
        return sorted(cats.values(), key=lambda e: (e["platform"], e["category"]))

    async def _provider_services(self, force: bool = False) -> list[dict]:
        now = time.monotonic()
        if not force and self._provider_cache and now - self._provider_cache[0] < 300:
            return self._provider_cache[1]
        raw = await self.provider.services()
        self._provider_cache = (now, raw)
        return raw

    async def import_services(self, categories: list[str] | None = None) -> dict:
        """Provayder xizmatlarini katalogga qo'shadi va mavjudlarini yangilaydi.

        categories=None -> BARCHA xizmatlar (API ulanganda avto-import).
        Mavjud xizmatlarda narx faqat auto_price=1 bo'lsa qayta hisoblanadi:
        admin qo'lda qo'ygan narx hech qachon o'zgarmaydi.
        """
        s = await self.settings.get_smm()
        raw = await self._provider_services(force=categories is None)
        wanted = None if categories is None else {c.strip() for c in categories if c and c.strip()}
        if wanted is not None and not wanted:
            return {"added": 0, "updated": 0, "skipped": 0}
        have = {
            r["provider_id"]: r
            for r in await self.db.fetch_all(
                "SELECT id, provider_id, price, auto_price FROM smm_services WHERE provider_id != ''")
        }
        inserts: list[tuple] = []
        updates: list[tuple] = []
        added = updated = skipped = 0
        seen: set[str] = set()
        now = now_iso()
        for x in raw:
            cat = str(x.get("category") or "Boshqa").strip()[:120]
            pid = str(x.get("service", "")).strip()[:40]
            if not pid or pid in seen:
                continue
            if wanted is not None and cat not in wanted:
                continue
            cost = _float(x.get("rate"))
            if cost <= 0:
                skipped += 1
                continue
            seen.add(pid)
            name = str(x.get("name", "")).strip()[:200] or f"Service {pid}"
            mn = max(1, _int(x.get("min"), 10))
            mx = max(mn, _int(x.get("max"), 10000))
            old = have.get(pid)
            auto_price = self.auto_price(cost, s["rate"], s["markup"])
            if old:
                auto = int(old.get("auto_price") or 0)
                price = auto_price if auto else float(old.get("price") or 0)
                updates.append((cost, name, cat, mn, mx, price, int(old["id"])))
                updated += 1
            else:
                inserts.append((pid, detect_platform(cat, name), cat, name, "", cost,
                                auto_price, 1, mn, mx, 1, now))
                added += 1
        if inserts:
            await self.db.execute_many(
                "INSERT INTO smm_services(provider_id, platform, category, name, description, "
                " cost, price, auto_price, min_qty, max_qty, active, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", inserts)
        if updates:
            await self.db.execute_many(
                "UPDATE smm_services SET cost=?, name=?, category=?, min_qty=?, max_qty=?, "
                " price=? WHERE id=?", updates)
        return {"added": added, "updated": updated, "skipped": skipped}

    # ------------------------------------------------------------------
    # Buyurtma berish
    # ------------------------------------------------------------------
    @staticmethod
    def valid_link(link: str) -> bool:
        return bool(_LINK_RE.match(link or ""))

    async def place_order(self, user_id: int, service_id: int, link: str, quantity: int,
                          source: str = "app") -> dict:
        """
        Natija: {"ok": True, "order_id", "price", "balance"} yoki {"ok": False, "error": kod}.
        Xato kodlari: disabled, no_provider, no_service, bad_link, bad_qty, duplicate,
                      insufficient_sum, provider (provayder rad etdi -> pul qaytarildi).
        """
        cfg = await self.settings.get_smm()
        if not cfg["enabled"]:
            return {"ok": False, "error": "disabled"}
        if not (cfg["url"] and cfg["key"]):
            return {"ok": False, "error": "no_provider"}
        svc = await self.get_service(int(service_id)) if service_id else None
        if not svc or not svc["active"] or float(svc["price"]) <= 0 or not svc["provider_id"]:
            return {"ok": False, "error": "no_service"}
        link = (link or "").strip()
        if not self.valid_link(link):
            return {"ok": False, "error": "bad_link"}
        try:
            qty = int(quantity)
        except (TypeError, ValueError):
            return {"ok": False, "error": "bad_qty"}
        if qty < int(svc["min_qty"]) or qty > int(svc["max_qty"]):
            return {"ok": False, "error": "bad_qty",
                    "min": int(svc["min_qty"]), "max": int(svc["max_qty"])}
        if source == "app":
            dup = await self.db.fetch_one(
                "SELECT id FROM smm_orders WHERE user_id=? AND service_id=? AND link=? AND quantity=? "
                "AND created_at >= ? AND status != 'failed'",
                (user_id, svc["id"], link, qty, _ago_iso(15)))
            if dup:
                return {"ok": False, "error": "duplicate", "order_id": dup["id"]}

        price = self.calc_price(svc["price"], qty, cfg["min_price"])
        # 1) Atomik yechish: balans yetmasa hech narsa o'zgarmaydi
        rc = await self.db.execute_rc(
            "UPDATE users SET balance_sum = balance_sum - ? WHERE id = ? AND balance_sum >= ?",
            (price, user_id, price - 1e-9))
        if rc == 0:
            return {"ok": False, "error": "insufficient_sum",
                    "balance": await self.users.balance_sum(user_id), "price": price}
        now = now_iso()
        order_id = await self.db.execute(
            "INSERT INTO smm_orders(user_id, service_id, service_name, link, quantity, price, "
            " status, source, created_at, updated_at) VALUES(?,?,?,?,?,?, 'pending', ?, ?, ?)",
            (user_id, svc["id"], svc["name"][:200], link, qty, price, source, now, now))
        await self.users._log_tx(user_id, None, price, "debit", f"smm order#{order_id}")

        # 2) Provayderga yuborish
        try:
            pid = await self.provider.add(svc["provider_id"], link, qty)
        except SmmError as exc:
            await self._finalize(order_id, "failed", refund=price, error=str(exc), notify=False)
            return {"ok": False, "error": "provider",
                    "balance": await self.users.balance_sum(user_id)}
        except Exception as exc:  # noqa: BLE001
            await self._finalize(order_id, "failed", refund=price,
                                 error=f"{type(exc).__name__}", notify=False)
            return {"ok": False, "error": "provider",
                    "balance": await self.users.balance_sum(user_id)}
        await self.db.execute(
            "UPDATE smm_orders SET status='processing', provider_order=?, remains=?, updated_at=? "
            "WHERE id=? AND status='pending'", (pid, qty, now_iso(), order_id))
        return {"ok": True, "order_id": order_id, "price": price, "quantity": qty,
                "balance": await self.users.balance_sum(user_id)}

    async def get_order(self, order_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM smm_orders WHERE id = ?", (order_id,))

    # ------------------------------------------------------------------
    # Yakunlash / qaytarish (atomik)
    # ------------------------------------------------------------------
    async def _finalize(self, order_id: int, status: str, refund: float = 0.0,
                        error: str = "", start_count: int | None = None,
                        remains: int | None = None, notify: bool = True) -> bool:
        """
        Faol (pending/processing) buyurtmani yakuniy holatga o'tkazadi va (kerak bo'lsa)
        pulni qaytaradi. O'tish faqat BIR marta bajariladi.
        """
        refund = round(max(0.0, float(refund)), 2)
        sets = "status = ?, refunded = refunded + ?, error = ?, updated_at = ?"
        args: list = [status, refund, error[:300], now_iso()]
        if start_count is not None:
            sets += ", start_count = ?"; args.append(int(start_count))
        if remains is not None:
            sets += ", remains = ?"; args.append(int(remains))
        rc = await self.db.execute_rc(
            f"UPDATE smm_orders SET {sets} WHERE id = ? AND status IN ('pending','processing')",
            (*args, order_id))
        if rc == 0:
            return False
        order = await self.db.fetch_one("SELECT * FROM smm_orders WHERE id = ?", (order_id,))
        if refund > 0 and order:
            await self.users.add_sum(order["user_id"], refund, f"smm refund order#{order_id}")
        if notify and self.on_result and order:
            try:
                await self.on_result(order, status)
            except Exception:  # noqa: BLE001
                pass
        return True

    async def apply_provider_status(self, order: dict, info: dict) -> bool:
        """Provayder javobini buyurtmaga qo'llaydi. O'zgarish bo'lsa True."""
        if order["status"] not in ACTIVE:
            return False
        new = map_status(str(info.get("status", "")))
        remains = _int(info.get("remains"), int(order["remains"] or 0))
        start = _int(info.get("start_count"), int(order["start_count"] or 0))
        qty = max(1, int(order["quantity"]))
        price = float(order["price"])
        if new == "completed":
            return await self._finalize(order["id"], "completed", start_count=start, remains=0)
        if new == "canceled":
            return await self._finalize(order["id"], "canceled", refund=price,
                                        error="provider canceled", start_count=start, remains=qty)
        if new == "partial":
            remains = min(max(remains, 0), qty)
            refund = min(price, round(price * remains / qty, 2))
            return await self._finalize(order["id"], "partial", refund=refund,
                                        start_count=start, remains=remains)
        # hali jarayonda: faqat progress yangilanadi
        if remains != int(order["remains"] or 0) or start != int(order["start_count"] or 0):
            await self.db.execute(
                "UPDATE smm_orders SET remains=?, start_count=?, updated_at=? "
                "WHERE id=? AND status IN ('pending','processing')",
                (min(max(remains, 0), qty), start, now_iso(), order["id"]))
        return False

    async def sync_orders(self, user_id: int | None = None, limit: int = 100) -> int:
        """Jarayondagi buyurtmalar holatini provayderdan oladi. O'zgarganlar sonini qaytaradi."""
        # Provayderga yetib bormagan (jarayon o'rtasida to'xtagan) eski 'pending' larni qaytarish
        stale = await self.db.fetch_all(
            "SELECT id, price FROM smm_orders WHERE status='pending' AND provider_order='' "
            "AND created_at < ?", (_ago_iso(600),))
        changed = 0
        for r in stale:
            if await self._finalize(r["id"], "failed", refund=float(r["price"]),
                                    error="not sent", notify=False):
                changed += 1
        if not await self.provider.configured():
            return changed
        where, args = "status='processing' AND provider_order != ''", []
        if user_id is not None:
            where += " AND user_id = ?"; args.append(user_id)
        rows = await self.db.fetch_all(
            f"SELECT * FROM smm_orders WHERE {where} ORDER BY id LIMIT ?", (*args, limit))
        if not rows:
            return changed
        try:
            infos = await self.provider.statuses([r["provider_order"] for r in rows])
        except SmmError:
            infos = {}
        for r in rows:
            info = infos.get(r["provider_order"])
            if info is None:
                try:
                    info = await self.provider.status(r["provider_order"])
                except SmmError:
                    continue
            if await self.apply_provider_status(r, info):
                changed += 1
        return changed

    async def refresh_user(self, user_id: int, min_gap: float = 15.0) -> None:
        """Foydalanuvchi ro'yxatni ochganda (oraliq bilan) o'z buyurtmalarini yangilaydi."""
        now = time.monotonic()
        if now - self._last_user_sync.get(user_id, 0.0) < min_gap:
            return
        self._last_user_sync[user_id] = now
        try:
            await self.sync_orders(user_id=user_id, limit=30)
        except Exception:  # noqa: BLE001
            pass

    async def admin_cancel(self, order_id: int) -> bool:
        """Admin buyurtmani qo'lda bekor qiladi va to'liq qaytaradi."""
        o = await self.db.fetch_one("SELECT * FROM smm_orders WHERE id = ?", (order_id,))
        if not o or o["status"] not in ACTIVE:
            return False
        return await self._finalize(order_id, "canceled", refund=float(o["price"]),
                                    error="admin canceled")

    # ------------------------------------------------------------------
    # Buyurtmalar ro'yxati / statistika
    # ------------------------------------------------------------------
    async def user_orders(self, user_id: int, limit: int = 30) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT id, service_name, link, quantity, price, refunded, status, remains, "
            "start_count, source, created_at FROM smm_orders WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ?", (user_id, max(1, min(limit, 100))))

    async def admin_orders(self, status: str = "", limit: int = 80) -> list[dict]:
        where, args = "", []
        if status == "active":
            where = "WHERE status IN ('pending','processing')"
        elif status:
            where = "WHERE status = ?"; args.append(status)
        return await self.db.fetch_all(
            f"SELECT * FROM smm_orders {where} ORDER BY id DESC LIMIT ?",
            (*args, max(1, min(limit, 200))))

    async def stats(self) -> dict:
        row = await self.db.fetch_one(
            "SELECT COUNT(*) AS orders, "
            " COALESCE(SUM(CASE WHEN status IN ('pending','processing') THEN 1 END),0) AS active, "
            " COALESCE(SUM(CASE WHEN status != 'failed' THEN price - refunded END),0) AS revenue "
            "FROM smm_orders") or {}
        svc = await self.db.fetch_one(
            "SELECT COUNT(*) AS total, COALESCE(SUM(active),0) AS active FROM smm_services") or {}
        return {"orders": row.get("orders", 0), "active_orders": row.get("active", 0),
                "revenue": row.get("revenue", 0), "services": svc.get("total", 0),
                "services_active": svc.get("active", 0)}

    # ------------------------------------------------------------------
    # Foydalanuvchi API kalitlari
    # ------------------------------------------------------------------
    async def key_info(self, user_id: int) -> dict | None:
        return await self.db.fetch_one(
            "SELECT prefix, created_at, last_used FROM smm_api_keys WHERE user_id = ?", (user_id,))

    async def create_key(self, user_id: int) -> str:
        """Yangi kalit yaratadi (eskisi o'chadi). To'liq kalit FAQAT shu yerda qaytadi."""
        key = "smm_" + secrets.token_urlsafe(27)
        await self.db.execute(
            "INSERT INTO smm_api_keys(user_id, key_hash, prefix, created_at) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET key_hash=excluded.key_hash, "
            "prefix=excluded.prefix, created_at=excluded.created_at, last_used=NULL",
            (user_id, hash_key(key), key[:9] + "…" + key[-4:], now_iso()))
        return key

    async def revoke_key(self, user_id: int) -> bool:
        return (await self.db.execute_rc(
            "DELETE FROM smm_api_keys WHERE user_id = ?", (user_id,))) > 0

    async def user_by_key(self, key: str) -> int | None:
        if not key or len(key) > 100:
            return None
        row = await self.db.fetch_one(
            "SELECT user_id FROM smm_api_keys WHERE key_hash = ?", (hash_key(key.strip()),))
        if not row:
            return None
        await self.db.execute(
            "UPDATE smm_api_keys SET last_used = ? WHERE user_id = ?", (now_iso(), row["user_id"]))
        return int(row["user_id"])


def _ago_iso(seconds: int) -> str:
    from datetime import datetime, timedelta

    return (datetime.now() - timedelta(seconds=seconds)).isoformat(timespec="seconds")
