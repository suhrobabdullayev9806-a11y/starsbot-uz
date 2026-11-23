# 🚀 Render'ga joylashtirish (qadam-baqadam)

Bot **Web Service** sifatida ishlaydi: bitta jarayonda Telegram polling + FastAPI
(admin panel, mini-app, `/api/callback`) birga turadi. Render bergan `PORT` avtomatik ishlatiladi.

## 1. GitHub'ga yuklash
> ⚠️ **`requirements.txt` topilmadi** xatosi chiqsa: fayllar repo **ILDIZIDA** bo'lishi kerak
> (`requirements.txt`, `render.yaml`, `src/` shu darajada). Zipni ochib, **ichidagi fayllarni**
> yuklang (papkani emas). Agar repo ichida `StarsBot/` papkasi bo'lib qolgan bo'lsa — Render'da
> *Settings → Root Directory* ga `StarsBot` deb yozing.

```bash
cd StarsBot
git init && git add . && git commit -m "StarsBot for Render"
git branch -M main
git remote add origin https://github.com/<login>/<repo>.git
git push -u origin main
```
`.env` va `data/` `.gitignore` da — ular GitHub'ga **chiqmaydi** (shunday bo'lishi kerak).

## 2. Render'da yaratish (Blueprint)
1. https://dashboard.render.com → **New + → Blueprint** → repo'ni tanlang.
2. `render.yaml` o'qiladi. So'ralgan 3 ta qiymatni kiriting:
   - `BOT_TOKEN` — @BotFather tokeni
   - `ADMIN_IDS` — admin ID lari (vergul bilan: `123,456`)
   - `SUPER_ADMIN_ID` — bosh admin ID
3. **Apply** bosing. Build ~2–4 daqiqa. Loglarda `Bot ishga tushmoqda...` chiqsa — tayyor.

> Qo'lda yaratsangiz: **New + → Web Service**, Language = **Python 3**,
> Build: `pip install -r requirements.txt`, Start: `python -m src.main`,
> Health Check Path: `/healthz`, Disk: Mount Path `/var/data`, va `DB_PATH=/var/data/stars.db`.
> (Language ni **Docker** qilmang — Dockerfile lokal uchun, diskka yozish huquqi muammosi chiqadi.)

