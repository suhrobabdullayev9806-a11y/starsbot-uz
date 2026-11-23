# ===================================================================
# modules/nft.py - NFT MODULI
# Admin t.me/nft/... havolasi + narx bilan NFT qo'shadi (rasm va
# Model/Backdrop/Symbol avtomatik aniqlanadi). Foydalanuvchi mini-app
# orqali so'mlik hisobidan sotib oladi. Har bir NFT YAGONA nusxa:
#   active -> reserved (buyurtma, admin yetkazishini kutmoqda) -> sold
# Admin rad etsa pul qaytariladi va NFT yana sotuvga chiqadi.
# ===================================================================

from __future__ import annotations

from src.database import Database, now_iso
from src.modules.orders import OrdersModule
from src.modules.users import UsersModule
from src.nft_parser import NftInfo
from src.schemas import PaymentResult


class NftModule:
    """NFT katalogi va sotib olish."""

    def __init__(self, db: Database, orders: OrdersModule, users: UsersModule):
        self.db = db
        self.orders = orders
        self.users = users

    # ---------- Katalog ----------

    async def get(self, nft_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM nfts WHERE id = ?", (nft_id,))

    async def list_active(self) -> list[dict]:
        """Mini-app katalogi: sotuvdagi NFT'lar (yangilari birinchi)."""
        return await self.db.fetch_all(
            "SELECT * FROM nfts WHERE status = 'active' AND price > 0 ORDER BY id DESC"
        )

    async def list_all(self) -> list[dict]:
        """Admin ro'yxati: o'chirilganlardan tashqari hammasi."""
        return await self.db.fetch_all(
            "SELECT * FROM nfts WHERE status != 'deleted' ORDER BY id DESC"
        )

    async def find_by_slug(self, slug: str) -> dict | None:
        return await self.db.fetch_one(
            "SELECT * FROM nfts WHERE lower(slug) = lower(?) AND status != 'deleted'", (slug,)
        )

    async def add(self, info: NftInfo, price: float) -> int:
        """Yangi NFT qo'shadi (narx so'mda)."""
        return await self.db.execute(
            "INSERT INTO nfts(url, slug, name, number, image, model, backdrop, symbol, "
            " price, status, created_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
            (info.url, info.slug, info.name[:100], int(info.number), info.image,
             info.model, info.backdrop, info.symbol, round(float(price), 2), now_iso()),
        )

    async def set_price(self, nft_id: int, price: float) -> bool:
        rc = await self.db.execute_rc(
            "UPDATE nfts SET price = ? WHERE id = ? AND status != 'deleted'",
            (round(float(price), 2), nft_id),
        )
        return rc > 0

    async def update(self, nft_id: int, **fields) -> bool:
        """Admin tahriri: price, name, number, image, model, backdrop, symbol."""
        allowed = {"price", "name", "number", "image", "model", "backdrop", "symbol"}
        sets, args = [], []
        for k, v in fields.items():
            if k not in allowed or v is None:
                continue
            if k == "price":
                v = round(float(v), 2)
            elif k == "number":
                v = int(v)
            elif k == "image":
                v = str(v).strip()
                if v and not v.lower().startswith("https://"):
                    continue
            else:
                v = str(v).strip()[:100]
            sets.append(f"{k} = ?"); args.append(v)
        if not sets:
            return False
        rc = await self.db.execute_rc(
            f"UPDATE nfts SET {', '.join(sets)} WHERE id = ? AND status != 'deleted'",
            (*args, nft_id))
        return rc > 0

    async def remove(self, nft_id: int) -> bool:
        """Katalogdan olib tashlaydi (faqat sotuvdagi NFT; buyurtmadagisi emas)."""
        rc = await self.db.execute_rc(
            "UPDATE nfts SET status = 'deleted' WHERE id = ? AND status = 'active'",
            (nft_id,),
        )
        return rc > 0

    # ---------- Sotib olish ----------

    async def purchase(self, user_id: int, nft_id: int, recipient: str = "") -> PaymentResult:
        """
        1) NFT atomik tarzda band qilinadi (ikki kishi bir vaqtda ololmaydi)
        2) So'mlik balansdan narx yechiladi (yetarli bo'lmasa band bekor qilinadi)
        3) 'nft' buyurtmasi yaratiladi — admin NFT'ni yetkazgach tasdiqlaydi
        """
        nft = await self.get(nft_id)
        if not nft or nft["status"] == "deleted":
            return PaymentResult(ok=False, error="no_nft")
        price = round(float(nft["price"]), 2)
        if price <= 0:
            return PaymentResult(ok=False, error="no_price")

        rc = await self.db.execute_rc(
            "UPDATE nfts SET status = 'reserved', buyer_id = ? "
            "WHERE id = ? AND status = 'active'",
            (user_id, nft_id),
        )
        if rc == 0:
            return PaymentResult(ok=False, error="unavailable")

        title = f"{nft['name']} #{nft['number']}"
        who = f"@{recipient.lstrip('@')}" if recipient else f"id:{user_id}"
        order_id = await self.orders.create(
            user_id, "nft", 0, "sum", price_amount=price,
            note=f"{title} -> {who} | {nft['url']}",
        )
        bal = await self.users.sub_sum(user_id, price, f"nft purchase order#{order_id}", order_id)
        if bal < 0:
            await self.orders.update_status(order_id, "rejected", "insufficient balance")
            await self._release(nft_id)
            return PaymentResult(ok=False, error="insufficient_sum", order_id=order_id)

        await self.db.execute("UPDATE nfts SET order_id = ? WHERE id = ?", (order_id, nft_id))
        return PaymentResult(ok=True, order_id=order_id, balance=bal)

    async def _release(self, nft_id: int) -> None:
        await self.db.execute(
            "UPDATE nfts SET status = 'active', buyer_id = NULL, order_id = NULL WHERE id = ?",
            (nft_id,),
        )

    async def by_order(self, order_id: int) -> dict | None:
        return await self.db.fetch_one("SELECT * FROM nfts WHERE order_id = ?", (order_id,))

    async def complete(self, order_id: int) -> bool:
        """Admin NFT'ni yetkazdi: buyurtma 'done', NFT 'sold'. Ikkinchi marta ishlamaydi."""
        rc = await self.db.execute_rc(
            "UPDATE orders SET status = 'done', updated_at = ? "
            "WHERE id = ? AND type = 'nft' AND status IN ('pending','processing')",
            (now_iso(), order_id),
        )
        if rc == 0:
            return False
        await self.db.execute("UPDATE nfts SET status = 'sold' WHERE order_id = ?", (order_id,))
        return True

    async def cancel(self, order_id: int) -> dict | None:
        """
        Buyurtmani bekor qiladi: pul qaytariladi, NFT yana sotuvga chiqadi.
        Faqat kutilayotgan buyurtma uchun (ikki marta qaytarilmaydi). Buyurtmani qaytaradi.
        """
        order = await self.orders.get(order_id)
        if not order or order["type"] != "nft":
            return None
        rc = await self.db.execute_rc(
            "UPDATE orders SET status = 'rejected', updated_at = ? "
            "WHERE id = ? AND status IN ('pending','processing')",
            (now_iso(), order_id),
        )
        if rc == 0:
            return None
        await self.users.add_sum(
            order["user_id"], float(order["price_amount"]),
            f"nft refund order#{order_id}", order_id,
        )
        nft = await self.by_order(order_id)
        if nft:
            await self._release(nft["id"])
        return order
