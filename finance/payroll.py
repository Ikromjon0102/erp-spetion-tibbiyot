"""Oylik hisoblash.

- Qat'iy oylik: qoidadagi summa.
- Foiz: xodimning (ustozning) o'quvchilari shu oy qilgan haqiqiy to'lovlaridan foiz. Bekor qilingan to'lov hisobga olinmaydi.
  Guruhda bir nechta ustoz dars bersa, o'quvchining to'lovi ustozlar o'rtasida teng bo'linadi (markazda odatda bitta ustoz).
"""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Count

from academics.models import Teaching
from billing.models import Payment

from .models import SALARY_CATEGORY, Expense, ExpenseCategory, Payslip, SalaryPayment, SalaryRule

ZERO = Decimal(0)


def percent_base(employee, branch, month):
    """(ustozga tegishli to'lovlar yig'indisi, o'quvchi to'lovlari soni) — shu filial va oy bo'yicha."""
    month = month.replace(day=1)
    group_ids = set(Teaching.objects.filter(teacher=employee, group__branch=branch).values_list('group_id', flat=True))
    if not group_ids:
        return ZERO, 0
    teachers_per_group = {row['group_id']: row['n'] for row in
                          Teaching.objects.filter(group_id__in=group_ids, teacher__isnull=False).values('group_id')
                          .annotate(n=Count('teacher', distinct=True))}
    payments = Payment.objects.filter(voided=False, paid_on__year=month.year, paid_on__month=month.month,
                                      student__group_id__in=group_ids, student__branch=branch).select_related('student')
    total, count = ZERO, 0
    for p in payments:
        gid = p.student.group_id
        total += Decimal(p.amount) / max(teachers_per_group.get(gid, 1), 1)
        count += 1
    return total, count


def calculate(employee, branch, month):
    """(qoida, hisoblangan summa, izoh) yoki qoida bo'lmasa (None, 0, '')."""
    rule = SalaryRule.current(employee, branch, month)
    if rule is None:
        return None, ZERO, ''
    if rule.kind == SalaryRule.Kind.FIXED:
        return rule, Decimal(rule.amount), "Qat'iy oylik"
    base, count = percent_base(employee, branch, month)
    amount = (base * rule.percent / Decimal(100)).quantize(Decimal(1), ROUND_HALF_UP)
    note = f"To'lovlar {base:,.0f} so'm ({count} ta) × {rule.percent:g}%".replace(',', ' ')
    return rule, amount, note


@transaction.atomic
def ensure_payslips(branch, month):
    """Filialdagi qoidasi bor xodimlar uchun oy oyligini yaratadi yoki hisoblangan summani yangilaydi
    (mukofot, ushlanma va to'lovlarga tegmaydi). Yaratilgan/yangilangan sonini qaytaradi."""
    month = month.replace(day=1)
    employees = {r.employee for r in SalaryRule.objects.filter(branch=branch).select_related('employee')}
    done = 0
    for employee in sorted(employees, key=lambda e: (e.last_name, e.first_name)):
        rule, amount, note = calculate(employee, branch, month)
        if rule is None:
            continue
        slip, created = Payslip.objects.get_or_create(employee=employee, branch=branch, month=month,
                                                      defaults={'kind': rule.kind, 'base_amount': amount, 'calc_note': note})
        if not created and (slip.kind, slip.base_amount, slip.calc_note) != (rule.kind, amount, note):
            slip.kind, slip.base_amount, slip.calc_note = rule.kind, amount, note
            slip.save(update_fields=['kind', 'base_amount', 'calc_note'])
        done += 1
    return done


def salary_category():
    return ExpenseCategory.objects.get_or_create(name=SALARY_CATEGORY, defaults={'order': 8, 'is_system': True})[0]


@transaction.atomic
def pay(payslip, amount, kind, paid_on, method, user):
    """Oylikdan to'lov yozadi va avtomatik «Maosh» xarajatini yaratadi."""
    name = payslip.employee.get_full_name() or payslip.employee.username
    label = 'Avans' if kind == SalaryPayment.Kind.ADVANCE else 'Oylik'
    expense = Expense.objects.create(branch=payslip.branch, category=salary_category(), date=paid_on, amount=amount, payee=name,
                                     method=method, created_by=user, note=f'{label} · {payslip.month:%m.%Y}')
    return SalaryPayment.objects.create(payslip=payslip, amount=amount, kind=kind, paid_on=paid_on, method=method,
                                        expense=expense, created_by=user)


@transaction.atomic
def delete_payment(payment):
    """To'lovni bekor qiladi: bog'langan «Maosh» xarajati ham o'chadi."""
    expense = payment.expense
    payment.delete()
    if expense is not None:
        expense.delete()
