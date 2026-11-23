# ===================================================================
# tests/test_smm.py - SMM Nakrutka: narx, buyurtma, qaytarish, sinxronlash, API kalitlar
# Haqiqiy provayderga so'rov yuborilmaydi (FakeProvider).
# ===================================================================

from __future__ import annotations

import asyncio

from src.modules.smm import SmmModule, detect_platform, map_status
from src.smm_client import SmmError


class FakeProvider:
    def __init__(self):
        self.fail = False
        self.sent: list[tuple] = []
        self.infos: dict[str, dict] = {}
        self.raw_services: list[dict] = []
        self._n = 100

    async def configured(self):
        return True

    async def add(self, service, link, quantity):
        if self.fail:
            raise SmmError("Not enough funds")
        self._n += 1
        self.sent.append((service, link, quantity))
        return str(self._n)

    async def status(self, order_id):
        return self.infos.get(order_id, {"status": "In progress", "remains": "0"})

    async def statuses(self, ids):
        return {i: self.infos[i] for i in ids if i in self.infos}

    async def services(self):
        return self.raw_services

    async def balance(self):
        return {"balance": "10", "currency": "USD"}


async def _setup(app, balance=10000.0, price=1000.0):
    fake = FakeProvider()
    app.smm.provider = fake
    app.smm_provider = fake
    await app.settings.set_smm(url="https://p.example/api/v2", key="secret", rate=1, markup=0)
    await app.users.get_or_create(1, "ali", "Ali", "uz")
    if balance:
        await app.users.add_sum(1, balance, "test")
    sid = await app.smm.add_service(name="TG obunachi", category="Telegram obunachilar",
                                    provider_id="77", price=price, min_qty=10, max_qty=100000)
    return fake, sid


def test_pure_helpers():
    assert SmmModule.calc_price(1000, 500) == 500
    assert SmmModule.calc_price(1234, 3) == 4          # yuqoriga yaxlitlanadi
    assert SmmModule.calc_price(0.001, 10) == 1         # minimal 1 so'm
    assert SmmModule.auto_price(2.0, 12500, 30) == 32500
    assert detect_platform("Telegram obunachilar", "") == "telegram"
    assert detect_platform("Instagram Likes", "") == "instagram"
    assert detect_platform("TikTok views", "") == "tiktok"
    assert detect_platform("Random", "") == "other"
    assert map_status("In progress") == "processing"
    assert map_status("Completed") == "completed"
    assert map_status("Partial") == "partial"
    assert map_status("Refunded") == "canceled"


async def test_order_debits_and_sends(app):
    fake, sid = await _setup(app)
    r = await app.smm.place_order(1, sid, "https://t.me/mychannel", 500)
    assert r["ok"] and r["price"] == 500 and r["balance"] == 9500
    assert fake.sent == [("77", "https://t.me/mychannel", 500)]
    o = (await app.smm.user_orders(1))[0]
    assert o["status"] == "processing" and o["quantity"] == 500
    assert await app.users.balance_sum(1) == 9500


async def test_insufficient_balance_changes_nothing(app):
    fake, sid = await _setup(app, balance=100)
    r = await app.smm.place_order(1, sid, "@mychannel", 500)
    assert not r["ok"] and r["error"] == "insufficient_sum"
    assert await app.users.balance_sum(1) == 100
    assert await app.smm.user_orders(1) == [] and fake.sent == []


async def test_provider_failure_refunds(app):
    fake, sid = await _setup(app)
    fake.fail = True
    r = await app.smm.place_order(1, sid, "@mychannel", 500)
    assert not r["ok"] and r["error"] == "provider"
    assert await app.users.balance_sum(1) == 10000
    o = (await app.smm.admin_orders())[0]
    assert o["status"] == "failed" and o["refunded"] == 500


async def test_validation_and_switches(app):
    fake, sid = await _setup(app)
    assert (await app.smm.place_order(1, sid, "not a link", 500))["error"] == "bad_link"
    assert (await app.smm.place_order(1, sid, "@mychannel", 5))["error"] == "bad_qty"
    assert (await app.smm.place_order(1, sid, "@mychannel", 10**7))["error"] == "bad_qty"
    assert (await app.smm.place_order(1, 9999, "@mychannel", 50))["error"] == "no_service"
    await app.settings.set_smm(enabled=False)
    assert (await app.smm.place_order(1, sid, "@mychannel", 50))["error"] == "disabled"
    await app.settings.set_smm(enabled=True, key="")
    assert (await app.smm.place_order(1, sid, "@mychannel", 50))["error"] == "no_provider"
    assert await app.users.balance_sum(1) == 10000 and fake.sent == []


async def test_duplicate_guard_only_for_app(app):
    fake, sid = await _setup(app)
    assert (await app.smm.place_order(1, sid, "@mychannel", 50))["ok"]
    assert (await app.smm.place_order(1, sid, "@mychannel", 50))["error"] == "duplicate"
    assert (await app.smm.place_order(1, sid, "@mychannel", 50, source="api"))["ok"]


async def test_sync_completed_no_refund(app):
    fake, sid = await _setup(app)
    r = await app.smm.place_order(1, sid, "@mychannel", 500)
    fake.infos["101"] = {"status": "Completed", "remains": "0", "start_count": "40"}
    assert await app.smm.sync_orders() == 1
    o = (await app.smm.user_orders(1))[0]
    assert o["status"] == "completed" and o["refunded"] == 0 and o["start_count"] == 40
    assert await app.users.balance_sum(1) == 9500
    assert r["ok"]


