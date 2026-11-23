# ===================================================================
# singleton.py - Yagona nusxa (single-instance) himoyasi
# LOCALHOST portga bind orqali: ikkinchi instansiya portni ololmay,
# darhol chiqib ketadi. OS socket bind atomik — race holati yo'q.
# Bot to'xtasa port avtomatik bo'shaydi (crash-safe).
# ===================================================================

from __future__ import annotations

import socket


class SingleInstance:
    """Yagona jarayonni port blokirovkasi orqali ta'minlaydi."""

    def __init__(self, port: int = 18087, host: str = "127.0.0.1"):
        # 18087 - bot uchun ayrim singleton porti (0..65535 oralig'i)
        self.port = port
        self.host = host
        self._sock: socket.socket | None = None

    def acquire(self) -> bool:
        """Portni egallaydi. Band bo'lsa False qaytaradi."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # SO_REUSEADDR o'rnatilmasa, port bandlikni aniq ko'rsatadi
            s.bind((self.host, self.port))
            s.listen(1)
            self._sock = s
            return True
        except OSError:
            s.close()
            return False

    def release(self) -> None:
        """Portni bo'shatadi."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None