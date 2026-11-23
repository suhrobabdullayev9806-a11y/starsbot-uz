# ===================================================================
# test_bank.py - AVTO-TO'LOV: bank xabarini tahlil qilish va tranzaksiya ID tekshiruvi
# ===================================================================

import pytest

from src.modules.bank import norm_tx, parse_notification

SMS = "➕ 50 000.00 UZS\n📍 HUMO P2P Ref: 4821937465\n💳 HUMOCARD *1234\n🕓 12:30 19.11.2026\n💰 1 250 000.00 UZS"


# ---------------- parser ----------------

def test_parse_income_amount_and_tokens():
    p = parse_notification(SMS)
    assert p["income"] is True
    assert p["amount"] == 50000.0           # qoldiq (1 250 000) emas, kirim summasi
    assert "4821937465" in p["tokens"]
    assert "humocard" not in p["tokens"]    # faqat harfli so'zlar ID emas


def test_parse_expense_is_not_income():
    p = parse_notification("➖ 25 000.00 UZS Oplata Korzinka\n💰 1 000 000.00 UZS")
    assert p["income"] is False


def test_parse_ru_and_comma_format():
    p = parse_notification("Пополнение 200,000.00 сум, чек №77889900")
    assert p["amount"] == 200000.0 and "77889900" in p["tokens"]


def test_parse_no_amount():
    assert parse_notification("salom dunyo") is None


def test_norm_tx():
    assert norm_tx(" ab-12 34 56 ") == "ab123456"


# ---------------- oqim ----------------

@pytest.fixture
async def bapp(app, monkeypatch):
    monkeypatch.setattr(app.cfg, "bank_auto", True)
    await app.users.get_or_create(7, "bob", "Bob")
    return app


async def test_topup_success(bapp):
    await bapp.bank.ingest(SMS, "test")
    res = await bapp.bank.submit(7, 50000, "4821937465")
    assert res["status"] == "done"
    assert await bapp.users.balance_sum(7) == 50000
    assert (await bapp.orders.get(res["order_id"]))["status"] == "done"


async def test_tx_cannot_be_reused(bapp):
    await bapp.users.get_or_create(8, "eve", "Eve")
    await bapp.bank.ingest(SMS, "test")
    assert (await bapp.bank.submit(7, 50000, "4821937465"))["status"] == "done"
    second = await bapp.bank.submit(8, 50000, "4821937465")
    assert second["status"] == "rejected"
    assert await bapp.users.balance_sum(8) == 0
    assert await bapp.users.balance_sum(7) == 50000   # ikki marta qo'shilmadi


async def test_wrong_amount_rejected(bapp):
    await bapp.bank.ingest(SMS, "test")
    res = await bapp.bank.submit(7, 100000, "4821937465")
    assert res["status"] == "rejected" and res["reason"] == "amount_mismatch"
    assert await bapp.users.balance_sum(7) == 0


async def test_wrong_id_waits_then_times_out(bapp):
    got = []

    async def hook(order, outcome, reason):
        got.append((outcome, reason))

    bapp.bank.on_result = hook
    await bapp.bank.ingest(SMS, "test")
    res = await bapp.bank.submit(7, 50000, "9999999999")
    assert res["status"] == "pending"
    bapp.cfg.topup_verify_timeout = 0           # muddat tugadi
    await bapp.bank.process_pending()
    assert got == [("rejected", "not_found_timeout")]
    assert await bapp.users.balance_sum(7) == 0


async def test_late_notification_completes_pending(bapp):
    got = []

    async def hook(order, outcome, reason):
        got.append(outcome)

    bapp.bank.on_result = hook
    res = await bapp.bank.submit(7, 50000, "4821937465")     # bank xabari hali kelmagan
    assert res["status"] == "pending"
    await bapp.bank.ingest(SMS, "test")                      # keyin keldi
    assert got == ["done"]
    assert await bapp.users.balance_sum(7) == 50000


async def test_validation(bapp):
    assert (await bapp.bank.submit(7, 50000, "abc"))["reason"] == "bad_tx"
    assert (await bapp.bank.submit(7, 50000, "abcdefgh"))["reason"] == "bad_tx"   # raqamsiz
    assert (await bapp.bank.submit(7, 1, "4821937465"))["reason"] == "amount_range"


async def test_manual_mode_when_no_source(app):
    await app.users.get_or_create(7, "bob", "Bob")
    assert app.bank.enabled is False
    res = await app.bank.submit(7, 50000, "4821937465")
    assert res["status"] == "manual"
    assert (await app.orders.get(res["order_id"]))["status"] == "pending"
