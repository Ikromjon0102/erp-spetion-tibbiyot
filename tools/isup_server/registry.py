"""ISUP qurilmalar ro'yxati: terminal ro'yxatdan o'tayotganda device ID bo'yicha uning ISUP kaliti topiladi.

Ro'yxatda yo'q device ID — rad etiladi (begona terminal serverimizga ulana olmaydi). Har terminalning kaliti alohida:
bitta kalit chiqib ketsa, faqat o'sha terminal kaliti almashtiriladi.
"""
import json
import re
import secrets
import string
from dataclasses import dataclass
from pathlib import Path

DEVICE_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,32}$')
KEY_RE = re.compile(r'^[A-Za-z0-9]{8,16}$')
KEY_ALPHABET = string.ascii_letters + string.digits


def generate_key(length=12):
    """Terminal web-sahifasiga qo'lda kiritiladigan ISUP kaliti: harf va raqam (ikkalasi ham bo'lsin), 8–16 belgi."""
    if not 8 <= length <= 16:
        raise ValueError('ISUP kaliti 8–16 belgi')
    while True:
        key = ''.join(secrets.choice(KEY_ALPHABET) for _ in range(length))
        if valid_key(key):
            return key


def valid_key(key):
    return bool(KEY_RE.match(key or '')) and any(c.isdigit() for c in key) and any(c.isalpha() for c in key)


def valid_device_id(device_id):
    return bool(DEVICE_ID_RE.match(device_id or ''))


@dataclass(frozen=True)
class Entry:
    device_id: str      # terminalda «Device ID» maydoni (masalan spt-d12)
    isup_key: str       # terminalda «Encryption key / ISUP key»
    token: str          # paneldagi Device.token: hodisalar /api/access/hikvision/<token>/ ga yuboriladi
    name: str = ''


class Registry:
    def __init__(self, entries=()):
        self._by_id = {}
        for e in entries:
            self.add(e)

    def add(self, entry):
        if not valid_device_id(entry.device_id):
            raise ValueError(f"Device ID noto'g'ri: {entry.device_id!r} (lotin harf, raqam, - _; 32 belgigacha)")
        if not valid_key(entry.isup_key):
            raise ValueError(f'{entry.device_id}: ISUP kaliti 8–16 belgi, harf va raqam aralash bo\'lsin')
        if not entry.token:
            raise ValueError(f'{entry.device_id}: panel qurilma tokeni yo\'q')
        if entry.device_id in self._by_id:
            raise ValueError(f'{entry.device_id}: takrorlangan')
        self._by_id[entry.device_id] = entry

    @classmethod
    def from_dicts(cls, rows):
        return cls(Entry(device_id=str(r['device_id']), isup_key=str(r['isup_key']), token=str(r['token']),
                         name=str(r.get('name', ''))) for r in rows)

    @classmethod
    def from_json(cls, path):
        """[{"device_id": ..., "isup_key": ..., "token": ..., "name": ...}, ...] (keyinchalik Django ichki API'sidan olinadi)."""
        return cls.from_dicts(json.loads(Path(path).read_text(encoding='utf-8')))

    def get(self, device_id):
        return self._by_id.get(device_id)

    def key_for(self, device_id):
        """SDK autentifikatsiya so'raganda (ENUM_DEV_AUTH) qaytariladigan kalit; ro'yxatda bo'lmasa None — rad etiladi."""
        e = self._by_id.get(device_id)
        return e.isup_key if e else None

    def __contains__(self, device_id):
        return device_id in self._by_id

    def __iter__(self):
        return iter(self._by_id.values())

    def __len__(self):
        return len(self._by_id)
