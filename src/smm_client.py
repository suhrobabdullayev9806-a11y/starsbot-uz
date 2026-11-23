# ===================================================================
# smm_client.py - SMM PANEL PROVAYDER KLIENTI (standart "API v2")
# Aksariyat SMM panellar (JAP, Peakerr, SMMKings va h.k.) bir xil protokolda ishlaydi:
#   POST <api_url>  form: key=<KALIT>&action=services|add|status|orders|balance
# URL va kalit admin paneldan (DB) o'rnatiladi.
# ===================================================================

from __future__ import annotations

import httpx

from src.database import SettingsRepo


class SmmError(Exception):
    """Provayder xatosi (matn foydalanuvchiga emas, faqat adminga ko'rsatiladi)."""


class SmmProvider:
    def __init__(self, settings: SettingsRepo, timeout: float = 25.0):
        self._settings = settings
        self._timeout = timeout

    async def configured(self) -> bool:
        s = await self._settings.get_smm()
        return bool(s["url"] and s["key"])

    async def _call(self, action: str, **params):
        s = await self._settings.get_smm()
        if not (s["url"] and s["key"]):
            raise SmmError("provider_not_configured")
        if not s["url"].lower().startswith(("http://", "https://")):
            raise SmmError("bad_provider_url")
        data = {"key": s["key"], "action": action, **{k: str(v) for k, v in params.items()}}
        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=False) as c:
                resp = await c.post(s["url"], data=data)
        except httpx.HTTPError as exc:
            raise SmmError(f"network: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise SmmError(f"http_{resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            raise SmmError("bad_response") from exc
        if isinstance(body, dict) and body.get("error"):
            raise SmmError(str(body["error"])[:200])
        return body

    async def balance(self) -> dict:
        """{'balance': '12.34', 'currency': 'USD'}"""
        body = await self._call("balance")
        if not isinstance(body, dict) or "balance" not in body:
            raise SmmError("bad_response")
        return {"balance": body.get("balance"), "currency": body.get("currency", "")}

    async def services(self) -> list[dict]:
        body = await self._call("services")
        if not isinstance(body, list):
            raise SmmError("bad_response")
        return [x for x in body if isinstance(x, dict)]

    async def add(self, service: str, link: str, quantity: int) -> str:
        """Buyurtma yuboradi, provayderdagi buyurtma ID sini qaytaradi."""
        body = await self._call("add", service=service, link=link, quantity=quantity)
        oid = body.get("order") if isinstance(body, dict) else None
        if not oid:
            raise SmmError("bad_response")
        return str(oid)

    async def status(self, order_id: str) -> dict:
        body = await self._call("status", order=order_id)
        if not isinstance(body, dict):
            raise SmmError("bad_response")
        return body

    async def statuses(self, order_ids: list[str]) -> dict[str, dict]:
        """Ko'p buyurtma holati (provayderning 'orders' amali; 100 tagacha)."""
        if not order_ids:
            return {}
        body = await self._call("status", orders=",".join(order_ids[:100]))
        out: dict[str, dict] = {}
        if isinstance(body, dict):
            for k, v in body.items():
                if isinstance(v, dict) and not v.get("error"):
                    out[str(k)] = v
        return out
