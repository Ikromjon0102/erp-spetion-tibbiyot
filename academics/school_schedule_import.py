"""Asosiy maktab dars jadvali (ruscha «Расписание Классов» varag'i) — 2026-11-28.

Tuzilish: 1-qator sarlavha: День недели | Урок | Время | «1-A\\n(Рус.)» | ... ; keyin har kun uchun 1..9 soat.
Katak: «Математика [ПАРА]\\n(Минадиева Алиме)», «ОБЕД», «Воспитание (Вакант)», «Урок Будущего\\n(Кл. руководитель)».
Fan nomlari o'zbekchaga o'giriladi, ustoz ismi kirill -> lotin qilib filial ustozlaridan topiladi.
«Кл. руководитель» — sinf rahbari (to'lov jadvalidagi), «Вакант» — ustozsiz dars, «ОБЕД» — tushlik (dars emas).
Qayta yuklansa: shu sinflarning eski darslari o'chirilmaydi, faqat nofaol qilinadi (davomat tarixi saqlanadi).
"""
import re
from datetime import datetime

import openpyxl
from django.db import transaction

from accounts.models import User
from accounts.pay_sheet_import import to_latin
from accounts.telegram_photos import name_key, part

from .models import Group, Lesson, Subject, Teaching

DAYS = {'понедельник': 0, 'вторник': 1, 'среда': 2, 'четверг': 3, 'пятница': 4, 'суббота': 5}

SUBJECTS = {
    'английский язык': 'Ingliz tili', 'биология': 'Biologiya', 'воспитание': 'Tarbiya', 'восптание': 'Tarbiya',
    'география': 'Geografiya', 'гончарное искусство': 'Kulolchilik', 'информатика': 'Informatika', 'история': 'Tarix',
    'литература': 'Adabiyot', 'математика': 'Matematika', 'ментальная арифметика': 'Mental arifmetika',
    'музыка': 'Musiqa', 'право': 'Huquq', 'родной язык': 'Ona tili', 'русский язык': 'Rus tili',
    'узбекский язык': "O'zbek tili", 'урок будущего': 'Kelajak darsi', 'физическое воспитание': 'Jismoniy tarbiya',
    'химия': 'Kimyo', 'читательская грамотность': "O'qish savodxonligi", 'science': 'Science',
}
SKIP = {'обед'}
VACANT = 'вакант'
CLASS_TEACHER = 'кл. руководитель'

# Jadvaldagi sinf -> tizimdagi sinf (founder tasdig'i bilan; sinf rahbari va o'qitish tili bo'yicha)
CLASS_MAP = {
    '1-A': '1-Red', '1-B': '1-White', '1-V': '1-Green', '1-G': '1-Blue', '2-A': '2-Red', '2-B': '2-Blue',
    '3-A': '3-Red', '3-B': '3-Blue', '4-A': '4-Red', '4-B': '4-Blue', '5-A': '5-Red', '5-B': '5-Blue', '5-V': '5-Green',
    '6-A': '6-Red', '6-B': '6-Blue', '7-A': '7-Red', '7-B': '7-Blue', '8-A': '8-9-Huquq', '8-B': '8-Red', '8-V': '8-Blue',
    '8-G': '8-Ingliz', '8-D': '8-Med rus', '10-A': '10-Huquq', '10-B': '10-Matem', '10-V': '10-Ingliz',
}


def parse_cell(value):
    """-> None (bo'sh/tushlik) yoki (fan, ustoz|None|CLASS_TEACHER). Noma'lum fan — ValueError."""
    text = str(value or '').strip()
    if not text:
        return None
    m = re.search(r'\(([^()]*)\)\s*$', text)
    teacher = m.group(1).strip() if m else None
    head = text[:m.start()] if m else text
    subject = re.sub(r'\[.*?\]', '', head.split('\n')[0])
    subject = re.sub(r'\(.*?\)', '', subject).strip().lower()                # «Урок Будущего (Воспитание)»
    if subject in SKIP:
        return None
    if subject not in SUBJECTS:
        raise ValueError(f'Noma\'lum fan: {text!r}')
    if teacher and teacher.lower() == VACANT:
        teacher = None
    elif teacher and teacher.lower() == CLASS_TEACHER:
        teacher = CLASS_TEACHER
    return SUBJECTS[subject], teacher


