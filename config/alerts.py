"""Ishlab chiqarishdagi xatolar (500) haqida Telegramga qisqa xabar.

Sozlama (.env): ALERT_BOT_TOKEN (bo'lmasa BOT_TOKEN), ALERT_CHAT_ID. Bo'sh bo'lsa hech narsa yuborilmaydi — xato faqat jurnalga (journald) yoziladi.
Bir xil xato 10 daqiqada bir martadan ko'p yuborilmaydi. Xabarda shaxsiy ma'lumot yo'q: faqat manzil, xato turi va qisqa matni.
Handler hech qachon o'zi xato chiqarmaydi va so'rovni kutdirmaydi (alohida oqimda yuboradi)."""
import hashlib
import json
import logging
import os
import threading
import urllib.request

SUPPRESS_SECONDS = 600


def _post(token, chat_id, text):
    try:
        req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage',
                                     data=json.dumps({'chat_id': chat_id, 'text': text[:3500]}).encode(),
                                     headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10).close()
    except Exception:
        pass


class TelegramErrorHandler(logging.Handler):
    def emit(self, record):
        try:
            from django.conf import settings
            from django.core.cache import cache
            token = os.environ.get('ALERT_BOT_TOKEN') or getattr(settings, 'BOT_TOKEN', '')
            chat_id = os.environ.get('ALERT_CHAT_ID', '')
            if not (token and chat_id):
                return
            exc = record.exc_info[1] if record.exc_info else None
            kind = type(exc).__name__ if exc else record.levelname
            request = getattr(record, 'request', None)
            where = f'{request.method} {request.path}' if request is not None else record.name
            sig = hashlib.md5(f'{kind}:{where}:{str(exc)[:80]}'.encode()).hexdigest()
            if not cache.add(f'alert:{sig}', 1, SUPPRESS_SECONDS):       # 10 daqiqa ichida takrorlanmasin
                return
            host = getattr(settings, 'SITE_URL', '')
            text = f'🔴 Xato: {host}\n{where}\n{kind}: {str(exc or record.getMessage())[:400]}'
            threading.Thread(target=_post, args=(token, chat_id, text), daemon=True).start()
        except Exception:
            pass
