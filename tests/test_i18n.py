# ===================================================================
# test_i18n.py - Ko'p tillik qatlam
# ===================================================================

from src.i18n import status_label, t


def test_translations_exist_uz():
    assert "Ali" in t("uz", "start", first="Ali")
    assert "Stars" in t("uz", "menu_buy")
    assert t("uz", "menu_buy") != t("ru", "menu_buy")


def test_fallback_to_uz():
    assert t("xy", "menu_buy") == t("uz", "menu_buy")


def test_formatting():
    text = t("uz", "buy_choose", prices="15", balance=100)
    assert "15" in text and "100" in text


def test_status_label():
    assert "⏳" in status_label("uz", "pending")
    assert "Delivered" in status_label("en", "done")
    assert status_label("uz", "unknown") == "unknown"


def test_unknown_key_returns_key():
    assert t("uz", "no_such_key_123") == "no_such_key_123"