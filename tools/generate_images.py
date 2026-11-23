# ===================================================================
# tools/generate_images.py - Paket rasmlari + bosh menyu banneri
# Gradient fon, glow yulduz, "AUTO STARS" branding.
# Rasmlar assets/images/ ga tushadi. O'zingiznikiga almashtirsangiz
# shu papkaga tashlang — xuddi shu nomda bo'lishi kifoya.
# ===================================================================

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "images"

# Palitra
_TOP = (24, 32, 74)        # to'q ko'k
_BOT = (46, 20, 60)        # binafsha
_STAR = (255, 205, 45)
_STAR_GLOW = (255, 170, 0)
_TEXT = (255, 255, 255)
_ACCENT = (46, 204, 113)

PACKAGES = [15, 30, 50, 100]


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _vertical_gradient(w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        r = int(_TOP[0] + (_BOT[0] - _TOP[0]) * y / h)
        g = int(_TOP[1] + (_BOT[1] - _TOP[1]) * y / h)
        b = int(_TOP[2] + (_BOT[2] - _TOP[2]) * y / h)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def _glow_star(x: int, y: int, size: int, draw: ImageDraw.ImageDraw) -> None:
    font = _font(size)
    glow_font = _font(size + int(size * 0.15))
    draw.text((x, y), "⭐", font=glow_font,
              fill=_STAR_GLOW, anchor="mm", stroke_width=2)
    draw.text((x, y), "⭐", font=font, fill=_STAR, anchor="mm")


def _ellipsis(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    while draw.textbbox((0, 0), text, font=font)[2] > max_w and len(text) > 1:
        text = text[:-2] + "…"
    return text


# ---------------------------------------------------------------
# Paket kartasi (512x512)
# ---------------------------------------------------------------

def generate_package(amount: int, out: Path) -> None:
    W = H = 512
    img = _vertical_gradient(W, H).filter(ImageFilter.GaussianBlur(2))
    draw = ImageDraw.Draw(img)

    # Rounded ramka
    draw.rounded_rectangle((28, 28, W - 28, H - 28), radius=44,
                           outline=(255, 255, 255, 60), width=5)
    draw.rounded_rectangle((40, 40, W - 40, H - 40), radius=38,
                           outline=_ACCENT, width=3)

    # Markaziy yulduz (glow)
    _glow_star(W // 2, 170, 150, draw)

    # "N Stars"
    font = _font(78)
    label = f"{amount} STARS"
    label = _ellipsis(draw, label, font, W - 120)
    bb = draw.textbbox((0, 0), label, font=font)
    draw.text((W // 2, 300), label, font=font, fill=_TEXT,
              anchor="mm", stroke_width=2, stroke_fill=_STAR_GLOW)

    # Pastki marker
    sub = _font(30)
    draw.text((W // 2, 430), "✦ AUTO STARS ✦", font=sub,
              fill=_ACCENT, anchor="mm")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"[OK] {out.name}")


# ---------------------------------------------------------------
# Bosh menyu banneri (1024x512, keng)
# ---------------------------------------------------------------

def generate_banner(out: Path) -> None:
    W, H = 1024, 512
    img = _vertical_gradient(W, H).filter(ImageFilter.GaussianBlur(2))
    draw = ImageDraw.Draw(img)

    # Yuqori chiziq
    draw.rounded_rectangle((0, 0, W, H), radius=0, outline=_ACCENT, width=8)

    # Chapdagi katta yulduz
    _glow_star(220, H // 2, 230, draw)

    # Sarlavha
    font = _font(110)
    title = "AUTO STARS"
    title = _ellipsis(draw, title, font, W - 620)
    draw.text((560, H // 2 - 70), title, font=font, fill=_TEXT,
              anchor="mm", stroke_width=3, stroke_fill=_STAR_GLOW)

    # Pastki slogan
    sub = _font(38)
    draw.text((560, H // 2 + 60), "TELEGRAM STARS  •  BUY  •  GIFT  •  FAST",
              font=sub, fill=(200, 220, 255), anchor="mm")

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"[OK] {out.name}")


def main() -> None:
    for amount in PACKAGES:
        generate_package(amount, ASSETS / f"star_{amount}.png")
    generate_banner(ASSETS / "banner.png")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] {exc}", file=sys.stderr)
        sys.exit(1)