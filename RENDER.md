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


## 💳 TO'LIQ AVTO-TO'LOV (Humo/Uzcard Telegram bildirishnomalari): qanday ishlaydi
1. Foydalanuvchi **mini-app → «Hisob to'ldirish»** (yoki botda «💳 Hisobni to'ldirish → Karta orqali») dan summani tanlaydi.
2. Bot unga **noyob summa** beradi: masalan 50 000 so'm → **50 037 so'm**. Karta raqami, karta egasi va aynan shu summa ko'rsatiladi.
3. Foydalanuvchi **aynan shu summani** kartaga o'tkazadi. Tranzaksiya ID kiritish shart emas.
4. Karta egasining userboti (Telethon) bankning Telegram bildirishnoma botidan kelgan xabarni o'qiydi:
   `➕ 50 037.00 UZS, HUMOCARD *1234, 25.11.26 15:42`
5. Userbot summani ajratib, kutilayotgan buyurtmalar orasidan aynan shu summani topadi va **balansni avtomatik to'ldiradi** (bitta bank kirimi faqat bir marta ishlatiladi).
6. Natija foydalanuvchiga bot orqali darhol yuboriladi. `TOPUP_VERIFY_TIMEOUT` (default 15 daqiqa) ichida to'lov kelmasa buyurtma bekor qilinadi.

### Userbotni sozlash (bir marta)
1. **Humo/Uzcard bildirishnomasini yoqing.** Humo uchun `HUMOcardbot` (yoki bankingizning xabar boti) ga kartangizni telefon raqami orqali ulang. Uzcard uchun bank ilovasi orqali Telegram bildirishnomalarini yoqing.
2. **Alohida Telegram akkaunt oching** (gift akkauntidan ham, asosiy akkauntingizdan ham boshqa). Shu akkauntda bank bildirishnoma botiga kirib, xabarlarni yoqing.
3. `python tools/gen_session.py` ni ishga tushiring (Telethon o'rnatilgan bo'lsin), telefon raqam + kod bilan kiring va chiqqan uzun `StringSession` qatorini oling.
4. Render → Environment:
   - `BANK_SESSION` = olingan session qatori (hech kimga bermang, gitga push qilmang!)
   - `BANK_SOURCE_CHATS` = bildirishnoma yuboradigan bot username'lari, vergul bilan: `HUMOcardbot,CardXabarBot`
   - `PAYMENT_CARD` = karta raqami, `PAYMENT_CARD_HOLDER` = karta egasi
5. Deploy qiling. Logda `Bank tinglovchi ishga tushdi: ...` ko'rinishi kerak. Test: o'zingiz kichik summa bilan to'lov qilib ko'ring.

### Zaxira usullar
| Usul | Sozlash |
|---|---|
| **Webhook** (SMS-forwarder) | `BANK_WEBHOOK_SECRET` kiriting. Telefonda SMS-forwarder ilovasi `POST https://<servis>.onrender.com/api/bank/notify`, sarlavha `X-Bank-Secret: <secret>`, tana `{"text":"<SMS matni>"}` yuboradi. |
| **Qo'lda** | `BANK_AUTO=1` va admin bank xabarini `/bankadd <matn>` bilan kiritadi. |

Hech biri sozlanmasa — to'lovlar **adminga qo'lda tasdiqlash** tugmalari bilan boradi (xavfsiz zaxira rejim).
Eski usul (tranzaksiya ID kiritish) ham saqlanadi: avto manba sozlanmagan bo'lsa bot ID so'raydi.

## 🔒 Majburiy obuna
Admin panel → «Kanal» (yoki `REQUIRED_CHANNEL` env) orqali kanal beriladi. Bot **kanalda admin** bo'lishi shart.
Endi obuna **har bir bosishda** tekshiriladi (faqat /start da emas), mini-app ham obunasizlarga yopiq.
Obunasizlarga «📢 Kanalga o'tish» + «✅ Tekshirish» tugmalari chiqadi. Adminlar tekshiruvdan ozod.
