# ===================================================================
# nft_parser.py - Telegram NFT (kolleksiya gift) havolasidan ma'lumot olish
#
# Admin  https://t.me/nft/PlushPepe-1234  havolasini yuboradi, bot esa:
#   * NFT nomi va raqamini  (Plush Pepe #1234)
#   * RASMini               (og:image yoki nft.fragment.com CDN)
#   * Model / Backdrop / Symbol xususiyatlarini
# avtomatik aniqlaydi. Qo'lda hech narsa kiritish shart emas.
#
# Xavfsizlik: faqat t.me/nft/... (va telegram.me) havolalari qabul qilinadi,
# shuning uchun serverdan ixtiyoriy manzilga so'rov yuborib bo'lmaydi (SSRF yo'q).
# ===================================================================

from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass
from typing import Awaitable, Callable

# t.me/nft/<Nom>-<raqam>   (https:// yoki www. bo'lmasligi ham mumkin)
_URL_RE = re.compile(
    r"^\s*(?:https?://)?(?:www\.)?(?:t|telegram)\.me/nft/"
    r"([A-Za-z0-9_]{2,64})-(\d{1,9})/?(?:[?#]\S*)?\s*$",
    re.IGNORECASE,
)
# Faqat "PlushPepe-1234" ko'rinishida yuborilsa ham tushunamiz
_BARE_RE = re.compile(r"^\s*([A-Za-z0-9_]{2,64})-(\d{1,9})\s*$")

CDN = "https://nft.fragment.com/gift"
PAGE = "https://t.me/nft"

# Fetcher: url -> matn (HTML/JSON) yoki None (xato bo'lsa)
Fetcher = Callable[[str], Awaitable["str | None"]]


class NftUrlError(ValueError):
    """Havola t.me/nft/<Nom>-<raqam> formatida emas."""


@dataclass
class NftInfo:
    url: str            # kanonik havola: https://t.me/nft/PlushPepe-1234
    slug: str           # PlushPepe-1234
    name: str           # Plush Pepe
    number: int         # 1234
    image: str          # rasm URL (https)
    model: str = ""
    backdrop: str = ""
    symbol: str = ""
    found_page: bool = False   # t.me sahifasi o'qildimi

    @property
    def title(self) -> str:
        return f"{self.name} #{self.number}"


def parse_nft_url(raw: str) -> tuple[str, int]:
    """Havoladan (Nom, raqam) ni ajratadi. Noto'g'ri bo'lsa NftUrlError."""
    raw = (raw or "").strip()
    m = _URL_RE.match(raw) or _BARE_RE.match(raw)
    if not m:
        raise NftUrlError("bad_url")
    return m.group(1), int(m.group(2))


def humanize(name: str) -> str:
    """PlushPepe -> 'Plush Pepe', Snoop_Dogg -> 'Snoop Dogg'."""
    name = name.replace("_", " ")
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    name = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def image_url(name: str, number: int, size: str = "large") -> str:
    """Fragment CDN dagi rasm (nom kichik harfda): .../plushpepe-1234.large.jpg"""
    key = f"{name.replace('_', '').lower()}-{number}"
    return f"{CDN}/{key}.{size}.jpg"


# ---------------------------------------------------------------
# HTML / JSON tahlili
# ---------------------------------------------------------------

_META_RE = re.compile(r"<meta\b([^>]*)>", re.IGNORECASE)
_ATTR_RE = re.compile(r"([a-zA-Z_:-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")


def _metas(page: str) -> dict[str, str]:
    """<meta property|name=... content=...> -> {kalit: qiymat} (birinchisi qoladi)."""
    out: dict[str, str] = {}
    for m in _META_RE.finditer(page or ""):
        attrs = {a.lower(): (v1 or v2) for a, v1, v2 in _ATTR_RE.findall(m.group(1))}
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key and "content" in attrs and key not in out:
            out[key] = _html.unescape(attrs["content"]).strip()
    return out


_TRAIT_RE = {
    "model": re.compile(r"\bModel\s*[:：]\s*([^\n\r<]+)", re.IGNORECASE),
    "backdrop": re.compile(r"\bBackdrop\s*[:：]\s*([^\n\r<]+)", re.IGNORECASE),
    "symbol": re.compile(r"\bSymbol\s*[:：]\s*([^\n\r<]+)", re.IGNORECASE),
}


