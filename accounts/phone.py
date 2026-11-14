import re

PHONE_LIKE = re.compile(r'\+?[\d\s\-()]{9,}')


def to_digits(value):
    """Telefon raqamni faqat raqamlarga keltiradi: '+998 95 010-76-39' / '95-010-76-39' / '950107639' -> '998950107639'.
    Telefonga o'xshamasa bo'sh satr qaytaradi."""
    text = (value or '').strip()
    if not PHONE_LIKE.fullmatch(text):
        return ''
    digits = re.sub(r'\D', '', text)
    return '998' + digits if len(digits) == 9 else digits


def normalize_login(value):
    """Telefon raqam ko'rinishidagi loginni raqamlarga keltiradi; boshqa loginlar (admin, 'diyora') o'zgarmaydi."""
    return to_digits(value) or (value or '').strip()
