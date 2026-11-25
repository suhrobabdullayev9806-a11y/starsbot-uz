# ===================================================================
# bank_listener.py - Bank bildirishnomalarini Telegram'dan o'qish
# Karta egasining Telegram akkaunti (BANK_SESSION) bank bildirishnoma
# boti (BANK_SOURCE_CHATS, masalan CardXabarBot) yozuvlarini tinglaydi
# va har bir yangi xabarni BankModule.ingest() ga uzatadi.
#
# MUHIM: BANK_SESSION gift/post-stars akkaunti bilan BIR XIL bo'lmasin
# (bir session ikki joyda ulansa Telegram uni uzib qo'yadi).
# ===================================================================

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("stars.banklisten")


async def run_bank_listener(app) -> None:
    cfg = app.cfg
    if not (cfg.bank_session and cfg.bank_source_chats):
        return
    try:
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession
    except Exception as exc:  # noqa: BLE001
        log.error("Telethon yo'q, bank tinglovchi ishlamaydi: %s", exc)
        return

    from src.telegram_gift import _API_HASH, _API_ID

    backoff = 5
    while True:
        client = None
        try:
            client = TelegramClient(
                StringSession(cfg.bank_session), _API_ID, _API_HASH,
                device_model="StarsBot-bank", system_version="Linux",
                app_version="stars-bot 1.0", lang_code="en",
            )
            await client.connect()
            if not await client.is_user_authorized():
                log.error("BANK_SESSION avtorizatsiyadan o'tmagan — qayta yarating (tools/gen_session.py)")
                return

            @client.on(events.NewMessage(chats=cfg.bank_source_chats, incoming=True))
            async def _on_msg(event):  # noqa: ANN001
                text = event.raw_text or ""
                if not text.strip():
                    return
                try:
                    res = await app.bank.ingest(text, "telegram")
                    log.info("bank xabari: stored=%s amount=%s", res.get("stored"), res.get("amount"))
                    if not res.get("stored"):
                        log.warning("bank xabari tushunilmadi (%s): %s",
                                    res.get("reason"), text[:200].replace("\n", " | "))
                except Exception as exc:  # noqa: BLE001
                    log.warning("bank xabarini saqlashda xato: %s", exc)

            log.info("Bank tinglovchi ishga tushdi: %s", ", ".join(cfg.bank_source_chats))
            backoff = 5
            await client.run_until_disconnected()
            log.warning("Bank tinglovchi uzildi, qayta ulanadi...")
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("Bank tinglovchi xatosi: %s (qayta urinish %ss)", exc, backoff)
        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 120)
