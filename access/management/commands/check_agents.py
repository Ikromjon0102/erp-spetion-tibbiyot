"""Binodagi agent uzoq vaqt aloqaga chiqmasa — ogohlantirish (holat o'zgarganda bir marta), qayta ulansa — xabar.

Cron: har 10 daqiqada. Faqat ish vaqtida (Du–Sh, 09:00–17:00) tekshiradi: kechasi kompyuter o'chirilishi normal.
Xabar: ALERT_CHAT_ID (server ogohlantirishlari) va Telegram'ga ulangan rahbarlar (founder).
"""
import os
from datetime import time, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from access.models import Agent

OFFLINE_MINUTES = 30
WORK_FROM, WORK_TO = time(9, 0), time(17, 0)


def _send(text):
    from config.alerts import _post
    token = os.environ.get('ALERT_BOT_TOKEN') or getattr(settings, 'BOT_TOKEN', '')
    chat = os.environ.get('ALERT_CHAT_ID', '')
    if token and chat:
        _post(token, chat, text)
    from accounts.models import User
    from panel.models import StaffProfile
    from tgbot.services import notify
    owners = [p.user for p in StaffProfile.objects.filter(is_active=True, position__is_owner=True).select_related('user')]
    owners += list(User.objects.filter(is_superuser=True, is_active=True))
    notify(owners, text, '/panel/qurilmalar/')


class Command(BaseCommand):
    help = "Aloqaga chiqmayotgan agentlar haqida ogohlantirish"

    def add_arguments(self, parser):
        parser.add_argument('--any-time', action='store_true', help='ish vaqtidan tashqarida ham tekshirish')

    def handle(self, *args, **opts):
        now = timezone.localtime()
        if not opts['any_time'] and (now.weekday() == 6 or not WORK_FROM <= now.time() <= WORK_TO):
            return
        limit = timezone.now() - timedelta(minutes=OFFLINE_MINUTES)
        for a in Agent.objects.filter(is_active=True).select_related('branch__organization'):
            where = f'{a.branch.organization.label} · {a.branch.name}'
            off = not a.last_seen_at or a.last_seen_at < limit
            if off and not a.offline_alerted:
                _send(f"⚠️ {where}: «{a.name or 'Agent'}» kompyuteri {OFFLINE_MINUTES} daqiqadan beri aloqaga chiqmadi. "
                      "Yangi rasmlar terminallarga yetib bormaydi. Kompyuter yoqilganini va internet borligini tekshiring.")
                Agent.objects.filter(pk=a.pk).update(offline_alerted=True)
                self.stdout.write(f'offline: {where}')
            elif not off and a.offline_alerted:
                _send(f"✅ {where}: «{a.name or 'Agent'}» kompyuteri qayta ulandi.")
                Agent.objects.filter(pk=a.pk).update(offline_alerted=False)
                self.stdout.write(f'online: {where}')
