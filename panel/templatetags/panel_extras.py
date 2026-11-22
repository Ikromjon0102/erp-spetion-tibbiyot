from django import template

register = template.Library()


@register.filter
def get(mapping, key):
    """Lug'atdan kalit bo'yicha olish: {{ d|get:key }}"""
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def pct(part, total):
    try:
        return round(100 * part / total) if total else 0
    except TypeError:
        return 0


@register.filter
def safe_json(value):
    """Shablon ichidagi <script> uchun xavfsiz JSON."""
    import json
    from django.utils.safestring import mark_safe
    return mark_safe(json.dumps(value).replace('<', '\u003c').replace('>', '\u003e').replace('&', '\u0026'))


@register.filter
def mln(value):
    """Katta summani qisqa ko'rsatadi: 1 234 000 000 -> '1.23 mlrd', 45 600 000 -> '45.6 mln'; kichigi — to'liq."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return value
    a = abs(v)
    sign = '−' if v < 0 else ''
    if a >= 1_000_000_000:
        return f"{sign}{a / 1_000_000_000:.2f} mlrd"
    if a >= 1_000_000:
        return f"{sign}{a / 1_000_000:.1f} mln"
    return f"{v:,}".replace(',', ' ')
