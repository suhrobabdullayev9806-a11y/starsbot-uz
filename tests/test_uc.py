# ===================================================================
# test_uc.py - PUBG UC moduli: paketlar, nickname, xarid, qaytarish, statistika
# ===================================================================

import asyncio

from src.modules.uc import clean_nickname, extract_nickname, normalize_pubg_id


def fake_fetcher(table: dict, calls: list | None = None):
    """url ichidagi PUBG ID bo'yicha (status, json) qaytaradi."""

    async def fetch(url, headers):
        if calls is not None:
            calls.append(url)
        for pid, resp in table.items():
            if pid in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        return 404, None

    return fetch


async def setup_lookup(app, table, **extra):
    await app.settings.set_uc(lookup_url="https://x.test/p/{id}", lookup_path="data.nickname", **extra)
    app.uc._fetch = fake_fetcher(table)


async def funded_user(app, uid=10, amount=1_000_000):
    await app.users.get_or_create(uid, "ali", "Ali", "uz")
    await app.users.add_sum(uid, amount, "test topup")


# ---------- sof funksiyalar ----------

def test_normalize_pubg_id():
    assert normalize_pubg_id(" 5123 456-789 ") == "5123456789"
    assert normalize_pubg_id("abc") is None
    assert normalize_pubg_id("1234") is None
    assert normalize_pubg_id("1" * 15) is None
    assert normalize_pubg_id(None) is None


def test_extract_nickname_paths_and_fallbacks():
    assert extract_nickname({"data": {"nickname": "Zoir"}}, "data.nickname") == "Zoir"
    assert extract_nickname({"items": [{"name": "A"}]}, "items.0.name") == "A"
    assert extract_nickname({"data": {"name": "Fallback"}}, "wrong.path") == "Fallback"
    assert extract_nickname({"success": False}, "nickname") is None
    assert clean_nickname("a\x00b\n" + "z" * 80) == "ab" + "z" * 38


# ---------- paketlar ----------

async def test_default_packages_seeded_once(app):
    pk = await app.uc.list_active()
    assert [p["uc"] for p in pk] == [60, 325, 660, 1800, 3850, 8100]
    await app.uc.delete_package(pk[0]["id"])
    await app.uc.ensure_defaults()  # o'chirilganini qayta qo'shmaydi
    assert len(await app.uc.list_all()) == 5


async def test_package_crud_and_validation(app):
    pid = await app.uc.add_package(100, 25000, bonus=10)
    assert (await app.uc.get_package(pid))["bonus"] == 10
    assert await app.uc.update_package(pid, price=30000, active=False)
    assert pid not in [p["id"] for p in await app.uc.list_active()]
    for bad in ((0, 1000), (100, 0)):
        try:
            await app.uc.add_package(*bad)
            assert False, "xato kutilgan edi"
        except ValueError:
            pass


# ---------- nickname ----------

async def test_lookup_found_cached_and_not_found(app):
    calls: list = []
    await app.settings.set_uc(lookup_url="https://x.test/p/{id}", lookup_path="data.nickname")
    app.uc._fetch = fake_fetcher({"5123456789": (200, {"data": {"nickname": "Zoir"}})}, calls)
    r = await app.uc.lookup("5123456789")
    assert r == {"status": "found", "nickname": "Zoir", "reason": ""}
    await app.uc.lookup("5123456789")
    assert len(calls) == 1  # kesh
    assert (await app.uc.lookup("5999999999"))["status"] == "not_found"  # HTTP 404


async def test_lookup_unavailable_cases(app):
    assert (await app.uc.lookup("5123456789"))["status"] == "unavailable"  # sozlanmagan
    await setup_lookup(app, {"5123456789": ConnectionError("down")})
    assert (await app.uc.lookup("5123456789"))["reason"] == "network"
    await setup_lookup(app, {"5123456789": (500, None)})
    assert (await app.uc.lookup("5123456789"))["status"] == "unavailable"


# ---------- xarid ----------

async def test_purchase_success_without_verification(app):
    await funded_user(app)
    pkg = (await app.uc.list_active())[2]  # 660 UC
    res = await app.uc.purchase(10, pkg["id"], "5123 456 789")
    assert res.ok and res.balance == 1_000_000 - pkg["price"]
    o = await app.uc.get_order(res.order_id)
    assert o["pubg_id"] == "5123456789" and o["nickname"] == "" and o["verified"] == 0
    assert o["status"] == "pending"
    order = await app.orders.get(res.order_id)
    assert order["type"] == "uc" and order["price_amount"] == pkg["price"]
    assert "660 UC" in order["note"] and "5123456789" in order["note"]


async def test_purchase_stores_server_side_nickname(app):
    await funded_user(app)
    await setup_lookup(app, {"5123456789": (200, {"data": {"nickname": "Zoir"}})})
    pkg = (await app.uc.list_active())[0]
    res = await app.uc.purchase(10, pkg["id"], "5123456789")
    o = await app.uc.get_order(res.order_id)
    assert o["nickname"] == "Zoir" and o["verified"] == 1


