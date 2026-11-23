# ===================================================================
# test_users_orders.py - Foydalanuvchilar va buyurtmalar moduli
# ===================================================================

async def test_get_or_create(app):
    user, created = await app.users.get_or_create(42, "ali", "Ali", "uz")
    assert created is True
    assert user["id"] == 42

    user2, created2 = await app.users.get_or_create(42, "ali", "Ali", "uz")
    assert created2 is False
    assert user2["id"] == 42


async def test_balance_add_sub(app):
    await app.users.get_or_create(1)
    assert await app.users.balance(1) == 0.0

    await app.users.add_balance(1, 50, "test credit")
    assert await app.users.balance(1) == 50.0

    bal = await app.users.sub_balance(1, 20, "test debit")
    assert bal == 30.0

    # Yetarli emas holati
    bal = await app.users.sub_balance(1, 999, "too much")
    assert bal == -1.0


async def test_orders_create_and_stats_range(app):
    await app.users.get_or_create(7)
    oid = await app.orders.create(7, "buy", 15, "card", price_amount=30000)
    assert oid > 0

    order = await app.orders.get(oid)
    assert order["status"] == "pending"

    await app.orders.update_status(oid, "done")
    # stats_range faqat approved/done ni hisoblaydi
    import datetime

    since = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat()
    stats = await app.orders.stats_range(since)
    assert float(stats["sold_stars"]) == 15.0
    assert float(stats["sold_sum"]) == 30000.0
    assert int(stats["count"]) == 1