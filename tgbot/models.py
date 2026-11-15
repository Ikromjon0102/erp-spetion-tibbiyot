import secrets

from django.conf import settings
from django.db import models


class TelegramLink(models.Model):
    """Telegram chat ↔ foydalanuvchi (ota-ona/ustoz). Bitta hisobga bir nechta chat bog'lanishi mumkin."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='telegram_links')
    chat_id = models.BigIntegerField(unique=True)
    username = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user} ↔ {self.chat_id}'


def _code():
    return secrets.token_urlsafe(9)


class LinkCode(models.Model):
    """Bir martalik bog'lash kodi (t.me/bot?start=KOD): telefon kontaktisiz ham ulash uchun."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='telegram_codes')
    code = models.CharField(max_length=20, unique=True, default=_code)
    created_at = models.DateTimeField(auto_now_add=True)
