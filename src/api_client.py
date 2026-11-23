# ===================================================================
# api_client.py - @Apilarimbot (Stars) API KLIENTI
# Bot stars sotib olishni ushbu API orqali avtomatik bajaradi.
#
# REAL URILISHI:
#   1. STARS_API_BASE_URL va STARS_API_KEY o'rnating (.env)
#   2. ApiProvider._call() metodini haqiqiy API hujjatiga moslang
#   3. API sizni webhook orqali chaqiradi (qarang: webhook handler)
# ===================================================================

from __future__ import annotations

import json

import httpx

from src.config import Settings
from src.database import SettingsRepo
from src.security import verify_callback_signature


class StarsApiClient:
    """(@Apilarimbot) Stars API bilan ishlash uchun adapter.

    URL va API key ikki manbadan keladi:
      1) DB (admin panelda o'rnatilgan) — asosiy;
      2) .env dagi STARS_API_BASE_URL / STARS_API_KEY — zaxira.
    - `purchase()` — buyurtmani APIga yuboradi
    - `verify_callback()` — API qayta chaqiruvini tekshiradi
    - `_call()` — asl HTTP so'rov (provider'ga moslanadi)
    """

    def __init__(self, cfg: Settings, settings: SettingsRepo | None = None):
        self.cfg = cfg
        self._settings = settings
        self._timeout = 30

    async def _credentials(self) -> tuple[str, str]:
        """(base_url, api_key) — DB o'rnatmasi, aks holda .env."""
        url, key = "", ""
        if self._settings is not None:
            url, key = await self._settings.get_stars_api()
        if not url:
            url = self.cfg.stars_api_base_url
        if not key:
            key = self.cfg.stars_api_key
        return url.rstrip("/"), key

    async def enabled(self) -> bool:
        """API ishga tushirilganmi (kalit va URL o'rnatilganmi)."""
        url, key = await self._credentials()
        return bool(url and key)

    async def purchase(self, amount: int, user_id: int, order_id: int, username: str = "") -> bool:
        """
        Buyurtmani API orqali yuboradi.
        True — so'rov qabul qilindi, False — xatolik.
        """
        if not await self.enabled():
            # API o'rnatilmagan bo'lsa: buyurtmani admin tasdig'iga o'tkazamiz
            return False

        payload = {
            "action": "purchase",
            "amount": amount,
            "user_id": user_id,
            "order_id": order_id,
            "reference": f"stars-{order_id}",
            "username": username.lstrip("@") if username else "",
        }
        try:
            resp = await self._call("purchase", payload)
            data = resp or {}
            return bool(data.get("ok") or data.get("accepted", False))
        except Exception:  # noqa: BLE001
            return False

    async def check_status(self, order_id: int) -> dict | None:
        """Buyurtma holatini API'dan so'raydi."""
        if not await self.enabled():
            return None
        try:
            return await self._call("status", {"order_id": order_id, "reference": f"stars-{order_id}"})
        except Exception:  # noqa: BLE001
            return None

    def verify_callback(self, payload: str, signature: str, cfg: Settings) -> bool:
        """API webhook so'rovining HMAC imzosini tekshiradi."""
        return verify_callback_signature(cfg.api_callback_secret, payload, signature)

    async def _call(self, endpoint: str, data: dict) -> dict:
        """Asosiy HTTP qo'ng'iroq. Provider spetsifikatsiyasiga moslang."""
        base_url, api_key = await self._credentials()
        if not base_url:
            return {}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        url = f"{base_url}/{endpoint}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=data, headers=headers)
            resp.raise_for_status()
            try:
                return json.loads(resp.text)
            except json.JSONDecodeError:
                return {"raw": resp.text}