def _times(text):
    a, b = re.split(r'\s*[–-]\s*', str(text).strip())
    return datetime.strptime(a, '%H:%M').time(), datetime.strptime(b, '%H:%M').time()


def read_schedule(path):
    """-> [(jadvaldagi sinf, kun, soat, boshlanish, tugash, fan, ustoz)]"""
    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    classes = [str(h).split('\n')[0].strip() if h else None for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not r[0] or str(r[0]).strip().lower() not in DAYS:
            continue
        day, period = DAYS[str(r[0]).strip().lower()], int(r[1])
        start, end = _times(r[2])
        for ci in range(3, len(r)):
            if not classes[ci]:
                continue
            cell = parse_cell(r[ci])
            if cell:
                out.append((classes[ci], day, period, start, end, cell[0], cell[1]))
    return out


class TeacherFinder:
    """Kirillcha «Юсупов Абдулбосит» -> filial ustozi «Yusupov Abdulvosid» (yozilish farqlari hisobga olinadi)."""

    def __init__(self, branch):
        self.people = [(u, name_key(f'{u.last_name} {u.first_name}').split())
                       for u in User.objects.filter(branches=branch, role=User.Role.TEACHER).distinct()]
        self.cache = {}

    def find(self, raw):
        if raw not in self.cache:
            words = name_key(to_latin(raw)).split()
            best = (0.0, None)
            for u, db in self.people:
                if len(words) < 2 or len(db) < 2:
                    continue
                for cl, cf in ((words[0], words[1]), (words[-1], words[0])):
                    ol, sl = part(cl, db[0], surname=True)
                    of, sf = part(cf, db[1])
                    if ol and of and (sl + sf) / 2 > best[0]:
                        best = ((sl + sf) / 2, u)
            self.cache[raw] = best[1]
        return self.cache[raw]


@transaction.atomic
def import_schedule(rows, branch, class_teachers=None, class_map=None, dry_run=False):
    """class_teachers: {tizimdagi sinf: ustoz ismi} (to'lov jadvalidan) — «Кл. руководитель» uchun."""
    class_map = class_map or CLASS_MAP
    finder = TeacherFinder(branch)
    report = {'lessons': 0, 'groups': set(), 'subjects': set(), 'teachers': set(), 'no_teacher': {}, 'unknown_class': set(),
              'deactivated': 0}
    groups = {}
    for cls in {r[0] for r in rows}:
        name = class_map.get(cls)
        g = Group.objects.filter(branch=branch, name=name).first() if name else None
        if g is None:
            report['unknown_class'].add(cls)
        groups[cls] = g
    if report['unknown_class'] and not dry_run:
        raise ValueError(f"Tizimda topilmagan sinflar: {', '.join(sorted(report['unknown_class']))}")
    heads = {}
    for gname, raw in (class_teachers or {}).items():
        heads[gname] = finder.find(raw) if raw else None
    if not dry_run:
        report['deactivated'] = Lesson.objects.filter(teaching__group__in=[g for g in groups.values() if g], active=True) \
            .update(active=False)
    for cls, day, period, start, end, subject, raw in rows:
        g = groups[cls]
        if raw == CLASS_TEACHER:
            teacher = heads.get(g.name) if g else None
            if teacher is None:
                report['no_teacher'][f'Sinf rahbari ({class_map.get(cls, cls)})'] = report['no_teacher'].get(f'Sinf rahbari ({class_map.get(cls, cls)})', 0) + 1
        elif raw:
            teacher = finder.find(raw)
            if teacher is None:
                report['no_teacher'][raw] = report['no_teacher'].get(raw, 0) + 1
            else:
                report['teachers'].add(f'{raw} -> {teacher.last_name} {teacher.first_name}')
        else:
            teacher = None
        report['lessons'] += 1
        report['subjects'].add(subject)
        if g:
            report['groups'].add(g.name)
        if dry_run or g is None:
            continue
        subj, _ = Subject.objects.get_or_create(name=subject)
        teaching, _ = Teaching.objects.get_or_create(teacher=teacher, subject=subj, group=g)
        Lesson.objects.create(teaching=teaching, weekday=day, period=period, start=start, end=end)
    return report
