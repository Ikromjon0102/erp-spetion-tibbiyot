from django import template

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
