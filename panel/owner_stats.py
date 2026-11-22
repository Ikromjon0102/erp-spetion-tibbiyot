"""Maktab egasi (founder) sahifasi uchun raqamli ko'rsatkichlar.

Qoidalar (founder bilan kelishilgan, 2026-11-22):
- **Foyda = kassaga tushgan tushum − xarajatlar** (ustoz/xodimlar oyligi ham xarajatga kiradi: oylik to'lovi xarajat sifatida yoziladi).
- **Kutilayotgan tushum** — shu oy uchun hisoblangan summa (narx − chegirma). Grantdagi o'quvchi 100% chegirma, ya'ni 0 so'm.
- Hammasi filial bo'yicha alohida (o'quv markazning har filiali o'z qatorida), tashkilot bo'yicha jamlanadi.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth

from billing.models import Charge, Payment
from billing.services import academic_months, academic_year_start, ensure_charges, first_of_month
from finance.models import Expense, Payslip
from org.models import default_branch
from org.scope import branches_for, scope_by_branch
from .views_core import real_students

ZERO = Decimal(0)
UZ_MONTHS = ['', 'Yan', 'Fev', 'Mar', 'Apr', 'May', 'Iyn', 'Iyl', 'Avg', 'Sen', 'Okt', 'Noy', 'Dek']


def parse_month(value, today):
    """'2026-11' -> date(2026, 11, 1); noto'g'ri yoki kelajakdagi qiymat bo'lsa joriy oy."""
    try:
        y, m = (int(x) for x in str(value).split('-'))
        d = date(y, m, 1)
    except (ValueError, TypeError):
        return first_of_month(today)
    return d if d <= first_of_month(today) else first_of_month(today)


