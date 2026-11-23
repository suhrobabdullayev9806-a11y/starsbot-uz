"""NftModule.update va oluvchi ajratish testlari (DB talab qilmaydi)."""
from src.handlers.nft import recipient_of


def test_recipient_of():
    o = {"note": "Plush Pepe #1 -> @ali (id:5) | https://t.me/nft/PlushPepe-1"}
    assert recipient_of(o) == "@ali (id:5)"
    assert recipient_of({"note": ""}) == "—"
