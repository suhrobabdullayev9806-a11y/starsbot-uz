# ⭐ Auto Stars Telegram Bot

Telegram Stars (yulduzlar) sotib olish/gift/postga stars yuborish uchun to'liq, modulli va xavfsiz Telegram bot.

**Texnologiyalar:** Python 3.12 · aiogram 3 · SQLite (aiosqlite) · FastAPI WebApp · Docker · GitHub Actions · Pytest

---

## 📌 Funksiyalar

### Foydalanuvchi
- 🛒 Paketlar orqali Stars sotib olish (**15, 30, 50, 100**)
- 🔗 **API orqali avtomatik sotib olish** (`@Apilarimbot` — `src/api_client.py`)
- 📝 Rasim/matn yuborib **postga stars olish** (admin tasdiqi bilan)
- 🎁 **Gift olish/berish** — akkaunt ulansa avtomatik yetkaziladi
- 🚀 **SMM Nakrutka (mini-app)** — obunachi/ko'rish/layk buyurtma qilish, so'm hisobidan to'lanadi, foydalanuvchilarga **API** beriladi
- 🎮 **PUBG UC olish (mini-app, `/uc`)** — PUBG ID kiritiladi, nickname ko'rsatiladi, so'mlik hisobdan yechiladi, adminga ariza boradi
- 🖼 **NFT olish (mini-app)** — admin qo'shgan Telegram NFT'larni so'mlik hisobdan sotib olish
- 👛 **Hisob yuritish** — progress bar, sotilgan/sotib olingan stars, harakatlar tarixi
- 💳 To'lov: **karta** (ruchka) va **online API** (balansdan ham mumkin)
- 📢 **Majburiy obuna** (@channel) — obuna bo'lmasa bot ishlamaydi
- 🌐 **Multilingual** — O'zbekcha / English / Русский

### Admin panel (Telegram ichida + WebApp)
- 📦 Buyurtmalar: qabul qilish, rad etish, status
- 📝 Postga starsni tasdiqlash/bekor qilish
- 🎁 Gift qo'shish / ayirish
- 💲 Narxlar va foizni belgilash
- 🎮 **UC boshqarish** (admin mini-app → UC): statistika, buyurtmalar, paketlar, nickname tekshiruvi sozlamasi
- 🖼 **NFT boshqarish**: `t.me/nft/...` havolasi + narx → rasm, Model, Backdrop, Symbol avtomatik
- 🔑 Akkaunt ulash / o'chirish
- 📊 Sotuvlar statistikasi (kunlik / haftalik / oylik)
- 🔋 Botni ON/OFF qilish, kanal sozlash, reklama (broadcast), VIP

### Dizayn
- 🔴🟢🔵 3 rangli inline tugmalar (rangli emoji markerlar)
- Har paket uchun rasm (`assets/images/star_*.png`)
- Step-by-step: Paket → To'lov → Yetkazish · do'kon navigatsiyada orqaga tugmasi

---

## 📁 Tuzilma

```
stars-bot/
├── src/
│   ├── main.py            # ishga tushirish (polling + webapp)
│   ├── config.py          # .env sozlamalari (pydantic)
│   ├── database.py        # SQLite + SettingsRepo
│   ├── models.py          # pydantic modellar (validation)
│   ├── security.py        # admin auth, HMAC, sanitization
│   ├── i18n.py            # Uz/En/Ru tarjimalar
│   ├── keyboards.py       # rangli inline tugmalar
│   ├── utils.py           # progress bar, parse, format
│   ├── api_client.py      # @Apilarimbot API adapter
│   ├── modules/           # ⬅ biznes mantiq
│   │   ├── users.py       #    foydalanuvchilar + balans
│   │   ├── orders.py      #    buyurtmalar + stats
│   │   ├── payments.py    #    to'lovlar (karta/API/balans)
│   │   ├── gifts.py       #    giftlar
│   │   ├── accounts.py    #    akkauntlar (shifrlangan session)
│   │   └── admin.py       #    admin panel mantiqasi
│   ├── handlers/          # Telegram qayta ishlovchilar
│   └── webapp/            # FastAPI admin WebApp + API callback
├── assets/images/         # paket rasmlari (ozingiz almashtirasiz)
├── tools/generate_images.py
├── tests/                 # 31 unit test
├── render.yaml            # Render Blueprint
├── RENDER.md              # Render qo'llanmasi
├── requirements-dev.txt   # test qaramliklari
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/ci.yml
```

