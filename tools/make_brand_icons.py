"""Brend ikonkalarini yasaydi: static/brand/ (favicon.svg, favicon.ico, icon-192/512, maskable-512, apple-touch-icon, og.png).
Belgi — logotipdagi «quyosh» (templates/teacher/_logo.svg, 0..300 qismi), to'q fonda, tashkilotlar ranglaridagi gradient.
PNG lar Chrome (headless) bilan chiziladi:  python tools/make_brand_icons.py
"""
import re
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'static' / 'brand'
CHROME = r'C:/Program Files/Google/Chrome/Application/chrome.exe'
BG = '#0B1020'
STOPS = [('0', '#34D399'), ('.36', '#60A5FA'), ('.68', '#FB923C'), ('1', '#F87171')]   # yashil, ko'k, to'q sariq, qizil (yorqinroq)

d = re.search(r'd="([^"]+)"', (ROOT / 'templates/teacher/_logo.svg').read_text(encoding='utf-8')).group(1)
grad = ''.join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in STOPS)


def mark_svg(size_box=300, scale=0.80, rounded=True, bg=True):
    """Belgi 300x300 koordinatada markazda (≈150,150). scale — fon ichidagi o'lchami."""
    t = f'translate(150 150) scale({scale}) translate(-150 -150)'
    rect = (f'<rect width="300" height="300" rx="{"68" if rounded else "0"}" fill="{BG}"/>'
            f'<rect width="300" height="300" rx="{"68" if rounded else "0"}" fill="url(#glow)"/>') if bg else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300">'
            f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">{grad}</linearGradient>'
            f'<radialGradient id="glow" cx=".3" cy=".25" r=".9"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".10"/>'
            f'<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></radialGradient>'
            f'<clipPath id="c"><rect width="300" height="300"/></clipPath></defs>'
            f'{rect}<g clip-path="url(#c)"><path transform="{t}" fill="url(#g)" fill-rule="evenodd" d="{d}"/></g></svg>')


# Brauzer tabi uchun: fonsiz, 8 ta nur juft-juft 4 rangda (soat yo'nalishida: tepa — yashil, o'ng — ko'k, past — to'q sariq, chap — qizil).
# Logotip yo'lidagi qism-yo'llar (subpath) tartibi: 18,17 tepa; 13,2 o'ng; 0,1 past; 3,12 chap.
TAB_COLORS = {18: '#22C55E', 17: '#22C55E', 13: '#3B82F6', 2: '#3B82F6', 0: '#F97316', 1: '#F97316', 3: '#EF4444', 12: '#EF4444'}


def tab_svg(colors=None):
    parts = [x for x in re.split(r'(?=M )', d) if x.strip()]
    colors = colors or TAB_COLORS
    paths = ''.join(f'<path fill="{c}" d="{parts[i].strip()}"/>' for i, c in colors.items())
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="38 38 223 223">{paths}</svg>'


def render(svg, w, h, html_extra=''):
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / 'p.html'
        png = Path(tmp) / 'p.png'
        page.write_text(f'<!doctype html><html><body style="margin:0;background:transparent">{html_extra or svg.replace("<svg ", f"<svg width=\"{w}\" height=\"{h}\" ", 1)}</body></html>',
                        encoding='utf-8')
        subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--hide-scrollbars', f'--window-size={w},{h}', '--default-background-color=00000000',
                        f'--screenshot={png}', page.as_uri()], capture_output=True, check=True)
        return Image.open(BytesIO(png.read_bytes())).convert('RGBA').crop((0, 0, w, h))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fav = mark_svg(scale=0.86)            # ilova ikonkasi (telefon ekrani) — fon bilan
    tab = tab_svg()                       # brauzer tabi — fonsiz, rangli nurlar
    (OUT / 'favicon.svg').write_text(tab, encoding='utf-8')
    (OUT / 'favicon-red.svg').write_text(tab_svg({k: '#DD1808' for k in TAB_COLORS}), encoding='utf-8')
    big = render(fav, 512, 512)
    big.save(OUT / 'icon-512.png')
    big.resize((192, 192), Image.LANCZOS).save(OUT / 'icon-192.png')
    sizes = [(s, s) for s in (16, 32, 48)]
    render(tab, 256, 256).save(OUT / 'favicon.ico', sizes=sizes)
    render(mark_svg(scale=0.62, rounded=False), 512, 512).save(OUT / 'icon-maskable-512.png')   # xavfsiz hudud 80%
    apple = render(mark_svg(scale=0.78, rounded=False), 180, 180)
    Image.alpha_composite(Image.new('RGBA', apple.size, BG), apple).convert('RGB').save(OUT / 'apple-touch-icon.png')
    # Ijtimoiy tarmoq ko'rinishi (Telegram, Facebook havolada)
    logo = (ROOT / 'templates/teacher/_logo.svg').read_text(encoding='utf-8').replace('fill="#166534"', 'fill="#EEF2F8"')
    og = f"""<div style="width:1200px;height:630px;position:relative;overflow:hidden;background:{BG};font-family:Inter,Segoe UI,Arial,sans-serif">
      <div style="position:absolute;width:620px;height:620px;left:-160px;top:-260px;border-radius:50%;background:#166534;filter:blur(90px);opacity:.7"></div>
      <div style="position:absolute;width:560px;height:560px;right:-140px;top:-180px;border-radius:50%;background:#1E3A8A;filter:blur(90px);opacity:.8"></div>
      <div style="position:absolute;width:620px;height:620px;left:200px;bottom:-380px;border-radius:50%;background:#F97316;filter:blur(100px);opacity:.55"></div>
      <div style="position:absolute;width:520px;height:520px;right:-120px;bottom:-300px;border-radius:50%;background:#E53935;filter:blur(100px);opacity:.6"></div>
      <div style="position:absolute;left:90px;top:110px;width:420px">{logo.replace('<svg ', '<svg style="width:420px;height:auto" ', 1)}</div>
      <div style="position:absolute;left:96px;top:300px;color:#EEF2F8;font-size:64px;font-weight:800;letter-spacing:-2px;line-height:1.05">Butun ta'lim oilasi —<br>bitta ilovada</div>
      <div style="position:absolute;left:98px;top:470px;color:#A3ADBD;font-size:30px">my.spetion.uz · davomat, baholar, to'lovlar, xabarlar</div>
    </div>"""
    render('', 1200, 630, html_extra=og).convert('RGB').save(OUT / 'og.png', quality=90)
    for f in sorted(OUT.iterdir()):
        print(f.name, f.stat().st_size)


if __name__ == '__main__':
    main()
