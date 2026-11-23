# ===================================================================
# test_nft.py - NFT: havola tahlili, katalog, sotib olish, qaytarish
# ===================================================================

import pytest

from src.nft_parser import (
    NftUrlError,
    fetch_nft,
    humanize,
    image_url,
    parse_nft_url,
    parse_traits,
)

PAGE = """<html><head>
<meta property="og:title" content="Plush Pepe #1234">
<meta property="og:image" content="https://nft.fragment.com/gift/plushpepe-1234.large.jpg">
<meta name="twitter:description" content="Model: Aquamarine (0.5%)&#10;Backdrop: Black (2%)&#10;Symbol: Double Axe (1.2%)">
</head><body></body></html>"""


# ---------- parser ----------

@pytest.mark.parametrize("url", [
    "https://t.me/nft/PlushPepe-1234",
    "http://t.me/nft/PlushPepe-1234/",
    "t.me/nft/PlushPepe-1234?startapp=1",
    "https://telegram.me/nft/PlushPepe-1234",
    "PlushPepe-1234",
])
def test_parse_url_ok(url):
    assert parse_nft_url(url) == ("PlushPepe", 1234)


@pytest.mark.parametrize("url", [
    "", "hello", "https://evil.com/nft/PlushPepe-1",
    "https://t.me/nft/PlushPepe", "https://t.me/durov", "https://t.me.evil.com/nft/A-1",
])
def test_parse_url_bad(url):
    with pytest.raises(NftUrlError):
        parse_nft_url(url)


def test_humanize_and_image():
    assert humanize("PlushPepe") == "Plush Pepe"
    assert humanize("Snoop_Dogg") == "Snoop Dogg"
    assert image_url("PlushPepe", 7) == "https://nft.fragment.com/gift/plushpepe-7.large.jpg"


def test_parse_traits():
    t = parse_traits("Model: The King (1%)\nBackdrop: Black\nSymbol: Head Scarf")
    assert t == {"model": "The King", "backdrop": "Black", "symbol": "Head Scarf"}


async def test_fetch_nft_from_page():
    async def fake(url):
        return PAGE if url.startswith("https://t.me/nft/") else None

    info = await fetch_nft("https://t.me/nft/PlushPepe-1234", fake)
    assert info.title == "Plush Pepe #1234"
    assert info.image == "https://nft.fragment.com/gift/plushpepe-1234.large.jpg"
    assert (info.model, info.backdrop, info.symbol) == ("Aquamarine", "Black", "Double Axe")
    assert info.found_page


async def test_fetch_nft_json_fallback_and_no_network():
    async def only_json(url):
        if url.endswith(".json"):
            return ('{"attributes":[{"trait_type":"Model","value":"Elder Wand"},'
                    '{"trait_type":"Backdrop","value":"Onyx"},{"trait_type":"Symbol","value":"Corn"}]}')
        return None

    info = await fetch_nft("t.me/nft/SnoopCigar-5", only_json)
    assert (info.model, info.backdrop, info.symbol) == ("Elder Wand", "Onyx", "Corn")
    assert info.image == image_url("SnoopCigar", 5)

    async def nothing(url):
        return None

    info = await fetch_nft("t.me/nft/SnoopCigar-5", nothing)
    assert not info.found_page and info.model == ""
    assert info.image.startswith("https://nft.fragment.com/")


async def test_fetch_nft_ignores_non_https_image():
    async def fake(url):
        return PAGE.replace("https://nft.fragment.com", "http://x.com")

    info = await fetch_nft("t.me/nft/PlushPepe-1234", fake)
    assert info.image.startswith("https://nft.fragment.com/")


# ---------- katalog va sotib olish ----------

async def _add(app, slug="PlushPepe-1", price=100_000):
    async def fake(url):
        return PAGE

    info = await fetch_nft(f"t.me/nft/{slug}", fake)
    return await app.nft.add(info, price)


async def test_add_list_remove(app):
    nid = await _add(app)
    assert [n["id"] for n in await app.nft.list_active()] == [nid]
    assert await app.nft.find_by_slug("plushpepe-1")
    assert await app.nft.set_price(nid, 250_000)
    assert (await app.nft.get(nid))["price"] == 250_000
    assert await app.nft.remove(nid)
    assert await app.nft.list_active() == []
    assert await app.nft.find_by_slug("PlushPepe-1") is None


async def test_purchase_success_and_complete(app):
    nid = await _add(app, price=100_000)
    await app.users.get_or_create(5, "ali", "Ali", "uz")
    await app.users.add_sum(5, 150_000, "topup")

    res = await app.nft.purchase(5, nid, "ali")
    assert res.ok and res.balance == 50_000
    order = await app.orders.get(res.order_id)
    assert order["type"] == "nft" and order["status"] == "pending"
    assert float(order["price_amount"]) == 100_000
    assert (await app.nft.get(nid))["status"] == "reserved"
    assert await app.nft.list_active() == []

    assert await app.nft.complete(res.order_id) is True
    assert await app.nft.complete(res.order_id) is False      # ikki marta emas
    assert (await app.nft.get(nid))["status"] == "sold"
    assert (await app.orders.get(res.order_id))["status"] == "done"
    assert await app.nft.cancel(res.order_id) is None          # yetkazilganni qaytarib bo'lmaydi
    assert await app.users.balance_sum(5) == 50_000


async def test_purchase_insufficient_releases_nft(app):
    nid = await _add(app, price=100_000)
    await app.users.get_or_create(6)
    await app.users.add_sum(6, 10_000, "topup")
    res = await app.nft.purchase(6, nid)
    assert not res.ok and res.error == "insufficient_sum"
    assert await app.users.balance_sum(6) == 10_000
    assert (await app.nft.get(nid))["status"] == "active"


async def test_double_purchase_blocked(app):
    nid = await _add(app, price=50_000)
    for uid in (7, 8):
        await app.users.get_or_create(uid)
        await app.users.add_sum(uid, 100_000, "topup")
    first = await app.nft.purchase(7, nid)
    second = await app.nft.purchase(8, nid)
    assert first.ok
    assert not second.ok and second.error == "unavailable"
    assert await app.users.balance_sum(8) == 100_000          # pul yechilmagan


async def test_cancel_refunds_once_and_relists(app):
    nid = await _add(app, price=80_000)
    await app.users.get_or_create(9)
    await app.users.add_sum(9, 80_000, "topup")
    res = await app.nft.purchase(9, nid)
    assert await app.users.balance_sum(9) == 0

    assert await app.nft.cancel(res.order_id) is not None
    assert await app.nft.cancel(res.order_id) is None          # ikki marta qaytarilmaydi
    assert await app.users.balance_sum(9) == 80_000
    assert (await app.nft.get(nid))["status"] == "active"
    assert (await app.orders.get(res.order_id))["status"] == "rejected"
    assert not await app.nft.remove(999)


async def test_cannot_remove_reserved(app):
    nid = await _add(app, price=10_000)
    await app.users.get_or_create(10)
    await app.users.add_sum(10, 10_000, "topup")
    await app.nft.purchase(10, nid)
    assert await app.nft.remove(nid) is False