def shift_month(d, delta):
    idx = d.year * 12 + d.month - 1 + delta
    return date(idx // 12, idx % 12 + 1, 1)


def _tier_label(percent, amount):
    if percent >= 100 or amount == 0:
        return 'Grant (100% chegirma)'
    if percent > 0:
        return f"Chegirma −{percent.normalize():f}%"
    return "To'liq narx"


def build_report(user, month, today):
    month = first_of_month(month)
    year_start = academic_year_start(month)
    months = [m for m in academic_months(year_start) if m <= first_of_month(today)]
    ytd_from = date(year_start, 9, 1)
    default_id = default_branch().pk
    bkey = lambda f: Coalesce(f, Value(default_id))      # filialsiz o'quvchi — asosiy filialda

    students = real_students(user)
    student_ids = list(students.values_list('pk', flat=True))
    ensure_charges(student_ids, today)       # 10 daqiqa eslab qolinadi (billing.services)
    sub = students.values('pk')              # keyingi so'rovlarda minglab id o'rniga ichki so'rov       # yetishmayotgan oylik hisoblar (narx bor bo'lsa) yoziladi; qayta chaqirish xavfsiz

    branches = list(branches_for(user).select_related('organization').order_by('organization__name', 'name'))   # tanlangan ish maydoni bo'yicha
    ids = {b.pk for b in branches}

    def per_branch(qs, key, **agg):
        out = defaultdict(lambda: defaultdict(Decimal))
        for row in qs.annotate(_b=bkey(key)).values('_b').annotate(**agg):
            for k, v in row.items():
                if k != '_b':
                    out[row['_b']][k] = v or ZERO
        return out

    pay = Payment.objects.filter(voided=False, student__in=sub)
    exp = scope_by_branch(Expense.objects.all(), user)
    n_students = per_branch(students, 'branch_id', n=Count('pk'))
    charges_m = Charge.objects.filter(month=month, cancelled=False, student__in=sub)
    expected = per_branch(charges_m, 'student__branch_id', s=Sum('amount'))
    income_m = per_branch(pay.filter(paid_on__year=month.year, paid_on__month=month.month), 'student__branch_id', s=Sum('amount'))
    income_y = per_branch(pay.filter(paid_on__gte=ytd_from, paid_on__lte=today), 'student__branch_id', s=Sum('amount'))
    exp_m = per_branch(exp.filter(date__year=month.year, date__month=month.month), 'branch_id', s=Sum('amount'))
    exp_y = per_branch(exp.filter(date__gte=ytd_from, date__lte=today), 'branch_id', s=Sum('amount'))
    sal_m = per_branch(exp.filter(date__year=month.year, date__month=month.month, salary_payment__isnull=False), 'branch_id', s=Sum('amount'))

    # qarz: jami hisoblangan − jami to'langan (o'quvchi bo'yicha, manfiysi — avans — hisobga olinmaydi)
    charged = dict(Charge.objects.filter(cancelled=False, month__lte=first_of_month(today), student__in=sub)
                   .values_list('student_id').annotate(s=Sum('amount')))
    paid = dict(pay.values_list('student_id').annotate(s=Sum('amount')))
    branch_of = dict(students.annotate(_b=bkey('branch_id')).values_list('pk', '_b'))
    debt = defaultdict(Decimal)
    for sid, total in charged.items():
        left = (total or ZERO) - (paid.get(sid) or ZERO)
        if left > 0:
            debt[branch_of.get(sid)] += left

    # to'lanmagan oyliklar (shu oy hisoblangan, hali to'lanmagan qismi)
    unpaid = defaultdict(Decimal)
    for ps in scope_by_branch(Payslip.objects.filter(month=month), user).prefetch_related('payments'):
        unpaid[ps.branch_id] += max(ps.remaining, ZERO)

    # chegirma bo'yicha taqsimot (kutilayotgan tushum tarkibi)
    tiers = defaultdict(lambda: defaultdict(lambda: [0, ZERO]))        # branch -> (percent, price) -> [soni, jami]
    for row in (charges_m.annotate(_b=bkey('student__branch_id')).values('_b', 'discount_percent', 'amount').annotate(n=Count('pk'))):
        t = tiers[row['_b']][(row['discount_percent'], row['amount'])]
        t[0] += row['n']
        t[1] += row['amount'] * row['n']
    charged_n = defaultdict(int)
    for bid, byp in tiers.items():
        charged_n[bid] = sum(v[0] for v in byp.values())

    def row_for(b):
        i = b.pk
        inc, ex = income_m[i]['s'], exp_m[i]['s']
        return {
            'branch': b, 'students': int(n_students[i]['n']), 'no_price': max(int(n_students[i]['n']) - charged_n[i], 0),
            'expected': expected[i]['s'], 'income_m': inc, 'expense_m': ex, 'salary_m': sal_m[i]['s'], 'profit_m': inc - ex,
            'income_y': income_y[i]['s'], 'expense_y': exp_y[i]['s'], 'profit_y': income_y[i]['s'] - exp_y[i]['s'],
            'debt': debt[i], 'unpaid_payroll': unpaid[i],
            'pct': round(100 * inc / expected[i]['s']) if expected[i]['s'] else None,
            'forecast': expected[i]['s'] - ex - unpaid[i], 'left': max(expected[i]['s'] - inc, ZERO),
        }

    def merge(rows):
        keys = ['students', 'no_price', 'expected', 'income_m', 'expense_m', 'salary_m', 'profit_m', 'income_y', 'expense_y', 'profit_y',
                'debt', 'unpaid_payroll', 'forecast', 'left']
        tot = {k: sum((r[k] for r in rows), ZERO) for k in keys}
        tot['pct'] = round(100 * tot['income_m'] / tot['expected']) if tot['expected'] else None
        return tot

    orgs, seen = [], {}
    for b in branches:
        r = row_for(b)
        if b.organization_id not in seen:
            seen[b.organization_id] = {'org': b.organization, 'rows': [], 'tiers': defaultdict(lambda: [0, ZERO])}
            orgs.append(seen[b.organization_id])
        seen[b.organization_id]['rows'].append(r)
        for (pct, price), (n, total) in tiers[b.pk].items():
            t = seen[b.organization_id]['tiers'][(pct, price)]
            t[0] += n
            t[1] += total
    for o in orgs:
        o['total'] = merge(o['rows'])
        o['multi'] = len(o['rows']) > 1
        o['tier_rows'] = [{'label': _tier_label(pct, price), 'percent': pct, 'price': price, 'n': n, 'sum': total}
                          for (pct, price), (n, total) in sorted(o['tiers'].items(), key=lambda kv: (kv[0][0], -kv[0][1]))]
        del o['tiers']
    grand = merge([o['total'] for o in orgs]) if orgs else merge([])

    # oylar bo'yicha qator: tushum, xarajat, foyda, kutilgan (butun tashkilotlar, tanlangan filtr bo'yicha)
    def by_month(qs, field):
        qs = qs.filter(**{f'{field}__gte': ytd_from})
        return {r['m'].date() if hasattr(r['m'], 'date') else r['m']: r['s'] or ZERO
                for r in qs.annotate(m=TruncMonth(field)).values('m').annotate(s=Sum('amount')).order_by('m')}
    sel_students = students.annotate(_b=bkey('branch_id')).filter(_b__in=ids).values('pk')
    inc_series = by_month(Payment.objects.filter(voided=False, student__in=sel_students), 'paid_on')
    exp_series = by_month(Expense.objects.filter(branch_id__in=ids), 'date')
    exp_plan = {}
    plan_rows = Charge.objects.filter(cancelled=False, student__in=sel_students, month__gte=ytd_from).values('month').annotate(s=Sum('amount'))
    for r in plan_rows:
        exp_plan[r['month']] = r['s'] or ZERO
    series = [{'label': UZ_MONTHS[m.month], 'month': m.isoformat(), 'income': int(inc_series.get(m, ZERO)), 'expense': int(exp_series.get(m, ZERO)),
               'profit': int(inc_series.get(m, ZERO) - exp_series.get(m, ZERO)), 'expected': int(exp_plan.get(m, ZERO)), 'current': m == month}
              for m in months]
    return {'month': month, 'orgs': orgs, 'grand': grand, 'series': series, 'ytd_from': ytd_from,
            'prev': shift_month(month, -1), 'next': shift_month(month, 1) if shift_month(month, 1) <= first_of_month(today) else None}
