# ===================================================================
# webapp/admin_api.py - TO'LIQ ADMIN MINI-APP uchun REST API  (/api/adm/*)
# Auth: Telegram initData + admin ro'yxati (.env + panel orqali qo'shilganlar).
# ===================================================================

from __future__ import annotations

import dataclasses
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.app import App
from src.nft_parser import NftUrlError, fetch_nft
from src.order_flow import decide_order

_log = logging.getLogger("stars.adm")


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


def register_admin_api(server: FastAPI, app: App, admin_user) -> None:
    """admin_user: async (Request) -> int | None."""

    _orig_get, _orig_post = server.get, server.post

    def _safe(deco):
        def outer(path, **kw):
            reg = deco(path, **kw)

            def wrap(fn):
                import functools

                @functools.wraps(fn)
                async def inner(*a, **k):
                    try:
                        return await fn(*a, **k)
                    except Exception as exc:  # noqa: BLE001
                        _log.exception("admin api xatosi: %s", path)
                        return JSONResponse(
                            {"ok": False, "error": "server",
                             "detail": f"{type(exc).__name__}: {exc}"[:200]})
                return reg(inner)
            return wrap
        return outer

    class _S:  # faqat shu ro'yxatdagi endpointlar uchun himoyalangan dekoratorlar
        get = staticmethod(_safe(_orig_get))
        post = staticmethod(_safe(_orig_post))

    def deny():
        return JSONResponse({"ok": False, "error": "auth"}, status_code=401)

    async def body_of(request: Request) -> dict:
        try:
            data = await request.json()
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    # ---------- Umumiy ko'rinish ----------
    @_S.get("/api/adm/overview")
    async def overview(request: Request):
        if not await admin_user(request):
            return deny()
        stats = await app.admin.stats(ttl=5)
        db = app.db
        pending = await db.fetch_one(
            "SELECT COUNT(*) AS c FROM orders WHERE status IN ('pending','processing')")
        nft_rows = await db.fetch_all("SELECT status, COUNT(*) AS c FROM nfts GROUP BY status")
        accounts = await app.accounts.list_all()
        post = await db.fetch_one(
            "SELECT COUNT(*) AS c, COALESCE(SUM(stars_amount),0) AS s FROM orders "
            "WHERE type='post_stars' AND status='done'")
        nft_sold = await db.fetch_one(
            "SELECT COUNT(*) AS c, COALESCE(SUM(price_amount),0) AS s FROM orders "
            "WHERE type='nft' AND status='done'")
        uc_done = await db.fetch_one(
            "SELECT COUNT(*) AS c, COALESCE(SUM(price_amount),0) AS s FROM orders "
            "WHERE type='uc' AND status='done'")
        return {
            "ok": True, **stats,
            "uc_done": uc_done,
            "pending": (pending or {}).get("c", 0),
            "nft": {r["status"]: r["c"] for r in nft_rows},
            "accounts": {"total": len(accounts),
                         "active": sum(1 for a in accounts if a.get("status") == "active")},
            "post_done": post, "nft_sold": nft_sold,
            "bot_active": await app.settings.bot_active(),
            "webapp": app.cfg.webapp_base_url or "",
        }

    # ---------- Buyurtmalar ----------
    @_S.get("/api/adm/orders")
    async def orders(request: Request, status: str = "", type: str = "", limit: int = 80):
        if not await admin_user(request):
            return deny()
        where, args = [], []
        if status == "pending":
            where.append("status IN ('pending','processing')")
        elif status:
            where.append("status = ?"); args.append(status)
        if type:
            where.append("type = ?"); args.append(type)
        sql = "SELECT * FROM orders" + (" WHERE " + " AND ".join(where) if where else "")
        rows = await app.db.fetch_all(sql + " ORDER BY id DESC LIMIT ?",
                                      (*args, max(1, min(limit, 200))))
        return {"ok": True, "orders": rows}

    @_S.post("/api/adm/orders/{order_id}/{action}")
    async def order_action(order_id: int, action: str, request: Request):
        if not await admin_user(request):
            return deny()
        if action not in ("approve", "reject"):
            return JSONResponse({"ok": False, "error": "bad_action"}, status_code=400)
        ok, reason = await decide_order(app, app.bot, order_id, action == "approve")
        return {"ok": ok, "reason": reason}

    # ---------- NFT ----------
    @_S.get("/api/adm/nfts")
    async def nfts(request: Request):
        if not await admin_user(request):
            return deny()
        return {"ok": True, "items": await app.nft.list_all()}

    @_S.post("/api/adm/nfts/preview")
    async def nft_preview(request: Request):
        if not await admin_user(request):
            return deny()
        b = await body_of(request)
        try:
            info = await fetch_nft(str(b.get("url", "")))
        except NftUrlError:
            return {"ok": False, "error": "bad_url"}
        dup = await app.nft.find_by_slug(info.slug)
        return {"ok": True, "info": dataclasses.asdict(info),
                "duplicate": dup["id"] if dup else None}

    @_S.post("/api/adm/nfts")
    async def nft_add(request: Request):
        if not await admin_user(request):
            return deny()
        b = await body_of(request)
        price = _num(b.get("price"))
        if price <= 0:
            return {"ok": False, "error": "bad_price"}
        try:
            info = await fetch_nft(str(b.get("url", "")))
        except NftUrlError:
            return {"ok": False, "error": "bad_url"}
        if await app.nft.find_by_slug(info.slug):
            return {"ok": False, "error": "duplicate"}
        nft_id = await app.nft.add(info, price)
        return {"ok": True, "id": nft_id}

    @_S.post("/api/adm/nfts/{nft_id}/update")
    async def nft_update(nft_id: int, request: Request):
        if not await admin_user(request):
            return deny()
        b = await body_of(request)
        fields = {k: b.get(k) for k in ("name", "number", "image", "model", "backdrop", "symbol")
                  if k in b}
        if "price" in b:
            price = _num(b.get("price"))
            if price <= 0:
                return {"ok": False, "error": "bad_price"}
            fields["price"] = price
        if "number" in fields:
            fields["number"] = int(_num(fields["number"]))
        if "name" in fields and not str(fields["name"] or "").strip():
            return {"ok": False, "error": "bad_request"}
        ok = await app.nft.update(nft_id, **fields)
        return {"ok": ok, "error": "" if ok else "not_found"}

    @_S.post("/api/adm/nfts/{nft_id}/price")
    async def nft_price(nft_id: int, request: Request):
        if not await admin_user(request):
            return deny()
        price = _num((await body_of(request)).get("price"))
        if price <= 0:
            return {"ok": False, "error": "bad_price"}
        return {"ok": await app.nft.set_price(nft_id, price)}

    @_S.post("/api/adm/nfts/{nft_id}/delete")
    async def nft_delete(nft_id: int, request: Request):
        if not await admin_user(request):
            return deny()
        ok = await app.nft.remove(nft_id)
        return {"ok": ok, "error": "" if ok else "not_active"}

    # ---------- PUBG UC ----------
    UC_ERR = {"bad_uc": "bad_uc", "bad_price": "bad_price"}

    @_S.get("/api/adm/uc/stats")
    async def uc_stats(request: Request):
        if not await admin_user(request):
            return deny()
        return {"ok": True, **await app.uc.stats()}

    @_S.get("/api/adm/uc/orders")
    async def uc_orders(request: Request, status: str = "", q: str = "", limit: int = 60):
        if not await admin_user(request):
            return deny()
        return {"ok": True, "orders": await app.uc.list_orders(status, q, limit)}

    @_S.get("/api/adm/uc/packages")
    async def uc_packages(request: Request):
        if not await admin_user(request):
            return deny()
        return {"ok": True, "items": await app.uc.list_all()}

    @_S.post("/api/adm/uc/packages")
    async def uc_package_add(request: Request):
        if not await admin_user(request):
            return deny()
        b = await body_of(request)
        try:
            pid = await app.uc.add_package(int(_num(b.get("uc"))), _num(b.get("price")),
                                           int(_num(b.get("bonus"))))
        except ValueError as exc:
            return {"ok": False, "error": UC_ERR.get(str(exc), "bad_request")}
        return {"ok": True, "id": pid}

    @_S.post("/api/adm/uc/packages/{package_id}/update")
    async def uc_package_update(package_id: int, request: Request):
        if not await admin_user(request):
            return deny()
        b = await body_of(request)
        fields = {}
        for k in ("uc", "bonus", "sort"):
            if k in b:
                fields[k] = int(_num(b[k]))
        if "price" in b:
            fields["price"] = _num(b["price"])
        if "active" in b:
            fields["active"] = bool(b["active"])
        try:
            ok = await app.uc.update_package(package_id, **fields)
        except ValueError as exc:
            return {"ok": False, "error": UC_ERR.get(str(exc), "bad_request")}
        return {"ok": ok, "error": "" if ok else "not_found"}

    @_S.post("/api/adm/uc/packages/{package_id}/delete")
    async def uc_package_delete(package_id: int, request: Request):
        if not await admin_user(request):
            return deny()
        ok = await app.uc.delete_package(package_id)
        return {"ok": ok, "error": "" if ok else "not_found"}

    @_S.get("/api/adm/uc/settings")
    async def uc_settings(request: Request):
        if not await admin_user(request):
            return deny()
        c = await app.settings.get_uc()
        return {"ok": True, "enabled": c["enabled"], "require_nick": c["require_nick"],
                "lookup_url": c["lookup_url"], "lookup_path": c["lookup_path"],
                "key_set": bool(c["lookup_key"])}

    @_S.post("/api/adm/uc/settings")
    async def uc_settings_save(request: Request):
        if not await admin_user(request):
            return deny()
        b = await body_of(request)
        url = str(b.get("lookup_url", "") or "").strip()
        if url and (not url.lower().startswith(("http://", "https://")) or "{id}" not in url):
            return {"ok": False, "error": "bad_lookup_url"}
        kw: dict = {}
        if "lookup_url" in b:
            kw["lookup_url"] = url
        if "lookup_path" in b:
            kw["lookup_path"] = str(b["lookup_path"] or "").strip()[:80]
        if str(b.get("lookup_key", "") or "").strip():
            kw["lookup_key"] = str(b["lookup_key"]).strip()[:300]
        if b.get("clear_key"):
            kw["lookup_key"] = ""
        for k in ("enabled", "require_nick"):
            if k in b:
                kw[k] = bool(b[k])
        await app.settings.set_uc(**kw)
        app.uc._cache.clear()
        return {"ok": True}

    @_S.post("/api/adm/uc/lookup")
    async def uc_lookup_test(request: Request):
        """Sozlamani sinash: PUBG ID bo'yicha nickname aniqlanadimi?"""
        if not await admin_user(request):
            return deny()
        from src.modules.uc import normalize_pubg_id

        pid = normalize_pubg_id((await body_of(request)).get("pubg_id"))
        if not pid:
            return {"ok": False, "error": "bad_pubg_id"}
        app.uc._cache.pop(pid, None)
        res = await app.uc.lookup(pid)
        return {"ok": True, **res}

    # ---------- Foydalanuvchilar ----------
    @_S.get("/api/adm/users")
    async def users(request: Request, q: str = ""):
        if not await admin_user(request):
            return deny()
        return {"ok": True, "users": await app.users.search(q, 30)}

    @_S.post("/api/adm/users/{user_id}/balance")
    async def user_balance(user_id: int, request: Request):
        if not await admin_user(request):
            return deny()
        b = await body_of(request)
        amount = round(_num(b.get("amount")), 2)
        if amount <= 0 or not await app.users.get(user_id):
            return {"ok": False, "error": "bad_request"}
        add = bool(b.get("add", True))
        kind = b.get("kind", "sum")
        if kind == "stars":
            res = await (app.users.add_balance if add else app.users.sub_balance)(
                user_id, amount, "admin mini-app balance", None)
        else:
            res = await (app.users.add_sum if add else app.users.sub_sum)(
                user_id, amount, "admin mini-app balance", None)
        if res < 0:
            return {"ok": False, "error": "insufficient"}
        return {"ok": True, "balance": res}

    # ---------- Sozlamalar ----------
    @_S.get("/api/adm/settings")
    async def get_settings(request: Request):
        if not await admin_user(request):
            return deny()
        s = app.settings
        pay_channel, _pay_id = await s.get_payment_channel()
        return {"ok": True, "star_price": await s.get_star_price(),
                "post_price": await s.get_post_price(),
                "post_min_stars": await s.get_post_min_stars(),
                "min_stars": await s.get_min_stars(),
                "percent": await s.get_percent(),
                "active": await s.bot_active(),
                "card": await s.payment_card(),
                "card_holder": await s.payment_card_holder(),
                "pay_channel": pay_channel,
                "channels": [c.get("username") or c.get("chat_id") or ""
                             for c in await s.get_channels()]}

    @_S.post("/api/adm/settings")
    async def save_settings(request: Request):
        if not await admin_user(request):
            return deny()
        b = await body_of(request)
        a = app.admin
        if "star_price" in b and _num(b["star_price"]) >= 0:
            await a.set_star_price(_num(b["star_price"]))
        if "post_price" in b and _num(b["post_price"]) >= 0:
            await a.set_post_price(_num(b["post_price"]))
        if "post_min_stars" in b and int(_num(b["post_min_stars"])) > 0:
            await a.set_post_min_stars(int(_num(b["post_min_stars"])))
        if "percent" in b and _num(b["percent"]) >= 0:
            await a.set_percent(_num(b["percent"]))
        if "card" in b and str(b["card"]).strip():
            await a.set_card(str(b["card"]).strip()[:40])
        if "card_holder" in b:
            await app.settings.set_payment_card_holder(str(b["card_holder"]).strip()[:60])
        if "pay_channel" in b:
            raw = str(b["pay_channel"] or "").strip()
            if not raw:
                await app.settings.clear_payment_channel()
            else:
                uname = raw.replace("https://t.me/", "").replace("t.me/", "").lstrip("@").strip()
                chat_id = ""
                if uname and app.bot:
                    try:
                        chat = await app.bot.get_chat("@" + uname)
                        chat_id = str(chat.id)
                        uname = chat.username or uname
                    except Exception:  # noqa: BLE001
                        pass
                if uname:
                    await app.settings.set_payment_channel(uname, chat_id)
        if "channels" in b:
            items: list[dict] = []
            seen: set[str] = set()
            for part in str(b["channels"] or "").replace(";", ",").replace("\n", ",").split(","):
                raw = part.strip().replace("https://t.me/", "").replace("t.me/", "").lstrip("@")
                if not raw or raw.lower() in seen:
                    continue
                seen.add(raw.lower())
                uname, chat_id = raw, ""
                numeric = raw.lstrip("-")
                if numeric.isdigit():
                    uname = ""
                    chat_id = raw
                    if app.bot:
                        try:
                            chat = await app.bot.get_chat(int(raw))
                            chat_id = str(chat.id)
                            uname = chat.username or ""
                        except Exception:  # noqa: BLE001
                            pass
                elif app.bot:
                    try:
                        chat = await app.bot.get_chat("@" + raw)
                        chat_id = str(chat.id)
                        uname = chat.username or raw
                    except Exception:  # noqa: BLE001
                        pass
                items.append({"username": uname, "chat_id": chat_id})
            await app.settings.set_channels(items)
        if "active" in b and bool(b["active"]) != await app.settings.bot_active():
            await a.toggle_bot()
        return {"ok": True}

    # ---------- Akkauntlar ----------
    @_S.get("/api/adm/accounts")
    async def accounts(request: Request):
        if not await admin_user(request):
            return deny()
        rows = await app.accounts.list_all()
        return {"ok": True, "accounts": [
            {"id": r["id"], "title": r.get("title"), "status": r.get("status"),
             "created_at": r.get("created_at")} for r in rows]}

    @_S.post("/api/adm/accounts/{account_id}/test")
    async def account_test(account_id: int, request: Request):
        if not await admin_user(request):
            return deny()
        ok, msg = await app.accounts.test_connection(account_id)
        return {"ok": ok, "message": msg}
