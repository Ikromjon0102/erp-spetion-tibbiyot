"""Telegram Bot API bilan ishlash (tashqi kutubxonasiz) va xabar yuborish."""
import hashlib
import hmac
import json
import logging
import threading
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)


def token():
    return getattr(settings, 'BOT_TOKEN', '') or ''


def app_url(path=''):
    from urllib.parse import quote
    url = getattr(settings, 'SITE_URL', 'https://my.spetion.uz').rstrip('/') + '/tg/app/'
    return url + ('?next=' + quote(path, safe='/') if path else '')


def webhook_secret():
    """Webhook so'rovi haqiqatan Telegramdan kelganini tekshirish uchun (token va SECRET_KEY dan olinadi)."""
    return hmac.new(settings.SECRET_KEY.encode(), b'tg-webhook:' + token().encode(), hashlib.sha256).hexdigest()[:48]


def api(method, **params):
    if not token():
        return None
    req = urllib.request.Request(
        f'https://api.telegram.org/bot{token()}/{method}', data=json.dumps(params).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception as e:      # tarmoq xatosi asosiy ishni buzmasin
        log.warning('Telegram %s xato: %s', method, str(e).replace(token(), '***'))
        return None


def send(chat_id, text, **extra):
    return api('sendMessage', chat_id=chat_id, text=text, parse_mode='HTML', **extra)


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _send_all(chat_ids, text, path=''):
    kb = {'inline_keyboard': [[{'text': 'Batafsil', 'web_app': {'url': app_url(path)}}]]}
    for cid in chat_ids:
        send(cid, text, reply_markup=kb)


def notify(users, text, path=''):
    """Foydalanuvchilarning bog'langan chatlariga xabar (fonda; token yo'q bo'lsa jim o'tadi)."""
    if not token():
        return
    from .models import TelegramLink
    ids = list(TelegramLink.objects.filter(user__in=list(users)).values_list('chat_id', flat=True))
    if not ids:
        return
    if getattr(settings, 'TELEGRAM_SYNC', False):
        _send_all(ids, text, path)
    else:
        threading.Thread(target=_send_all, args=(ids, text, path), daemon=True).start()


def validate_init_data(init_data, max_age=24 * 3600):
    """Mini App initData ni tekshiradi (Telegram hujjatidagi HMAC usuli). To'g'ri bo'lsa user dict, aks holda None."""
    import time
    from urllib.parse import parse_qsl
    if not token() or not init_data:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    got = pairs.pop('hash', '')
    check = '\n'.join(f'{k}={v}' for k, v in sorted(pairs.items()))
    secret = hmac.new(b'WebAppData', token().encode(), hashlib.sha256).digest()
    if not got or not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), got):
        return None
    try:
        if time.time() - int(pairs.get('auth_date', 0)) > max_age:
            return None
        return json.loads(pairs.get('user', ''))
    except (ValueError, TypeError):
        return None
