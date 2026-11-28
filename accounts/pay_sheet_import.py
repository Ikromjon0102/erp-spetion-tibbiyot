"""Maktabning o'z Excel'laridan yuklash (Asosiy maktab formati, 2026-11-28).

1) «O'quvchilar to'lov jadvali»: har sinf alohida varaq. 2-qatorda «Sinf: <nom> | Sinf rahbari: <ism>»,
   3-qatorda sarlavha: № | O'quvchi ism-familiyasi | Ota-ona ism-familiyasi | Telefon 1 | Telefon 2 | Oylik badal | Sentabr..Iyun.
   Bu yerdan faqat sinf, o'quvchi va ota-ona telefonlari olinadi. Oylik badal va to'lovlar alohida (founder javobidan keyin).
2) «Xodimlar raqamlari»: T/r | IFO | Fani (yoki lavozim) | Tug'ilgan sana | Telefon.

Qayta ishga tushirsa takrorlanmaydi (o'quvchi sinf + ism bo'yicha, xodim telefon yoki ism bo'yicha topiladi).
"""
import datetime
import re

import openpyxl
from django.db import transaction

from academics.models import Group
from panel.models import Position, StaffProfile

from .face_ids import next_staff_id, next_teacher_id
from .models import Student, User
from .student_import import RELATIONS, _unique_username, clean_text, normalize_phone, split_name

# «Fani» ustunidagi qiymat dars bermaydigan xodimni bildirsa — lavozim nomi (panel lavozimi bilan bir xil bo'lsa, o'sha olinadi)
STAFF_TITLES = {
    'direktor': 'Direktor', 'adminstrator': 'Administrator', 'administrator': 'Administrator', 'savxoz': 'Zavxoz',
    'zavxoz': 'Zavxoz', 'nazoratchi': 'Nazoratchi', 'oshxona': 'Oshxona', 'oshpaz': 'Oshpaz', 'konditer': 'Konditer',
    'hamshira': 'Hamshira', 'marketolog': 'Marketolog', 'qorovul': 'Qorovul', 'tozalov': 'Tozalovchi',
}
PANEL_TITLES = {'Direktor'}          # panelga kirish shu lavozimlarda (parolni panelda «bir martalik parol» bilan berasiz)
SKIP_TITLES = {'asoschi'}            # egasi hisobi alohida (founder o'zi)


def class_name(raw):
    """'Sinf 1-Green' -> '1-Green'; 'Sinf 3 Blue' -> '3-Blue'; 'Sinf 8-med rus' -> '8-Med rus'."""
    name = clean_text(re.sub(r'^\s*sinf\s*', '', str(raw or ''), flags=re.I))
    name = re.sub(r'^(\d+(?:-\d+)?)[\s-]+', r'\1-', name)
    head, _, tail = name.partition('-')
    return f'{head}-{tail[:1].upper()}{tail[1:]}' if tail else name


def read_pay_sheets(path):
    """{sinf: {'teacher': ism, 'students': [(ism, ota-ona ismi, tel1, tel2, oylik), ...]}}"""
    wb = openpyxl.load_workbook(path, data_only=True)
    out = {}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 4 or not str(rows[1][1] or '').strip().lower().startswith('sinf'):
            continue                                              # «Umumiy» kabi hisobot varaqlari
        name = class_name(rows[1][2] or ws.title)
        students = []
        for r in rows[3:]:
            if not isinstance(r[0], (int, float)) or not re.search(r'[^\W\d_]', str(r[1] or '')):
                continue
            students.append((clean_text(r[1]), clean_text(r[2]), r[3], r[4], r[5]))
        out[name] = {'teacher': clean_text(rows[1][4]), 'students': students}
    return out


def read_staff_sheet(path):
    """[(ism, fan/lavozim, tug'ilgan sana, telefon)] — sana bo'lmasa ham telefon 4-ustunda kelishi mumkin."""
    ws = openpyxl.load_workbook(path, data_only=True).active
    out = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not isinstance(r[0], (int, float)) or not r[1]:
            continue
        birth, phone = r[3], r[4]
        if not isinstance(birth, (datetime.date, datetime.datetime)):
            birth, phone = None, phone or birth                   # sana o'rnida telefon yozilgan qatorlar
        out.append((clean_text(r[1]), clean_text(r[2]), birth.date() if isinstance(birth, datetime.datetime) else birth, phone))
    return out