async def test_purchase_errors(app):
    await funded_user(app, amount=1000)
    pkg = (await app.uc.list_active())[0]
    assert (await app.uc.purchase(10, pkg["id"], "12ab")).error == "bad_pubg_id"
    assert (await app.uc.purchase(10, 9999, "5123456789")).error == "no_package"
    assert (await app.uc.purchase(10, pkg["id"], "5123456789")).error == "insufficient_sum"
    assert await app.users.balance_sum(10) == 1000  # pul yechilmagan
    await setup_lookup(app, {})  # hamma ID -> 404
    await funded_user(app, uid=11)
    assert (await app.uc.purchase(11, pkg["id"], "5123456789")).error == "player_not_found"
    await app.settings.set_uc(enabled=False)
    assert (await app.uc.purchase(11, pkg["id"], "5123456789")).error == "disabled"


async def test_require_nick_blocks_unverified(app):
    await funded_user(app)
    await app.settings.set_uc(require_nick=True)
    pkg = (await app.uc.list_active())[0]
    assert (await app.uc.purchase(10, pkg["id"], "5123456789")).error == "nick_required"
    await setup_lookup(app, {"5123456789": (200, {"data": {"nickname": "Zoir"}})}, require_nick=True)
    assert (await app.uc.purchase(10, pkg["id"], "5123456789")).ok


async def test_duplicate_click_is_blocked(app):
    await funded_user(app)
    pkg = (await app.uc.list_active())[0]
    first = await app.uc.purchase(10, pkg["id"], "5123456789")
    second = await app.uc.purchase(10, pkg["id"], "5123456789")
    assert first.ok and second.error == "duplicate"
    assert await app.users.balance_sum(10) == 1_000_000 - pkg["price"]


async def test_parallel_purchases_cannot_overspend(app):
    pk = await app.uc.list_active()
    await funded_user(app, amount=pk[0]["price"])  # faqat bittasiga yetadi
    results = await asyncio.gather(
        app.uc.purchase(10, pk[0]["id"], "5123456789"),
        app.uc.purchase(10, pk[0]["id"], "5123456780"),
    )
    assert sorted(r.ok for r in results) == [False, True]
    assert await app.users.balance_sum(10) == 0


# ---------- admin qarori ----------

async def test_complete_once_and_cancel_refunds_once(app):
    await funded_user(app)
    pk = await app.uc.list_active()
    a = await app.uc.purchase(10, pk[0]["id"], "5123456789")
    b = await app.uc.purchase(10, pk[1]["id"], "5123456789")
    start = await app.users.balance_sum(10)

    assert await app.uc.complete(a.order_id) is True
    assert await app.uc.complete(a.order_id) is False
    assert await app.uc.cancel(a.order_id) is None  # bajarilganini qaytarib bo'lmaydi

    assert await app.uc.cancel(b.order_id) is not None
    assert await app.uc.cancel(b.order_id) is None  # ikki marta qaytarilmaydi
    assert await app.users.balance_sum(10) == start + pk[1]["price"]
    assert await app.uc.complete(b.order_id) is False


async def test_cancel_ignores_other_order_types(app):
    await funded_user(app)
    oid = await app.orders.create(10, "buy", 50, "sum", price_amount=5000)
    assert await app.uc.cancel(oid) is None
    assert await app.uc.complete(oid) is False


# ---------- ro'yxat va statistika ----------

async def test_stats_orders_and_history(app):
    await funded_user(app)
    await funded_user(app, uid=20)
    pk = await app.uc.list_active()
    a = await app.uc.purchase(10, pk[0]["id"], "5123456789")
    b = await app.uc.purchase(10, pk[2]["id"], "5123456789")
    c = await app.uc.purchase(20, pk[2]["id"], "5000000001")
    await app.uc.complete(a.order_id)
    await app.uc.complete(b.order_id)
    await app.uc.cancel(c.order_id)

    s = await app.uc.stats()
    assert s["periods"]["all"]["orders"] == 2
    assert s["periods"]["all"]["uc"] == 60 + 660
    assert s["periods"]["today"]["revenue"] == pk[0]["price"] + pk[2]["price"]
    assert s["periods"]["all"]["buyers"] == 1
    assert s["rejected"] == 1 and s["pending"]["c"] == 0
    assert len(s["daily"]) == 14 and s["daily"][-1]["orders"] == 2
    assert s["top_buyers"][0]["user_id"] == 10

    assert len(await app.uc.list_orders("done")) == 2
    assert [o["order_id"] for o in await app.uc.list_orders("rejected")] == [c.order_id]
    assert len(await app.uc.list_orders("", "5000000001")) == 1
    hist = await app.uc.user_history(10)
    assert [h["order_id"] for h in hist] == [b.order_id, a.order_id]
    assert await app.uc.last_pubg_id(20) == "5000000001"
