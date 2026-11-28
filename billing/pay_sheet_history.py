"""Maktab to'lov jadvalidagi (sinf varaqlari) oylik badal va sentabr..iyun to'lovlarini tizimga o'tkazish.

Founder qoidalari (2026-11-28, Asosiy maktab):
- Oylik badal 2 000 000. Kamroq yozilgani — shaxsiy chegirma (foizi badaldan hisoblanadi), sentabrdan.
- «Grand» — choraklik imtihonda 1-o'rin: o'sha oylar uchun 100% grant (hozircha noyabr–dekabr).
- «Free» — bepul o'qiydi: 100% chegirma, muddatsiz (panelda olib tashlansa — yana to'laydi).
- «1300000(bol)» — kasal bo'lgan oy: shu summa to'langan va oy hisobi shu summaga tushiriladi.
- «bol-y» / «spravka» — 10+ kun kasal: kelmagan kunlari to'lanmaydi, lekin summa yozilmagan → ko'rib chiqishga.
- «tibbiyot» — Tibbiyot maktabiga o'tgan: shu oydan hisob bekor, o'quvchi Asosiy maktabdan chiqariladi (tarixi qoladi).
- «Yozda» — to'lovni yozda to'lashga ruxsat: qarz qoladi, ko'rib chiqish ro'yxatiga yoziladi.
Qayta ishga tushirsa takrorlanmaydi (shu jadvaldan kiritilgan o'quvchi o'tkazib yuboriladi).
"""
import datetime
import re
from collections import Counter
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from academics.models import Group
from accounts.models import Student
from accounts.pay_sheet_import import find_student
from accounts.student_import import split_name

from .models import BillingSettings, Charge, Discount, Payment, StudentDiscount
from .services import _ensure_charges, first_of_month

BASE = Decimal(2_000_000)
NOTE = "Excel to'lov jadvali"
MONTH_NAMES = ['sentabr', 'oktabr', 'noyabr', 'dekabr', 'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun']
SICK = re.compile(r'^\s*(\d[\d\s]*)\s*\(\s*bol\s*\)\s*$', re.I)


def _months(year):
    return [datetime.date(year + (m < 9), m, 1) for m in (9, 10, 11, 12, 1, 2, 3, 4, 5, 6)]


