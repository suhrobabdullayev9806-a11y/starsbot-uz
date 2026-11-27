# ===================================================================
# test_gram.py - GRAM (TON) moduli: manzil tekshirish, paketlar,
# xarid, qaytarish, statistika va admin ro'yxatlari.
# ===================================================================

import asyncio

from src.modules.gram import format_grams, normalize_wallet

# 48 belgili haqiqiy formatdagi TON manzillari
ADDR_A = "UQ" + "A" * 46
ADDR_B = "EQ" + "b" * 46
RAW = "0:" + "a" * 64


async def funded_user(app, uid=10, amount=1_000_000):
    await app.users.get_or_create(uid, "ali", "Ali", "uz")
    await app.users.add_sum(uid, amount, "test topup")


# ---------- sof funksiyalar ----------

def test_normalize_wallet_accepts_addresses_and_usernames():
    assert normalize_wallet(ADDR_A) == {"wallet": ADDR_A, "kind": "address"}
    assert normalize_wallet("  " + ADDR_B + " ") == {"wallet": ADDR_B, "kind": "address"}
    assert normalize_wallet(RAW) == {"wallet": RAW, "kind": "address"}
    assert normalize_wallet("@Ali_99") == {"wallet": "@Ali_99", "kind": "username"}
    assert normalize_wallet("https://t.me/Ali_99") == {"wallet": "@Ali_99", "kind": "username"}
    assert normalize_wallet("t.me/Ali_99") == {"wallet": "@Ali_99", "kind": "username"}
    # qisqa, lekin username formatiga mos matn — Telegram profili sifatida qabul qilinadi
    assert normalize_wallet("UQ123") == {"wallet": "@UQ123", "kind": "username"}
    for bad in ("", "   ", "ab", "not a wallet", "@a", None):
        assert normalize_wallet(bad) is None


def test_format_grams():
    assert format_grams(1) == "1"
    assert format_grams(1000) == "1 000"
    assert format_grams(0.5) == "0.5"
    assert format_grams(1.25) == "1.25"
    assert format_grams(None) == "0"


# ---------- paketlar ----------

async def test_default_packages_seeded_once(app):
    pk = await app.gram.list_active()
    assert [p["grams"] for p in pk] == [1, 5, 10, 25, 50, 100]
    assert all(float(p["price"]) > 0 for p in pk)
    await app.gram.delete_package(pk[0]["id"])
    await app.gram.ensure_defaults()  # o'chirilganini qayta qo'shmaydi
    assert len(await app.gram.list_all()) == 5


async def test_package_crud_and_validation(app):
    pid = await app.gram.add_package(2.5, 40000)
    assert (await app.gram.get_package(pid))["grams"] == 2.5
    assert await app.gram.update_package(pid, price=45000, active=False)
    assert pid not in [p["id"] for p in await app.gram.list_active()]
    assert await app.gram.update_package(pid, active=True, grams=3, sort=9)
    row = await app.gram.get_package(pid)
    assert row["active"] == 1 and row["grams"] == 3 and row["sort"] == 9
    for bad in ((0, 1000), (100, 0), (-1, 1000)):
        try:
            await app.gram.add_package(*bad)
            assert False, "xato kutilgan edi"
        except ValueError:
            pass
    assert await app.gram.delete_package(pid)
    assert not await app.gram.delete_package(pid)


# ---------- xarid ----------

async def test_purchase_success_deducts_and_stores_full_wallet(app):
    await funded_user(app)
    pkg = (await app.gram.list_active())[1]  # 5 Gram
    res = await app.gram.purchase(10, pkg["id"], "  " + ADDR_A + "  ")
    assert res.ok and res.balance == 1_000_000 - pkg["price"]

    o = await app.gram.get_order(res.order_id)
    assert o["wallet"] == ADDR_A and o["wallet_kind"] == "address"
    assert o["username"] == "ali" and o["grams"] == 5
    assert o["status"] == "pending"

    order = await app.orders.get(res.order_id)
    assert order["type"] == "gram" and order["price_amount"] == pkg["price"]
    assert "5 Gram" in order["note"] and ADDR_A in order["note"] and "@ali" in order["note"]
    assert await app.gram.last_wallet(10) == ADDR_A


async def test_purchase_to_telegram_username(app):
    await funded_user(app)
    pkg = (await app.gram.list_active())[0]
    res = await app.gram.purchase(10, pkg["id"], "@Friend_01")
    o = await app.gram.get_order(res.order_id)
    assert o["wallet"] == "@Friend_01" and o["wallet_kind"] == "username"


