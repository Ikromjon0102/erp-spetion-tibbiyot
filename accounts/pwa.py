"""Ilova sifatida o'rnatish (PWA): manifest va service worker. Hech qanday ma'lumot keshlanmaydi."""
import json

from django.http import HttpResponse
from django.templatetags.static import static
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

APP_NAME = 'Spetion'      # hamma tashkilot uchun umumiy (tibbiyot, maktab, bog'cha, markaz)
ICON_V = '?v=4'           # ikonka almashganda oshiring (o'rnatilgan ilova yangisini oladi)


@require_GET
@cache_control(max_age=3600)
def manifest(request):
    from org.context import org_theme
    color = org_theme(request)['org_theme']['accent']          # o'rnatilgan ilova rangi — foydalanuvchining tashkilotidan
    data = {
        'name': APP_NAME, 'short_name': APP_NAME, 'description': "Spetion: ota-ona, ustoz va ma'muriyat ilovasi",
        'lang': 'uz', 'start_url': '/?source=pwa', 'scope': '/', 'id': '/', 'display': 'standalone',
        'orientation': 'portrait', 'background_color': '#0B0C10', 'theme_color': color,
        'icons': [
            {'src': static('brand/icon-192.png') + ICON_V, 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': static('brand/icon-512.png') + ICON_V, 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            {'src': static('brand/icon-maskable-512.png') + ICON_V, 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    }
    return HttpResponse(json.dumps(data, ensure_ascii=False), content_type='application/manifest+json')


# Chrome o'rnatish uchun fetch ishlovchisi bo'lgan service worker talab qiladi. Biz hech narsani keshlamaymiz
# (shaxsiy ma'lumotlar), shuning uchun so'rovlar oddiygina tarmoqqa o'tadi.
SW = """self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
"""


@require_GET
@cache_control(no_cache=True)
def service_worker(request):
    resp = HttpResponse(SW, content_type='application/javascript')
    resp['Service-Worker-Allowed'] = '/'
    return resp
