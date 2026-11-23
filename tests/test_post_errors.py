"""telegram_gift.explain_error va post havolasi regex testlari."""
from src.telegram_gift import _POST_LINK_RE, explain_error


class BalanceTooLowError(Exception):
    pass


class MessageIdInvalidError(Exception):
    pass


def test_explain_known_errors():
    assert "Stars yetarli emas" in explain_error(BalanceTooLowError("x"))
    assert "post topilmadi" in explain_error(MessageIdInvalidError("x"))


def test_explain_text_and_unknown():
    assert explain_error("something_else") == "something_else"
    assert "Stars yetarli emas" in explain_error("account_balance_low: 5/10")
    

def test_post_link_regex():
    m = _POST_LINK_RE.search("https://t.me/mychannel/123")
    assert m and m.group("user") == "mychannel" and m.group("mid") == "123"
    m = _POST_LINK_RE.search("t.me/c/1234567890/55")
    assert m and m.group("cid") == "1234567890"
