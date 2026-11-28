"""Yuz rasmini terminalga yetkazish: ISUP orqali rasm faylining o'zi emas, uning manzili (faceURL) yuboriladi,
terminal rasmni o'zi yuklab oladi.

Rasm shlyuz xotirasida tasodifiy (32 belgili) token bilan qisqa muddat (standart 5 daqiqa) turadi va terminal javob bergach
darhol o'chiriladi. Manzil taxmin qilinmaydi, ro'yxati yo'q, muddati o'tgani 404. Shuning uchun bolalarning rasmlari
ochiq papkada turmaydi va mavjud /api/access/agent/photo/ (kalit bilan) ochilmaydi.
"""
import secrets
import threading
import time

MAX_BYTES = 200 * 1024          # ISUP SS va terminal cheklovi; accounts/photos.py rasmlarni allaqachon <= 200 KB qiladi


class FaceStore:
    def __init__(self, ttl=300, max_items=500, clock=time.monotonic):
        self.ttl, self.max_items, self.clock = ttl, max_items, clock
        self._items = {}
        self._lock = threading.Lock()

    def put(self, jpeg):
        if not isinstance(jpeg, (bytes, bytearray)) or not bytes(jpeg[:2]) == b'\xff\xd8':
            raise ValueError('JPEG emas')
        if len(jpeg) > MAX_BYTES:
            raise ValueError(f'Rasm {len(jpeg) // 1024} KB — 200 KB dan katta')
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._purge()
            if len(self._items) >= self.max_items:
                raise ValueError("Rasm navbati to'la")
            self._items[token] = (self.clock() + self.ttl, bytes(jpeg))
        return token

    def get(self, token):
        with self._lock:
            item = self._items.get(token)
            if item is None:
                return None
            if item[0] < self.clock():
                del self._items[token]
                return None
            return item[1]

    def drop(self, token):
        with self._lock:
            self._items.pop(token, None)

    def _purge(self):
        now = self.clock()
        for t in [t for t, (exp, _) in self._items.items() if exp < now]:
            del self._items[t]

    def __len__(self):
        with self._lock:
            self._purge()
            return len(self._items)
