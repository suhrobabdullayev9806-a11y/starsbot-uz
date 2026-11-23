# ===================================================================
# app.py - Applikatsiya konteyneri
# Barcha modullar va sozlamalarni bitta obyektga to'playdi.
# aiogram dispatcher'ga 'app' sifatida ulanadi (dp["app"]).
# ===================================================================

from __future__ import annotations

from src.api_client import StarsApiClient
from src.config import Settings
from src.database import Database, SettingsRepo
from src.modules.accounts import AccountsModule
from src.modules.admin import AdminModule
from src.modules.bank import BankModule
from src.modules.gifts import GiftsModule
from src.modules.nft import NftModule
from src.modules.orders import OrdersModule
from src.modules.payments import PaymentsModule
from src.modules.smm import SmmModule
from src.modules.uc import UcModule
from src.modules.users import UsersModule
from src.smm_client import SmmProvider
from src.subscription import SubscriptionGuard


class App:
    """Barcha qatlamlarni yig'adigan konteyner (DI)."""

    def __init__(self, cfg: Settings, db_path: str | None = None):
        self.cfg = cfg
        self.db = Database(db_path or cfg.db_path)
        self.bot = None  # main.py'da ulanishdan keyin Bot obyekti o'rnatiladi

        # Repository / modullar
        self.settings = SettingsRepo(self.db)
        self.users = UsersModule(self.db)
        self.orders = OrdersModule(self.db)
        self.accounts = AccountsModule(self.db, self.cfg.bot_token)
        self.api = StarsApiClient(cfg, self.settings)

        # Yuqori darajadagi modullar
        self.payments = PaymentsModule(self.orders, self.users, self.api)
        self.gifts = GiftsModule(self.db, self.orders, self.users, self.accounts)
        self.nft = NftModule(self.db, self.orders, self.users)
        self.uc = UcModule(self.db, self.orders, self.users, self.settings)
        self.admin = AdminModule(self.orders, self.users, self.accounts, self.settings)
        self.bank = BankModule(self.db, self.orders, self.users, self.cfg)
        self.sub_guard = SubscriptionGuard()

        # SMM Nakrutka (provayder admin paneldan sozlanadi)
        self.smm_provider = SmmProvider(self.settings)
        self.smm = SmmModule(self.db, self.users, self.settings, self.smm_provider)

    async def connect(self) -> None:
        """Bazaga ulanadi."""
        await self.db.connect()
        await self.uc.ensure_defaults()

    async def is_admin(self, user_id: int) -> bool:
        """Foydalanuvchi admin ekanligini tekshiradi.
        .env'dagi ADMIN_IDS + super admin + panel orqali qo'shilgan adminlar."""
        if self.cfg.is_admin(user_id):
            return True
        extra = await self.settings.get_extra_admins()
        return user_id in extra

    async def close(self) -> None:
        """Bazani yopadi."""
        await self.db.close()