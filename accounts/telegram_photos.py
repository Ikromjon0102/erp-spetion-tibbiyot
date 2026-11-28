"""Telegram guruh eksportidan (Telegram Desktop → Export chat history, JSON + Photos) o'quvchi rasmlarini biriktirish.

Har xabar: rasm + izoh «Familiya Ism\\n7b uzb». Ism bo'yicha filial o'quvchilaridan eng yaqini topiladi (kirill/lotin,
o'/g' yozilishi, harf xatolari hisobga olinadi); izohdagi sinf raqami teng kuchli nomzodlarni ajratadi.
Bitta o'quvchiga bir nechta rasm bo'lsa — eng oxirgisi. Ishonchsiz moslik biriktirilmaydi, ro'yxatga chiqadi.
"""
import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from .pay_sheet_import import to_latin

ACCEPT = 0.88          # shu balldan past — biriktirilmaydi, ko'rib chiqishga (eng yaqin nomzod bilan)
SUFFIXES = ('begim', 'bonu', 'xon', 'bek', 'oy', 'jon')   # ism qo'shimchalari: Imron = Imronbek, Sadaf = Sadafxon
SURNAME_END = r'(j[aoi]?n?)?[aoie]v[aoi]?$'   # familiya qo'shimchasi: Gafurjanova = Gafurova, Atxamjov = Adxamjanov
COLORS = {'r': 'red', 'b': 'blue', 'w': 'white', 'g': 'green'}    # «7b uzb» -> 7-Blue


def _text(msg):
    x = msg.get('text', '')
    return x if isinstance(x, str) else ''.join(p if isinstance(p, str) else p.get('text', '') for p in x)


def name_key(text):
    """Solishtirish uchun: kichik harf, lotin, tutuq belgilarsiz; o'/g' -> o/g, ò/ó -> o; kh -> x."""
    s = to_latin(str(text or '')).lower()
    s = re.sub("[ʻʼ‘’`'ʹ]", '', s)
    s = s.replace('ò', 'o').replace('ó', 'o').replace('ğ', 'g').replace('kh', 'x')
    s = re.sub(r'\(.*?\)', ' ', s)                                    # «Melek(Karomat)»
    s = re.sub(r'\b\w+\s+(qizi|ogli|ugli)\b', ' ', s)                 # otasining ismi: «Azizbek qizi»
    return ' '.join(re.sub(r'[^a-z ]', ' ', s).split())


def sound(word):
    """Talaffuz kaliti: h/x, q/k, f/p, o/a, u/o, i/y, ye/e, qo'sh harflar — o'zbekcha yozilish farqlari."""
    w = re.sub(r'(.)\1+', r'\1', word)
    w = w.replace('yu', 'u').replace('ye', 'e').replace('ya', 'a')
    w = w.translate(str.maketrans('hqfouyw', 'xkpaaiv'))
    return re.sub(r'(.)\1+', r'\1', w)


def _root(word):
    for suf in SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[:-len(suf)]
    return word


def _stem(surname):
    stem = re.sub(SURNAME_END, '', surname)
    return stem if len(stem) >= 3 else surname


