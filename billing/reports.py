"""Moliya hisobotlari: ma'lumotlarni tayyorlaydi (ekranda ko'rsatish, Excel va PDF uchun bir xil shakl).

Hisobot: {'key', 'title', 'subtitle', 'headers', 'kinds', 'rows', 'totals', 'summary'}
  kinds  — ustun turi: text | money | date | int | pct
  totals — oxirgi "Jami" qatori (yoki None); summary — [(nom, summa)] qo'shimcha jamlanma.
"""
import re
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from academics.models import Group
from accounts.models import Student

from .models import BillingSettings, Payment, StudentDiscount
from .services import summaries, ZERO

REPORTS = [
    ('qarzdorlar', "Qarzdorlar ro'yxati", "Kim qancha qarz va qaysi qismi muddati o'tgan"),
    ('tushum', 'Tushum (kassa)', "Tanlangan davrdagi to'lovlar: sana, usul, qabul qilgan xodim. Bir kunni tanlasangiz — kunlik kassa"),
    ('sinflar', "Sinflar bo'yicha hisob", "Har bir sinf: hisoblangan, to'langan, qarz va yig'ilish foizi"),
    ('chegirmalar', "Chegirmalar ro'yxati", "Kimda qanday chegirma bor va oyiga qancha tejaydi"),
]
TITLES = {k: t for k, t, _ in REPORTS}


def real_students():
    """Haqiqiy o'quvchilar (sinov hisobining namunaviy o'quvchilari — `sinov_...` — chiqarib tashlanadi)."""
    return Student.objects.exclude(user__username__startswith='sinov_').filter(user__is_active=True)


def _natural(name):
    m = re.match(r'\s*(\d+)', name or '')
    return (int(m.group(1)) if m else 999, name or '')


def _fio(student):
    return f'{student.user.last_name} {student.user.first_name}'.strip() or student.user.username


def _parent(student, with_phone):
    p = next(iter(student.parents.all()), None)
    if not p:
        return ''
    name = p.get_full_name() or p.username
    return f'{name} {p.phone}'.strip() if with_phone and p.phone else name


def _base(key, subtitle=''):
    return {'key': key, 'title': TITLES[key], 'subtitle': subtitle, 'headers': [], 'kinds': [], 'rows': [], 'totals': None, 'summary': []}


def _sum_cols(rows, indexes, label_idx=0):
    totals = [''] * len(rows[0]) if rows else []
    if not rows:
        return None
    totals[label_idx] = 'JAMI'
    for i in indexes:
        totals[i] = sum((r[i] for r in rows), ZERO)
    return totals


def qarzdorlar(group_id=None, with_phone=False, today=None):
    today = today or timezone.localdate()
    qs = real_students().select_related('user', 'group').prefetch_related('parents')
    group = Group.objects.filter(pk=group_id).first() if group_id else None
    if group:
        qs = qs.filter(group=group)
    students = list(qs)
    sums = summaries([s.pk for s in students], today)
    rep = _base('qarzdorlar', f"{today:%d.%m.%Y} holatiga" + (f' · {group.name}' if group else ' · barcha sinflar'))
    rep['headers'] = ["O'quvchi", 'Sinf', 'Ota-ona'] + (['Hisoblangan', "To'langan", 'Qarz', "Muddati o'tgan"])
    rep['kinds'] = ['text', 'text', 'text', 'money', 'money', 'money', 'money']
    rows = []
    for s in students:
        x = sums[s.pk]
        if x['debt'] > 0:
            rows.append([_fio(s), s.group.name if s.group else '—', _parent(s, with_phone), x['charged'], x['paid'], x['debt'], x['overdue']])
    rows.sort(key=lambda r: (-r[5], r[0]))
    rep['rows'], rep['totals'] = rows, _sum_cols(rows, [3, 4, 5, 6])
    return rep


