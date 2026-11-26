# ===================================================================
# webapp/smm_api.py - SMM NAKRUTKA uchun REST API
#   /smm                    mini-app sahifasi
#   /api/smm/*              mini-app (Telegram initData auth)
#   /api/v2                 foydalanuvchilarga beriladigan API (kalit bilan; standart SMM-panel formati)
#   /api/adm/smm/*          admin paneldagi sozlash (faqat adminlar)
# ===================================================================

from __future__ import annotations

import functools
import json
import logging
import time
import urllib.parse
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.app import App
from src.modules.smm import PLATFORMS
from src.smm_client import SmmError

_log = logging.getLogger("stars.smm")
STATIC_DIR = Path(__file__).parent / "static"

API_RATE_LIMIT = 60        # so'rov / daqiqa / kalit
OUT_STATUS = {"pending": "Pending", "processing": "In progress", "completed": "Completed",
              "partial": "Partial", "canceled": "Canceled", "failed": "Canceled"}


def _num(v, default=0.0) -> float:
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


def _safe(fn):
    """Kutilmagan xato bo'lsa serverni yiqitmay JSON qaytaradi."""
    @functools.wraps(fn)
    async def inner(*a, **k):
        try:
            return await fn(*a, **k)
        except Exception as exc:  # noqa: BLE001
            _log.exception("smm api xatosi: %s", fn.__name__)
            return JSONResponse({"ok": False, "error": "server",
                                 "detail": f"{type(exc).__name__}"}, status_code=200)
    return inner


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def register_smm_api(server: FastAPI, app: App, any_user, admin_user) -> None:
    smm = app.smm
    cfg = app.cfg
    hits: dict[int, deque] = defaultdict(deque)

    def deny():
        return JSONResponse({"ok": False, "error": "auth"}, status_code=401)

    def base_url(request: Request) -> str:
        return (cfg.webapp_base_url or str(request.base_url)).rstrip("/")

    # ==================================================================
    # MINI-APP
    # ==================================================================
    @server.get("/smm", response_class=HTMLResponse)
    async def smm_page():
        html = (STATIC_DIR / "smm.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @server.get("/api/smm/catalog")
    @_safe
    async def smm_catalog(request: Request):
        info = await any_user(request)
        if not info:
            return deny()
        uid = int(info["id"])
        await app.users.get_or_create(uid, info.get("username") or "", "", "uz")
        s = await app.settings.get_smm()
        channel, _cid = await app.settings.get_channel()
        items = await smm.public_catalog()
        return {
            "ok": True,
            "ready": bool(s["enabled"] and s["url"] and s["key"]),
            "enabled": s["enabled"],
            "need_sub": not await app.sub_guard.ok(app, app.bot, uid),
            "channel": channel,
            "balance_sum": await app.users.balance_sum(uid),
            "platforms": PLATFORMS,
            "items": items,
        }

    @server.post("/api/smm/order")
    @_safe
    async def smm_order(request: Request):
        info = await any_user(request)
        if not info:
            return deny()
        uid = int(info["id"])
        if not await app.sub_guard.ok(app, app.bot, uid):
            return {"ok": False, "error": "subscribe"}
        b = await _body(request)
        await app.users.get_or_create(uid, info.get("username") or "", "", "uz")
        res = await smm.place_order(uid, int(_num(b.get("service_id"))),
                                    str(b.get("link", "")), int(_num(b.get("quantity"))), "app")
        if res.get("ok") and app.bot:
            try:
                from src.handlers._helpers import notify_smm_channel

                o = await smm.get_order(res["order_id"])
                if o:
                    await notify_smm_channel(app.bot, app, o, "new")
            except Exception:  # noqa: BLE001
                pass
        return res

    @server.get("/api/smm/orders")
    @_safe
    async def smm_orders(request: Request, refresh: int = 0):
        info = await any_user(request)
        if not info:
            return deny()
        uid = int(info["id"])
        if refresh:
            await smm.refresh_user(uid)
        return {"ok": True, "orders": await smm.user_orders(uid),
                "balance_sum": await app.users.balance_sum(uid)}

    @server.get("/api/smm/apikey")
    @_safe
    async def smm_apikey_info(request: Request):
        info = await any_user(request)
        if not info:
            return deny()
        s = await app.settings.get_smm()
        return {"ok": True, "enabled": s["public_api"],
                "key": await smm.key_info(int(info["id"])),
                "endpoint": f"{base_url(request)}/api/v2"}

    @server.post("/api/smm/apikey")
    @_safe
    async def smm_apikey_create(request: Request):
        info = await any_user(request)
        if not info:
            return deny()
        if not (await app.settings.get_smm())["public_api"]:
            return {"ok": False, "error": "api_disabled"}
        uid = int(info["id"])
        await app.users.get_or_create(uid, info.get("username") or "", "", "uz")
        key = await smm.create_key(uid)
        return {"ok": True, "key": key}  # to'liq kalit faqat shu javobda ko'rsatiladi

    @server.post("/api/smm/apikey/revoke")
    @_safe
    async def smm_apikey_revoke(request: Request):
        info = await any_user(request)
        if not info:
            return deny()
        return {"ok": await smm.revoke_key(int(info["id"]))}

    # ==================================================================
    # FOYDALANUVCHILARGA BERILADIGAN API  (POST /api/v2)
    #   key=...&action=services|add|status|balance
    # ==================================================================
    def api_err(msg: str):
        return JSONResponse({"error": msg}, status_code=200)

    @server.post("/api/v2")
    @_safe
    async def public_api(request: Request):
        # JSON yoki application/x-www-form-urlencoded (python-multipart talab qilinmasin)
        raw = (await request.body())[:20000]
        data: dict = {}
        if "json" in request.headers.get("content-type", ""):
            try:
                parsed = json.loads(raw.decode("utf-8", "replace"))
                data = parsed if isinstance(parsed, dict) else {}
            except ValueError:
                data = {}
        else:
            data = dict(urllib.parse.parse_qsl(raw.decode("utf-8", "replace")))
        if not data and request.query_params:
            data = dict(request.query_params)
        if not (await app.settings.get_smm())["public_api"]:
            return api_err("API is disabled")
        uid = await smm.user_by_key(str(data.get("key", "")))
        if not uid:
            return api_err("Invalid API key")
        # tezlik cheklovi
        now = time.monotonic()
        dq = hits[uid]
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= API_RATE_LIMIT:
            return api_err("Rate limit exceeded")
        dq.append(now)

        action = str(data.get("action", "")).lower()
        if action == "services":
            items = await smm.public_catalog()
            return [{"service": r["id"], "name": r["name"], "type": "Default",
                     "category": r["category"], "rate": f"{float(r['price']):.2f}",
                     "min": r["min_qty"], "max": r["max_qty"], "refill": False, "cancel": False}
                    for r in items]
        if action == "balance":
            return {"balance": f"{await app.users.balance_sum(uid):.2f}", "currency": "UZS"}
        if action == "add":
            res = await smm.place_order(uid, int(_num(data.get("service"))),
                                        str(data.get("link", "")), int(_num(data.get("quantity"))),
                                        "api")
            if res["ok"]:
                if app.bot:
                    try:
                        from src.handlers._helpers import notify_smm_channel

                        o = await smm.get_order(res["order_id"])
                        if o:
                            await notify_smm_channel(app.bot, app, o, "new")
                    except Exception:  # noqa: BLE001
                        pass
                return {"order": res["order_id"]}
            msg = {"insufficient_sum": "Not enough funds on balance",
                   "no_service": "Incorrect service ID", "bad_link": "Incorrect link",
                   "bad_qty": "Incorrect quantity", "disabled": "Service is temporarily unavailable",
                   "no_provider": "Service is temporarily unavailable",
                   "provider": "Order could not be placed, funds were returned"}
            return api_err(msg.get(res["error"], "Incorrect request"))
        if action == "status":
            await smm.refresh_user(uid)
            ids_raw = str(data.get("orders") or data.get("order") or "")
            ids = [int(x) for x in ids_raw.replace(" ", "").split(",")
                   if x.strip().isdigit()][:100]
            if not ids:
                return api_err("Incorrect order ID")
            out: dict[str, dict] = {}
            for oid in ids:
                o = await app.db.fetch_one(
                    "SELECT * FROM smm_orders WHERE id = ? AND user_id = ?", (oid, uid))
                out[str(oid)] = ({"error": "Incorrect order ID"} if not o else {
                    "charge": f"{float(o['price']) - float(o['refunded']):.2f}",
                    "start_count": str(o["start_count"]), "status": OUT_STATUS.get(o["status"], "Pending"),
                    "remains": str(o["remains"]), "currency": "UZS"})
            if "orders" not in data and len(ids) == 1:
                return out[str(ids[0])]
            return out
        return api_err("Incorrect request")

    # ==================================================================
    # ADMIN
    # ==================================================================
    def mask(key: str) -> str:
        return ("•" * 8 + key[-4:]) if len(key) > 4 else ("•" * len(key))

    @server.get("/api/adm/smm/settings")
    @_safe
    async def adm_settings(request: Request):
        if not await admin_user(request):
            return deny()
        s = await app.settings.get_smm()
        return {"ok": True, "url": s["url"], "key_set": bool(s["key"]), "key_hint": mask(s["key"]),
                "currency": s["currency"], "rate": s["rate"],
                "usd_rate": s["usd_rate"], "rub_rate": s["rub_rate"],
                "effective_rate": smm.effective_rate(s),
                "markup": s["markup"], "min_price": s["min_price"],
                "enabled": s["enabled"], "public_api": s["public_api"],
                "audit": await smm.pricing_audit(),
                "stats": await smm.stats()}

    @server.post("/api/adm/smm/settings")
    @_safe
    async def adm_save_settings(request: Request):
        if not await admin_user(request):
            return deny()
        b = await _body(request)
        upd: dict = {}
        if "url" in b:
            url = str(b["url"]).strip()
            if url and not url.lower().startswith(("http://", "https://")):
                return {"ok": False, "error": "bad_url"}
            upd["url"] = url
        if str(b.get("key", "")).strip():      # bo'sh yuborilsa eski kalit saqlanadi
            upd["key"] = str(b["key"]).strip()
        if "currency" in b:
            cur = str(b["currency"]).strip().upper()
            if cur not in ("AUTO", "UZS", "USD", "RUB"):
                return {"ok": False, "error": "bad_currency"}
            upd["currency"] = cur
        for k in ("rate", "markup", "min_price", "usd_rate", "rub_rate"):
            if k in b:
                v = _num(b[k], -1)
                if v < 0 or (k in ("rate", "usd_rate", "rub_rate") and v == 0):
                    return {"ok": False, "error": "bad_number"}
                upd[k] = v
        for k in ("enabled", "public_api"):
            if k in b:
                upd[k] = bool(b[k])
        await app.settings.set_smm(**upd)
        current = await app.settings.get_smm()
        detected = ""
        # Avto rejimda provayder balansidagi valyutani aniqlaymiz: UZS bo'lsa
        # kurs 1 bo'ladi va narxlar sun'iy ravishda qimmatlashmaydi.
        if current["url"] and current["key"] and current["currency"] == "AUTO":
            detected = await smm.detect_currency()
            if detected:
                current = await app.settings.get_smm()
        repriced = 0
        if (any(k in upd for k in ("rate", "markup", "currency", "usd_rate", "rub_rate"))
                or detected):
            repriced = await smm.reprice_all()
        # API ulanishi saqlanganda barcha xizmatlar avtomatik import qilinadi.
        imported = None
        if current["url"] and current["key"] and (
                any(k in upd for k in ("url", "key", "enabled", "currency", "usd_rate", "rub_rate"))
                or "url" in b or "key" in b):
            try:
                imported = await smm.import_services()
            except SmmError as exc:
                imported = {"error": str(exc)}
        autofixed = str((imported or {}).get("autofixed") or "") if isinstance(imported, dict) else ""
        if not autofixed:
            autofixed = await smm.autofix_auto_currency()
            if autofixed:
                repriced = await smm.reprice_all()
        current = await app.settings.get_smm()
        return {"ok": True, "repriced": repriced, "imported": imported,
                "currency": current["currency"], "detected": detected,
                "autofixed": autofixed, "audit": await smm.pricing_audit()}

    @server.post("/api/adm/smm/test")
    @_safe
    async def adm_test(request: Request):
        if not await admin_user(request):
            return deny()
        try:
            bal = await app.smm_provider.balance()
        except SmmError as exc:
            return {"ok": False, "error": "provider", "detail": str(exc)}
        before = (await app.settings.get_smm())["currency"]
        detected = await smm.detect_currency()
        autofixed = ""
        if not detected:
            autofixed = await smm.autofix_auto_currency()
        repriced = 0
        if (detected and detected != before) or autofixed:
            repriced = await smm.reprice_all()
        current = await app.settings.get_smm()
        return {"ok": True, **bal, "detected_currency": detected,
                "currency": current["currency"], "autofixed": autofixed,
                "repriced": repriced, "audit": await smm.pricing_audit()}

    @server.get("/api/adm/smm/provider/categories")
    @_safe
    async def adm_categories(request: Request, force: int = 0):
        if not await admin_user(request):
            return deny()
        try:
            return {"ok": True, "categories": await smm.provider_categories(bool(force))}
        except SmmError as exc:
            return {"ok": False, "error": "provider", "detail": str(exc)}

    @server.post("/api/adm/smm/import")
    @_safe
    async def adm_import(request: Request):
        if not await admin_user(request):
            return deny()
        b = await _body(request)
        cats = b.get("categories")
        # Kategoriya tanlanmasa yoki all=true bo'lsa — BARCHA xizmatlar import qilinadi.
        if b.get("all") or not isinstance(cats, list) or not cats:
            selected = None
        else:
            selected = [str(c) for c in cats][:500]
        try:
            if (await app.settings.get_smm())["currency"] == "AUTO":
                await smm.detect_currency()
            res = await smm.import_services(selected)
        except SmmError as exc:
            return {"ok": False, "error": "provider", "detail": str(exc)}
        return {"ok": True, **res, "audit": await smm.pricing_audit()}

    @server.get("/api/adm/smm/services")
    @_safe
    async def adm_services(request: Request, q: str = "", platform: str = "",
                           limit: int = 60, offset: int = 0):
        if not await admin_user(request):
            return deny()
        rows, total = await smm.admin_services(q, platform, limit, offset)
        return {"ok": True, "items": rows, "total": total, "platforms": PLATFORMS}

    @server.post("/api/adm/smm/services")
    @_safe
    async def adm_service_add(request: Request):
        if not await admin_user(request):
            return deny()
        b = await _body(request)
        name = str(b.get("name", "")).strip()
        price = _num(b.get("price"))
        if not name or price <= 0:
            return {"ok": False, "error": "bad_request"}
        mn = max(1, int(_num(b.get("min_qty"), 10)))
        mx = max(mn, int(_num(b.get("max_qty"), 10000)))
        sid = await smm.add_service(
            name=name, category=str(b.get("category", "")), platform=str(b.get("platform", "")),
            provider_id=str(b.get("provider_id", "")), price=price, min_qty=mn, max_qty=mx,
            description=str(b.get("description", "")))
        return {"ok": True, "id": sid}

    @server.post("/api/adm/smm/services/bulk")
    @_safe
    async def adm_service_bulk(request: Request):
        if not await admin_user(request):
            return deny()
        b = await _body(request)
        n = await smm.bulk(str(b.get("action", "")), str(b.get("category", "")),
                           str(b.get("platform", "")))
        return {"ok": n > 0, "count": n, "error": "" if n else "nothing"}

    @server.post("/api/adm/smm/services/{service_id}/update")
    @_safe
    async def adm_service_update(service_id: int, request: Request):
        if not await admin_user(request):
            return deny()
        b = await _body(request)
        f = {k: b[k] for k in ("name", "category", "description", "provider_id", "platform", "active")
             if k in b}
        if "price" in b:
            f["price"] = _num(b["price"], -1)
            if f["price"] < 0:
                return {"ok": False, "error": "bad_number"}
        for k in ("min_qty", "max_qty", "sort"):
            if k in b:
                f[k] = int(_num(b[k]))
        if b.get("auto_price") is True:
            f["auto_price"] = True
            f.pop("price", None)
        ok = await smm.update_service(service_id, **f)
        return {"ok": ok, "error": "" if ok else "not_found"}

    @server.post("/api/adm/smm/services/{service_id}/delete")
    @_safe
    async def adm_service_delete(service_id: int, request: Request):
        if not await admin_user(request):
            return deny()
        ok = await smm.delete_service(service_id)
        return {"ok": ok, "error": "" if ok else "not_found"}

    @server.get("/api/adm/smm/orders")
    @_safe
    async def adm_orders(request: Request, status: str = "", limit: int = 80):
        if not await admin_user(request):
            return deny()
        return {"ok": True, "orders": await smm.admin_orders(status, limit)}

    @server.post("/api/adm/smm/orders/{order_id}/cancel")
    @_safe
    async def adm_order_cancel(order_id: int, request: Request):
        if not await admin_user(request):
            return deny()
        ok = await smm.admin_cancel(order_id)
        return {"ok": ok, "error": "" if ok else "already_processed"}

    @server.post("/api/adm/smm/sync")
    @_safe
    async def adm_sync(request: Request):
        if not await admin_user(request):
            return deny()
        return {"ok": True, "changed": await smm.sync_orders()}
