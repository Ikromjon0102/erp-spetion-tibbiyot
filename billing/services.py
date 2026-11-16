"""Moliya hisob-kitobi.

Qoidalar:
- O'quv yili sentabrdan iyungacha (10 oy). Har oy uchun o'quvchiga hisob (Charge) yoziladi: asosiy narx − chegirma.
- Chegirma standart holatda yo'q; o'quvchiga qo'lda biriktiriladi. Bir necha bo'lsa, eng kattasi qo'llanadi.
- To'lovlar eng eski oydan boshlab taqsimlanadi (qisman to'lov mumkin). Ortiqcha summa (avans) keyingi oylar hisobiga o'tadi.
- Muddati o'tgan qarz: to'lov muddati (oyning X-kuni) o'tgan, lekin to'lanmagan summa. Jarima yo'q.
"""
from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Sum
from django.utils import timezone

from .models import BillingSettings, Charge, Payment, StudentDiscount

ZERO = Decimal(0)
CHUNK = 400   # SQLite parametrlar cheklovidan qochish uchun


def first_of_month(d):
    return d.replace(day=1)


def academic_year_start(d):
    return d.year if d.month >= 9 else d.year - 1


def academic_months(year_start):
    """Sentabr–iyun: [date(Y,9,1), ..., date(Y+1,6,1)]"""
    return [date(year_start, m, 1) for m in range(9, 13)] + [date(year_start + 1, m, 1) for m in range(1, 7)]


def billed_months(today=None, cfg=None):
    """Joriy o'quv yilida hisob yoziladigan oylar: hisob boshlanish oyidan bugungi oygacha."""
    today = today or timezone.localdate()
    cfg = cfg or BillingSettings.get()
    start = cfg.billing_start or first_of_month(today)
    return [m for m in academic_months(academic_year_start(today)) if start <= m <= first_of_month(today)]


def due_date(month, cfg=None):
    cfg = cfg or BillingSettings.get()
    return month.replace(day=min(cfg.due_day, 28))


def pct_text(value):
    return f'{Decimal(value).normalize():f}'


def best_discount(assignments, month):
    best = None
    for a in assignments:
        if a.discount.is_active and a.covers(month) and (best is None or a.discount.percent > best.discount.percent):
            best = a
    return best


def price_after(base, percent):
    return (Decimal(base) * (Decimal(100) - Decimal(percent)) / Decimal(100)).quantize(Decimal(1), ROUND_HALF_UP)


def _label(assignment):
    return f'{assignment.discount.name} −{pct_text(assignment.discount.percent)}%' if assignment else ''


def _chunks(items, size=CHUNK):
    items = list(items)
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _assignments(student_ids):
    result = defaultdict(list)
    for chunk in _chunks(student_ids):
        for a in StudentDiscount.objects.filter(student_id__in=chunk).select_related('discount'):
            result[a.student_id].append(a)
    return result


def ensure_charges(student_ids, today=None):
    """Yetishmayotgan oylik hisoblarni yaratadi (narx belgilangan bo'lsa). Qayta chaqirish xavfsiz."""
    cfg = BillingSettings.get()
    if cfg.monthly_price <= 0:
        return 0
    months = billed_months(today, cfg)
    ids = sorted({int(i) for i in student_ids})
    if not months or not ids:
        return 0
    existing = set()
    for chunk in _chunks(ids):
        existing |= set(Charge.objects.filter(student_id__in=chunk, month__in=months).values_list('student_id', 'month'))
    missing = [(sid, m) for sid in ids for m in months if (sid, m) not in existing]
    if not missing:
        return 0
    assignments = _assignments({sid for sid, _ in missing})
    created = []
    for sid, m in missing:
        a = best_discount(assignments[sid], m)
        pct = a.discount.percent if a else ZERO
        created.append(Charge(student_id=sid, month=m, base_price=cfg.monthly_price, discount_percent=pct,
                              discount_label=_label(a), amount=price_after(cfg.monthly_price, pct)))
    Charge.objects.bulk_create(created, ignore_conflicts=True)
    return len(created)


def recalc_charges(student, from_month=None):
    """Chegirma biriktirilganda/o'zgarganda: berilgan oydan boshlab hisoblarni qayta yozadi (narx — hisoblangan paytdagi asosiy narx)."""
    assignments = _assignments([student.pk])[student.pk]
    qs = student.charges.filter(cancelled=False)
    if from_month:
        qs = qs.filter(month__gte=from_month)
    changed = 0
    for charge in qs:
        a = best_discount(assignments, charge.month)
        pct = a.discount.percent if a else ZERO
        amount = price_after(charge.base_price, pct)
        if (charge.discount_percent, charge.amount, charge.discount_label) != (pct, amount, _label(a)):
            charge.discount_percent, charge.amount, charge.discount_label = pct, amount, _label(a)
            charge.save(update_fields=['discount_percent', 'amount', 'discount_label'])
            changed += 1
    return changed


