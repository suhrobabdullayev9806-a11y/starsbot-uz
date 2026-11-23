"""Telethon StringSession yaratish (bank bildirishnomalarini o'qiydigan akkaunt uchun).

Ishlatish (o'z kompyuteringizda):
    pip install telethon
    python tools/gen_session.py
Chiqqan uzun qatorni Render'da BANK_SESSION o'zgaruvchisiga kiriting.
DIQQAT: bu qator akkauntingizga to'liq kirish beradi — hech kimga bermang!
"""
import asyncio

from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID = 2040
API_HASH = "b18441a1ff607e10a989891a5462e627"


async def main() -> None:
    async with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        print("\nBANK_SESSION =\n")
        print(client.session.save())


if __name__ == "__main__":
    asyncio.run(main())
