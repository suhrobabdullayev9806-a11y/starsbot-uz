# ===================================================================
# modules/bank.py - AVTO-TO'LOV (karta -> tranzaksiya ID tekshiruvi)
#
# Qanday ishlaydi:
#  1) Karta egasiga kelgan KIRIM bildirishnomalari (bank SMS / CardXabar
#     boti va h.k.) botga tushadi: webhook, Telethon tinglovchi yoki /bankadd.
#     Har biridan SUMMA va ID nomzodlari ajratib `bank_transactions` ga yoziladi.
#  2) Foydalanuvchi summani tanlaydi, to'laydi va tranzaksiya ID sini yozadi.
#  3) Bot shu ID + aynan shu summa bilan yozilgan, hali ishlatilmagan kirimni
#     qidiradi: topilsa balansga qo'shadi (bir tranzaksiya bir marta!), summa
#     mos kelmasa darhol bekor qiladi, topilmasa kutadi va muddat tugagach
#     bekor qiladi.
# ===================================================================

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable

from src.config import Settings
from src.database import Database, now_iso
from src.modules.orders import OrdersModule
from src.modules.users import UsersModule

log = logging.getLogger("stars.bank")

METHOD = "card_auto"          # orders.payment_method qiymati
MAX_PENDING_PER_USER = 3
MAX_ATTEMPTS_PER_HOUR = 10
TX_MAX_AGE_HOURS = 72          # shundan eski bank yozuvlari hisobga olinmaydi

_AMOUNT_RE = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:[ \u00a0,]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
    r"\s*(?:uzs|so['’`ʻ]?m\b|сум|sum\b)",
    re.IGNORECASE,
)
_INCOME_RE = re.compile(
    r"➕|(?<!\w)\+\s*\d|kirim|tushum|tushdi|qabul qilindi|o['’`ʻ]tkazma qabul|"
    r"пополнен|поступлен|зачислен|credit|received|incoming|deposit",
    re.IGNORECASE,
)
_EXPENSE_RE = re.compile(
    r"➖|chiqim|yechildi|xarid|списан|оплата|покупка|debit|purchase|withdraw",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-_]{5,}")


def norm_tx(value: str) -> str:
    """Tranzaksiya ID ni solishtirish uchun normallashtiradi (harf/raqam, kichik harf)."""
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _to_amount(raw: str) -> float:
    s = raw.replace("\u00a0", " ").strip()
    m = re.match(r"^(.*?)[.,](\d{1,2})$", s)
    if m and not re.fullmatch(r"\d{1,3}(?:[ ,]\d{3})+", s):
        int_part, frac = m.group(1), m.group(2)
        digits = re.sub(r"\D", "", int_part)
        return float(f"{digits or 0}.{frac}")
    return float(re.sub(r"\D", "", s) or 0)


def parse_notification(text: str) -> dict | None:
    """Bank bildirishnomasidan {amount, income, tokens} ajratadi (summa topilmasa None)."""
    text = (text or "").strip()
    if not text:
        return None
    amounts: list[tuple[float, bool, str]] = []   # (summa, kirim_qatormi, qator)
    for line in text.splitlines():
        for m in _AMOUNT_RE.finditer(line):
            amounts.append((_to_amount(m.group(1)), bool(_INCOME_RE.search(line)), line))
    if not amounts:
        return None
    income_lines = [a for a in amounts if a[1]]
    chosen = (income_lines or amounts)[0]
    amount = chosen[0]
    has_income = bool(income_lines) or bool(_INCOME_RE.search(text))
    has_expense = bool(_EXPENSE_RE.search(text))
    income = has_income or not has_expense

    # ID nomzodlari: kamida 6 belgi; summa raqamlari, telefon raqamlari chiqarib tashlanadi
    skip = set()
    for a, _, _ in amounts:
        skip.add(norm_tx(f"{a:.2f}"))
        skip.add(norm_tx(f"{int(a)}"))
    tokens: list[str] = []
    for tok in _TOKEN_RE.findall(text):
        n = norm_tx(tok)
        if len(n) < 6 or n in skip or not any(ch.isdigit() for ch in n):
            continue   # so'zlar (HUMOCARD...) ID bo'la olmaydi
        if re.fullmatch(r"998\d{9}", n):          # telefon raqami
            continue
        if n not in tokens:
            tokens.append(n)
    return {"amount": amount, "income": income, "tokens": tokens}


