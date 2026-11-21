"""O'quvchilar ro'yxati Excel faylini (sinf bo'yicha) yuklash.

Kutilgan sarlavhalar (qatori fayldan o'zi topiladi): "O'quvchi F.I.Sh." | "Kimning raqami" (ona/ota) | "Telefon raqami".
Telefon — ota-onaniki: shu raqam bo'yicha ota-ona hisobi yaratiladi va o'quvchiga bog'lanadi.
"""
import re

import openpyxl
from django.db import transaction
from django.utils.text import slugify

from academics.models import Group

from .models import Student, User

# Kirill alifbosidagi lotinga o'xshash harflar (masalan "Аbdukarimov" dagi birinchi "А" kirillcha bo'lishi mumkin)
LOOKALIKES = str.maketrans('АаВЕеКМНОоРрСсТХхУуІ', 'AaBEeKMHOoPpCcTXxYyI')
APOSTROPHES = re.compile(r"[ʼʻ’‘`´ʹ′]")
RELATIONS = {'ona': 'onasi', 'ota': 'otasi'}


def clean_text(value):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    if re.search('[A-Za-z]', text):  # lotincha matn ichidagi kirill "ikkilamchi" harflarni lotinga o'tkazamiz
        text = text.translate(LOOKALIKES)
    return APOSTROPHES.sub("'", text)


def split_name(full):
    """'Familiya Ism [Ism...]' -> (familiya, ism)."""
    parts = clean_text(full).split(' ', 1)
    return parts[0], (parts[1] if len(parts) > 1 else '')


def normalize_phone(value):
    """'95-010-76-39' -> '+998 95 010-76-39'; yaroqsiz bo'lsa None."""
    digits = re.sub(r'\D', '', str(value or ''))
    if len(digits) == 9:
        digits = '998' + digits
    if len(digits) != 12 or not digits.startswith('998'):
        return None
    return f'+{digits[:3]} {digits[3:5]} {digits[5:8]}-{digits[8:10]}-{digits[10:]}'


def group_name_from_filename(path):
    m = re.search(r'(\d+)\s*-\s*sinf', str(path), re.I)
    return f'{m.group(1)}-Sinf' if m else None


def _unique_username(base, prefix=''):
    base = (prefix + (slugify(base) or 'user'))[:140]
    username, n = base, 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f'{base}{n}'
    return username


def _read_rows(path):
    ws = openpyxl.load_workbook(path, data_only=True).active
    header = None
    for r in range(1, min(ws.max_row, 20) + 1):
        cells = {c: str(ws.cell(r, c).value or '').lower() for c in range(1, ws.max_column + 1)}
        name_col = next((c for c, v in cells.items() if 'f.i.sh' in v or 'f.i.o' in v), None)
        if name_col:
            header = (r, name_col,
                      next((c for c, v in cells.items() if 'kimning' in v), None),
                      next((c for c, v in cells.items() if 'telefon' in v), None))
            break
    if header is None:
        raise ValueError("'F.I.Sh.' sarlavhali ustun topilmadi")
    hr, name_col, rel_col, phone_col = header
    for r in range(hr + 1, ws.max_row + 1):
        name = clean_text(ws.cell(r, name_col).value)
        first_cell = str(ws.cell(r, 1).value or '').strip().lower()
        # "Jami" qatori (formula natijasi, masalan 20) o'quvchi emas; ismda kamida bitta harf bo'lishi shart
        if first_cell.startswith('jami') or not re.search(r'[^\W\d_]', name):
            continue
        yield (name,
               clean_text(ws.cell(r, rel_col).value).lower() if rel_col else '',
               ws.cell(r, phone_col).value if phone_col else None)


@transaction.atomic
def import_students(path, group_name, branch=None):
    return import_rows(group_name, _read_rows(path), branch=branch)


@transaction.atomic
def import_rows(group_name, rows, branch=None):
    """rows: (to'liq ism, 'ona'/'ota'/'', ota-ona telefoni) — fayl formatidan qat'i nazar."""
    group, _ = Group.objects.get_or_create(name=group_name, defaults={'branch': branch})
    report = {'group': group_name, 'created': 0, 'existing': 0, 'parents_new': 0, 'parents_linked': 0,
              'no_phone': [], 'bad_phone': []}

    for full, relation, phone_raw in rows:
        last, first = split_name(full)
        student = (Student.objects.filter(group=group, user__last_name__iexact=last, user__first_name__iexact=first)
                   .first())
        if student is None:
            user = User(username=_unique_username(f'{last}-{first}'), first_name=first, last_name=last,
                        role=User.Role.STUDENT)
            user.set_unusable_password()  # o'quvchi hozircha tizimga kirmaydi (kerak bo'lsa admin parol beradi)
            user.save()
            student = Student.objects.create(user=user, group=group)
            report['created'] += 1
        else:
            report['existing'] += 1

        if not phone_raw:
            report['no_phone'].append(full)
            continue
        phone = normalize_phone(phone_raw)
        if phone is None:
            report['bad_phone'].append(f'{full}: {phone_raw}')
            continue
        digits = re.sub(r'\D', '', phone)
        # Shu raqam egasi allaqachon tizimda bo'lsa (masalan, farzandi ham o'qiydigan ustoz), yangi hisob ochilmaydi —
        # farzand o'sha hisobga bog'lanadi, shunda bitta login bilan ham ustoz, ham ota-ona bo'ladi.
        existing = User.objects.filter(phone_digits=digits).order_by('id')
        parent = existing.filter(role=User.Role.TEACHER).first() or existing.first()
        if parent is None:
            parent = User(username=digits, role=User.Role.PARENT, phone=phone,
                          first_name=f"{last} {first} {RELATIONS.get(relation, 'ota-onasi')}")
            parent.set_unusable_password()  # parol: admin panelda "telefonning oxirgi 4 raqami" amali bilan
            parent.save()
            report['parents_new'] += 1
        if not student.parents.filter(pk=parent.pk).exists():
            student.parents.add(parent)
            report['parents_linked'] += 1
    return report
