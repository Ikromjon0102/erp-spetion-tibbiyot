"""Dars jadvali Excel faylini (Dars_Jadvali(Noyabr).xlsx tuzilishida) bazaga yuklash.

Fayl tuzilishi: 3-qatorda sarlavha (Hafta kuni | Dars soati | Davomiylik | 5-Sinf | 6-Sinf ...),
keyingi qatorlarda har kun uchun dars soatlari. Katak: "Fan(Ustoz)", ustozsiz bo'lsa "Fan",
"+17:00" qo'shimchasi darsning shu vaqtda o'tishini bildiradi.
"""
import re
import secrets
from collections import defaultdict
from datetime import datetime, timedelta

import openpyxl
from django.db import transaction
from django.utils.text import slugify

from accounts.models import User

from .constants import DAY_NAMES
from .models import Group, Lesson, Subject, Teaching

CELL_RE = re.compile(r"^\s*(?P<subject>[^(+,]+?)\s*(?:\((?P<teacher>[^)]*)\))?\s*,?\s*(?:\+(?P<extra>\d{1,2}:\d{2}))?\s*$")
PASSWORD_ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'  # o/0, l/1/i kabi adashadigan belgilarsiz
EXTRA_LESSON_MINUTES = 45


# Jadvaldagi ism -> ustozlar ro'yxatidagi (Word) ism. Fanlar mos kelishi tekshirilgan.
TEACHER_ALIASES = {'oychexra': 'Oychehra', 'nigoraxon': 'Nigora', 'ranoxon': "Ra'no", 'boburmirzo': 'Bobur', 'shuxratjon': 'Shuhrat'}


def normalize_teacher(raw):
    """'Oychexra aya' va 'Oychexra' — bir odam. Qo'shimcha so'zlar (aya/opa) olib tashlanadi."""
    name = (raw or '').strip().replace('’', "'").replace('ʻ', "'").replace('`', "'")
    name = re.sub(r'\s+(aya|opa|ustoz)$', '', name, flags=re.I)
    return name.strip()


def parse_cell(value):
    """-> (fan, ustoz|None, qo'shimcha_vaqt|None) yoki None (bo'sh katak / '-')."""
    text = str(value or '').strip()
    if text in ('', '-'):
        return None
    m = CELL_RE.match(text)
    if not m:
        raise ValueError(f'Katakni o\'qib bo\'lmadi: {text!r}')
    return m['subject'].strip(), normalize_teacher(m['teacher']) or None, m['extra']


def _make_username(name):
    base = slugify(name.replace("'", '')) or 'ustoz'
    username, n = base, 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f'{base}{n}'
    return username


def _time(hhmm):
    return datetime.strptime(hhmm, '%H:%M').time()


@transaction.atomic
def import_workbook(path, branch=None):
    ws = openpyxl.load_workbook(path, data_only=True).active

    header_row = next((r for r in range(1, 15) if str(ws.cell(r, 1).value or '').strip().lower() == 'hafta kuni'), None)
    if header_row is None:
        raise ValueError("'Hafta kuni' sarlavhali qator topilmadi")
    classes = {c: str(ws.cell(header_row, c).value).strip()
               for c in range(4, ws.max_column + 1) if ws.cell(header_row, c).value}

    day_lookup = {n.lower(): i for i, n in enumerate(DAY_NAMES)}
    report = {'created': 0, 'updated': 0, 'deactivated': 0, 'teachers_new': [], 'warnings': []}
    credentials = []
    teacher_cache = {}
    if branch is None:
        from org.models import default_branch
        branch = default_branch()
    groups = {c: Group.objects.get_or_create(name=name, branch=branch)[0] for c, name in classes.items()}
    seen = set()
    busy = defaultdict(list)  # (ustoz, kun, soat) -> [sinflar]  — to'qnashuvlarni topish uchun

    def get_teacher(name):
        if name not in teacher_cache:
            teachers = User.objects.filter(role=User.Role.TEACHER)
            u = (teachers.filter(first_name__iexact=TEACHER_ALIASES.get(name.lower(), name)).first()
                 or teachers.filter(first_name__iexact=name).first())   # alias topilmasa — asl ism bo'yicha
            if u is None:
                password = ''.join(secrets.choice(PASSWORD_ALPHABET) for _ in range(8))
                u = User(username=_make_username(name), first_name=name, role=User.Role.TEACHER)
                u.set_password(password)
                u.save()
                credentials.append((name, u.username, password))
                report['teachers_new'].append(name)
            teacher_cache[name] = u
        return teacher_cache[name]

    weekday = None
    for r in range(header_row + 1, ws.max_row + 1):
        day_cell = str(ws.cell(r, 1).value or '').strip().lower()
        if day_cell in day_lookup:
            weekday = day_lookup[day_cell]
        period_cell, time_cell = ws.cell(r, 2).value, str(ws.cell(r, 3).value or '')
        if weekday is None or not str(period_cell or '').strip().isdigit() or '-' not in time_cell:
            continue
        period = int(str(period_cell).strip())
        start_s, end_s = [t.strip() for t in time_cell.split('-', 1)]

        for col, class_name in classes.items():
            coord = ws.cell(r, col).coordinate
            try:
                parsed = parse_cell(ws.cell(r, col).value)
            except ValueError as e:
                report['warnings'].append(f'{coord}: {e}')
                continue
            if parsed is None:
                continue
            subject_name, teacher_name, extra = parsed
            start, end = _time(start_s), _time(end_s)
            if extra:  # masalan "+17:00": dars soat 17:00 da o'tadi
                start = _time(extra)
                end = (datetime.combine(datetime.today(), start) + timedelta(minutes=EXTRA_LESSON_MINUTES)).time()

            teacher = get_teacher(teacher_name) if teacher_name else None
            subject = Subject.objects.get_or_create(name=subject_name)[0]
            teaching = Teaching.objects.get_or_create(teacher=teacher, subject=subject, group=groups[col])[0]

            lesson = Lesson.objects.filter(teaching__group=groups[col], weekday=weekday, period=period,
                                           active=True).first()
            if lesson is None:
                lesson = Lesson.objects.create(teaching=teaching, weekday=weekday, period=period, start=start, end=end)
                report['created'] += 1
            else:
                changed = (lesson.teaching_id, lesson.start, lesson.end) != (teaching.id, start, end)
                if changed:
                    lesson.teaching, lesson.start, lesson.end = teaching, start, end
                    lesson.save()
                    report['updated'] += 1
            seen.add(lesson.id)
            if teacher:
                busy[(teacher.id, teacher_name, weekday, period)].append(class_name)

    stale = Lesson.objects.filter(active=True, teaching__group__in=groups.values()).exclude(id__in=seen)
    report['deactivated'] = stale.update(active=False)

    for (_, name, wd, period), cls in busy.items():
        if len(cls) > 1:
            report['warnings'].append(
                f"To'qnashuv: {name} — {DAY_NAMES[wd]}, {period}-soat bir vaqtda {', '.join(cls)} sinflarida")
    report['credentials'] = credentials
    report['lessons_total'] = len(seen)
    return report