def recalc_current_month(today=None):
    """Narx o'zgargandan keyin joriy oy hisoblarini yangi narx bilan qayta yozadi (o'tgan oylar o'zgarmaydi)."""
    today = today or timezone.localdate()
    cfg = BillingSettings.get()
    month = first_of_month(today)
    count = 0
    for charge in Charge.objects.filter(month=month, cancelled=False).select_related('student'):
        pct = charge.discount_percent
        amount = price_after(cfg.monthly_price, pct)
        if (charge.base_price, charge.amount) != (cfg.monthly_price, amount):
            charge.base_price, charge.amount = cfg.monthly_price, amount
            charge.save(update_fields=['base_price', 'amount'])
            count += 1
    return count


def account(student, today=None):
    """Bitta o'quvchining to'liq hisobi: oylar bo'yicha taqsimot, qarz, avans, to'lovlar tarixi."""
    today = today or timezone.localdate()
    cfg = BillingSettings.get()
    ensure_charges([student.pk], today)
    charges = list(student.charges.filter(cancelled=False).order_by('month'))
    payments = list(student.fee_payments.select_related('received_by').order_by('-paid_on', '-id'))
    paid_total = sum((p.amount for p in payments if not p.voided), ZERO)
    remaining, rows = paid_total, []
    for c in charges:
        applied = min(remaining, c.amount)
        remaining -= applied
        debt = c.amount - applied
        due = due_date(c.month, cfg)
        rows.append({'charge': c, 'paid': applied, 'debt': debt, 'due': due,
                     'status': 'paid' if debt <= 0 else 'partial' if applied > 0 else 'unpaid',
                     'overdue': debt > 0 and today > due,
                     'pct': min(100, round(100 * applied / c.amount)) if c.amount else 100})
    return {
        'rows': rows, 'payments': payments, 'charged': sum((c.amount for c in charges), ZERO), 'paid': paid_total,
        'debt': sum((r['debt'] for r in rows), ZERO), 'advance': remaining,
        'overdue': sum((r['debt'] for r in rows if r['overdue']), ZERO),
        'discounts': list(student.discounts.select_related('discount', 'assigned_by')),
        'price': cfg.monthly_price, 'pay_info': cfg.pay_info.strip(),
    }


def summaries(student_ids, today=None):
    """Ko'p o'quvchi uchun qisqa hisob: {id: {charged, paid, debt, advance, overdue}} (ro'yxatlar va hisobotlar uchun)."""
    today = today or timezone.localdate()
    cfg = BillingSettings.get()
    ids = sorted({int(i) for i in student_ids})
    ensure_charges(ids, today)
    charged, overdue_charged, paid = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for chunk in _chunks(ids):
        for sid, month, amount in Charge.objects.filter(student_id__in=chunk, cancelled=False).values_list('student_id', 'month', 'amount'):
            charged[sid] += amount
            if today > due_date(month, cfg):
                overdue_charged[sid] += amount
        for row in Payment.objects.filter(student_id__in=chunk, voided=False).values('student_id').annotate(t=Sum('amount')):
            paid[row['student_id']] = row['t']
    result = {}
    for sid in ids:
        debt = max(charged[sid] - paid[sid], ZERO)
        result[sid] = {'charged': charged[sid], 'paid': paid[sid], 'debt': debt, 'advance': max(paid[sid] - charged[sid], ZERO),
                       'overdue': min(max(overdue_charged[sid] - paid[sid], ZERO), debt)}
    return result


def add_test_payment(student, month, amount, paid):
    """Sinov/demo ma'lumot: bir oy uchun hisob va (paid > 0 bo'lsa) to'lov yozadi. Haqiqiy ishda ishlatilmaydi."""
    month = first_of_month(month)
    Charge.objects.get_or_create(student=student, month=month, defaults={'base_price': amount, 'amount': amount})
    if paid:
        if not Payment.objects.filter(student=student, paid_on__year=month.year, paid_on__month=month.month, note='Sinov').exists():
            Payment.objects.create(student=student, amount=paid, paid_on=month.replace(day=min(5, 28)), note='Sinov')
