# ===================================================================
# test_payments.py - To'lovlar moduli
# ===================================================================

from src.modules.payments import PaymentsModule


async def test_pay_from_balance_success(app):
    await app.users.get_or_create(5)
    await app.users.add_sum(5, 100000, "seed")

    oid = await app.payments.create_intent(5, "buy", 30, "balance", price=5000)
    result = await app.payments.pay_from_balance(oid, 5, 30, price=5000)

    assert result.ok is True
    # 100 000 so'm - 5000 so'm = 95 000 so'm qoladi, 30 stars qo'shiladi
    assert float(await app.users.balance_sum(5)) == 95000.0
    assert float(await app.users.balance(5)) == 30.0
    order = await app.orders.get(oid)
    assert order["status"] == "done"


async def test_pay_from_balance_insufficient(app):
    await app.users.get_or_create(6)

    oid = await app.payments.create_intent(6, "buy", 300, "balance", price=999)
    result = await app.payments.pay_from_balance(oid, 6, 300, price=999)

    assert result.ok is False
    assert result.error == "insufficient"
    assert float(await app.users.balance_sum(6)) == 0.0


async def test_topup_card_approve_credits_sum(app):
    await app.users.get_or_create(9)
    oid = await app.payments.create_intent(9, "topup", 0, "card", price=50000)

    await app.payments.submit_card_payment(oid, 9, "chek 50000")
    assert (await app.orders.get(oid))["status"] == "pending"

    # Admin tasdiqlaganda SO'M hisobga yoziladi (stars emas)
    await app.payments.approve_card_order(oid, 9, 0)
    assert float(await app.users.balance_sum(9)) == 50000.0
    assert float(await app.users.balance(9)) == 0.0


async def test_approve_card_order_delivers(app):
    await app.users.get_or_create(8)
    oid = await app.payments.create_intent(8, "buy", 50, "card", price=8000)

    # Avval tasdiq yuborish
    await app.payments.submit_card_payment(oid, 8, "chek.png")
    assert (await app.orders.get(oid))["status"] == "pending"

    # Admin tasdiqlaganda stars yetkaziladi
    await app.payments.approve_card_order(oid, 8, 50)
    assert float(await app.users.balance(8)) == 50.0
    assert (await app.orders.get(oid))["status"] == "approved"