---

## 🚀 Ishga tushirish

### 1. Sozlash
```bash
cp .env.example .env
```
`.env` ichida:
- `BOT_TOKEN` — @BotFather'dan
- `ADMIN_IDS` / `SUPER_ADMIN_ID` — adminlar ID lari
- `REQUIRED_CHANNEL` — majburiy kanal (@belgisiz) + `REQUIRED_CHANNEL_ID` (botni kanalga admin qiling)
- `PAYMENTS_PROVIDER_TOKEN` — Stars (XTR) qabuli uchun (ixtiyoriy)
- `STARS_API_BASE_URL` / `STARS_API_KEY` — `@Apilarimbot` API (ixtiyoriy)

### 2. Lokal (Windows/Linux)
```bash
python -m venv venv
venv\Scripts\activate            # Windows  |  source venv/bin/activate
pip install -r requirements.txt
python tools/generate_images.py  # paket rasmlari
python -m src.main
```

### 3. Render (tavsiya etiladi)
> ⚠️ Zip ichidagi fayllarni repo **ildiziga** yuklang (`requirements.txt` ildizda bo'lsin).
Qadam-baqadam qo'llanma: **[RENDER.md](RENDER.md)** · Blueprint: `render.yaml`

### 4. Docker
```bash
docker compose up -d --build
# WebApp admin panel: http://localhost:8080/admin
```

---

## 📲 Botdan foydalanish

- `/start` → menyu · `/admin` → admin panel · `/lang` → til
- WebApp WebAdmin sahifasini Telegram orqali ochish uchun: BotFather → Menu button → `https://your-host/admin`

---

## 🧪 Testlar

```bash
pytest -q
```
CI (GitHub Actions) har push'da testlarni yuritadi va `ghcr.io` ga Docker tasvirini build qiladi.

---

## 🔌 API integratsiyasi (@Apilarimbot)

`src/api_client.py::StarsApiClient` — avtomatik sotib olish adapteri.

- `purchase()` — buyurtmani APIga yuboradi
- Provider'ingiz `POST /api/callback` ga qayta chaqiradi:
  ```json
  {"order_id": 1, "status": "done", "reference": "stars-1"}
  ```
  Header: `X-API-Signature: HMAC-SHA256(payload)` (kalit: `API_CALLBACK_SECRET`)
- Haqiqiy provider API spetsifikatsiyasiga moslash uchun `_call()` ni sozlang.

---

## 🛡 Xavfsizlik

- Admin huquqlar: `security.is_admin()` — hamma admin amallarda tekshiriladi
- API callback: `verify_callback_signature()` HMAC-SHA256
- WebApp: initData `WebAppData` HMAC tekshiruvi (24 soat)
- Aloqa tashqi API: HTTPX + timeout
- Akkaunt sessionlari: `sha256` bilan shifrlanib saqlanadi
- Kiruvchi matnlar: uzunlik/son cheklovlari, sanitization (`safe_text`, `safe_amount`)
- `.env` va `data/` gitdan himoyalangan (`.gitignore`)

---

## 📝 Eslatmalar

- Gift yetkazish va post ostidagi haqiqiy stars yuborish Telegram user-session (Telethon/Pyrogram) talab qiladi — `accounts.py::deliver_gift` nuqtasini o'z sessiyangiz bilan to'ldiring.
- Paket rasmlari `assets/images/star_{n}.png` — o'zingiznikiga osongina almashtiring.

---

## 🖼 NFT olish (mini-app)

**Admin:** `/admin` → **🖼 NFT boshqarish** → **➕ NFT qo'shish (URL)**
1. `https://t.me/nft/PlushPepe-1234` havolasini yuboradi
2. Bot sahifani o'qib **rasm**, **Model / Backdrop / Symbol** ni o'zi aniqlaydi va oldindan ko'rsatadi
3. Admin **narxni (so'mda)** yuboradi — NFT katalogga tushadi

**Foydalanuvchi:** bosh menyudagi **🖼 NFT olish** tugmasi mini-app (`/nft`) ni ochadi: katalog → NFT → *Sotib olish*.
Narx so'mlik hisobdan yechiladi (yetmasa «Hisobni to'ldirish» tugmasi chiqadi).

**Yetkazish:** buyurtma adminlarga rasm bilan keladi. Admin NFT'ni xaridorga Telegramda yuboradi va
**Tasdiqlash** ni bosadi → xaridorga xabar. **Rad etish** → pul qaytariladi, NFT yana sotuvga chiqadi.
Har bir NFT yagona nusxa: bir vaqtda ikki kishi ola olmaydi.

> Mini-app tugmasi ishlashi uchun `WEBAPP_BASE_URL` (Render'da avtomatik) sozlangan bo'lishi kerak.
> Fayllar: `src/nft_parser.py`, `src/modules/nft.py`, `src/handlers/nft.py`, `src/webapp/static/nft.html`, `tests/test_nft.py`.

---

## 🛠 Admin mini-app (yangi) — `/admin`

Botda `/admin` → **🛠 Admin mini-app** tugmasi (yoki BotFather → Menu button → `https://HOST/admin`).
Bo'limlar: **Bosh** (statistika, akkaunt testi) · **Buyurtma** (tasdiqlash/rad: Stars, Post, Gift, Hisob, NFT) ·
**NFT** (havola bilan qo'shish + ko'rish, narx o'zgartirish, o'chirish) · **Users** (qidirish, hisob qo'shish/ayirish) ·
**Sozlama** (bot ON/OFF, narxlar, karta). API: `src/webapp/admin_api.py` (`/api/adm/*`).

## 📝 Postga stars — tuzatishlar
- Post oldindan tekshiriladi, akkaunt Stars balansi tekshiriladi, FloodWait kutiladi, ulanish qayta uriniladi.
- Xato sababi endi tushunarli ko'rsatiladi (foydalanuvchiga ham, adminga ham).
- Muhim: kanalda **Stars reaksiya (paid reactions)** yoqilgan bo'lishi va ulangan akkauntda yetarli ⭐ bo'lishi kerak.


## 🚀 SMM Nakrutka (mini-app)

Bosh menyudagi **🚀 SMM Nakrutka** tugmasi mini-app (`/smm`) ni ochadi: platforma → xizmat → havola va miqdor → narx (jonli hisoblagich) → *Buyurtma berish*.
Summa so'mlik hisobdan **atomik** yechiladi, buyurtma provayderga yuboriladi. Provayder rad etsa, bekor qilsa yoki qisman bajarsa — pul (proporsional) **avtomatik qaytariladi** va foydalanuvchiga botda xabar boradi. Holat har 60 soniyada provayderdan yangilanadi.

**Admin sozlashi** (`/admin` → **🚀 SMM** tabi):
1. **Sozlama:** provayder API manzili va kaliti (standart SMM-panel "API v2": `action=services|add|status|balance`), *Ulanishni tekshirish*; kurs (provayder valyutasi → so'm) va ustama foiz; xizmatni va "foydalanuvchilarga API berish"ni yoqish/o'chirish.
2. **Xizmatlar:** *Provayderdan import* (kategoriyalarni tanlang, narx = provayder narxi × kurs × (1+foiz)), qo'lda qo'shish, narx/min/max tahrirlash, yashirish, ommaviy amallar. Kurs yoki foiz o'zgarsa avto-narxlar qayta hisoblanadi; qo'lda qo'yilgan narx saqlanadi.
3. **Buyurtmalar:** holatlar, provayder ID, qo'lda bekor qilish + qaytarish, holatni majburan yangilash.

**API berish:** mini-appdagi **API** bo'limida foydalanuvchi kalit yaratadi (faqat hash saqlanadi, to'liq kalit bir marta ko'rsatiladi). Manzil: `POST /api/v2` (`key`, `action=services|add|status|balance`; form yoki JSON), minutiga 60 so'rov. Narxlar so'mda (1000 ta uchun), valyuta `UZS`.

Eslatma: provayder kaliti `settings` jadvalida (Stars API kaliti kabi) saqlanadi; admin panelda faqat oxirgi 4 belgi ko'rinadi.