class BankModule:
    """Bank kirimlarini saqlash va foydalanuvchi to'lovini tekshirish."""

    def __init__(self, db: Database, orders: OrdersModule, users: UsersModule, cfg: Settings):
        self.db = db
        self.orders = orders
        self.users = users
        self.cfg = cfg
        # (order, status, reason) -> bot orqali foydalanuvchiga xabar (main.py ulaydi)
        self.on_result: Callable[[dict, str, str], Awaitable[None]] | None = None

    # ---------------- holat ----------------
    @property
    def enabled(self) -> bool:
        """Avto tekshiruv manbasi sozlanganmi? Aks holda admin qo'lda tasdiqlaydi."""
        c = self.cfg
        return bool(
            c.bank_webhook_secret
            or (c.bank_session and c.bank_source_chats)
            or c.bank_auto
        )

    # ---------------- kirimlarni qabul qilish ----------------
    async def ingest(self, raw: str, source: str = "webhook",
                     amount: float | None = None, tx_id: str | None = None) -> dict:
        """Bank bildirishnomasini saqlaydi. Qaytaradi: {ok, stored, amount}."""
        raw = (raw or "").strip()
        parsed = parse_notification(raw) or {"amount": 0.0, "income": True, "tokens": []}
        if amount is not None:
            parsed["amount"] = float(amount)
        if tx_id:
            n = norm_tx(tx_id)
            if n and n not in parsed["tokens"]:
                parsed["tokens"].insert(0, n)
        if parsed["amount"] <= 0:
            return {"ok": False, "stored": False, "reason": "amount_not_found"}
        if not parsed["income"]:
            return {"ok": True, "stored": False, "reason": "not_income"}
        if not parsed["tokens"]:
            # ID yo'q xabar ham saqlanadi (admin ko'rishi mumkin), lekin ID bo'yicha topilmaydi
            log.info("bank: ID topilmadi (summa=%s)", parsed["amount"])
        key = f"{raw}|{amount}|{tx_id}"
        raw_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        try:
            rc = await self.db.execute_rc(
                "INSERT OR IGNORE INTO bank_transactions"
                "(raw_hash, tokens, amount, income, source, raw, created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (raw_hash, " ".join(parsed["tokens"]), parsed["amount"], 1,
                 source[:40], raw[:1000], now_iso()),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("bank ingest xatosi: %s", exc)
            return {"ok": False, "stored": False, "reason": "db_error"}
        stored = rc > 0
        if stored:
            await self.process_pending()
        return {"ok": True, "stored": stored, "amount": parsed["amount"]}

    # ---------------- foydalanuvchi to'lovi ----------------
    async def submit(self, user_id: int, amount: float, tx_input: str) -> dict:
        """To'lovni qabul qiladi (tx ID bilan) va darhol tekshiradi.

        Qaytaradi: {ok, status: done|pending|manual|rejected, order_id, reason, balance_sum}
        """
        res = {"ok": False, "status": "rejected", "order_id": 0, "reason": "", "balance_sum": 0.0}
        try:
            amount = round(float(amount), 2)
        except (TypeError, ValueError):
            res["reason"] = "bad_amount"
            return res
        if amount < self.cfg.topup_min or amount > self.cfg.topup_max:
            res["reason"] = "amount_range"
            return res
        tx = norm_tx(tx_input)
        if len(tx) < 6 or len(tx) > 40 or not any(ch.isdigit() for ch in tx):
            res["reason"] = "bad_tx"
            return res

        pend = await self.db.fetch_one(
            "SELECT COUNT(*) AS c FROM orders WHERE user_id=? AND type='topup' "
            "AND payment_method=? AND status='pending'", (user_id, METHOD))
        if pend and pend["c"] >= MAX_PENDING_PER_USER:
            res["reason"] = "too_many_pending"
            return res
        since = (datetime.now() - timedelta(hours=1)).isoformat(timespec="seconds")
        recent = await self.db.fetch_one(
            "SELECT COUNT(*) AS c FROM orders WHERE user_id=? AND type='topup' "
            "AND payment_method=? AND created_at>=?", (user_id, METHOD, since))
        if recent and recent["c"] >= MAX_ATTEMPTS_PER_HOUR:
            res["reason"] = "rate_limit"
            return res
        dup = await self.db.fetch_one(
            "SELECT id FROM orders WHERE type='topup' AND payment_method=? "
            "AND note=? AND status IN ('pending','done')", (METHOD, f"tx:{tx}"))
        if dup:
            res["reason"] = "duplicate"
            return res

        order_id = await self.orders.create(
            user_id, "topup", 0, METHOD, price_amount=amount, note=f"tx:{tx}"
        )
        res["order_id"] = order_id
        if not self.enabled:
            res.update(ok=True, status="manual", reason="manual_review")
            return res

        outcome, reason = await self._try_match(order_id, user_id, amount, tx)
        res["balance_sum"] = await self.users.balance_sum(user_id)
        if outcome == "done":
            res.update(ok=True, status="done", reason="ok")
        elif outcome == "rejected":
            res.update(ok=False, status="rejected", reason=reason)
        else:
            res.update(ok=True, status="pending", reason="waiting")
        return res

    async def _try_match(self, order_id: int, user_id: int, amount: float, tx: str) -> tuple[str, str]:
        """('done'|'rejected'|'pending', sabab). Atomik: bir tranzaksiya bir marta ishlatiladi."""
        cur = await self.orders.get(order_id)
        if cur and cur["status"] == "done":          # parallel tekshiruv allaqachon yakunlagan
            return "done", "ok"
        if cur and cur["status"] != "pending":
            return "rejected", "not_pending"
        since = (datetime.now() - timedelta(hours=TX_MAX_AGE_HOURS)).isoformat(timespec="seconds")
        rows = await self.db.fetch_all(
            "SELECT * FROM bank_transactions WHERE created_at>=? AND income=1 "
            "ORDER BY id DESC LIMIT 500", (since,))
        same_id = [r for r in rows if tx in (r["tokens"] or "").split()]
        if not same_id:
            return "pending", "not_found_yet"
        free = [r for r in same_id if r["used_order"] is None]
        if not free:
            await self._reject(order_id, "tx_already_used")
            return "rejected", "tx_already_used"
        good = [r for r in free if abs(float(r["amount"]) - amount) < 0.5]
        if not good:
            await self._reject(order_id, "amount_mismatch")
            return "rejected", "amount_mismatch"

        row = good[0]
        # 1) bank yozuvini band qilamiz (faqat bo'sh bo'lsa)
        if await self.db.execute_rc(
            "UPDATE bank_transactions SET used_order=? WHERE id=? AND used_order IS NULL",
            (order_id, row["id"])) != 1:
            await self._reject(order_id, "tx_already_used")
            return "rejected", "tx_already_used"
        # 2) buyurtmani yakunlaymiz (faqat pending bo'lsa) va pul qo'shamiz
        if await self.db.execute_rc(
            "UPDATE orders SET status='done', note=?, updated_at=? WHERE id=? AND status='pending'",
            (f"tx:{tx} | auto ok", now_iso(), order_id)) != 1:
            # admin qo'lda hal qilib bo'lgan: bank yozuvini qaytaramiz
            await self.db.execute_rc(
                "UPDATE bank_transactions SET used_order=NULL WHERE id=?", (row["id"],))
            return "pending", "order_not_pending"
        await self.users.add_sum(user_id, amount, f"topup auto order#{order_id}", order_id)
        return "done", "ok"

    async def _reject(self, order_id: int, reason: str) -> None:
        await self.db.execute_rc(
            "UPDATE orders SET status='rejected', note=note || ?, updated_at=? "
            "WHERE id=? AND status='pending'", (f" | {reason}", now_iso(), order_id))

    # ---------------- kutilayotganlarni tekshirish ----------------
    async def process_pending(self) -> int:
        """Kutilayotgan avto-to'lovlarni qayta tekshiradi, muddati o'tganini bekor qiladi."""
        if not self.enabled:
            return 0
        pend = await self.db.fetch_all(
            "SELECT * FROM orders WHERE type='topup' AND payment_method=? AND status='pending' "
            "ORDER BY id LIMIT 200", (METHOD,))
        handled = 0
        now = datetime.now()
        for o in pend:
            tx = (o.get("note") or "")[3:] if str(o.get("note") or "").startswith("tx:") else ""
            tx = tx.split(" ", 1)[0]
            amount = float(o["price_amount"])
            outcome, reason = await self._try_match(o["id"], o["user_id"], amount, tx)
            if outcome == "pending":
                try:
                    age = (now - datetime.fromisoformat(str(o["created_at"]))).total_seconds()
                except ValueError:
                    age = 0
                if age >= self.cfg.topup_verify_timeout:
                    await self._reject(o["id"], "not_found_timeout")
                    outcome, reason = "rejected", "not_found_timeout"
                else:
                    continue
            handled += 1
            fresh = await self.orders.get(o["id"]) or o
            await self._emit(fresh, outcome, reason)
        return handled

    async def _emit(self, order: dict, outcome: str, reason: str) -> None:
        if self.on_result is None:
            return
        try:
            await self.on_result(order, outcome, reason)
        except Exception as exc:  # noqa: BLE001
            log.warning("topup xabari yuborilmadi: %s", exc)

    async def order_status(self, user_id: int, order_id: int) -> dict | None:
        o = await self.orders.get(order_id)
        if not o or o["user_id"] != user_id:
            return None
        return o
