# ===================================================================
# telethon_login.py - BOT ICHIDA AKKAUNT ULASH (Telethon login oqimi)
# Admin panel orqali:  telefon raqam -> kod -> (2FA parol) -> session
# Telethon StringSession orqali ishlaydi; kod chang'iga muhtoj emas.
# FSM darajasi har qadamda foydalanuvchi holatini (temp session) saqlab
# oladi — bir nechta admin parallel ulashsa ham xato bo'lmaydi.
# ===================================================================

from __future__ import annotations

import asyncio
import re
import time

# Telegram rasmiy Desktop app identifikatorlari (Telegram Cloud API ma'lum
# ommaviy api_id/api_hash) — login uchun talab qilinmaydi.
_API_ID: int = 2040
_API_HASH: str = "b18441a1ff607e10a989891a5462e627"
_DEVICE: str = "StarsBot"
_SYSTEM: str = "Windows 10"
_APP: str = "stars-bot 1.0"

# Telegram'tga ulanish timeout'i — tarmoq tiqilgan bo'lsa login oqimi
# "Tekshirilmoqda" holatida qotib qolmasligi uchun.
_CONNECT_TIMEOUT: float = 20.0

# Kod so'rovlari orasidagi minimal interval (sekund). Telegram tez-tez
# kod so'rovini qilsa raqamni BLOKLAYDI (FloodWait) — shuning uchun
# bir xil raqamga qayta so'rov 30s dan oldin taqiqlanadi.
_CODE_COOLDOWN: float = 30.0
_last_code_request: dict[str, float] = {}

# Har raqam uchun hali amalda bo'lgan pending login (session, hash, vaqt).
# Kod yuborilgandan so'ng 2 daqiqa ichida flow qayta boshlansa, yangi
# kod yuborilmaydi — o'sha kod ishlatiladi. Bu Telegram'da "har yangi
# so'rov oldingi kodni bekor qiladi" muammosini bartaraf qiladi.
_PENDING_TTL: float = 120.0
_pending_login: dict[str, set | tuple | None] = {}

# Raqam uchun faol FloodWait blokirovkasi: phone -> (until_monotonic, seconds)
_flood_until: dict[str, float] = {}


def get_flood_wait(phone: str) -> int:
    """Bu raqam uchun qancha soniya Telegram bloklagan (0 = blok yo'q)."""
    until = _flood_until.get(phone, 0.0)
    remaining = int(until - time.monotonic())
    return max(remaining, 0)


def _set_flood(phone: str, seconds: int) -> None:
    _flood_until[phone] = time.monotonic() + seconds


def get_pending_login(phone: str) -> tuple[str, str] | None:
    """Raqam uchun amalda bo'lgan (session, phone_code_hash) — yoki None."""
    pending = _pending_login.get(phone)
    if not pending:
        return None
    session, hash_val, at = pending  # type: ignore[misc]
    if time.monotonic() - at > _PENDING_TTL:
        _pending_login.pop(phone, None)
        return None
    return session, hash_val


def set_pending_login(phone: str, session: str, hash_val: str) -> None:
    _pending_login[phone] = (session, hash_val, time.monotonic())


def clear_pending_login(phone: str) -> None:
    _pending_login.pop(phone, None)


def can_request_code(phone: str) -> tuple[bool, float]:
    """Raqamga kod so'rashga hozir ruxsat bormi? (ok, kutilgan_soniya)"""
    if get_pending_login(phone):
        return False, 0.0  # aktiv kod bor — yangi so'rov shart emas
    last = _last_code_request.get(phone, 0.0)
    wait = _CODE_COOLDOWN - (time.monotonic() - last)
    if wait > 0:
        return False, round(wait)
    return True, 0.0


def _mark_code_requested(phone: str) -> None:
    _last_code_request[phone] = time.monotonic()


def re_first(pattern: str, text: str) -> str | None:
    """Birinchi regex mosligini qaytaradi yoki None."""
    m = re.search(pattern, text or "")
    return m.group(1) if m else None


async def _client(session_str: str | None = None):
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    session = StringSession(session_str) if session_str else StringSession()
    return TelegramClient(
        session,
        _API_ID,
        _API_HASH,
        device_model=_DEVICE,
        system_version=_SYSTEM,
        app_version=_APP,
        lang_code="en",
    )


