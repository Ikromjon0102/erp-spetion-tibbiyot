"""Ilova ikonkasi: «Dark liquid glass» — qorong'i shisha fonda 4 rangli Spetion belgisi (2026-11-28).

Fon chetigacha to'liq kvadrat (iOS/Android o'zi burchaklaydi yoki doira qiladi), ramka va tashqi soya yo'q.
Ishga tushirish: python tools/brand/make_app_icon.py  ->  static/brand/icon-*.png, apple-touch-icon.png
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / 'static/brand/logo/spetion-belgi-rangli.png'
OUT = ROOT / 'static/brand'
S = 2048                                    # ishchi o'lcham (keyin kichraytiriladi — silliq chiqadi)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def background(rim=True):
    # 1) vertikal gradient: yuqorisi grafit, pasti deyarli qora
    top, bottom = (46, 50, 60), (8, 9, 13)
    bg = Image.new('RGB', (S, S))
    d = ImageDraw.Draw(bg)
    for y in range(S):
        d.line([(0, y), (S, y)], fill=lerp(top, bottom, (y / S) ** 0.9))
    bg = bg.convert('RGBA')

    # 2) yuqori chapdan yumshoq yorug'lik (shisha ichidagi nur)
    glow = Image.new('L', (S, S), 0)
    ImageDraw.Draw(glow).ellipse([-S * 0.35, -S * 0.45, S * 0.75, S * 0.55], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(S * 0.12))
    bg = Image.composite(Image.new('RGBA', (S, S), (120, 130, 150, 255)), bg, glow)

    # 3) shisha yaltirog'i: yuqori qismda keng, chegarasi juda yumshoq (logoni kesib o'tadigan chiziq bo'lmasin)
    sheen = Image.new('L', (S, S), 0)
    ImageDraw.Draw(sheen).ellipse([-S * 0.3, -S * 0.95, S * 1.3, S * 0.30], fill=255)
    sheen = sheen.filter(ImageFilter.GaussianBlur(S * 0.07))
    fade = Image.linear_gradient('L').resize((S, S))                 # yuqoridan pastga: 0 -> 255
    sheen = ImageChops.multiply(sheen, ImageChops.invert(fade)).point(lambda v: int(v * 0.17))
    bg = Image.composite(Image.new('RGBA', (S, S), (255, 255, 255, 255)), bg, sheen)

    # 4) pastki qismda yengil qaytgan nur (qalin shisha hissi)
    low = Image.new('L', (S, S), 0)
    ImageDraw.Draw(low).ellipse([S * 0.1, S * 0.82, S * 0.9, S * 1.25], fill=40)
    low = low.filter(ImageFilter.GaussianBlur(S * 0.08))
    bg = Image.composite(Image.new('RGBA', (S, S), (90, 110, 150, 255)), bg, low)

    if rim:                                                           # chekka nuri: niqob qaysi shaklda kessa ham yumshoq yorug' chet
        r = Image.new('L', (S, S), 0)
        ImageDraw.Draw(r).rectangle([0, 0, S - 1, S - 1], outline=255, width=int(S * 0.03))
        r = r.filter(ImageFilter.GaussianBlur(S * 0.03))
        topmask = ImageChops.invert(Image.linear_gradient('L').resize((S, S))).point(lambda v: int(25 + v * 0.35))
        r = ImageChops.multiply(r, topmask)
        bg = Image.composite(Image.new('RGBA', (S, S), (255, 255, 255, 255)), bg, r)
    return bg


def with_logo(bg, frac):
    logo = Image.open(LOGO).convert('RGBA')
    size = int(S * frac)
    logo = logo.resize((size, size), Image.LANCZOS)
    pos = ((S - size) // 2, (S - size) // 2)
    layer = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    layer.alpha_composite(logo, pos)
    alpha = layer.getchannel('A')

    out = bg.copy()
    # soya (logo shisha ustida turgandek)
    shadow = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda v: int(v * 0.55)))
    shadow = ImageChops.offset(shadow, 0, int(S * 0.012)).filter(ImageFilter.GaussianBlur(S * 0.012))
    out.alpha_composite(shadow)
    # rangli nur (glow)
    glow = layer.filter(ImageFilter.GaussianBlur(S * 0.022))
    glow.putalpha(glow.getchannel('A').point(lambda v: int(v * 0.55)))
    out.alpha_composite(glow)
    out.alpha_composite(layer)
    # logo ustida yengil yaltiroq (yuqori qismi biroz yorug'roq)
    hi = Image.new('RGBA', (S, S), (255, 255, 255, 0))
    grad = ImageChops.invert(Image.linear_gradient('L').resize((S, S))).point(lambda v: int(v * 0.18))
    hi.putalpha(ImageChops.multiply(alpha, grad))
    out.alpha_composite(hi)
    return out.convert('RGB')


def save(img, px, name):
    img.resize((px, px), Image.LANCZOS).save(OUT / name, optimize=True)


if __name__ == '__main__':
    any_icon = with_logo(background(rim=True), 0.62)
    mask_icon = with_logo(background(rim=False), 0.50)     # Android doira/qirqish: logo xavfsiz zona (80%) ichida
    save(any_icon, 512, 'icon-512.png')
    save(any_icon, 192, 'icon-192.png')
    save(any_icon, 180, 'apple-touch-icon.png')
    save(mask_icon, 512, 'icon-maskable-512.png')
    any_icon.resize((1024, 1024), Image.LANCZOS).save(OUT / 'logo' / 'spetion-ilova-ikonka-1024.png', optimize=True)
    print('ok')
