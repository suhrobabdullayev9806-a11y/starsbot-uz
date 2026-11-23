# ===================================================================
# test_utils.py - Yordamchi funksiyalar
# ===================================================================

from src.utils import (
    parse_phone,
    parse_price_input,
    parse_stars_request,
    prices_text,
    progress_bar,
)


def test_progress_bar():
    bar = progress_bar(50, 100, 10)
    assert bar.count("▰") == 5
    assert bar.count("▱") == 5


def test_progress_bar_full():
    assert progress_bar(200, 100, 10) == "▰" * 10


def test_prices_text():
    text = prices_text({15: 3.0, 30: 5.0})
    assert "15" in text and "30" in text


def test_parse_price_input_ok():
    assert parse_price_input("15=30000,30=55000") == {15: 30000.0, 30: 55000.0}
    assert parse_price_input("100:100000") == {100: 100000.0}


def test_parse_price_input_bad():
    assert parse_price_input("hello") is None
    assert parse_price_input("") is None
    assert parse_price_input("15=") is None


def test_parse_phone():
    assert parse_phone("+998901234567") == "+998901234567"
    assert parse_phone("901234567") == "+998901234567"
    assert parse_phone("123") is None


def test_parse_stars_request():
    amount, link = parse_stars_request("100 stars\nhttps://t.me/mychannel/15")
    assert amount == 100
    assert link == "https://t.me/mychannel/15"


def test_parse_stars_request_missing_link():
    amount, link = parse_stars_request("50")
    assert amount is None and link is None