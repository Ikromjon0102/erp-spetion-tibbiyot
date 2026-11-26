"""Qidiruv tizimlari uchun: robots.txt, sitemap.xml, bosh sahifa (kirmagan foydalanuvchiga — kirish sahifasi).
Faqat asosiy domen (CANONICAL_HOST, my.spetion.uz) indekslanadi; sinov va eski manzillar (med-new, med) — yo'q.
Ichki sahifalar (panel, ustoz, ota-ona) shaxsiy ma'lumot: robots.txt da yopiq va sahifalarda `noindex`."""
from django.conf import settings
from django.http import HttpResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

PRIVATE = ['/panel/', '/ustoz/', '/oquvchi/', '/api/', '/tg/', '/admin/', '/galereya/', '/elonlar/', '/parol/', '/vazifa/', '/rasm/', '/taom/']


def canonical_host():
    return getattr(settings, 'CANONICAL_HOST', 'my.spetion.uz')


def is_canonical(request):
    return request.get_host().split(':')[0] == canonical_host()


@require_GET
@cache_control(max_age=86400, public=True)
def robots(request):
    if not is_canonical(request):
        return HttpResponse('User-agent: *\nDisallow: /\n', content_type='text/plain')
    lines = ['User-agent: *', 'Allow: /$', 'Allow: /login/'] + [f'Disallow: {p}' for p in PRIVATE]
    lines += ['', f'Sitemap: https://{canonical_host()}/sitemap.xml', f'Host: https://{canonical_host()}']
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain')


@require_GET
@cache_control(max_age=86400, public=True)
def sitemap(request):
    body = ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'  <url><loc>https://{canonical_host()}/</loc><changefreq>weekly</changefreq><priority>1.0</priority></url>\n'
            '</urlset>\n')
    return HttpResponse(body, content_type='application/xml')


def seo_context(request):
    """Shablonlar uchun: kanonik manzil, indekslash mumkinmi, qidiruv tizimlari tasdiqlash kodlari (.env dan)."""
    return {'seo': {
        'canonical': f'https://{canonical_host()}/',
        'indexable': is_canonical(request),
        'google': getattr(settings, 'GOOGLE_SITE_VERIFICATION', ''),
        'bing': getattr(settings, 'BING_SITE_VERIFICATION', ''),
        'yandex': getattr(settings, 'YANDEX_VERIFICATION', ''),
    }}
