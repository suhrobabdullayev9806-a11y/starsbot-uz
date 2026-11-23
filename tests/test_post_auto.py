# ===================================================================
# test_post_auto.py - Postga stars AVTOMATIK yetkazish
# Telethon o'rniga soxta (fake) yetkazuvchi ishlatiladi.
# ===================================================================

import pytest


async def _make_order(app, price=15000.0, stars=50):
    await app.users.get_or_create(5, "ali", "Ali")
    await app.users.add_sum(5, 50000, "test topup")
    oid = await app.orders.create(
        5, "post_stars", stars, "balance", price_amount=price, note="https://t.me/chan/12"
    )
    await app.users.sub_sum(5, price, "post stars", oid)
    return oid


async def test_auto_post_success(app, monkeypatch):
    calls = []

    async def fake(amount, link):
        calls.append((amount, link))
        return True, "ok"

    monkeypatch.setattr(app.accounts, "deliver_post_stars", fake)
    oid = await _make_order(app)
    res = await app.admin.deliver_post_stars(oid)

    assert res["ok"] is True
    assert calls == [(50.0, "https://t.me/chan/12")]
    order = await app.orders.get(oid)
    assert order["status"] == "done"
    assert order["note"] == "https://t.me/chan/12"  # havola saqlanadi
    assert await app.users.balance_sum(5) == 35000  # qaytarilmagan


async def test_auto_post_failure_refunds(app, monkeypatch):
    async def fake(amount, link):
        return False, "no_active_account"

    monkeypatch.setattr(app.accounts, "deliver_post_stars", fake)
    oid = await _make_order(app)
    res = await app.admin.deliver_post_stars(oid)

    assert res["ok"] is False
    assert res["refunded"] == 15000
    assert (await app.orders.get(oid))["status"] == "failed"
    assert await app.users.balance_sum(5) == 50000  # pul to'liq qaytdi


async def test_auto_post_partial_refunds_rest(app, monkeypatch):
    async def fake(amount, link):
        return False, "partial:20|FloodWaitError"

    monkeypatch.setattr(app.accounts, "deliver_post_stars", fake)
    oid = await _make_order(app)  # 50 stars = 15000
    res = await app.admin.deliver_post_stars(oid)

    assert res["sent"] == 20
    assert res["refunded"] == pytest.approx(9000)  # 30/50 * 15000
    assert await app.users.balance_sum(5) == pytest.approx(44000)


async def test_auto_post_not_sent_twice(app, monkeypatch):
    calls = []

    async def fake(amount, link):
        calls.append(1)
        return True, "ok"

    monkeypatch.setattr(app.accounts, "deliver_post_stars", fake)
    oid = await _make_order(app)
    await app.admin.deliver_post_stars(oid)
    second = await app.admin.deliver_post_stars(oid)

    assert second["already"] is True
    assert len(calls) == 1


async def test_auto_post_no_account(app):
    # Haqiqiy deliver: aktiv akkaunt yo'q -> xato + pul qaytadi
    oid = await _make_order(app)
    res = await app.admin.deliver_post_stars(oid)
    assert res["ok"] is False
    assert res["reason"] == "no_active_account"
    assert await app.users.balance_sum(5) == 50000