def _num(v):
    return Decimal(int(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


@transaction.atomic
def import_pay_history(sheets, branch, year=2026, today=None):
    today = today or timezone.localdate()
    now_month = first_of_month(today)
    months = _months(year)
    org = branch.organization
    cfg = BillingSettings.get(org)
    cfg.monthly_price, cfg.billing_start = BASE, months[0]
    cfg.save(update_fields=['monthly_price', 'billing_start'])

    discounts = {}

    def discount(name, percent, description):
        key = (name, percent)
        if key not in discounts:
            discounts[key] = (Discount.objects.filter(organization=org, name=name, percent=percent).first()
                              or Discount.objects.create(organization=org, name=name, percent=percent, description=description))
        return discounts[key]

    report = {'students': 0, 'skipped': 0, 'payments': 0, 'paid_sum': Decimal(0), 'discounts': Counter(), 'grant': 0,
              'free': 0, 'moved': [], 'sick_fixed': [], 'review': [], 'missing': []}
    touched, sick_fix, moved = [], [], []

    for gname, data in sheets.items():
        group = Group.objects.filter(branch=branch, name=gname).first()
        for full, _parent, _t1, _t2, fee, cells in data['students']:
            last, first = split_name(full)
            st = find_student(group, last, first)
            label = f'{gname}: {full}'
            if st is None:
                report['missing'].append(label)
                continue
            if st.fee_payments.filter(note__startswith=NOTE).exists() or st.discounts.filter(note__startswith=NOTE).exists():
                report['skipped'] += 1
                continue
            report['students'] += 1
            touched.append(st)
            texts = [str(c).strip() for c in cells if isinstance(c, str)]

            # 1) oylik badal -> chegirma
            amount = _num(fee)
            if fee == 'Free' or 'Free' in texts:
                StudentDiscount.objects.create(student=st, discount=discount('Free (bepul)', Decimal(100), "Bepul o'qiydi"),
                                               valid_from=months[0], note=f'{NOTE}: Free')
                report['free'] += 1
            elif amount is None:
                report['review'].append(f"{label} — oylik badal yozilmagan (asosiy narx {BASE:,.0f} olindi)".replace(',', ' '))
            elif amount < BASE / 2:
                report['review'].append(f"{label} — oylik badal {amount:,.0f}: xato bo'lsa kerak (asosiy narx olindi)".replace(',', ' '))
            elif amount < BASE:
                pct = ((BASE - amount) * 100 / BASE).quantize(Decimal('0.01')).normalize()
                d = discount(f'Chegirma {pct:f}%', pct, f"Oylik badal {amount:,.0f} so'm".replace(',', ' '))
                StudentDiscount.objects.create(student=st, discount=d, valid_from=months[0], note=f"{NOTE}: badal {amount:,.0f}".replace(',', ' '))
                report['discounts'][d.name] += 1
            elif amount > BASE:
                report['review'].append(f"{label} — oylik badal {amount:,.0f} (asosiydan ko'p)".replace(',', ' '))

            # 2) grant (choraklik imtihon 1-o'rin)
            grant_months = [months[i] for i, c in enumerate(cells) if isinstance(c, str) and c.strip().lower() == 'grand']
            if grant_months:
                StudentDiscount.objects.create(student=st, discount=discount("Grant (chorak imtihoni 1-o'rin)", Decimal(100),
                                                                              "Keyingi chorakkacha bepul"),
                                               valid_from=min(grant_months), valid_to=max(grant_months), note=f'{NOTE}: Grand')
                report['grant'] += 1

            # 3) oylar: to'lovlar va belgilar
            last_paid = months[0]
            for i, c in enumerate(cells):
                month, mname = months[i], MONTH_NAMES[i]
                paid = _num(c)
                text = c.strip() if isinstance(c, str) else ''
                low = text.lower()
                if paid is not None and paid < 100_000:            # masalan 46346 — Excel sana raqami, to'lov emas
                    report['review'].append(f"{label} — {mname}: {paid} — to'lov summasi emas (sana bo'lishi mumkin), kiritilmadi")
                    paid = None
                if text and SICK.match(text):
                    paid = Decimal(re.sub(r'\D', '', SICK.match(text).group(1)))
                    sick_fix.append((st, month, paid, label, mname))
                elif low == 'tibbiyot':
                    moved.append((st, month, label, mname))
                    break
                elif low in ('grand', 'free', ''):
                    pass
                elif low in ('bol-y', 'spravka'):
                    report['review'].append(f"{label} — {mname}: «{text}» (kasal, kelmagan kunlar to'lanmaydi) — oy summasini panelda tuzating")
                elif low == 'yozda':
                    if not any('yozda' in r and label in r for r in report['review']):
                        report['review'].append(f"{label} — «Yozda»: to'lovni yozda to'lashga ruxsat (qarz ko'rinib turadi)")
                else:
                    report['review'].append(f"{label} — {mname}: «{text}» — tushunarsiz, kiritilmadi")
                if paid:
                    # o'tgan/joriy oy — shu oy 1-sanasi; kelgusi oylar (oldindan to'lov) — oxirgi to'lov oyi
                    paid_on = month if month <= now_month else last_paid
                    last_paid = paid_on
                    Payment.objects.create(student=st, amount=paid, paid_on=paid_on, note=f'{NOTE}: {mname}')
                    report['payments'] += 1
                    report['paid_sum'] += paid

    _ensure_charges(sorted(s.pk for s in touched), today)   # chegirmalar bilan sentabr..joriy oy (keshsiz: har doim to'liq)

    for st, month, paid, label, mname in sick_fix:
        ch = Charge.objects.filter(student=st, month=month).first()
        if ch and ch.amount != paid:
            ch.amount, ch.discount_label = paid, 'Kasal (bol-y): kelmagan kunlar to\'lanmaydi'
            ch.save(update_fields=['amount', 'discount_label'])
        report['sick_fixed'].append(f'{label} — {mname}: {paid:,.0f}'.replace(',', ' '))

    for st, month, label, mname in moved:
        st.charges.filter(month__gte=month, cancelled=False).update(cancelled=True, cancel_reason="Tibbiyot maktabiga o'tdi")
        st.leave()
        Student.objects.filter(pk=st.pk).update(left_at=month)
        report['moved'].append(f'{label} — {mname}dan')
    return report
