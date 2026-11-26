"""Rangli logotip fayllari (fonsiz): belgi va to'liq logo (belgi + «Spetion» yozuvi), SVG va PNG.
Chiqadi: static/brand/logo/ — python tools/make_color_logo.py"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_brand_icons import TAB_COLORS, d, render  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'static' / 'brand' / 'logo'
parts = [x.strip() for x in re.split(r'(?=M )', d) if x.strip()]
MARK = set(TAB_COLORS)


def svg(viewbox, text_color=None):
    paths = ''.join(f'<path fill="{TAB_COLORS[i]}" d="{p}"/>' for i, p in enumerate(parts) if i in MARK)
    if text_color:
        text = ' '.join(p for i, p in enumerate(parts) if i not in MARK)       # bitta yo'l: «o», «e», «p» teshiklari evenodd bilan qoladi
        paths += f'<path fill="{text_color}" fill-rule="evenodd" d="{text}"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">{paths}</svg>'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        'spetion-belgi-rangli': (svg('38 38 223 223'), 1024, 1024),
        'spetion-logo-rangli-qora-yozuv': (svg('30 30 1031 240', '#111111'), 2062, 480),
        'spetion-logo-rangli-oq-yozuv': (svg('30 30 1031 240', '#FFFFFF'), 2062, 480),
    }
    for name, (s, w, h) in files.items():
        (OUT / f'{name}.svg').write_text(s, encoding='utf-8')
        render(s, w, h).save(OUT / f'{name}.png')
        print(name)


if __name__ == '__main__':
    main()
