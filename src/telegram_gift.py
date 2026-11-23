# ===================================================================
# telegram_gift.py - TELEGRAM USER-SESSION ORQALI GIFT YETKAZISH
# Admin panelga ulangan Telegram akkaunt (Telethon StringSession)
# orqali @username / +telefon raqamiga haqiqiy gift yuboradi.
#   - payments.getStarGifts      -> qiymati (stars) to'g'ri keladigan gift
#   - InputInvoiceStarGift + GetPaymentFormRequest + SendStarsFormRequest
#                               -> gift yuborish (yangi Telegram API)
# Barqarorlik: har qanday xatoda False + asosli xabar qaytadi, bot
# o'zi ishlayveradi. Telethon importi lazy (yuklanish xatosiz).
# ===================================================================

from __future__ import annotations

import asyncio
import random
import re

# Telegram Desktop ommaviy identifikatorlari (API login uchun kerak).
_API_ID: int = 2040
_API_HASH: str = "b18441a1ff607e10a989891a5462e627"
_CONNECT_TIMEOUT: float = 20.0  # ulanish tiqilib qolmasligi uchun
# Telegram: bitta paid reaction so'rovida maksimal stars (stars_paid_reaction_amount_max)
_MAX_PAID_REACTION: int = 2500

# Post havolasi: t.me/username/123 yoki t.me/c/1234567890/123
_POST_LINK_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/"
    r"(?:s/)?(?:c/(?P<cid>\d+)|(?P<user>[A-Za-z0-9_]{3,32}))/(?P<mid>\d+)"
)

# Muqobil gift id'lar: agar getStarGifts javobida stars qiymati
# topilmasa, ushbu ma'lum qiymatlar bilan sendStarsGift chaqiriladi.
# Har bir value = giftning stars qiymati. (Kerak bo'lsa o'zingiz
# o'rnatasiz — real gift id lar Telegram serverdan dinamik keladi.)
FALLBACK_GIFT_IDS: dict[int, int] = {}


# Telegram RPC xatolari -> tushunarli sabab (admin va foydalanuvchi ko'radi)
_ERR_HINTS: tuple[tuple[str, str], ...] = (
    ("account_balance_low", "ulangan akkauntda Stars yetarli emas (balansni to'ldiring)"),
    ("post_not_found", "post topilmadi (havola noto'g'ri yoki post o'chirilgan)"),
    ("post_channel_not_found", "kanal topilmadi yoki yopiq"),
    ("bad_post_link", "post havolasi noto'g'ri"),
    ("no_active_account", "faol akkaunt ulanmagan"),
    ("session_not_authorized", "akkaunt sessiyasi eskirgan, qayta ulang"),
    ("BalanceTooLow", "akkauntda Stars yetarli emas"),
    ("StarsBalance", "akkauntda Stars yetarli emas"),
    ("BALANCE_TOO_LOW", "akkauntda Stars yetarli emas"),
    ("MessageIdInvalid", "post topilmadi (havola noto'g'ri yoki post o'chirilgan)"),
    ("ChannelPrivate", "kanal yopiq yoki akkaunt bloklangan"),
    ("ChatAdminRequired", "bu chatda ruxsat yo'q"),
    ("ChatWriteForbidden", "bu chatda ruxsat yo'q"),
    ("ReactionInvalid", "bu kanalda Stars reaksiya (paid reaction) yoqilmagan"),
    ("ReactionsTooMany", "bu kanalda Stars reaksiya yoqilmagan"),
    ("PaidReaction", "bu kanalda Stars reaksiya yoqilmagan"),
    ("PeerIdInvalid", "kanal topilmadi"),
    ("UsernameNotOccupied", "kanal username topilmadi"),
    ("UsernameInvalid", "kanal username noto'g'ri"),
    ("FloodWait", "Telegram vaqtincha cheklov qo'ydi, birozdan so'ng urining"),
    ("AuthKeyUnregistered", "akkaunt sessiyasi bekor qilingan, qayta ulang"),
    ("AuthKeyDuplicated", "sessiya boshqa joyda ishlatilmoqda, akkauntni qayta ulang"),
    ("SessionRevoked", "akkaunt sessiyasi bekor qilingan, qayta ulang"),
    ("UserDeactivated", "akkaunt o'chirilgan yoki bloklangan"),
    ("Timeout", "Telegram serveriga ulanib bo'lmadi"),
    ("ConnectionError", "Telegram serveriga ulanib bo'lmadi"),
)