async def request_code(phone: str) -> tuple[bool, str, str, str]:
    """Telefonga tasdiqlash kodini yuboradi.

    (ok, message, temp_session_string, phone_code_hash) qaytaradi.
    temp_session + hash keyingi qadamlar (kod/parol) uchun saqlanadi.
    Kod so'rovlari orasida minimal interval (30s) — Telegram bloklamasligi uchun.
    """
    import logging

    log = logging.getLogger("stars.login")

    # 1) Cooldown: bir xil raqamga tez-tez kod so'rash — TAQIQLANGAN.
    ok_wait, wait_s = can_request_code(phone)
    if not ok_wait:
        return False, f"COOLDOWN:{wait_s}", "", ""

    client = await _client()
    try:
        await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
        result = await client.send_code_request(phone)
        # Telethon 1.45 StringSession'da phone_code_hash ni saqlamayapti,
        # shuning uchun uni alohida qaytaramiz.
        sess = client.session.save()
        hash_val = getattr(result, "phone_code_hash", None)
        await client.disconnect()
        _mark_code_requested(phone)
        if not sess:
            return False, "empty_session", "", ""
        return True, "code_sent", sess, hash_val or ""
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        # FloodWait: Telegram kutishni so'raydi — kutamiz va kodni qayta so'raymiz.
        if "FloodWait" in name or "flood" in str(exc).lower():
            try:
                seconds = int(
                    re_first(r"(\d+)", str(exc)) or (
                        exc.seconds if hasattr(exc, "seconds") else 1
                    )
                )
            except Exception:  # noqa: BLE001
                seconds = 2
            # 25 soniyadan ko'p kutilmasin — XATOLIK deb qaytaramiz.
            if seconds > 25:
                log.warning("FloodWait %ss (%s)", seconds, phone)
                _set_flood(phone, seconds)
                return False, f"FLOOD_WAIT:{seconds}", "", ""
            log.info("FloodWait %ss — kutamiz (%s)", seconds, phone)
            await asyncio.sleep(seconds)
            _mark_code_requested(phone)
            try:
                await client.reconnect()
                result = await client.send_code_request(phone)
                sess = client.session.save()
                hash_val = getattr(result, "phone_code_hash", None)
                await client.disconnect()
                if not sess:
                    return False, "empty_session", "", ""
                return True, "code_sent", sess, hash_val or ""
            except Exception as exc2:  # noqa: BLE001
                log.warning("FloodWait qayta so'rov xato: %s", exc2)
                return False, f"{type(exc2).__name__}: {exc2}", "", ""
        return False, f"{name}: {exc}", "", ""


async def resend_code(
    session_str: str,
    phone: str,
    phone_code_hash: str,
) -> tuple[bool, str]:
    """Eskirgan kod o'rniga yangisini yuboradi.

    auth.resendCode — xuddi shu phone_code_hash bilan ishlaydi, yangi
    hash yaratmaydi va oldingi session bekor bo'lmaydi. Foydalanuvchi
    shunchaki Telegram'dagi yangilangan kodni kiritadi.
    (ok, message)
    """
    import logging

    log = logging.getLogger("stars.login")
    client = await _client(session_str)
    try:
        await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
        from telethon import functions

        await client(functions.auth.ResendCodeRequest(
            phone_number=phone,
            phone_code_hash=phone_code_hash,
        ))
        await client.disconnect()
        _mark_code_requested(phone)
        return True, "resended"
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        log.warning("resend_code xato (%s): %s", phone, exc)
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        return False, f"{name}: {exc}"


async def sign_in(
    session_str: str,
    phone: str,
    code: str,
    phone_code_hash: str | None = None,
) -> tuple[bool, str, str, bool]:
    """Kod bilan tizimga kirish.

    (ok, message, final_session, need_password)
    exist SessionPasswordNeeded -> need_password=True, final_session parol qadami uchun.
    """
    import logging

    log = logging.getLogger("stars.login")
    client = await _client(session_str)
    try:
        await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
        await client.sign_in(
            phone=phone,
            code=code.strip(),
            phone_code_hash=phone_code_hash,
        )
        sess = client.session.save()
        await client.disconnect()
        return True, "authorized", sess, False
    except asyncio.TimeoutError:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        return False, "timeout: telegram serverga ulanib bo'lmadi (20s)", "", False
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        log.warning("sign_in xato (%s): %s", phone, exc)
        # FloodWait: Telegram kutishni so'raydi — 25s dan kam bo'lsa kutamiz
        # va bitta qayta urinish qilamiz.
        if (
            "FloodWait" in name or "flood" in str(exc).lower()
        ) and hasattr(exc, "seconds") and exc.seconds <= 25:
            await asyncio.sleep(exc.seconds)
            try:
                await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
                await client.sign_in(
                    phone=phone,
                    code=code.strip(),
                    phone_code_hash=phone_code_hash,
                )
                sess = client.session.save()
                await client.disconnect()
                return True, "authorized", sess, False
            except Exception as exc2:  # noqa: BLE001
                name = type(exc2).__name__
                log.warning("sign_in qayta urinish xato: %s", exc2)
        sess = ""
        try:
            if hasattr(client, "session"):
                sess = client.session.save()
        except Exception:  # noqa: BLE001
            pass
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        return False, f"{name}: {exc}", sess, name in (
            "SessionPasswordNeededError", "PasswordHashInvalidError",
        ) or "password" in str(exc).lower()


async def confirm_password(session_str: str, password: str) -> tuple[bool, str, str]:
    """2FA parolini tasdiqlaydi va yakuniy session qaytaradi."""
    client = await _client(session_str)
    try:
        await asyncio.wait_for(client.connect(), timeout=_CONNECT_TIMEOUT)
        await client.sign_in(password=password)
        sess = client.session.save()
        await client.disconnect()
        return True, "authorized", sess
    except asyncio.TimeoutError:
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        return False, "timeout: telegram serverga ulanib bo'lmadi (20s)", ""
    except Exception as exc:  # noqa: BLE001
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        return False, f"{type(exc).__name__}: {exc}", ""