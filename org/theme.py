"""Tashkilot brendi: bitta HEX rangdan butun ilova palitrasi (och va qorong'i rejim).

Logo hamma tashkilotda bir xil, faqat fon/urg'u ranglari tashkilotga qarab o'zgaradi. Ilova va panel bir xil CSS o'zgaruvchilarini
(`--accent`, `--bg`, ...) ishlatadi, shuning uchun bu yerda faqat o'zgaruvchilar qiymati beriladi.
"""
import colorsys
import re

DEFAULT_COLOR = '#166534'
HEX_RE = re.compile(r'^#[0-9a-fA-F]{6}$')


def is_valid(value):
    return bool(value) and bool(HEX_RE.match(value))


def _parse(value):
    value = value if is_valid(value) else DEFAULT_COLOR
    r, g, b = (int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h, s, l


def _hex(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, min(max(l, 0), 1), min(max(s, 0), 1))
    return '#{:02X}{:02X}{:02X}'.format(round(r * 255), round(g * 255), round(b * 255))


def _luminance(value):
    r, g, b = (int(value[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def palette(color):
    """{'light': {...}, 'dark': {...}} — CSS o'zgaruvchilari qiymatlari. Noto'g'ri rang bo'lsa standart (yashil) olinadi."""
    h, s, l = _parse(color)
    base = color if is_valid(color) else DEFAULT_COLOR
    soft = min(s, 0.42)       # fon/chiziqlar tashkilot rangida sezilarli tusli (kun/tun rejimi kabi butun sahifa rangi o'zgaradi)
    light = {
        '--accent': base.upper(),
        '--accent-deep': _hex(h, s, l * 0.78),
        '--on-accent': '#FFFFFF' if _luminance(base) < 0.5 else '#111111',
        '--tint': _hex(h, min(s, 0.55), 0.92),
        '--tint-line': _hex(h, min(s, 0.45), 0.74),
        '--bg': _hex(h, soft, 0.93),
        '--card': '#FFFFFF',
        '--line': _hex(h, soft, 0.86),
        '--line-strong': _hex(h, soft, 0.74),
        '--ink': _hex(h, 0.25, 0.10),
        '--dim': _hex(h, 0.10, 0.40),
        '--faint': _hex(h, 0.08, 0.68),
    }
    dark_accent = _hex(h, s * 0.9, max(l, 0.40))
    dark = {
        '--accent': dark_accent,
        '--accent-deep': _hex(h, min(s, 0.7), 0.72),
        '--on-accent': '#FFFFFF' if _luminance(dark_accent) < 0.5 else '#111111',
        '--tint': _hex(h, min(s, 0.5), 0.14),
        '--tint-line': _hex(h, min(s, 0.45), 0.27),
        '--bg': _hex(h, soft, 0.075),
        '--card': _hex(h, soft, 0.11),
        '--line': _hex(h, soft, 0.17),
        '--line-strong': _hex(h, soft, 0.27),
        '--ink': _hex(h, 0.20, 0.92),
        '--dim': _hex(h, 0.12, 0.68),
        '--faint': _hex(h, 0.10, 0.42),
    }
    return {'light': light, 'dark': dark}


def _decl(values):
    return ''.join(f'{k}:{v};' for k, v in values.items())


def css(color):
    """<style> ichiga qo'yiladigan matn. Faqat tekshirilgan HEX dan quriladi, shuning uchun xavfsiz."""
    p = palette(color)
    light, dark = _decl(p['light']), _decl(p['dark'])
    return (f':root{{{light}}}'
            f'@media (prefers-color-scheme: dark){{:root:not([data-theme="light"]){{{dark}}}}}'
            f':root[data-theme="dark"]{{{dark}}}'
            f':root[data-theme="light"]{{{light}}}'
            'html,body{transition:background-color .35s ease,color .35s ease}')
