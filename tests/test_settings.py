# ===================================================================
# test_settings.py - SettingsRepo va admin moduli
# ===================================================================

async def test_settings_prices_roundtrip(app):
    await app.settings.set_prices({15: 3.0, 100: 15.0})
    return await app.settings.get_prices()


async def test_settings_bot_toggle(app):
    assert await app.settings.bot_active() is True
    active = await app.admin.toggle_bot()
    assert active is False
    assert await app.settings.bot_active() is False


async def test_admin_stats_empty(app):
    s = await app.admin.stats()
    assert float(s["daily"]["sold_stars"]) == 0
    assert int(s["users"]) == 0
    assert "daily" in s and "weekly" in s and "monthly" in s


async def test_accounts_module(app):
    await app.accounts.add("Main", "session_secret")
    await app.accounts.add("Second", "another_secret")
    rows = await app.accounts.list_all()
    assert len(rows) == 2
    # session_data shifrlangan bo'lishi kerak
    assert rows[0]["session_data"] != "session_secret"

    await app.accounts.remove(rows[0]["id"])
    assert len(await app.accounts.list_all()) == 1


async def test_gift_insufficient(app):
    await app.users.get_or_create(9)
    result = await app.gifts.purchase_gift(9, 100, "+998901234567")
    assert result.ok is False
    assert result.error == "insufficient"