def _clean_trait(value: str) -> str:
    """'Aquamarine (0.5%)' -> 'Aquamarine'; ortiqcha bo'shliqlarni olib tashlaydi."""
    value = re.sub(r"\s*\(?\d+(?:[.,]\d+)?\s*%\)?\s*$", "", value.strip())
    return re.sub(r"\s+", " ", value).strip()[:80]


def parse_traits(text: str) -> dict[str, str]:
    """Matndan Model / Backdrop / Symbol ni topadi (har biri bo'lmasa bo'sh)."""
    res = {}
    for key, rx in _TRAIT_RE.items():
        m = rx.search(text or "")
        res[key] = _clean_trait(m.group(1)) if m else ""
    return res


def _traits_from_page(page: str) -> dict[str, str]:
    """Avval meta description, bo'lmasa sahifadagi jadvaldan (<th>Model</th><td>..)."""
    metas = _metas(page)
    traits = parse_traits(
        "\n".join(metas.get(k, "") for k in ("twitter:description", "og:description", "description"))
    )
    if all(traits.values()):
        return traits
    # Jadval: <tr><th>Model</th><td>Aquamarine<mark>0.5%</mark></td></tr>
    for key, label in (("model", "Model"), ("backdrop", "Backdrop"), ("symbol", "Symbol")):
        if traits[key]:
            continue
        m = re.search(
            rf"<th[^>]*>\s*{label}\s*</th>\s*<td[^>]*>(.*?)</td>", page or "",
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            cell = re.sub(r"<mark[^>]*>.*?</mark>", "", m.group(1), flags=re.DOTALL | re.IGNORECASE)
            cell = _html.unescape(re.sub(r"<[^>]+>", "", cell))
            traits[key] = _clean_trait(cell)
    return traits


def _traits_from_json(text: str) -> dict[str, str]:
    """nft.fragment.com/gift/<slug>.json (TON NFT metadata: attributes[])."""
    res = {"model": "", "backdrop": "", "symbol": ""}
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return res
    attrs = data.get("attributes") if isinstance(data, dict) else None
    if isinstance(attrs, list):
        for a in attrs:
            if not isinstance(a, dict):
                continue
            k = str(a.get("trait_type", "")).strip().lower()
            if k in res:
                res[k] = _clean_trait(str(a.get("value", "")))
    return res


def _safe_https(url: str) -> str:
    """Rasm manzili faqat https:// bo'lsa qabul qilinadi."""
    url = (url or "").strip()
    return url if url.lower().startswith("https://") else ""


async def fetch_nft(raw_url: str, fetch: Fetcher | None = None) -> NftInfo:
    """
    Havola bo'yicha NFT ma'lumotini yig'adi.
    Raises NftUrlError - havola noto'g'ri bo'lsa.
    Tarmoq xatosida ham tashlamaydi: rasm CDN qoidasi bo'yicha tuziladi.
    """
    name_raw, number = parse_nft_url(raw_url)
    slug = f"{name_raw}-{number}"
    fetch = fetch or _http_fetch

    info = NftInfo(
        url=f"{PAGE}/{slug}",
        slug=slug,
        name=humanize(name_raw),
        number=number,
        image=image_url(name_raw, number),
    )

    page = await fetch(info.url)
    if page:
        info.found_page = True
        metas = _metas(page)
        img = _safe_https(metas.get("og:image") or metas.get("twitter:image", ""))
        if img:
            info.image = img
        title = metas.get("og:title", "")
        # "Plush Pepe #1234" yoki "Plush Pepe #1234 — Telegram"
        tm = re.match(r"\s*(.+?)\s*#\s*(\d+)", title)
        if tm:
            info.name = tm.group(1).strip()[:100]
            info.number = int(tm.group(2))
        traits = _traits_from_page(page)
        info.model, info.backdrop, info.symbol = (
            traits["model"], traits["backdrop"], traits["symbol"])

    if not (info.model and info.backdrop and info.symbol):
        # Zaxira: Fragment CDN dagi JSON metadata
        blob = await fetch(f"{CDN}/{slug.replace('_', '').lower()}.json")
        if blob:
            t = _traits_from_json(blob)
            info.model = info.model or t["model"]
            info.backdrop = info.backdrop or t["backdrop"]
            info.symbol = info.symbol or t["symbol"]
            if not info.found_page and any(t.values()):
                info.found_page = True
    return info


async def _http_fetch(url: str) -> str | None:
    """Standart yuklovchi (httpx). Xatoda None qaytaradi."""
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=12, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; StarsBot/1.0)"},
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            return r.text[:600_000]
    except Exception:  # noqa: BLE001
        return None