async def test_sync_canceled_refunds_once(app):
    fake, sid = await _setup(app)
    await app.smm.place_order(1, sid, "@mychannel", 500)
    fake.infos["101"] = {"status": "Canceled", "remains": "500"}
    await app.smm.sync_orders()
    await app.smm.sync_orders()
    assert await app.users.balance_sum(1) == 10000     # ikki marta qaytarilmaydi
    o = (await app.smm.user_orders(1))[0]
    assert o["status"] == "canceled" and o["refunded"] == 500


async def test_partial_refunds_proportionally(app):
    fake, sid = await _setup(app)
    await app.smm.place_order(1, sid, "@mychannel", 500)
    fake.infos["101"] = {"status": "Partial", "remains": "100"}
    await app.smm.sync_orders()
    o = (await app.smm.user_orders(1))[0]
    assert o["status"] == "partial" and o["refunded"] == 100.0
    assert await app.users.balance_sum(1) == 9600


async def test_result_callback_fires_once(app):
    fake, sid = await _setup(app)
    seen = []

    async def cb(order, outcome):
        seen.append((order["id"], outcome))

    app.smm.on_result = cb
    await app.smm.place_order(1, sid, "@mychannel", 500)
    fake.infos["101"] = {"status": "Completed", "remains": "0"}
    await app.smm.sync_orders()
    await app.smm.sync_orders()
    assert seen == [(1, "completed")]


async def test_admin_cancel_refunds_once(app):
    fake, sid = await _setup(app)
    r = await app.smm.place_order(1, sid, "@mychannel", 500)
    assert await app.smm.admin_cancel(r["order_id"]) is True
    assert await app.smm.admin_cancel(r["order_id"]) is False
    assert await app.users.balance_sum(1) == 10000


async def test_concurrent_orders_cannot_overspend(app):
    fake, sid = await _setup(app, balance=1000, price=1000)
    results = await asyncio.gather(*[
        app.smm.place_order(1, sid, f"@chan{i}", 500) for i in range(5)])
    assert sum(1 for r in results if r["ok"]) == 2
    assert await app.users.balance_sum(1) == 0


async def test_api_keys(app):
    await app.users.get_or_create(1, "ali", "Ali", "uz")
    k1 = await app.smm.create_key(1)
    assert k1.startswith("smm_") and await app.smm.user_by_key(k1) == 1
    info = await app.smm.key_info(1)
    assert info["prefix"] != k1 and k1 not in str(info)   # to'liq kalit saqlanmaydi
    k2 = await app.smm.create_key(1)
    assert await app.smm.user_by_key(k1) is None and await app.smm.user_by_key(k2) == 1
    assert await app.smm.revoke_key(1) and await app.smm.user_by_key(k2) is None
    assert await app.smm.user_by_key("") is None


async def test_import_and_reprice(app):
    fake, _ = await _setup(app, balance=0)
    fake.raw_services = [
        {"service": "1", "name": "TG Members", "category": "Telegram Members", "rate": "2.0", "min": "10", "max": "5000"},
        {"service": "2", "name": "IG Likes", "category": "Instagram Likes", "rate": "1.0", "min": "10", "max": "5000"},
        {"service": "3", "name": "Zero", "category": "Telegram Members", "rate": "0", "min": "1", "max": "9"},
    ]
    cats = await app.smm.provider_categories(force=True)
    assert {c["category"] for c in cats} == {"Telegram Members", "Instagram Likes"}
    await app.settings.set_smm(rate=12000, markup=25)
    res = await app.smm.import_services(["Telegram Members"])
    assert res == {"added": 1, "skipped": 1}
    assert (await app.smm.import_services(["Telegram Members"]))["added"] == 0   # takroran qo'shilmaydi
    svc = [s for s in await app.smm.list_services() if s["provider_id"] == "1"][0]
    assert svc["price"] == 30000 and svc["platform"] == "telegram"
    await app.settings.set_smm(rate=13000)
    assert await app.smm.reprice_all() >= 1
    svc = [s for s in await app.smm.list_services() if s["provider_id"] == "1"][0]
    assert svc["price"] == 32500
    # qo'lda narx qo'yilsa avto-narx o'chadi
    await app.smm.update_service(svc["id"], price=40000)
    await app.settings.set_smm(rate=20000)
    await app.smm.reprice_all()
    svc = [s for s in await app.smm.list_services() if s["provider_id"] == "1"][0]
    assert svc["price"] == 40000 and svc["auto_price"] == 0


async def test_public_catalog_hides_provider_data(app):
    fake, sid = await _setup(app, balance=0)
    await app.smm.add_service(name="Hidden", provider_id="9", price=0, auto_price=False)  # narxsiz
    cat = await app.smm.public_catalog()
    assert [c["name"] for c in cat] == ["TG obunachi"]
    assert "provider_id" not in cat[0] and "cost" not in cat[0]


async def test_bulk_requires_filter(app):
    fake, sid = await _setup(app, balance=0)
    assert await app.smm.bulk("delete") == 0
    assert await app.smm.bulk("deactivate", platform="telegram") == 1
    assert await app.smm.public_catalog() == []
