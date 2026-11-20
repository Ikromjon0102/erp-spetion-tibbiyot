from django import template
from django.urls import reverse
from django.utils.html import format_html

from academics.constants import DAY_CODES

register = template.Library()


@register.filter
def money(value):
    """1500000 -> '1 500 000'"""
    try:
        return f'{int(value):,}'.replace(',', ' ')
    except (TypeError, ValueError):
        return value


@register.filter
def initials(user):
    """Ism-familiyaning bosh harflari (avatar uchun)."""
    parts = [p for p in [getattr(user, 'last_name', ''), getattr(user, 'first_name', '')] if p]
    if not parts:
        parts = [getattr(user, 'username', '?')]
    letters = ''.join(p.strip()[:1] for p in ' '.join(parts).split()[:2])
    return letters.upper() or '?'


@register.filter
def wd(day):
    """Sana -> hafta kuni qisqartmasi (Du, Se, Ch, Pa, Ju, Sh, Ya)."""
    return (DAY_CODES + ['Ya'])[day.weekday()]


@register.simple_tag
def avatar(user):
    """Ro'yxatlar uchun avatar: rasmi bo'lsa kichik (96px) rasm, bo'lmasa bosh harflar."""
    if getattr(user, 'photo', None):
        # rasm fayli har yuklashda yangi nom oladi, shuning uchun nom URL ga qo'shiladi (kesh yangilanadi)
        src = f"{reverse('face_photo', args=[user.pk])}?s=1&v={user.photo.name.rsplit('/', 1)[-1][:-4]}"
        return format_html('<span class="av has-img"><img src="{}" alt="" loading="lazy" width="32" height="32"></span>', src)
    return format_html('<span class="av">{}</span>', initials(user))