## 3. Qo'shimcha o'zgaruvchilar (Dashboard → Environment)
| Kalit | Izoh |
|---|---|
| `REQUIRED_CHANNEL`, `REQUIRED_CHANNEL_ID` | Majburiy obuna kanali (bot kanalga admin bo'lsin) |
| `PAYMENT_CARD` | To'lov kartasi |
| `PAYMENTS_PROVIDER_TOKEN` | Ixtiyoriy |
| `STARS_API_BASE_URL`, `STARS_API_KEY` | @Apilarimbot API |
| `API_CALLBACK_SECRET` | Uzun tasodifiy kalit; API provayderga ham shuni bering |

`WEBAPP_BASE_URL` **kerak emas**: Render'ning `RENDER_EXTERNAL_URL` i avtomatik olinadi
(mini-app tugmasi `https://<servis>.onrender.com/app` ni ochadi).

API callback manzili: `https://<servis>.onrender.com/api/callback`
Admin panel: `https://<servis>.onrender.com/admin`

## ⚠️ Ma'lumotlar saqlanishi (juda muhim)
Bot SQLite ishlatadi. Render'da fayl tizimi **vaqtinchalik**, faqat **Persistent Disk** saqlanadi.
- **Starter (pullik) + Disk** (`render.yaml` dagi default): baza deploy/restartdan keyin ham saqlanadi. ✅
- **Free tarif**: disk yo'q → har deploy, restart va uxlab-uyg'onishda **baza (foydalanuvchilar, balans,
  buyurtmalar, ulangan akkauntlar) o'chadi**. Faqat sinov uchun.
  Free'da `render.yaml` da `plan: free` yozing, `disk:` blokini va `DB_PATH` qatorini olib tashlang;
  servis uxlab qolmasligi uchun `KEEP_ALIVE` default yoqiq (o'zini har 10 daqiqada ping qiladi).

Pul bilan ishlovchi bot uchun Starter + Disk tavsiya etiladi.

## Eski bazani ko'chirish (ixtiyoriy)
`data/stars.db` ni Render **Shell** (Dashboard → Shell) yoki `scp` orqali `/var/data/stars.db` ga qo'ying.
Avval lokal botni to'xtating va `stars.db-wal` ni `stars.db` ga qo'shing:
`sqlite3 stars.db "PRAGMA wal_checkpoint(TRUNCATE);"`.
Ulangan Telegram akkaunt sessiyalari `BOT_TOKEN` dan olingan kalit bilan shifrlangan — token o'zgarsa,
akkauntlarni qayta ulashingiz kerak bo'ladi.

## Xavfsizlik
- Eski `.env` dagi **BOT_TOKEN, STARS_API_KEY** va boshqa kalitlar fayl sifatida yuborilgan edi —
  @BotFather'da `/revoke` qilib tokenni yangilash tavsiya etiladi (yangi token Render'ga kiritiladi).
- Bir vaqtda faqat **1 ta** instans ishlasin (polling). Lokal botni Render ishga tushgach o'chiring,
  aks holda `TelegramConflictError` chiqadi.

## Muammolar
| Belgi | Yechim |
|---|---|
| `BOT_TOKEN muhit o'zgaruvchisi belgilanmagan` | Environment ga `BOT_TOKEN` qo'shing |
| `ADMIN_IDS noto'g'ri` | Faqat raqamlar, vergul bilan |
| Deploy "No open ports detected" | `startCommand` = `python -m src.main`, `WEBAPP_HOST` ni 0.0.0.0 qoldiring |
| `TelegramConflictError` | Boshqa joyda (lokal/eski server) bot ishlayapti — o'chiring |
| "Stars olish" mini-app ochmaydi | `RENDER_EXTERNAL_URL` bor-yo'qligini tekshiring yoki `WEBAPP_BASE_URL` ni https bilan kiriting |


## ⭐ Postga stars — AVTOMATIK
Foydalanuvchi post havolasini yuborib "Tasdiqlash" bosganda:
1. Summa hisobidan yechiladi, buyurtma yaratiladi.
2. Stars **ulangan Telegram akkaunt** (admin panel → akkaunt ulash) orqali postga *paid reaction* sifatida yuboriladi
   (2500 dan ko'p bo'lsa bo'laklab).
3. Muvaffaqiyatli bo'lsa — foydalanuvchiga va to'lovlar kanaliga xabar; adminlarga ham xabar boradi.
4. Xato bo'lsa (akkaunt yo'q, Stars yetmaydi, havola noto'g'ri...) — pul **avtomatik qaytariladi**
   (qisman yuborilgan bo'lsa faqat qolgan qismi), adminlarga sababi bilan xabar boradi.

Talablar: kamida bitta **faol** akkaunt ulangan va uning **Stars balansi** yetarli bo'lishi kerak;
post ochiq kanalda bo'lsin (yopiq kanal `t.me/c/...` uchun akkaunt kanal a'zosi bo'lishi shart).


## 💳 AVTO-TO'LOV (mini-app + bot): qanday ishlaydi
1. Foydalanuvchi **mini-app → «Hisob to'ldirish»** (yoki botda «💳 Hisobni to'ldirish → Karta orqali») dan summani tanlaydi.
2. Karta raqami, **karta egasi ismi** va aynan to'lanadigan summa ko'rinadi (nusxalash tugmalari bilan).
3. U to'laydi va **tranzaksiya ID** sini yozadi.
4. Bot shu ID + aynan shu summa bilan yozilgan kirim bildirishnomasini qidiradi:
   - topilsa → balansga qo'shadi (**bitta tranzaksiya faqat bir marta**);
   - summa mos kelmasa / ID ishlatilgan bo'lsa → darhol **bekor qiladi**;
   - hali kelmagan bo'lsa → `TOPUP_VERIFY_TIMEOUT` (default 10 daqiqa) kutadi, kelmasa **bekor qiladi**.
   Natija botga tugmali xabar bo'lib keladi.

### Bank xabarlari botga qanday keladi? (MUHIM)
Bot bank API'siga ulanmaydi, u **karta egasiga kelgan kirim bildirishnomasini** o'qiydi.
Quyidagilardan kamida bittasini sozlang:

| Usul | Sozlash |
|---|---|
| **Webhook** (SMS-forwarder) | Render'da `BANK_WEBHOOK_SECRET` kiriting. Karta ulangan telefonda SMS-forwarder ilovasi o'rnatib, `POST https://<servis>.onrender.com/api/bank/notify`, sarlavha `X-Bank-Secret: <secret>`, tana `{"text":"<SMS matni>"}` yuboring. |
| **Telegram bildirishnoma boti** (CardXabar va h.k.) | `python tools/gen_session.py` bilan karta egasi akkaunti sessiyasini oling → `BANK_SESSION`, bot username'ini `BANK_SOURCE_CHATS` ga yozing (vergul bilan). Gift akkauntidan **boshqa** akkaunt ishlating. |
| **Qo'lda** | `BANK_AUTO=1` va admin bank xabarini `/bankadd <matn>` bilan kiritadi. |

Hech biri sozlanmasa — to'lovlar **adminga qo'lda tasdiqlash** tugmalari bilan boradi (xavfsiz zaxira rejim).

Tranzaksiya ID bildirishnoma matnida bo'lishi kerak (masalan `Ref: 4821937465`, `ID: ...`, `Чек №...`).
Bank xabarida ID umuman bo'lmasa, avto-tekshiruv ishlamaydi — shu holda qo'lda rejimdan foydalaning.
Test uchun: `/bankadd ➕ 50 000.00 UZS Ref: 4821937465` ni yuborib, so'ng 50 000 so'm va shu ID bilan to'lov qilib ko'ring.

## 🔒 Majburiy obuna
Admin panel → «Kanal» (yoki `REQUIRED_CHANNEL` env) orqali kanal beriladi. Bot **kanalda admin** bo'lishi shart.
Endi obuna **har bir bosishda** tekshiriladi (faqat /start da emas), mini-app ham obunasizlarga yopiq.
Obunasizlarga «📢 Kanalga o'tish» + «✅ Tekshirish» tugmalari chiqadi. Adminlar tekshiruvdan ozod.
