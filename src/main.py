# ===================================================================
# main.py - Botni ishga tushiruvchi asosiy fayl
#  - config yuklash
#  - App konteynerni qurish (DB + modullar)
#  - WebApp (FastAPI) serverni ishga tushirish va port ochilishini kutish
#  - Dispatcher sozlash va polling
# Usage:  python -m src.main  (Render / Docker / lokal)
# ===================================================================

from __future__ import annotations

import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramRetryAfter

# Agar Windows bo'lsa va Python eski versiya — loop uchun proaktiv sozlash
if sys.platform.startswith("win") and sys.version_info < (3, 14):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from src.app import App  # noqa: E402
from src.config import load_settings  # noqa: E402
from src.handlers import register_handlers  # noqa: E402
from src.session_middleware import ParseFallbackMiddleware  # noqa: E402
from src.subscription import SubscriptionMiddleware  # noqa: E402
from src.singleton import SingleInstance  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,  # Render loglari stdout dan o'qiladi
)
logger = logging.getLogger("stars.bot")


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Faylga log yozish ixtiyoriy (LOG_TO_FILE=1). Render'da stdout yetarli:
# disk to'lib ketmasligi uchun faylga yozish default o'chiq.
if _env_flag("LOG_TO_FILE", False):
    try:
        _data_dir = Path(os.getenv("LOG_DIR") or (Path(__file__).resolve().parent.parent / "data"))
        _data_dir.mkdir(parents=True, exist_ok=True)
        _fh = RotatingFileHandler(
            _data_dir / "bot.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        _fh.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logging.getLogger().addHandler(_fh)
    except Exception:  # noqa: BLE001
        logger.warning("Log faylini ochib bo'lmadi, faqat stdout ishlatiladi.")


def _make_quiet_server_cls():
    """uvicorn signal handler o'rnatmasin: SIGTERM/SIGINT ni aiogram boshqaradi.

    uvicorn versiyasiga qarab ikki xil mexanizm bor: eski versiyada
    install_signal_handlers(), yangisida capture_signals(). Ikkalasi ham o'chiriladi.
    """
    import contextlib

    import uvicorn

    class _QuietServer(uvicorn.Server):
        def install_signal_handlers(self) -> None:  # eski uvicorn
            return None

        @contextlib.contextmanager
        def capture_signals(self):  # yangi uvicorn
            yield

    return _QuietServer


class WebServer:
    """uvicorn serverni fon vazifasida ishga tushiradi va to'xtatadi."""

    def __init__(self, app: App):
        self.app = app
        self._server = None
        self._task: asyncio.Task | None = None

    async def start(self, timeout: float = 30.0) -> None:
        """Serverni ishga tushiradi va port ochilguncha kutadi.

        Xato bo'lsa istisno ko'taradi (Render deploy'ni aniq xato bilan
        to'xtatadi, "port topilmadi" deb osilib qolmaydi).
        """
        import uvicorn

        from src.keyboards import set_webapp_url
        from src.webapp.server import make_server

        cfg = self.app.cfg
        set_webapp_url(cfg.webapp_base_url)

        config = uvicorn.Config(
            make_server(self.app),
            host=cfg.webapp_host,
            port=cfg.webapp_port,
            log_level="warning",
            log_config=None,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
        self._server = _make_quiet_server_cls()(config)
        self._task = asyncio.create_task(self._server.serve(), name="webapp")

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not self._server.started:
            if self._task.done():
                exc = self._task.exception()
                raise RuntimeError(f"WebApp ishga tushmadi: {exc!r}") from exc
            if loop.time() > deadline:
                raise RuntimeError("WebApp belgilangan vaqtda ishga tushmadi")
            await asyncio.sleep(0.1)

        logger.info("WebApp: http://%s:%s", cfg.webapp_host, cfg.webapp_port)
        if cfg.webapp_base_url:
            logger.info("Mini-App URL: %s/app (Stars olish tugmasi)", cfg.webapp_base_url)
        else:
            logger.warning(
                "WEBAPP_BASE_URL bo'sh: 'Stars olish' tugmasi mini-app o'rniga "
                "oddiy inline paketlarni ko'rsatadi."
            )

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except Exception:  # noqa: BLE001
                self._task.cancel()


async def keep_alive(url: str, interval: int = 600) -> None:
    """Render (free) servisi 15 daqiqa so'rovsiz qolsa uxlab qoladi.

    O'z ommaviy URL'imizga vaqti-vaqti bilan so'rov yuborib uni uyg'oq
    tutamiz. Pullik (Starter+) tarifda kerak emas: KEEP_ALIVE=0.
    """
    import httpx

    target = f"{url.rstrip('/')}/healthz"
    async with httpx.AsyncClient(timeout=15) as client:
        while True:
            await asyncio.sleep(interval)
            try:
                await client.get(target)
            except Exception as exc:  # noqa: BLE001
                logger.debug("keep-alive xatosi: %s", exc)


async def bank_verify_loop(app: App, interval: int = 15) -> None:
    """Kutilayotgan avto-to'lovlarni qayta tekshiradi va muddati o'tganini bekor qiladi."""
    while True:
        await asyncio.sleep(interval)
        try:
            await app.bank.process_pending()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("bank tekshiruv xatosi: %s", exc)


async def smm_auto_import(app: App) -> None:
    """SMM API ulangan bo'lsa, barcha xizmatlarni fonda import qiladi."""
    try:
        s = await app.settings.get_smm()
        if not (s["enabled"] and s["url"] and s["key"]):
            return
        res = await app.smm.import_services()
        logger.info("SMM avto-import: qo'shildi=%s, yangilandi=%s, o'tkazildi=%s",
                    res.get("added"), res.get("updated"), res.get("skipped"))
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("SMM avto-import xatosi: %s", exc)


async def smm_sync_loop(app: App, interval: int = 60) -> None:
    """SMM buyurtmalar holatini provayderdan olib turadi (tugaganlarni yakunlaydi/qaytaradi)."""
    while True:
        await asyncio.sleep(interval)
        try:
            await app.smm.sync_orders()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("smm sinxronlash xatosi: %s", exc)


async def main() -> None:
    cfg = load_settings()

    # Yagona nusxa himoyasi (bitta konteyner/jarayon ichida).
    guard = SingleInstance()
    if _env_flag("SINGLE_INSTANCE", True) and not guard.acquire():
        logger.warning("Bot allaqachon ishlayapti — ikkinchi nusxa chiqib ketdi.")
        return

    app = App(cfg)
    web = WebServer(app)
    bot: Bot | None = None
    ka_task: asyncio.Task | None = None
    bg_tasks: list[asyncio.Task] = []
    try:
        await app.connect()
        logger.info("Ma'lumotlar bazasi ulandi: %s", cfg.db_path)

        # Avval port ochiladi — Render health-check darhol o'tadi
        await web.start()

        bot = Bot(
            cfg.bot_token,
            session=AiohttpSession(timeout=70),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        bot.session.middleware(ParseFallbackMiddleware())
        dp = Dispatcher()
        dp["app"] = app
        app.bot = bot

        # MAJBURIY OBUNA: har bir xabar va tugma bosishda tekshiriladi
        sub_mw = SubscriptionMiddleware(app.sub_guard)
        dp.message.outer_middleware(sub_mw)
        dp.callback_query.outer_middleware(sub_mw)

        register_handlers(dp)

        # Kanalni .env dan boshlang'ich qiymat sifatida yozib qo'yamiz (panel o'zgartira oladi)
        if cfg.required_channel or cfg.required_channel_id:
            cur_ch, cur_id = await app.settings.get_channel()
            if not cur_ch and not cur_id:
                await app.settings.set_channel(
                    cfg.required_channel, str(cfg.required_channel_id or ""))
                logger.info("Majburiy obuna kanali .env dan o'rnatildi: @%s", cfg.required_channel)
        if cfg.payment_card_holder and not await app.settings.payment_card_holder():
            await app.settings.set_payment_card_holder(cfg.payment_card_holder)
        if cfg.payment_card and not await app.settings.payment_card():
            await app.settings.set_payment_card(cfg.payment_card)

        # Render bepul rejada baza restartda tozalanadi: muhim API sozlamalarini
        # env dan tiklaymiz, aks holda SMM/UC provayderi har deployda yo'qoladi.
        if cfg.smm_api_url or cfg.smm_api_key:
            cur = await app.settings.get_smm()
            seed = {}
            if cfg.smm_api_url and not cur["url"]:
                seed["url"] = cfg.smm_api_url
            if cfg.smm_api_key and not cur["key"]:
                seed["key"] = cfg.smm_api_key
            if seed:
                if not cur["url"] and cfg.smm_rate:
                    seed["rate"] = cfg.smm_rate
                if not cur["url"] and cfg.smm_markup:
                    seed["markup"] = cfg.smm_markup
                await app.settings.set_smm(**seed)
                logger.info("SMM API sozlamalari env dan o'rnatildi: %s", cfg.smm_api_url)
        if cfg.uc_lookup_url:
            cur = await app.settings.get_uc()
            if not cur["lookup_url"]:
                await app.settings.set_uc(
                    lookup_url=cfg.uc_lookup_url, lookup_key=cfg.uc_lookup_key)
                logger.info("UC nickname provayderi env dan o'rnatildi")

        # AVTO-TO'LOV: natijalarni foydalanuvchiga yuborish + fon tekshiruvi + bank tinglovchi
        from src.bank_listener import run_bank_listener
        from src.handlers.wallet import notify_topup_result

        async def _topup_result(order: dict, outcome: str, reason: str) -> None:
            await notify_topup_result(bot, app, order, outcome, reason)

        app.bank.on_result = _topup_result
        if app.bank.enabled:
            bg_tasks.append(asyncio.create_task(bank_verify_loop(app), name="bank-verify"))
            bg_tasks.append(asyncio.create_task(run_bank_listener(app), name="bank-listen"))
            logger.info("Avto-to'lov YOQILGAN (webhook=%s, telegram=%s)",
                        bool(cfg.bank_webhook_secret),
                        bool(cfg.bank_session and cfg.bank_source_chats))
        else:
            logger.warning("Avto-to'lov manbasi sozlanmagan: to'lovlar adminga qo'lda tasdiqlashga boradi "
                           "(BANK_WEBHOOK_SECRET yoki BANK_SESSION+BANK_SOURCE_CHATS ni kiriting).")

        # SMM NAKRUTKA: natija xabarlari + holatni fon sinxronlash
        from src.handlers.smm import notify_smm_result

        async def _smm_result(order: dict, outcome: str) -> None:
            await notify_smm_result(bot, app, order, outcome)

        app.smm.on_result = _smm_result
        bg_tasks.append(asyncio.create_task(smm_sync_loop(app), name="smm-sync"))
        bg_tasks.append(asyncio.create_task(smm_auto_import(app), name="smm-import"))

        # Token tekshiruvi: noto'g'ri bo'lsa aniq xabar bilan to'xtaydi.
        # Telegram flood control (429) bo'lsa, servisni yiqitmaymiz: kutamiz
        # va oxirida getMe'ni o'tkazib yuborib pollingni davom ettiramiz.
        me = None
        for attempt in range(1, 6):
            try:
                me = await bot.get_me()
                break
            except TelegramRetryAfter as exc:
                wait = max(int(exc.retry_after), 5)
                logger.warning(
                    "Telegram flood control (getMe): %s soniya kutilmoqda (urinish %s/5)...",
                    wait, attempt,
                )
                await asyncio.sleep(wait)
        if me is not None:
            logger.info("Bot: @%s (id=%s)", me.username, me.id)
        else:
            logger.warning("getMe tekshiruvi o'tkazib yuborildi (flood control); polling davom etadi.")

        # Polling bilan webhook bir vaqtda ishlamaydi
        await bot.delete_webhook(drop_pending_updates=False)

        render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
        if render_url and _env_flag("KEEP_ALIVE", True):
            ka_task = asyncio.create_task(keep_alive(render_url), name="keep-alive")

        logger.info("Bot ishga tushmoqda...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            polling_timeout=25,
        )
    finally:
        for task in bg_tasks:
            task.cancel()
        if ka_task is not None:
            ka_task.cancel()
        await web.stop()
        guard.release()
        if bot is not None:
            await bot.session.close()
        await app.close()
        logger.info("Bot to'xtatildi.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