def _staff_title(subject):
    key = subject.lower()
    if key in SKIP_TITLES:
        return 'skip'
    return next((v for k, v in STAFF_TITLES.items() if key.startswith(k)), None)


@transaction.atomic
def import_staff_sheet(rows, branch):
    report = {'teachers': 0, 'staff': 0, 'existing': 0, 'skipped': [], 'no_phone': []}
    for full, subject, birth, phone_raw in rows:
        title = _staff_title(subject)
        if title == 'skip':
            report['skipped'].append(f'{full} ({subject})')
            continue
        phone = normalize_phone(phone_raw)
        last, first = split_name(full)
        user = User.objects.filter(phone_digits=re.sub(r'\D', '', phone)).order_by('id').first() if phone else \
            User.objects.filter(last_name=last, first_name=first).exclude(role__in=['student', 'parent']).first()
        if user and (user.role in (User.Role.TEACHER, User.Role.STAFF) or hasattr(user, 'staff_profile')):
            user.branches.add(branch)
            report['existing'] += 1
            continue
        if not phone:
            report['no_phone'].append(full)
        if title:                                                 # dars bermaydigan xodim
            position = Position.objects.filter(name=title).first() or Position.objects.create(name=title, default_perms=[])
            if user is None:
                user = User(username=_unique_username(phone and re.sub(r'\D', '', phone) or f'{last}-{first}'),
                            first_name=first, last_name=last, phone=phone or '', role=User.Role.STAFF)
                user.set_unusable_password()
            user.access_id = user.access_id or next_staff_id()
            user.save()
            panel = title in PANEL_TITLES
            StaffProfile.objects.create(user=user, position=position, is_active=panel,
                                        perms=list(position.default_perms) if panel else [])
            report['staff'] += 1
        else:                                                     # fan o'qituvchisi
            if user is None:
                user = User(username=_unique_username(phone and re.sub(r'\D', '', phone) or f'{last}-{first}'),
                            first_name=first, last_name=last, phone=phone or '')
            user.role = User.Role.TEACHER
            if phone:
                user.set_password(re.sub(r'\D', '', phone)[-4:])  # boshlang'ich parol: telefonning oxirgi 4 raqami
                user.must_change_password = True
            else:
                user.set_unusable_password()
            user.access_id = user.access_id or next_teacher_id()
            user.save()
            report['teachers'] += 1
        user.branches.add(branch)
    return report


def _link_parent(student, phone_raw, parent_name, report):
    phone = normalize_phone(phone_raw)
    if phone is None:
        report['bad_phone'].append(f'{student.user.get_full_name()}: {phone_raw}')
        return
    digits = re.sub(r'\D', '', phone)
    existing = User.objects.filter(phone_digits=digits).order_by('id')
    parent = existing.filter(role=User.Role.TEACHER).first() or existing.first()   # ustoz ham ota-ona bo'lishi mumkin
    if parent is None:
        u = student.user
        parent = User(username=digits, role=User.Role.PARENT, phone=phone,
                      first_name=parent_name or f"{u.last_name} {u.first_name} {RELATIONS.get('', 'ota-onasi')}")
        parent.set_unusable_password()
        parent.save()
        report['parents_new'] += 1
    if not student.parents.filter(pk=parent.pk).exists():
        student.parents.add(parent)
        report['parents_linked'] += 1


@transaction.atomic
def import_pay_sheets(sheets, branch):
    report = {'groups': 0, 'created': 0, 'existing': 0, 'parents_new': 0, 'parents_linked': 0, 'no_phone': [], 'bad_phone': []}
    for name, data in sheets.items():
        group, created = Group.objects.get_or_create(name=name, branch=branch)
        report['groups'] += created
        for full, parent_name, tel1, tel2, _fee in data['students']:
            last, first = split_name(full)
            student = Student.objects.filter(group=group, user__last_name__iexact=last, user__first_name__iexact=first).first()
            if student is None:
                user = User(username=_unique_username(f'{last}-{first}'), first_name=first, last_name=last, role=User.Role.STUDENT)
                user.set_unusable_password()
                user.save()
                student = Student.objects.create(user=user, group=group, branch=branch)
                report['created'] += 1
            else:
                report['existing'] += 1
            phones = [p for p in (tel1, tel2) if p not in (None, '')]
            if not phones:
                report['no_phone'].append(f'{name}: {full}')
            for p in phones:
                _link_parent(student, p, parent_name, report)
    return report