def tushum(date_from=None, date_to=None, today=None):
    today = today or timezone.localdate()
    date_to = date_to or today
    date_from = date_from or date_to.replace(day=1)
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    pays = list(Payment.objects.filter(voided=False, paid_on__range=(date_from, date_to))
                .exclude(student__user__username__startswith='sinov_')
                .select_related('student__user', 'student__group', 'received_by').order_by('paid_on', 'id'))
    period = f'{date_from:%d.%m.%Y}' if date_from == date_to else f'{date_from:%d.%m.%Y} — {date_to:%d.%m.%Y}'
    rep = _base('tushum', period)
    rep['headers'] = ['Sana', 'Chek', "O'quvchi", 'Sinf', 'Usul', 'Summa', 'Qabul qilgan', 'Izoh']
    rep['kinds'] = ['date', 'text', 'text', 'text', 'text', 'money', 'text', 'text']
    rows, by_method = [], defaultdict(lambda: ZERO)
    for p in pays:
        rows.append([p.paid_on, p.receipt_no, _fio(p.student), p.student.group.name if p.student.group else '—', p.get_method_display(),
                     p.amount, (p.received_by.get_full_name() or p.received_by.username) if p.received_by else '—', p.note])
        by_method[p.get_method_display()] += p.amount
    rep['rows'], rep['totals'] = rows, _sum_cols(rows, [5], label_idx=0)
    rep['summary'] = [(f'{k} bo\'yicha', v) for k, v in by_method.items()]
    rep['params'] = {'date_from': date_from, 'date_to': date_to}
    return rep


def sinflar(today=None):
    today = today or timezone.localdate()
    by_group = defaultdict(list)
    for s in real_students().select_related('group'):
        by_group[s.group].append(s.pk)
    sums = summaries([pk for ids in by_group.values() for pk in ids], today)
    rep = _base('sinflar', f'{today:%d.%m.%Y} holatiga')
    rep['headers'] = ['Sinf', "O'quvchilar", 'Hisoblangan', "To'langan", 'Qarz', 'Avans', "Yig'ilish (%)"]
    rep['kinds'] = ['text', 'int', 'money', 'money', 'money', 'money', 'pct']
    rows = []
    for group in sorted(by_group, key=lambda g: _natural(g.name if g else '')):
        ids = by_group[group]
        charged = sum((sums[i]['charged'] for i in ids), ZERO)
        paid = sum((min(sums[i]['paid'], sums[i]['charged']) for i in ids), ZERO)   # avans hisobga olinmaydi
        rows.append([group.name if group else 'Sinfsiz', len(ids), charged, sum((sums[i]['paid'] for i in ids), ZERO),
                     sum((sums[i]['debt'] for i in ids), ZERO), sum((sums[i]['advance'] for i in ids), ZERO),
                     round(100 * paid / charged) if charged else 0])
    rep['rows'] = rows
    if rows:
        totals = _sum_cols(rows, [1, 2, 3, 4, 5])
        charged_all = totals[2]
        totals[6] = round(100 * (totals[3] - totals[5]) / charged_all) if charged_all else 0
        rep['totals'] = totals
    return rep


def chegirmalar(today=None):
    today = today or timezone.localdate()
    cfg = BillingSettings.get()
    rep = _base('chegirmalar', f'{today:%d.%m.%Y} holatiga · oylik narx {cfg.monthly_price:,.0f} so\'m'.replace(',', ' '))
    rep['headers'] = ["O'quvchi", 'Sinf', 'Chegirma', 'Foiz', 'Qaysi oydan', 'Qaysi oygacha', 'Sabab', 'Oyiga tejaydi']
    rep['kinds'] = ['text', 'text', 'text', 'pct', 'text', 'text', 'text', 'money']
    rows = []
    qs = (StudentDiscount.objects.select_related('student__user', 'student__group', 'discount')
          .exclude(student__user__username__startswith='sinov_'))
    for sd in qs:
        saving = (cfg.monthly_price * sd.discount.percent / Decimal(100)).quantize(Decimal(1))
        rows.append([_fio(sd.student), sd.student.group.name if sd.student.group else '—', sd.discount.name, sd.discount.percent,
                     f'{sd.valid_from:%m.%Y}' if sd.valid_from else 'boshidan', f'{sd.valid_to:%m.%Y}' if sd.valid_to else 'muddatsiz',
                     sd.note, saving])
    rows.sort(key=lambda r: (-r[3], r[0]))
    rep['rows'], rep['totals'] = rows, _sum_cols(rows, [7])
    return rep


def build(key, params, with_phone=False):
    if key == 'qarzdorlar':
        gid = params.get('sinf')
        return qarzdorlar(int(gid) if gid and str(gid).isdigit() else None, with_phone)
    if key == 'tushum':
        from datetime import date
        parse = lambda v: date.fromisoformat(v) if v else None
        try:
            return tushum(parse(params.get('dan')), parse(params.get('gacha')))
        except ValueError:
            return tushum()
    if key == 'sinflar':
        return sinflar()
    if key == 'chegirmalar':
        return chegirmalar()
    raise KeyError(key)
