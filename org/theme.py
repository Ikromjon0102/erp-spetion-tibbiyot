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


def _rgb(hex_value):
    return ','.join(str(int(hex_value[i:i + 2], 16)) for i in (1, 3, 5))


def _glass(h, s, l, base, dark_accent):
    """"Liquid glass" dizayn tizimi (templates/ui/_glass.html) ishlatadigan o'zgaruvchilar: fon gradienti, shisha yuzalar, chiziqlar, soyalar.
    Hammasi bitta rangdan (h, s, l) hisoblanadi, shuning uchun tashkilot almashganda butun sahifa shu rangga o'tadi.
    Holat ranglari (--bad, --late, --exc, --ok) tegilmaydi."""
    acc = _rgb(base)
    lt_glow = _rgb(_hex(h, s, max(l, 0.45)))
    lt_bg = _hex(h, min(s, 0.42), 0.93)
    hue2 = h + 0.04
    light = {
        '--rgb': acc, '--glow': lt_glow,
        '--card': 'rgba(255,255,255,.58)', '--card-strong': 'rgba(255,255,255,.88)', '--card-solid': '#FFFFFF',
        '--line': f'rgba({acc},.14)', '--line-strong': f'rgba({acc},.28)',
        '--tint': f'rgba({acc},.10)', '--tint-line': f'rgba({acc},.30)',
        '--accent-2': _hex(hue2, s, l),
        '--accent-grad': f'linear-gradient(180deg,{_hex(h, s, min(l * 1.18, 0.62))} 0%,{base} 100%)',
        '--bar-bg': f'rgba({_rgb(lt_bg)},.62)', '--input-bg': 'rgba(255,255,255,.62)',
        '--shadow': f'var(--spec), 0 10px 34px rgba({acc},.12), 0 2px 6px rgba({acc},.07)',
        '--shadow-lift': f'var(--spec), 0 18px 44px rgba({acc},.20), 0 4px 10px rgba({acc},.09)',
        '--bg-img': (f'radial-gradient(820px 560px at 6% -6%, rgba({lt_glow},.40), transparent 62%),'
                     f'radial-gradient(760px 520px at 100% 2%, rgba({_rgb(_hex(hue2, s, max(l, 0.4)))},.26), transparent 58%),'
                     f'radial-gradient(880px 640px at 72% 112%, rgba({acc},.24), transparent 62%),'
                     f'linear-gradient(180deg,{_hex(h, min(s, 0.45), 0.965)} 0%,{_hex(h, min(s, 0.4), 0.91)} 100%)'),
        '--cross': f'rgba({acc},.07)',
    }
    pale = _hex(h, min(s, 0.6), 0.72)
    dk_glow = _rgb(_hex(h, min(s, 0.8), 0.52))
    dk_bg = _hex(h, min(s, 0.4), 0.06)
    dark = {
        '--rgb': acc, '--glow': dk_glow,
        '--card': f'rgba({_rgb(_hex(h, min(s, 0.3), 0.17))},.50)', '--card-strong': f'rgba({_rgb(_hex(h, min(s, 0.3), 0.13))},.90)',
        '--card-solid': _hex(h, min(s, 0.3), 0.12),
        '--line': f'rgba({_rgb(pale)},.12)', '--line-strong': f'rgba({_rgb(pale)},.26)',
        '--tint': f'rgba({_rgb(pale)},.10)', '--tint-line': f'rgba({_rgb(pale)},.32)',
        '--accent-2': _hex(hue2, min(s, 0.8), 0.55),
        '--accent-grad': f'linear-gradient(180deg,{_hex(h, s * 0.9, max(l, 0.40) + 0.08)} 0%,{_hex(h, s * 0.9, max(l * 0.8, 0.30))} 100%)',
        '--bar-bg': f'rgba({_rgb(dk_bg)},.58)', '--input-bg': 'rgba(255,255,255,.06)',
        '--shadow': 'var(--spec), 0 12px 40px rgba(0,0,0,.42)', '--shadow-lift': 'var(--spec), 0 20px 50px rgba(0,0,0,.55)',
        '--bg-img': (f'radial-gradient(820px 560px at 6% -6%, rgba({dk_glow},.30), transparent 62%),'
                     f'radial-gradient(760px 520px at 100% 2%, rgba({_rgb(_hex(hue2, min(s, 0.8), 0.40))},.26), transparent 58%),'
                     f'radial-gradient(880px 640px at 72% 112%, rgba({acc},.34), transparent 62%),'
                     f'linear-gradient(180deg,{_hex(h, min(s, 0.4), 0.075)} 0%,{_hex(h, min(s, 0.4), 0.035)} 100%)'),
        '--cross': f'rgba({_rgb(pale)},.045)',
    }
    return light, dark


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
    gl, gd = _glass(h, s, l, base.upper(), dark_accent)
    light.update(gl)
    dark.update(gd)
    light.update({'--bg': _hex(h, min(s, 0.42), 0.93), '--ink': _hex(h, 0.35, 0.09), '--dim': _hex(h, 0.12, 0.36), '--faint': _hex(h, 0.10, 0.60)})
    dark.update({'--bg': _hex(h, min(s, 0.4), 0.06), '--ink': _hex(h, 0.35, 0.93), '--dim': _hex(h, 0.15, 0.70), '--faint': _hex(h, 0.12, 0.45)})
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
