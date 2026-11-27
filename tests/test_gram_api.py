# ===================================================================
# test_gram_api.py - Gram mini-app va admin API integratsiyasi
# ===================================================================

import hashlib
import hmac
import json
import time
import urllib.parse

import httpx

from src.webapp.server import make_server

ADDR = "UQ" + "A" * 46


def init_data(user_id: int, username: str = "ali", token: str = "123:TESTTOKEN") -> str:
    """Telegram WebApp initData imzosini yaratadi (test uchun)."""
    pairs = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "username": username}, separators=(",", ":")),
    }
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(pairs)


def client_for(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_server(app)),
        base_url="http://test",
    )


def headers(uid: int, username: str = "ali") -> dict:
    return {"X-Telegram-Init-Data": init_data(uid, username)}


async def test_gram_page_and_user_buy_flow(app):
    await app.users.get_or_create(10, "ali", "Ali", "uz")
    await app.users.add_sum(10, 100_000, "test")
    pkg = (await app.gram.list_active())[0]

    async with client_for(app) as c:
        page = await c.get("/gram")
        assert page.status_code == 200 and "Gram olish" in page.text

        info = await c.get("/api/gram/info", headers=headers(10))
        assert info.status_code == 200
        data = info.json()
        assert data["ok"] and data["enabled"] and not data["need_sub"]
        assert data["balance_sum"] == 100_000
        assert len(data["packages"]) == 6

        buy = await c.post(
            "/api/gram/buy",
            headers=headers(10),
            json={"package_id": pkg["id"], "wallet": "  " + ADDR + "  "},
        )
        assert buy.status_code == 200 and buy.json()["ok"]
        result = buy.json()
        assert result["wallet"] == ADDR and result["wallet_kind"] == "address"
        assert result["balance_sum"] == 100_000 - pkg["price"]

        order = await app.gram.get_order(result["order_id"])
        assert order["wallet"] == ADDR and order["username"] == "ali"
        assert order["status"] == "pending"

        bad = await c.post(
            "/api/gram/buy",
            headers=headers(10),
            json={"package_id": pkg["id"], "wallet": "12ab"},
        )
        assert bad.json()["error"] == "bad_wallet"

        info2 = await c.get("/api/gram/info", headers=headers(10))
        assert info2.json()["last_wallet"] == ADDR
        assert len(info2.json()["history"]) == 1

        noauth = await c.get("/api/gram/info")
        assert noauth.status_code == 401


async def test_gram_admin_packages_and_order_decisions(app):
    await app.users.get_or_create(20, "vali", "Vali", "uz")
    await app.users.add_sum(20, 1_000_000, "test")
    pkg = (await app.gram.list_active())[0]

    async with client_for(app) as c:
        created = await c.post(
            "/api/adm/gram/packages",
            headers=headers(111, "admin"),
            json={"grams": "2.5", "price": "33000"},
        )
        assert created.json()["ok"]
        new_id = created.json()["id"]

        listed = await c.get("/api/adm/gram/packages", headers=headers(111, "admin"))
        assert new_id in [p["id"] for p in listed.json()["items"]]

        updated = await c.post(
            f"/api/adm/gram/packages/{new_id}/update",
            headers=headers(111, "admin"),
            json={"price": "35000", "active": False},
        )
        assert updated.json()["ok"]
        row = await app.gram.get_package(new_id)
        assert row["price"] == 35000 and row["active"] == 0

        deleted = await c.post(
            f"/api/adm/gram/packages/{new_id}/delete",
            headers=headers(111, "admin"),
        )
        assert deleted.json()["ok"]
        assert await app.gram.get_package(new_id) is None

        denied = await c.get("/api/adm/gram/stats", headers=headers(10))
        assert denied.status_code == 401

        buy = await c.post(
            "/api/gram/buy",
            headers=headers(20, "vali"),
            json={"package_id": pkg["id"], "wallet": "@Friend_01"},
        )
        order_id = buy.json()["order_id"]
        orders = await c.get("/api/adm/gram/orders", headers=headers(111, "admin"))
        assert orders.json()["ok"]
        assert order_id in [o["order_id"] for o in orders.json()["orders"]]

        stats = await c.get("/api/adm/gram/stats", headers=headers(111, "admin"))
        assert stats.json()["ok"]
        assert stats.json()["pending"]["c"] == 1

        approved = await c.post(
            f"/api/adm/orders/{order_id}/approve", headers=headers(111, "admin"))
        assert approved.json()["ok"]
        assert (await app.gram.get_order(order_id))["status"] == "done"

        buy2 = await c.post(
            "/api/gram/buy",
            headers=headers(20, "vali"),
            json={"package_id": pkg["id"], "wallet": ADDR},
        )
        order2 = buy2.json()["order_id"]
        before = await app.users.balance_sum(20)
        rejected = await c.post(
            f"/api/adm/orders/{order2}/reject", headers=headers(111, "admin"))
        assert rejected.json()["ok"]
        assert await app.users.balance_sum(20) == before + pkg["price"]
        assert (await app.gram.get_order(order2))["status"] == "rejected"
