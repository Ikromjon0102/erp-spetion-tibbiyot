"""Oylik: kimga qancha (qoida), qachon to'lanadi (avans va yakuniy hisob), nima qoldi.

Jadval tashkilot bo'yicha: avans — har oyning `advance_day` kuni (odatda 15), oylikning `advance_percent` foizi (odatda 50%);
yakuniy hisob — oyning oxirgi kuni, qolgan hamma summa. Avans summasi minggacha yaxlitlanadi.
"""
from calendar import monthrange
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q

from .models import Payslip, SalaryRule

ZERO = Decimal(0)


def month_end(month):
    return month.replace(day=monthrange(month.year, month.month)[1])


def advance_date(org, month):
    return month.replace(day=min(getattr(org, 'advance_day', 15) or 15, 28))


def advance_plan(slip, percent):
    """Avans rejasi: jami oylikning foizi, minggacha yaxlitlangan."""
    v = Decimal(slip.total) * Decimal(percent) / 100
    return (v / 1000).quantize(Decimal(1)) * 1000


def slip_status(slip, percent):
    """Avans va yakuniy hisob bo'yicha holat (sahifadagi ustunlar uchun)."""
    plan = advance_plan(slip, percent)
    covered = min(slip.paid, plan)            # avans sifatida yozilmagan bo'lsa ham, to'langan pul avansni yopadi
    return {'adv_plan': plan, 'adv_paid': covered, 'adv_due': plan - covered, 'remaining': max(slip.remaining, ZERO)}


def _days_word(target, today):
    d = (target - today).days
    if d == 0:
        return 'bugun', 'today'
    if d == 1:
        return 'ertaga', 'soon'
    if d > 0:
        return f'{d} kun qoldi', 'soon' if d <= 3 else 'later'
    return f"{-d} kun o'tdi", 'late'


def schedule(org, month, slips, today):
    """Oy uchun ikki muddat: avans va yakuniy hisob (sana, qancha kun qoldi, reja, to'langan, qoldiq)."""
    pct = getattr(org, 'advance_percent', 50)
    rows = [slip_status(s, pct) for s in slips]
    adv_day, end_day = advance_date(org, month), month_end(month)
    adv = {'date': adv_day, 'percent': pct, 'plan': sum((r['adv_plan'] for r in rows), ZERO),
           'paid': sum((r['adv_paid'] for r in rows), ZERO),
           'people': sum(1 for r in rows if r['adv_due'] > 0)}
    adv['due'] = max(adv['plan'] - adv['paid'], ZERO)
    fin = {'date': end_day, 'due': sum((r['remaining'] for r in rows), ZERO), 'people': sum(1 for r in rows if r['remaining'] > 0)}
    for item in (adv, fin):
        item['when'], item['state'] = _days_word(item['date'], today)
    return {'advance': adv, 'final': fin}


# ---- qoidalar -----------------------------------------------------------------------------------------------------------

def current_rules(employee, branches):
    """[(filial, amaldagi qoida yoki None)] — har filial uchun."""
    from django.utils import timezone
    today = timezone.localdate().replace(day=1)
    return [(b, SalaryRule.current(employee, b, today)) for b in branches]


def set_rule(employee, branch, kind, amount, percent, effective_from, user):
    """Yangi oylik qoidasi. Amaldagisi bilan bir xil bo'lsa — hech narsa qilinmaydi (None). Shu oydan kuchga kiradigan qoida allaqachon
    bo'lsa, u yangilanadi (bir oyda ikki qoida bo'lmasin)."""
    effective_from = effective_from.replace(day=1)
    amount = Decimal(amount or 0) if kind == SalaryRule.Kind.FIXED else ZERO
    percent = Decimal(percent if percent is not None else 0) if kind == SalaryRule.Kind.PERCENT else Decimal('40')
    cur = SalaryRule.current(employee, branch, effective_from)
    if cur and cur.kind == kind and cur.amount == amount and (kind == SalaryRule.Kind.FIXED or cur.percent == percent):
        return None
    same = SalaryRule.objects.filter(employee=employee, branch=branch, effective_from=effective_from).first()
    if same:
        same.kind, same.amount, same.percent = kind, amount, percent
        same.save(update_fields=['kind', 'amount', 'percent'])
        return same
    return SalaryRule.objects.create(employee=employee, branch=branch, effective_from=effective_from, kind=kind, amount=amount,
                                     percent=percent, created_by=user)


def employees_qs(user):
    """Oylik oladiganlar: ustozlar va xodimlar (founder va texnik admin quyi xodimlarga ko'rinmaydi), faqat ruxsatli filiallardan."""
    from accounts.models import User
    from org.scope import branch_ids
    from panel.access import is_owner
    qs = User.objects.filter(role__in=[User.Role.TEACHER, User.Role.STAFF], is_active=True, is_demo=False)
    if not is_owner(user):
        qs = qs.exclude(Q(is_superuser=True) | Q(staff_profile__position__is_owner=True))
    ids = branch_ids(user)
    if ids is not None:
        qs = qs.filter(branches__in=ids).distinct()
    return qs


# ---- eslatma (bosh sahifa) -----------------------------------------------------------------------------------------------

def reminders(user, today):
    """Avans va yakuniy hisob yaqinlashganda (yoki o'tib ketganda) to'lanmagan summa haqida eslatma — tashkilot bo'yicha.
    Avans: muddatdan 3 kun oldin boshlab; yakuniy: oyning oxirgi 3 kuni va keyingi oyning 1–10 kunlari (o'tgan oy qoldig'i)."""
    from org.scope import branches_for
    from . import payroll
    out = []
    month = today.replace(day=1)
    prev = (month - timedelta(days=1)).replace(day=1)
    branches = list(branches_for(user).select_related('organization'))
    by_org = {}
    for b in branches:
        by_org.setdefault(b.organization, []).append(b)
    for org, obranches in by_org.items():
        checks = []
        adv_day = advance_date(org, month)
        if (adv_day - today).days <= 3:
            checks.append(('advance', month))
        if (month_end(month) - today).days <= 3:
            checks.append(('final', month))
        if today.day <= 10:
            checks.append(('final', prev))
        for kind, m in checks:
            if m == month:
                for b in obranches:
                    if SalaryRule.objects.filter(branch=b, effective_from__lte=month_end(m)).exists() and \
                            not Payslip.objects.filter(branch=b, month=m).exists():
                        payroll.ensure_payslips(b, m)
            slips = list(Payslip.objects.filter(branch__in=obranches, month=m).prefetch_related('payments'))
            if not slips:
                continue
            sch = schedule(org, m, slips, today)[kind]
            if sch['due'] > 0:
                out.append({'org': org, 'kind': kind, 'month': m, **sch,
                            'branch': obranches[0] if len(obranches) == 1 else None})
    return out