def _dist(a, b):
    """Levenshtein masofasi."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _allowed(n):
    return 1 if n <= 6 else 2 if n <= 10 else 3


def part(a, b, surname=False):
    """(o'xshash, ball 0..1): talaffuz kaliti bo'yicha harf farqlari soni so'z uzunligiga yarasha bo'lsin."""
    pairs = [(sound(_stem(a)), sound(_stem(b)))] if surname else         [(sound(a), sound(b)), (sound(_root(a)), sound(_root(b)))]
    best = (False, 0.0)
    for x, y in pairs:
        d, n = _dist(x, y), max(len(x), len(y), 1)
        best = max(best, (d <= _allowed(min(len(x), len(y))), 1 - d / n))
    return best


def grade_of(label):
    """'7b uzb' -> 7; '8-9 huquq' -> 8; '1g-sinf' -> 1; sinf yo'q -> None."""
    m = re.match(r'\s*(\d{1,2})', str(label or ''))
    return int(m.group(1)) if m else None


def color_of(label):
    """'7b uzb' -> 'blue'; '1g-sinf' -> 'green'; '10 huquq' -> None."""
    m = re.match(r'\s*\d{1,2}\s*([rbwg])\b', str(label or '').lower())
    return COLORS[m.group(1)] if m else None


def group_grades(name):
    """'8-9-Huquq' -> {8, 9}; '10-Matem' -> {10}."""
    head = re.match(r'^([\d-]+)', name or '')
    return {int(x) for x in re.findall(r'\d+', head.group(1))} if head else set()


def read_export(folder):
    """[(rasm yo'li, ism, sinf yozuvi, xabar id, sana)] — faqat rasmli va izohli xabarlar."""
    folder = Path(folder)
    data = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    out = []
    for m in data.get('messages', []):
        if not m.get('photo'):
            continue
        lines = [x.strip() for x in _text(m).split('\n') if x.strip()]
        if not lines:
            continue
        out.append((folder / m['photo'], ' '.join(lines[0].split()), lines[1] if len(lines) > 1 else '', m.get('id'), m.get('date', '')))
    return out


def _score(caption_key, last, first):
    """Familiya va ism alohida; ikkalasi ham o'xshash bo'lsagina ball (izohda tartib almashgan bo'lishi mumkin)."""
    words = caption_key.split()
    db = name_key(f'{last} {first}').split()
    if len(words) < 2 or len(db) < 2:
        return 0.0
    l, f = db[0], db[1]
    best = 0.0
    for cl, cf in ((words[0], words[1]), (words[-1], words[0])):
        ok_l, sl = part(cl, l, surname=True)
        ok_f, sf = part(cf, f)
        if ok_l and ok_f:
            best = max(best, (sl + sf) / 2)
    return best


def match(entries, students):
    """students: [(id, familiya, ism, sinf nomi)]. Natija: {'matched': {student_id: entry}, 'unmatched': [...], 'ambiguous': [...]}"""
    matched, unmatched, ambiguous = {}, [], []
    for entry in entries:
        _path, caption, label, _id, _date = entry
        key = name_key(caption)
        grade, color = grade_of(label), color_of(label)
        scored = []
        for sid, last, first, group in students:
            s = _score(key, last, first)
            if s <= 0:
                scored.append((0.0, sid, f'{last} {first} ({group or "-"})'))
                continue
            grades = group_grades(group)
            if grade is not None and grades:
                if grade in grades:
                    s += 0.04                                     # sinf mos
                elif min(abs(grade - g) for g in grades) > 1:
                    s -= 0.10                                     # boshqa sinf (±1 — jadvalda adashish bo'lishi mumkin)
            if color and color in (group or '').lower():
                s += 0.05                                         # «7b» — Blue
            scored.append((s, sid, f'{last} {first} ({group or "-"})'))
        scored.sort(reverse=True)
        best = scored[0] if scored else None
        second = scored[1][0] if len(scored) > 1 else 0
        if best is None or best[0] < ACCEPT:
            if best is not None and best[0] <= 0:              # hech kim o'xshamadi — hisobot uchun eng yaqin yozilish
                near = max(students, key=lambda x: SequenceMatcher(None, key, name_key(f'{x[1]} {x[2]}')).ratio())
                best = (0.0, near[0], f'{near[1]} {near[2]} ({near[3] or "-"})')
            unmatched.append((entry, best and best[2], best and round(best[0], 2)))
        elif second > 0 and best[0] - second < 0.05 and scored[1][2].split(' (')[0] != best[2].split(' (')[0]:
            ambiguous.append((entry, [x[2] for x in scored[:2]]))
        else:
            matched[best[1]] = (entry, best[2], round(best[0], 2))   # keyingi (yangiroq) rasm eskisini almashtiradi
    return {'matched': matched, 'unmatched': unmatched, 'ambiguous': ambiguous}
