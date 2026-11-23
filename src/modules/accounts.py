# ===================================================================
# modules/accounts.py - AKKAUNTLAR MODULI
# Gift yuborish uchun Telegram akkauntlarni ulash / o'chirish.
# session_data (Telethon StringSession) Fernet bilan SHIFRLANIB
# saqlanadi (bot_token dan olingan kalit), asl qiymatning sha256
# hashi alohida session_hash ustunida turadi (identifikatsiya).
# ===================================================================

from __future__ import annotations

from src.database import Database, now_iso
from src.security import decrypt_secret, encrypt_secret, sha256_hex
from src.telegram_gift import TelegramGiftSender


class AccountsModule:
    """Ulangan akkauntlarni boshqarish va gift yetkazish."""

    def __init__(self, db: Database, bot_token: str = ""):
        self.db = db
        self.bot_token = bot_token
        self._sender = TelegramGiftSender()
        self._rr = 0  # round-robin hisoblagich

    async def add(self, title: str, session_data: str) -> int:
        """Yangi akkaunt ulaydi (session_data Fernet bilan shifrlanadi)."""
        encrypted = encrypt_secret(session_data, self.bot_token)
        hashed = sha256_hex(session_data)
        return await self.db.execute(
            "INSERT INTO accounts(title, session_data, session_hash, status, created_at) "
            "VALUES(?, ?, ?, 'active', ?)",
            (title[:100], encrypted, hashed, now_iso()),
        )

    async def remove(self, account_id: int) -> bool:
        """Akkauntni o'chiradi."""
        await self.db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        return True

    async def set_status(self, account_id: int, active: bool) -> None:
        await self.db.execute(
            "UPDATE accounts SET status = ? WHERE id = ?",
            ("active" if active else "inactive", account_id),
        )

    async def list_all(self) -> list[dict]:
        return await self.db.fetch_all("SELECT * FROM accounts ORDER BY id DESC")

    async def active(self) -> list[dict]:
        return await self.db.fetch_all(
            "SELECT * FROM accounts WHERE status = 'active' ORDER BY id DESC"
        )

    def decrypt_session(self, row: dict) -> str:
        """Saqlangan shifrlangan session'ni ochadi."""
        return decrypt_secret(row.get("session_data") or "", self.bot_token)

    async def deliver_gift(self, amount: float, recipient: str, kind: str = "phone") -> tuple[bool, str]:
        """
        Gift'ni oluvchiga haqiqiy yetkazish (Telethon user-session).
        recipient: "@username" yoki "+998901234567".
        Qaytaradi: (ok, xato_sababi). Aktiv akkaunt yo'q yoki yuborish
        xato bo'lsa (False, sabab) qaytadi.
        """
        active = await self.active()
        if not active:
            return False, "no_active_account"
        # Round-robin: navbatdagi aktiv akkauntni tanlaymiz
        account = active[self._rr % len(active)]
        self._rr += 1
        session = self.decrypt_session(account)
        if not session:
            return False, "empty_or_corrupt_session"
        return await self._sender.send(
            session, int(amount), recipient, kind
        )

    async def deliver_post_stars(self, amount: float, post_link: str) -> tuple[bool, str]:
        """
        Postga stars (paid reaction) yetkazish (Telethon user-session).
        post_link: "https://t.me/username/123" yoki t.me/c/<id>/<msg>.
        Qaytaradi: (ok, sabab).
        """
        active = await self.active()
        if not active:
            return False, "no_active_account"
        account = active[self._rr % len(active)]
        self._rr += 1
        session = self.decrypt_session(account)
        if not session:
            return False, "empty_or_corrupt_session"
        return await self._sender.send_post_stars(
            session, int(amount), post_link
        )

    async def test_connection(self, account_id: int) -> tuple[bool, str]:
        """Akkauntni test qiladi: ulanish + get_me. (ok, xabar)"""
        row = await self.db.fetch_one(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        )
        if not row:
            return False, "account_not_found"
        session = self.decrypt_session(row)
        if not session:
            return False, "empty_or_corrupt_session"
        return await self._sender.test_session(session)

    async def resolve_username(self, username: str) -> tuple[str, str, int]:
        """Ulangan akkaunt orqali @username ni topadi: (found|not_found|unknown, ism, id)."""
        for account in await self.active():
            session = self.decrypt_session(account)
            if session:
                return await self._sender.resolve_user(session, username)
        return "unknown", "", 0