async def test_purchase_errors_and_no_charge(app):
    await funded_user(app, amount=1000)
    pkg = (await app.gram.list_active())[0]
    assert (await app.gram.purchase(10, pkg["id"], "12ab")).error == "bad_wallet"
    assert (await app.gram.purchase(10, 9999, ADDR_A)).error == "no_package"
    assert (await app.gram.purchase(10, pkg["id"], ADDR_A)).error == "insufficient_sum"
    assert await app.users.balance_sum(10) == 1000  # pul yechilmagan
    await app.settings.set_gram(enabled=False)
    assert (await app.gram.purchase(10, pkg["id"], ADDR_A)).error == "disabled"
    await app.settings.set_gram(enabled=True)

    pid = await app.gram.add_package(2, 5000)
    await app.gram.update_package(pid, active=False)
    assert (await app.gram.purchase(10, pid, ADDR_A)).error == "no_package"


async def test_duplicate_click_is_blocked(app):
    await funded_user(app)
    pkg = (await app.gram.list_active())[0]
    first = await app.gram.purchase(10, pkg["id"], ADDR_A)
    second = await app.gram.purchase(10, pkg["id"], "  " + ADDR_A + "  ")
    assert first.ok and second.error == "duplicate"
    assert await app.users.balance_sum(10) == 1_000_000 - pkg["price"]


async def test_parallel_purchases_cannot_overspend(app):
    pk = await app.gram.list_active()
    await funded_user(app, amount=pk[0]["price"])  # faqat bittasiga yetadi
    results = await asyncio.gather(
        app.gram.purchase(10, pk[0]["id"], ADDR_A),
        app.gram.purchase(10, pk[0]["id"], ADDR_B),
    )
    assert sorted(r.ok for r in results) == [False, True]
    assert await app.users.balance_sum(10) == 0


# ---------- admin qarori ----------

async def test_complete_once_and_cancel_refunds_once(app):
    await funded_user(app)
    pk = await app.gram.list_active()
    a = await app.gram.purchase(10, pk[0]["id"], ADDR_A)
    b = await app.gram.purchase(10, pk[1]["id"], "@Friend_01")
    start = await app.users.balance_sum(10)

    assert await app.gram.complete(a.order_id) is True
    assert await app.gram.complete(a.order_id) is False
    assert await app.gram.cancel(a.order_id) is None  # bajarilganini qaytarib bo'lmaydi

    assert await app.gram.cancel(b.order_id) is not None
    assert await app.gram.cancel(b.order_id) is None  # ikki marta qaytarilmaydi
    assert await app.users.balance_sum(10) == start + pk[1]["price"]
    assert await app.gram.complete(b.order_id) is False


async def test_cancel_ignores_other_order_types(app):
    await funded_user(app)
    oid = await app.orders.create(10, "uc", 60, "sum", price_amount=5000)
    assert await app.gram.cancel(oid) is None
    assert await app.gram.complete(oid) is False


# ---------- ro'yxat va statistika ----------

async def test_stats_orders_and_history(app):
    await funded_user(app)
    await funded_user(app, uid=20)
    pk = await app.gram.list_active()
    a = await app.gram.purchase(10, pk[0]["id"], ADDR_A)
    b = await app.gram.purchase(10, pk[2]["id"], ADDR_A)
    c = await app.gram.purchase(20, pk[2]["id"], "@Friend_01")
    await app.gram.complete(a.order_id)
    await app.gram.complete(b.order_id)
    await app.gram.cancel(c.order_id)

    s = await app.gram.stats()
    assert s["periods"]["all"]["orders"] == 2
    assert s["periods"]["all"]["grams"] == pk[0]["grams"] + pk[2]["grams"]
    assert s["periods"]["today"]["revenue"] == pk[0]["price"] + pk[2]["price"]
    assert s["periods"]["all"]["buyers"] == 1
    assert s["rejected"] == 1 and s["pending"]["c"] == 0
    assert len(s["daily"]) == 14 and s["daily"][-1]["orders"] == 2
    assert s["top_buyers"][0]["user_id"] == 10

    assert len(await app.gram.list_orders("done")) == 2
    assert [o["order_id"] for o in await app.gram.list_orders("rejected")] == [c.order_id]
    assert len(await app.gram.list_orders("", ADDR_A)) == 2
    assert len(await app.gram.list_orders("", "Friend_01")) == 1
    assert len(await app.gram.list_orders("", "20")) == 1
    hist = await app.gram.user_history(10)
    assert [h["order_id"] for h in hist] == [b.order_id, a.order_id]
    assert await app.gram.last_wallet(20) == "@Friend_01"