def explain_error(exc) -> str:
    """Istisno (yoki matn) ni qisqa, tushunarli sababga aylantiradi."""
    name = exc if isinstance(exc, str) else type(exc).__name__
    raw = exc if isinstance(exc, str) else f"{name}: {exc}"
    for key, hint in _ERR_HINTS:
        if key.lower() in raw.lower():
            return f"{hint} [{name}]"
    return raw[:200]


class TelegramGiftSender:
    """Bitta Telegram user-session orqali gift yetkazadi."""

    # JS Quirk: Telethon StringSession usa to'g'ri; faqatgina
    # generate-session orqali olingan string kutiladi.

    async def send(self, session_string: str, amount: int,
                   recipient: str, kind: str = "phone") -> tuple[bool, str]:
        """
        recipient: "@username" yoki "+998901234567"
        Qaytaradi: (ok, message). message error yoki "ok".
        """
        from telethon import TelegramClient
        from telethon.errors import ForbiddenError
        from telethon.sessions import StringSession
        from telethon.tl import functions as _f
        from telethon.tl import types as _t

        session = (session_string or "").strip()
        if not session:
            return False, "empty_session"
        if len(session) < 40 or " " in session:
            return False, "invalid_session_string"

        try:
            parsed_session = StringSession(session)
        except ValueError:
            return False, "invalid_session_string"

        client = TelegramClient(
            parsed_session,
            _API_ID,
            _API_HASH,
            device_model="StarsBot",
            system_version="Windows 10",
            app_version="stars-bot 1.0",
            lang_code="en",
        )
        try:
            await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
            if not await client.is_user_authorized():
                return False, "session_not_authorized"

            # 1) Qabul qiluvchini yechish (@username yoki +telefon)
            try:
                peer = await client.get_input_entity(recipient.strip())
            except Exception:  # noqa: BLE001
                return False, f"recipient_not_found ({recipient.strip()})"

            # 2) Qiymatga to'g'ri keladigan gift id ni izlash
            gift_id = await self._find_gift_id(client, amount)
            if gift_id is None:
                return False, f"gift_not_found_for_{amount}_stars"

            # 3) Yangi Telegram API oqimi: form yaratish + to'lash.
            #    Eski SendStarsGiftRequest o'rniga InputInvoiceStarGift +
            #    GetPaymentFormRequest + SendStarsFormRequest ishlatiladi.
            invoice = _t.InputInvoiceStarGift(peer=peer, gift_id=gift_id)
            form = await client(_f.payments.GetPaymentFormRequest(invoice=invoice))
            form_id = getattr(form, "form_id", None)
            if not form_id:
                return False, "no_payment_form_id"
            try:
                await client(_f.payments.SendStarsFormRequest(
                    form_id=form_id, invoice=invoice
                ))
            except (TypeError, ValueError) as exc:  # noqa: BLE001
                return False, f"send_stars_gift_api_not_supported: {type(exc).__name__}: {exc}"
            return True, "ok"
        except ForbiddenError:
            return False, "gift_restricted_by_telegram"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    async def _find_gift_id(self, client, amount: int) -> int | None:
        from telethon.tl import functions as _f

        try:
            res = await client(_f.payments.GetStarGiftsRequest(hash=0))
            for g in getattr(res, "gifts", []) or []:
                if getattr(g, "stars", None) == amount:
                    return g.id
        except Exception:  # noqa: BLE001
            pass
        # Zaxira: ma'lum qiymatlar jadvali
        return FALLBACK_GIFT_IDS.get(amount)

    async def send_post_stars(
        self, session_string: str, amount: int, post_link: str
    ) -> tuple[bool, str]:
        """
        Postga stars (paid reaction) yuborish - ulangan akkaunt hisobidan.
        Qaytaradi: (ok, message):
          - muvaffaqiyat:  (True, "ok")
          - qisman:        (False, "partial:<yuborilgan>|<sabab>")
          - xato:          (False, "<sabab>")
        Tuzatishlar: post oldindan tekshiriladi, akkaunt Stars balansi
        tekshiriladi, FloodWait kutiladi, ulanish qayta uriniladi,
        Telegram xatolari tushunarli sababga aylantiriladi.
        """
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl import functions as _f
        from telethon.tl import types as _t

        session = (session_string or "").strip()
        if not session:
            return False, "empty_session"
        if len(session) < 40 or " " in session:
            return False, "invalid_session_string"
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return False, "bad_amount"
        if amount <= 0:
            return False, "bad_amount"

        m = _POST_LINK_RE.search(post_link or "")
        if not m:
            return False, "bad_post_link"
        # Oxirgi raqam = xabar ID (forum: t.me/c/<id>/<topic>/<msg>)
        tail = re.search(r"(\d+)(?:/?[?#].*)?\s*$", post_link.strip())
        msg_id = int(tail.group(1)) if tail else int(m.group("mid"))
        cid = m.group("cid")
        username = m.group("user")

        try:
            parsed_session = StringSession(session)
        except ValueError:
            return False, "invalid_session_string"

        client = TelegramClient(
            parsed_session, _API_ID, _API_HASH,
            device_model="StarsBot", system_version="Linux",
            app_version="stars-bot 1.0", lang_code="en",
            connection_retries=3, retry_delay=1, auto_reconnect=True,
        )
        sent = 0

        def _fail(exc_or_text) -> tuple[bool, str]:
            err = exc_or_text if isinstance(exc_or_text, str) else explain_error(exc_or_text)
            return False, (f"partial:{sent}|{err}" if sent else err)

        try:
            # Ulanish: 2 marta urinamiz
            last_exc: Exception | None = None
            for _ in range(2):
                try:
                    await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
                    last_exc = None
                    break
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    await asyncio.sleep(1.0)
            if last_exc is not None:
                return _fail("connect_failed: " + explain_error(last_exc))
            if not await client.is_user_authorized():
                return False, "session_not_authorized"

            # 1) Kanal / chatni aniqlash
            peer = None
            target = (-1000000000000 - int(cid)) if cid else username
            for attempt in range(3):
                try:
                    peer = await client.get_input_entity(target)
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 0:
                        try:
                            await client.get_dialogs(limit=200)
                        except Exception:  # noqa: BLE001
                            pass
                    elif attempt == 1 and username:
                        try:
                            ent = await client.get_entity(username)
                            peer = await client.get_input_entity(ent)
                            break
                        except Exception as exc2:  # noqa: BLE001
                            exc = exc2
                    if attempt == 2:
                        return _fail("post_channel_not_found: " + explain_error(exc))
            if peer is None:
                return False, "post_channel_not_found"

            # 2) Post mavjudligini tekshirish (MESSAGE_ID_INVALID ni oldindan ushlaydi)
            try:
                msg = await client.get_messages(peer, ids=msg_id)
                if msg is None or getattr(msg, "empty", False):
                    return False, "post_not_found"
            except Exception:  # noqa: BLE001  tekshiruv majburiy emas
                pass

            # 3) Akkaunt Stars balansi yetarlimi?
            try:
                st = await client(_f.payments.GetStarsStatusRequest(peer=_t.InputPeerSelf()))
                bal = getattr(st, "balance", None)
                have = getattr(bal, "amount", bal)
                if isinstance(have, (int, float)) and have < amount:
                    return False, f"account_balance_low: {int(have)}/{amount}"
            except Exception:  # noqa: BLE001
                pass

            # 4) Yuborish (bo'laklab)
            remaining = amount
            while remaining > 0:
                chunk = min(remaining, _MAX_PAID_REACTION)
                done = False
                for attempt in range(3):
                    kwargs = dict(peer=peer, msg_id=msg_id, count=chunk,
                                  random_id=random.getrandbits(62))
                    try:
                        try:
                            await client(_f.messages.SendPaidReactionRequest(
                                private=_t.PaidReactionPrivacyDefault(), **kwargs))
                        except (TypeError, AttributeError):
                            await client(_f.messages.SendPaidReactionRequest(**kwargs))
                        done = True
                        break
                    except Exception as exc:  # noqa: BLE001
                        secs = getattr(exc, "seconds", None)
                        if type(exc).__name__.startswith("FloodWait") and secs and secs <= 30 \
                                and attempt < 2:
                            await asyncio.sleep(secs + 1)
                            continue
                        return _fail(exc)
                if not done:
                    return _fail("unknown_error")
                sent += chunk
                remaining -= chunk
                if remaining > 0:
                    await asyncio.sleep(1.0)
            return True, "ok"
        except Exception as exc:  # noqa: BLE001
            return _fail(exc)
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    async def resolve_user(self, session_string: str, username: str) -> tuple[str, str, int]:
        """@username haqiqiy Telegram foydalanuvchisimi? -> (holat, ism, id).
        holat: found | not_found | unknown (tekshirib bo'lmadi)."""
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from telethon.tl import types as _t

        session = (session_string or "").strip()
        if len(session) < 40 or " " in session:
            return "unknown", "", 0
        client = TelegramClient(StringSession(session), _API_ID, _API_HASH,
                                device_model="StarsBot", system_version="Linux",
                                app_version="stars-bot 1.0", lang_code="en")
        try:
            await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
            if not await client.is_user_authorized():
                return "unknown", "", 0
            try:
                ent = await asyncio.wait_for(
                    client.get_entity(username.lstrip("@")), timeout=_CONNECT_TIMEOUT)
            except Exception as exc:  # noqa: BLE001
                n = type(exc).__name__
                if n in ("UsernameNotOccupiedError", "UsernameInvalidError", "ValueError"):
                    return "not_found", "", 0
                return "unknown", "", 0
            if not isinstance(ent, _t.User) or getattr(ent, "bot", False) or ent.deleted:
                return "not_found", "", 0
            name = " ".join(x for x in (ent.first_name, ent.last_name) if x) or username
            return "found", name, int(ent.id)
        except Exception:  # noqa: BLE001
            return "unknown", "", 0
        finally:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    async def test_session(self, session_string: str) -> tuple[bool, str]:
        """Akkaunt bunga ulanish + get_me orqali tekshirish."""
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        session = (session_string or "").strip()
        if not session:
            return False, "empty_session"
        # StringSession minimal uzunlik (~3 baz64 token). Qisqa/noto'g'ri
        # qiymat Telethon'da ValueError tashlaydi — oldin ushlab olamiz.
        if len(session) < 40 or " " in session:
            return False, "invalid_session_string"
        client = TelegramClient(
            StringSession(session),
            _API_ID,
            _API_HASH,
            device_model="StarsBot",
            system_version="Windows 10",
            app_version="stars-bot 1.0",
            lang_code="en",
        )
        try:
            # Timeout: ulanish bloklanda (firewall/proxy) hech qachon
            # "tekshirilmoqda" holatida qotib qolmaydi.
            await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
            if not await client.is_user_authorized():
                return False, "session_not_authorized"
            me = await asyncio.wait_for(client.get_me(), timeout=_CONNECT_TIMEOUT)
            await client.disconnect()
            return True, f"@{me.username or 'no-username'} (id={me.id})"
        except asyncio.TimeoutError:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            return False, "timeout: telegram serverga ulanib bo'lmadi (20s)"
        except Exception as exc:  # noqa: BLE001
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            return False, f"{type(exc).__name__}: {exc}"