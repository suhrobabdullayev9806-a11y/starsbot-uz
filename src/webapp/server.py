# ===================================================================
# src/webapp/server.py - WebApp ADMIN PANEL + API CALLBACK SERVERI
# FastAPI asosida:
#   /admin              - Telegram WebApp sahifasi
#   /api/callback       - @Apilarimbot API qayta chaqiruvi (HMAC tekshiruvi)
#   /api/stats, orders... - admin WebApp REST API (initData auth)
# ===================================================================

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.app import App

STATIC_DIR = Path(__file__).parent / "static"


def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """
    Telegram WebApp initData ni tekshiradi.
    Hujjat: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        return None
    pairs = {}
    for chunk in init_data.split("&"):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        pairs[k] = urllib.parse.unquote_plus(v)
    received_hash = pairs.pop("hash", "")
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={pairs[k]}" for k in sorted(pairs)
    )
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256
    ).digest()
    calc = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        return None
    try:
        user = json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError:
        user = {}
    auth_date = pairs.get("auth_date", "0")
    # 24 soatdan eski bo'lsa o'tkazmaymiz
    try:
        auth_ts = int(auth_date)
    except ValueError:
        return None
    if auth_ts < int(time.time()) - 86400:
        return None
    return {"id": user.get("id"), "username": user.get("username"), "auth_date": auth_date}


def make_server(app: App) -> FastAPI:
    cfg = app.cfg

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    server = FastAPI(title="Auto Stars Admin", lifespan=lifespan)

    # Buyurtmalar keshi (admin panel 2 sekund ichida javob beradi)
    orders_cache: dict = {"ts": 0.0, "data": None}

    # ---------------------------------------------------------------
    # API CALLBACK (@Apilarimbot tomonidan chaqiriladi)
    # Headers: X-API-Signature: HMAC-SHA256(payload)
    # ---------------------------------------------------------------
    @server.post("/api/callback")
    async def api_callback(request: Request):
        body = await request.body()
        payload = body.decode("utf-8")
        sig = request.headers.get("X-API-Signature", "")
        if not app.api.verify_callback(payload, sig, cfg):
            return JSONResponse({"ok": False, "error": "bad signature"}, status_code=403)
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

        if not isinstance(data, dict):
            return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)
        try:
            order_id = int(data.get("order_id") or 0)
        except (TypeError, ValueError):
            return JSONResponse({"ok": False, "error": "bad order_id"}, status_code=400)
        status = data.get("status", "done")
        order = await app.orders.get(order_id) if order_id else None
        if not order:
            return JSONResponse({"ok": False, "error": "order not found"}, status_code=404)

        if status == "done":
            await app.payments.complete_successful(int(order_id), order["user_id"],
                                                   float(order["stars_amount"]))
        elif status in ("rejected", "canceled"):
            await app.orders.update_status(int(order_id), "rejected",
                                           data.get("note", "api rejected"))
        else:
            await app.orders.update_status(int(order_id), "processing")
        return JSONResponse({"ok": True})

    # ---------------------------------------------------------------
    # ADMIN WebApp API (initData auth)
    # ---------------------------------------------------------------
    async def admin_user(request: Request) -> int | None:
        init = request.headers.get("X-Telegram-Init-Data", "")
        info = verify_init_data(init, cfg.bot_token)
        if not info or not info.get("id") or not await app.is_admin(int(info["id"])):
            return None
        return int(info["id"])

    @server.get("/api/stats")
    async def api_stats(request: Request):
        if not await admin_user(request):
            return JSONResponse({"ok": False}, status_code=401)
        stats = await app.admin.stats()
        return {"ok": True, **stats}

    @server.get("/api/orders")
    async def api_orders(request: Request):
        if not await admin_user(request):
            return JSONResponse({"ok": False}, status_code=401)
        now = time.monotonic()
        if orders_cache["data"] is not None and now - orders_cache["ts"] < 2:
            return {"ok": True, "orders": orders_cache["data"]}
        rows = await app.orders.all_orders(100)
        orders_cache.update(ts=now, data=rows)
        return {"ok": True, "orders": rows}

    @server.post("/api/orders/{order_id}/approve")
    async def api_approve(order_id: int, request: Request):
        if not await admin_user(request):
            return JSONResponse({"ok": False}, status_code=401)
        from src.order_flow import decide_order

        ok, reason = await decide_order(app, app.bot, order_id, True)
        orders_cache["ts"] = 0.0
        return {"ok": ok, "reason": reason}

    @server.post("/api/orders/{order_id}/reject")
    async def api_reject(order_id: int, request: Request):
        if not await admin_user(request):
            return JSONResponse({"ok": False}, status_code=401)
        from src.order_flow import decide_order

        ok, reason = await decide_order(app, app.bot, order_id, False)
        orders_cache["ts"] = 0.0
        return {"ok": ok, "reason": reason}

    @server.get("/api/settings")
    async def api_settings(request: Request):
        if not await admin_user(request):
            return JSONResponse({"ok": False}, status_code=401)
        return {"ok": True,
                "prices": await app.settings.get_prices(),
                "star_price": await app.settings.get_star_price(),
                "min_stars": await app.settings.get_min_stars(),
                "post_min_stars": await app.settings.get_post_min_stars(),
                "percent": await app.settings.get_percent(),
                "active": await app.settings.bot_active(),
                "card": await app.settings.payment_card(),
                "api_enabled": await app.api.enabled()}

    @server.post("/api/settings/prices")
    async def api_set_prices(request: Request):
        if not await admin_user(request):
            return JSONResponse({"ok": False}, status_code=401)
        body = await request.json()
        prices = body.get("prices")
        if isinstance(prices, dict):
            await app.admin.set_prices({int(k): float(v) for k, v in prices.items()})
        return {"ok": True}

    from src.webapp.admin_api import register_admin_api

    register_admin_api(server, app, admin_user)

    # ---------------------------------------------------------------
    # MINI-APP (buy) — oddiy foydalanuvchi auth, admin shart emas
    # Sotib olish mini-app sahifasi /app, ma'lumot /api/me, buy /api/buy
    # ---------------------------------------------------------------
    async def any_user(request: Request) -> dict | None:
        """Har qanday tasdiqlangan Telegram foydalanuvchi (admin shart emas)."""
        init = request.headers.get("X-Telegram-Init-Data", "")
        info = verify_init_data(init, cfg.bot_token)
        return info if info and info.get("id") else None

    # SMM Nakrutka mini-app (/smm), foydalanuvchi API (/api/v2), admin sozlamalari
    from src.webapp.smm_api import register_smm_api

    register_smm_api(server, app, any_user, admin_user)

    @server.get("/app", response_class=HTMLResponse)
    async def buy_page():
        html = (STATIC_DIR / "app.html").read_text(encoding="utf-8")
        return HTMLResponse(html)

    @server.get("/api/me")
    async def api_me(request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        user_id = int(info["id"])
        user = await app.users.get(user_id) or {}
        star_price = await app.settings.get_star_price()
        min_stars = await app.settings.get_min_stars()
        api_enabled = await app.api.enabled()
        username = (user.get("username") or "") or (info.get("username") or "")
        channel, _cid = await app.settings.get_channel()
        need_sub = not await app.sub_guard.ok(app, app.bot, user_id)
        return {
            "ok": True,
            "need_sub": need_sub,
            "channel": channel,
            "user": user_id,
            "username": username,
            "first_name": user.get("first_name") or "",
            "balance_sum": float(user.get("balance_sum", 0)),
            "balance_stars": float(user.get("balance_stars", 0)),
            "star_price": star_price,
            "min_stars": min_stars,
            "api_enabled": api_enabled,
        }

    @server.get("/api/buy/prices")
    async def api_buy_prices(request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        star_price = await app.settings.get_star_price()
        min_stars = await app.settings.get_min_stars()
        pkg = {}
        if star_price > 0:
            for mult in (1, 2, 3, 5, 10):
                a = min_stars * mult
                if a <= 100000:
                    pkg[a] = round(star_price * a, 2)
        else:
            from src.utils import prices_text  # noqa: F401
            defaults = await app.settings.get_prices() or app.cfg.default_prices
            pkg = {int(k): float(v) for k, v in defaults.items()}
        return {"ok": True, "packages": pkg, "star_price": star_price, "min_stars": min_stars}

    @server.post("/api/buy")
    async def api_buy(request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        user_id = int(info["id"])
        if not await app.sub_guard.ok(app, app.bot, user_id):
            return {"ok": False, "error": "subscribe"}
        try:
            body = await request.json()
            stars = int(body.get("stars", 0))
            username = str(body.get("username", "") or "").strip().lstrip("@")
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
        star_price = await app.settings.get_star_price()
        min_stars = await app.settings.get_min_stars()
        if star_price <= 0:
            return {"ok": False, "error": "no_price"}
        if stars < min_stars:
            return {"ok": False, "error": "min_stars", "min_stars": min_stars}
        if stars > 100000:
            return {"ok": False, "error": "too_much"}
        if not username:
            return {"ok": False, "error": "need_username"}
        price = round(star_price * stars, 2)
        result = await app.payments.demand(user_id, stars, price, username)
        if not result.ok:
            return {"ok": False, "error": result.error,
                    "balance_sum": await app.users.balance_sum(user_id)}
        try:
            from src.handlers._helpers import notify_payments_channel
            if app.bot:
                await notify_payments_channel(app.bot, app, result.order_id)
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": True,
            "order_id": result.order_id,
            "stars": stars,
            "username": username,
            "price": price,
            "balance_stars": result.balance,
            "balance_sum": await app.users.balance_sum(user_id),
        }

    # ---------------------------------------------------------------
    # NFT DO'KONI (mini-app): katalog (admin t.me/nft/... + narx bilan qo'shgan)
    # Sahifa /nft, ro'yxat /api/nft/list, sotib olish /api/nft/buy
    # ---------------------------------------------------------------
    @server.get("/nft", response_class=HTMLResponse)
    async def nft_page():
        html = (STATIC_DIR / "nft.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    def _nft_public(n: dict) -> dict:
        """Mijozga faqat kerakli maydonlar (buyer_id/order_id sirt qoladi)."""
        return {
            "id": n["id"], "name": n["name"], "number": n["number"],
            "image": n["image"], "model": n["model"], "backdrop": n["backdrop"],
            "symbol": n["symbol"], "price": float(n["price"]), "url": n["url"],
        }

    @server.get("/api/nft/list")
    async def api_nft_list(request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        user_id = int(info["id"])
        channel, _cid = await app.settings.get_channel()
        need_sub = not await app.sub_guard.ok(app, app.bot, user_id)
        items = await app.nft.list_active()
        return {
            "ok": True,
            "need_sub": need_sub,
            "channel": channel,
            "balance_sum": await app.users.balance_sum(user_id),
            "username": (await app.users.get(user_id) or {}).get("username") or info.get("username") or "",
            "items": [_nft_public(n) for n in items],
        }

    @server.post("/api/nft/buy")
    async def api_nft_buy(request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        user_id = int(info["id"])
        if not await app.sub_guard.ok(app, app.bot, user_id):
            return {"ok": False, "error": "subscribe"}
        try:
            body = await request.json()
            nft_id = int(body.get("nft_id", 0))
            username = str(body.get("username", "") or "").strip().lstrip("@")
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
        import re as _re

        if not _re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", username):
            return {"ok": False, "error": "bad_username"}
        status, full_name, tg_id = await app.accounts.resolve_username(username)
        if status == "not_found":
            return {"ok": False, "error": "user_not_found"}
        await app.users.get_or_create(user_id, info.get("username") or "", "", "uz")
        recipient = f"@{username}" + (f" (id:{tg_id})" if tg_id else "")
        result = await app.nft.purchase(user_id, nft_id, recipient)
        if not result.ok:
            return {"ok": False, "error": result.error,
                    "balance_sum": await app.users.balance_sum(user_id)}
        try:
            from src.handlers.nft import notify_buyer_accepted, notify_nft_order
            if app.bot:
                await notify_buyer_accepted(app.bot, app, result.order_id)
                await notify_nft_order(app.bot, app, result.order_id)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "order_id": result.order_id, "username": username,
                "name": full_name, "verified": status == "found",
                "balance_sum": await app.users.balance_sum(user_id)}

    # ---------------------------------------------------------------
    # PUBG UC DO'KONI (mini-app): paket + PUBG ID -> nickname -> balansdan to'lov
    # Sahifa /uc, ma'lumot /api/uc/info, nickname /api/uc/lookup, xarid /api/uc/buy
    # ---------------------------------------------------------------
    uc_last_lookup: dict[int, list[float]] = {}

    @server.get("/uc", response_class=HTMLResponse)
    async def uc_page():
        html = (STATIC_DIR / "uc.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @server.get("/api/uc/info")
    async def api_uc_info(request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        user_id = int(info["id"])
        channel, _cid = await app.settings.get_channel()
        need_sub = not await app.sub_guard.ok(app, app.bot, user_id)
        ucfg = await app.settings.get_uc()
        history = await app.uc.user_history(user_id, 8)
        return {
            "ok": True,
            "need_sub": need_sub,
            "channel": channel,
            "enabled": ucfg["enabled"],
            "can_verify": bool(ucfg["lookup_url"]),
            "require_nick": ucfg["require_nick"],
            "balance_sum": await app.users.balance_sum(user_id),
            "last_pubg_id": await app.uc.last_pubg_id(user_id),
            "packages": [
                {"id": p["id"], "uc": p["uc"], "bonus": p["bonus"], "price": float(p["price"])}
                for p in await app.uc.list_active()],
            "history": [
                {"order_id": h["order_id"], "uc": h["uc"] + (h["bonus"] or 0), "price": h["price"],
                 "pubg_id": h["pubg_id"], "nickname": h["nickname"], "status": h["status"],
                 "created_at": h["created_at"]} for h in history],
        }

    @server.post("/api/uc/lookup")
    async def api_uc_lookup(request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        user_id = int(info["id"])
        # Provayderni ortiqcha yuklamaslik: bir foydalanuvchidan minutiga 20 ta
        now = time.monotonic()
        hits = [x for x in uc_last_lookup.get(user_id, []) if now - x < 60]
        if len(hits) >= 20:
            return {"ok": False, "error": "too_fast"}
        hits.append(now)
        uc_last_lookup[user_id] = hits
        if len(uc_last_lookup) > 5000:
            uc_last_lookup.clear()
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
        from src.modules.uc import normalize_pubg_id

        pid = normalize_pubg_id(body.get("pubg_id") if isinstance(body, dict) else "")
        if not pid:
            return {"ok": False, "error": "bad_pubg_id"}
        res = await app.uc.lookup(pid)
        return {"ok": True, "pubg_id": pid, "status": res["status"], "nickname": res["nickname"]}

    @server.post("/api/uc/buy")
    async def api_uc_buy(request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        user_id = int(info["id"])
        if not await app.sub_guard.ok(app, app.bot, user_id):
            return {"ok": False, "error": "subscribe"}
        try:
            body = await request.json()
            package_id = int(body.get("package_id", 0))
            pubg_id = str(body.get("pubg_id", "") or "")
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
        await app.users.get_or_create(user_id, info.get("username") or "", "", "uz")
        # Nickname mijozdan olinmaydi — serverning o'zi qayta aniqlaydi (soxtalashtirib bo'lmaydi)
        result = await app.uc.purchase(user_id, package_id, pubg_id)
        if not result.ok:
            return {"ok": False, "error": result.error,
                    "balance_sum": await app.users.balance_sum(user_id)}
        order = await app.uc.get_order(result.order_id) or {}
        try:
            from src.handlers.uc import notify_buyer_accepted, notify_uc_order
            if app.bot:
                await notify_buyer_accepted(app.bot, app, result.order_id)
                await notify_uc_order(app.bot, app, result.order_id)
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": True, "order_id": result.order_id,
            "uc": int(order.get("uc", 0)) + int(order.get("bonus", 0) or 0),
            "price": float(order.get("price", 0)),
            "pubg_id": order.get("pubg_id", ""), "nickname": order.get("nickname", ""),
            "verified": bool(order.get("verified")),
            "balance_sum": await app.users.balance_sum(user_id),
        }

    # ---------------------------------------------------------------
    # AVTO-TO'LOV (mini-app): summa -> karta rekvizitlari -> tranzaksiya ID
    # ---------------------------------------------------------------
    @server.get("/api/topup/info")
    async def api_topup_info(request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        from src.keyboards import TOPUP_PRESETS

        card = (await app.settings.payment_card() or cfg.payment_card or "").strip()
        holder = (await app.settings.payment_card_holder() or cfg.payment_card_holder or "").strip()
        return {
            "ok": True,
            "card": card,
            "holder": holder,
            "min": cfg.topup_min,
            "max": cfg.topup_max,
            "presets": [v for v in TOPUP_PRESETS if cfg.topup_min <= v <= cfg.topup_max],
            "auto": app.bank.enabled,
            "timeout": cfg.topup_verify_timeout,
        }

    def _order_reason(order: dict) -> str:
        note = str(order.get("note") or "")
        return note.split("|")[-1].strip() if "|" in note else ""

    @server.post("/api/topup/create")
    async def api_topup_create(request: Request):
        """Noyob summa bilan avto-to'lov yaratadi (mini-app uchun)."""
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        user_id = int(info["id"])
        if not await app.sub_guard.ok(app, app.bot, user_id):
            return {"ok": False, "error": "subscribe"}
        if not app.bank.enabled:
            return {"ok": False, "error": "auto_disabled"}
        try:
            body = await request.json()
            amount = float(body.get("amount", 0))
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
        card = (await app.settings.payment_card() or cfg.payment_card or "").strip()
        holder = (await app.settings.payment_card_holder() or cfg.payment_card_holder or "").strip()
        if not card:
            return {"ok": False, "error": "no_card"}
        await app.users.get_or_create(user_id, info.get("username") or "", "", "uz")
        res = await app.bank.create_topup(user_id, amount)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error", "bad_request")}
        return {
            "ok": True,
            "order_id": res["order_id"],
            "amount": res["amount"],
            "base": res.get("base", amount),
            "card": card,
            "holder": holder,
            "timeout": res.get("timeout", cfg.topup_verify_timeout),
        }

    @server.post("/api/topup/submit")
    async def api_topup_submit(request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        user_id = int(info["id"])
        if not await app.sub_guard.ok(app, app.bot, user_id):
            return {"ok": False, "error": "subscribe"}
        try:
            body = await request.json()
            amount = float(body.get("amount", 0))
            tx_id = str(body.get("tx_id", "") or "")
        except Exception:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": "bad_request"}, status_code=400)
        card = (await app.settings.payment_card() or cfg.payment_card or "").strip()
        if not card:
            return {"ok": False, "error": "no_card"}
        await app.users.get_or_create(
            user_id, info.get("username") or "", "", "uz"
        )
        res = await app.bank.submit(user_id, amount, tx_id)
        out = {
            "ok": res["status"] in ("done", "pending", "manual"),
            "status": res["status"],
            "error": "" if res["status"] in ("done", "pending", "manual") else res["reason"],
            "order_id": res["order_id"],
            "balance_sum": await app.users.balance_sum(user_id),
            "timeout": cfg.topup_verify_timeout,
        }
        if app.bot is not None:
            try:
                from src.handlers.wallet import notify_topup_result, _sp
                from src.handlers._helpers import notify_all_admins, user_ref
                from src.i18n import t
                from src.keyboards import admin_orders_kb

                order = await app.orders.get(res["order_id"]) if res["order_id"] else None
                if res["status"] == "done" and order:
                    await notify_topup_result(app.bot, app, order, "done", "ok")
                elif res["status"] == "manual" and order:
                    user = await app.users.get(user_id) or {}
                    await notify_all_admins(
                        app.bot,
                        t("uz", "topup_sent_admin", uid=user_id, user=user_ref(user),
                          amount=_sp(amount), proof=tx_id[:60]),
                        app, admin_orders_kb("uz", res["order_id"]),
                    )
            except Exception:  # noqa: BLE001
                pass
        return out

    @server.get("/api/topup/status")
    async def api_topup_status(order_id: int, request: Request):
        info = await any_user(request)
        if not info:
            return JSONResponse({"ok": False, "error": "auth"}, status_code=401)
        user_id = int(info["id"])
        order = await app.bank.check_topup(user_id, order_id)
        if not order:
            return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
        return {
            "ok": True,
            "status": order["status"],
            "reason": _order_reason(order) if order["status"] == "rejected" else "",
            "balance_sum": await app.users.balance_sum(user_id),
        }

    @server.post("/api/bank/notify")
    async def api_bank_notify(request: Request):
        """Bank/SMS bildirishnomalarini qabul qiladi (SMS-forwarder ilovalari uchun).

        Sarlavha:  X-Bank-Secret: <BANK_WEBHOOK_SECRET>
        Tana:      JSON {"text": "...", "amount": 50000, "tx_id": "123456"} yoki oddiy matn.
        """
        secret = cfg.bank_webhook_secret
        got = request.headers.get("X-Bank-Secret", "") or request.query_params.get("secret", "")
        if not secret or not hmac.compare_digest(got.encode(), secret.encode()):
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        raw_body = (await request.body())[:5000]
        text, amount, tx_id = "", None, None
        try:
            data = json.loads(raw_body.decode("utf-8", "replace"))
            if isinstance(data, dict):
                text = str(data.get("text") or data.get("message") or data.get("body") or "")
                if data.get("amount") not in (None, ""):
                    amount = float(data["amount"])
                tx_id = str(data.get("tx_id") or data.get("id") or "") or None
            else:
                text = str(data)
        except (ValueError, TypeError):
            text = raw_body.decode("utf-8", "replace")
        res = await app.bank.ingest(text, "webhook", amount=amount, tx_id=tx_id)
        return {"ok": bool(res.get("ok")), "stored": bool(res.get("stored"))}

    # Render health-check / keep-alive uchun (autentifikatsiyasiz, bazaga tegmaydi)
    @server.get("/healthz")
    @server.head("/healthz")
    async def healthz():
        return {"ok": True}

    # Sahifa va statika
    server.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @server.get("/", response_class=HTMLResponse)
    @server.get("/admin", response_class=HTMLResponse)
    async def admin_page():
        html = (STATIC_DIR / "admin.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    return server


async def serve(host: str, port: int, app: App) -> None:
    """FastAPI serverni uvicorn bilan (async task) ishga tushiradi."""
    import uvicorn

    server = make_server(app)
    config = uvicorn.Config(server, host=host, port=port, log_level="warning", log_config=None)
    await uvicorn.Server(config).serve()