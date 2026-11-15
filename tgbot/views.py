import hmac
import json
import logging

from django.contrib.auth import login
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import bot, services
from .models import TelegramLink


@csrf_exempt
@require_POST
def webhook(request):
    if not services.token() or not hmac.compare_digest(
            request.headers.get('X-Telegram-Bot-Api-Secret-Token', ''), services.webhook_secret()):
        return HttpResponse(status=403)
    try:
        bot.handle(json.loads(request.body))
    except Exception:       # Telegram qayta-qayta yubormasligi uchun doim 200
        logging.getLogger(__name__).exception('bot xato')
    return HttpResponse('ok')


def app(request):
    """Mini App kirish sahifasi: Telegram initData ni serverga yuborib, sessiya ochadi."""
    nxt = request.GET.get('next', '/')
    if not nxt.startswith('/') or nxt.startswith('//') or '\\' in nxt:     # faqat sayt ichidagi yo'l
        nxt = '/'
    return render(request, 'tgbot/app.html', {'next': nxt})


@csrf_exempt
@require_POST
def auth(request):
    tg_user = services.validate_init_data(request.POST.get('initData', ''))
    link = tg_user and TelegramLink.objects.filter(chat_id=tg_user.get('id')).select_related('user').first()
    if not link or not link.user.is_active:
        return JsonResponse({'ok': False}, status=403)
    login(request, link.user, backend='accounts.backends.PhoneBackend')
    return JsonResponse({'ok': True})
