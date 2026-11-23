# ===================================================================
# utils.py - Umumiy yordamchi funksiyalar
# Progress bar, narx formatlash, statistikalar.
# ===================================================================

from __future__ import annotations

import re
from datetime import datetime, timedelta

# Progress bar uchun belgilar
FILL = "▰"
EMPTY = "▱"


def progress_bar(current: float, total: float = 100.0, width: int = 10) -> str:
    """Foydalanuvchi balansini vizual progress bar shaklida ko'rsatadi."""
    if total <= 0:
        return FILL * 0 + EMPTY * width
    ratio = max(0.0, min(1.0, current / total))
    filled = round(ratio * width)
    return FILL * filled + EMPTY * (width - filled)


def prices_text(prices: dict[int, float], percent: float = 0.0) -> str:
    """Narxlar ro'yxatini chiroyli matn shaklida formatlaydi."""
    lines = []
    for amount in sorted(prices):
        price = prices[amount]
        final = round(price * (1 + percent / 100), 2) if price else 0
        lines.append(f"⭐ <b>{amount}</b> Stars  →  {final:,.0f} so'm")
    return "\n".join(lines)


def format_amount(value: float) -> str:
    """Sonni minglik ajratgichlar bilan formatlaydi."""
    return f"{value:,.0f}".replace(",", " ")


def parse_price_input(raw: str) -> dict[int, float] | None:
    """Admin kiritgan narx formatini parse qiladi: 15=30000,30=55000."""
    result: dict[int, float] = {}
    pattern = re.compile(r"^\s*(\d{1,4})\s*[=:]\s*(\d{1,9})\s*$")
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        m = pattern.match(part)
        if not m:
            return None
        result[int(m.group(1))] = float(m.group(2))
    return result or None


def parse_phone(value: str) -> str | None:
    """Telefon raqamini tekshiradi va normalizatsiya qiladi."""
    digits = re.sub(r"\D", "", value)
    # 10 yoki 12 raqamli (998901234567 yoki 901234567)
    if len(digits) == 12:
        return "+" + digits
    if len(digits) == 9:
        return "+998" + digits
    return None


def parse_recipient(value: str) -> tuple[str, str] | None:
    """Gift qabul qiluvchini qabul qiladi.

    Qabul qiladi:
      - telefon raqam  -> ("phone", "+998901234567")
      - @username      -> ("username", "@ali")
    Noto'g'ri bo'lsa None qaytaradi.
    """
    text = (value or "").strip()
    if text.startswith("tel:"):
        text = text[4:]
    if text.startswith("@"):
        uname = text[1:]
        if re.fullmatch(r"[A-Za-z0-9_]{3,32}", uname):
            return ("username", "@" + uname)
        return None
    # Telefon raqam
    phone = parse_phone(text)
    if phone:
        return ("phone", phone)
    # @ belgisisiz username kiritilsa ham qabul qilamiz
    if re.fullmatch(r"[A-Za-z0-9_]{3,32}", text):
        return ("username", "@" + text)
    return None


def parse_stars_request(text: str) -> tuple[int | None, str | None]:
    """Post-stars so'rovini parse qiladi.
    Kutilgan rasm:  '100 stars\\\\nhttps://t.me/username/123'
    Qaytaradi: (amount, post_link)
    """
    first_line = (text or "").strip().splitlines()[0]
    m = re.match(r"^\s*(\d{1,6})\s*(?:stars|звёзд|звезд|yulduz|старов)?\s*$", first_line, re.IGNORECASE)
    if not m:
        return None, None
    link = next(
        (ln.strip() for ln in text.splitlines() if "t.me/" in ln),
        None,
    )
    if not link:
        return None, None
    return int(m.group(1)), link


def day_start(dt: datetime | None = None) -> datetime:
    dt = dt or datetime.now()
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def week_start(dt: datetime | None = None) -> datetime:
    today = day_start(dt)
    return today - timedelta(days=today.weekday())


def month_start(dt: datetime | None = None) -> datetime:
    today = day_start(dt)
    return today.replace(day=1)