"""Maktab ro'yxatlarini yuklash: o'quvchilar (.xls/.xlsx, sinf bo'yicha varaqlar) va xodimlar (.docx jadval)."""
import re
import zipfile

from django.db import transaction

from panel.models import Position, StaffProfile

from .face_ids import next_teacher_id
from .models import User
from .phone import to_digits
from .student_import import _unique_username, clean_text, import_rows, normalize_phone, split_name

# Lavozim -> panel lavozimi (mavjud 'Position' nomlari). Qolgan fan o'qituvchilari — ustoz.
PANEL_POSITIONS = {'direktor': 'Direktor', "direktor o'rinbosari": "Zam (o'quv ishlari)", 'reseption': 'Reception',
                   'reception': 'Reception'}
NON_TEACHING = {'hamshira', 'oshpaz', 'yordamchi oshpaz', 'texnik hodim', "o't yoquvchi"}


def pretty_name(text):
    """'JUMABOYEV JAVOXIR' -> 'Jumaboyev Javoxir' (apostrofli ismlar buzilmaydi)."""
    return ' '.join(w[:1].upper() + w[1:].lower() for w in clean_text(text).split(' '))


def _rows_of_workbook(path):
    """Har bir varaq uchun qatorlar ro'yxati (matn)."""
    if str(path).lower().endswith('.xls'):
        import xlrd
        wb = xlrd.open_workbook(path)
        for sh in wb.sheets():
            yield [[str(c).strip() for c in sh.row_values(r)] for r in range(sh.nrows)]
    else:
        import openpyxl
        for ws in openpyxl.load_workbook(path, data_only=True).worksheets:
            yield [[str(c or '').strip() for c in row] for row in ws.iter_rows(values_only=True)]


SUMMARY = re.compile(r"^(jami|o\S{0,2}\s*-?\s*\d+\s*[.,]?\s*q)", re.I)   # 'Jami', "O'-12. Q-7" (o'g'il/qiz soni) — o'quvchi emas


def _is_name_header(cell):
    return any(k in cell for k in ('i.f.o', 'f.i.o', 'f.i.sh'))


def read_student_sheets(path):
    """{'5-Sinf': [(ism, '', telefon), ...], ...}. Sinf nomi varaq ichidagi 'N-SINF' sarlavhadan olinadi."""
    classes = {}
    for rows in _rows_of_workbook(path):
        group, cols = None, None
        for row in rows:
            m = re.match(r'^(\d+)\s*-?\s*SINF\b', row[0] if row else '', re.I)
            if m:
                group, cols = f'{m.group(1)}-Sinf', None
                continue
            low = [c.lower() for c in row]
            name_col = next((i for i, c in enumerate(low) if _is_name_header(c)), None)
            if name_col is not None:
                cols = (name_col, next((i for i, c in enumerate(low) if c.startswith('tel')), None))
                continue
            if group and cols and len(row) > cols[0] and re.search(r'[^\W\d_]', row[cols[0]]) and not SUMMARY.match(row[cols[0]]):
                phone = row[cols[1]] if cols[1] is not None and len(row) > cols[1] else ''
                classes.setdefault(group, []).append((pretty_name(row[cols[0]]), '', phone))
    return classes


def import_student_file(path):
    sheets = read_student_sheets(path)
    return [import_rows(group, sheets[group]) for group in sorted(sheets, key=lambda g: int(g.split('-')[0]))]


def read_staff_docx(path):
    """[(ism, lavozim, telefon)] — Word jadvalidan (T/r | Ism | Lavozim | Telefon)."""
    xml = zipfile.ZipFile(path).read('word/document.xml').decode('utf8')
    out = []
    for tr in re.findall(r'<w:tr[ >].*?</w:tr>', xml, re.S):
        cells = [''.join(re.findall(r'<w:t[^>]*>([^<]*)</w:t>', tc)).strip() for tc in re.findall(r'<w:tc>.*?</w:tc>', tr, re.S)]
        if len(cells) >= 4 and re.search(r'\d', cells[3]):
            out.append((pretty_name(cells[1]), clean_text(cells[2]), cells[3]))
    return out


@transaction.atomic
def import_staff(rows):
    report = {'teachers': 0, 'panel': 0, 'other': 0, 'existing': 0, 'bad_phone': []}
    for full, title, phone_raw in rows:
        phone = normalize_phone(phone_raw)
        if phone is None:
            report['bad_phone'].append(f'{full}: {phone_raw}')
            continue
        digits = to_digits(phone)
        last, first = split_name(full)
        key = title.lower()
        user = User.objects.filter(phone_digits=digits).order_by('id').first()
        if user and (user.role in (User.Role.TEACHER, User.Role.STAFF, User.Role.ADMIN) or hasattr(user, 'staff_profile')):
            report['existing'] += 1
            continue
        if key in PANEL_POSITIONS or key in NON_TEACHING:
            position, _ = Position.objects.get_or_create(name=PANEL_POSITIONS.get(key, title), defaults={'default_perms': []})
            if user is None:
                user = User(username=_unique_username(digits), first_name=first, last_name=last, phone=phone,
                            role=User.Role.STAFF)
                user.set_unusable_password()   # panelga kirishi kerak bo'lsa: Xodimlar -> bir martalik parol berish
                user.save()
            panel = key in PANEL_POSITIONS
            StaffProfile.objects.create(user=user, position=position, perms=list(position.default_perms) if panel else [],
                                        is_active=panel)
            report['panel' if panel else 'other'] += 1
        else:   # fan o'qituvchisi
            if user is None:
                user = User(username=_unique_username(digits), first_name=first, last_name=last, phone=phone,
                            role=User.Role.TEACHER)
            else:   # ota-ona hisobi bor — ustoz roli qo'shiladi (loyihadagi ikki rolli hisob mantiqi)
                user.role = User.Role.TEACHER
            user.save()
            user.set_password(user.phone_digits[-4:])    # boshlang'ich parol: telefonning oxirgi 4 raqami
            user.must_change_password = True
            user.access_id = user.access_id or next_teacher_id()
            user.save()
            report['teachers'] += 1
    return report
