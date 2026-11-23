"""Ustoz/xodim oyligi panelda: qo'shish formasidagi «Oylik» bloki, ustoz/xodim kartasidagi «Oylik» kartasi va bitta odamning oylik sahifasi.

Ruxsat: ko'rish — `payroll.view`, kiritish/o'zgartirish — `payroll.manage` (founder va hisobchi). Direktor ustoz qo'shsa-yu, payroll ruxsati
bo'lmasa, oylik bloki formada chiqmaydi — oylikni keyin hisobchi kiritadi.
Oylik o'zgarsa yangi qoida yoziladi (qaysi oydan), eski oylar hisobi o'zgarmaydi."""
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from finance import salary
from finance.models import Payslip, SalaryRule
from org.models import Branch
from org.scope import branches_for

from . import audit
from .access import panel_required, perms_of

KINDS = [('', 'Keyin kiritiladi'), (SalaryRule.Kind.FIXED, "Qat'iy oylik"), (SalaryRule.Kind.PERCENT, "Foiz (o'quvchilar to'lovidan)")]


def _money_field(**kw):
    from .views_finance import MoneyField
    return MoneyField(**kw)


def add_fields(form, user, required=False):
    """Formaga oylik maydonlarini qo'shadi (faqat `payroll.manage` bo'lsa). True — qo'shildi."""
    if 'payroll.manage' not in perms_of(user):
        return False
    form.fields['salary_kind'] = forms.ChoiceField(label="Oylik turi", required=required, choices=KINDS[1:] if required else KINDS)
    form.fields['salary_amount'] = _money_field(label="Oylik (so'm)", min_value=0, required=False)
    form.fields['salary_percent'] = forms.DecimalField(label='Foiz (%)', min_value=0, max_value=100, decimal_places=2, required=False,
                                                       help_text="O'quvchilari shu oy qilgan to'lovdan")
    return True


def check(form):
    """Oylik maydonlarini tekshiradi; xato bo'lsa formaga qo'shadi. (turi, summa, foiz) yoki None."""
    if 'salary_kind' not in form.fields or not form.is_valid():
        return None
    d = form.cleaned_data
    kind = d.get('salary_kind') or ''
    if kind == SalaryRule.Kind.FIXED and not d.get('salary_amount'):
        form.add_error('salary_amount', "Oylik summasini kiriting")
    elif kind == SalaryRule.Kind.PERCENT and d.get('salary_percent') in (None, ''):
        form.add_error('salary_percent', 'Foizni kiriting')
    return (kind, d.get('salary_amount') or 0, d.get('salary_percent')) if kind else None


def apply(request, employee, branch_ids, data, effective_from=None):
    """Oylik qoidasini yozadi: foiz — barcha belgilangan filiallarga, qat'iy oylik — birinchi filialga (bitta oylik ikki marta
    hisoblanmasin; boshqa filial uchun keyin kartadan qo'shiladi)."""
    if not data or not branch_ids:
        return []
    kind, amount, percent = data
    branches = list(Branch.objects.filter(pk__in=branch_ids).select_related('organization').order_by('organization__name', 'name'))
    if kind == SalaryRule.Kind.FIXED:
        branches = branches[:1]
    start = (effective_from or timezone.localdate()).replace(day=1)
    made = []
    for b in branches:
        r = salary.set_rule(employee, b, kind, amount, percent, start, request.user)
        if r:
            made.append(r)
            audit.log(request, "Oylik belgiladi", r, label=f'{employee.get_full_name()} — {r.describe()}',
                      details={'filial': str(b), 'qaysi oydan': f'{start:%m.%Y}'}, target_type='payroll')
    return made


def card(viewer, employee):
    """Ustoz/xodim kartasidagi «Oylik» bloki uchun ma'lumot; ruxsat bo'lmasa None."""
    granted = perms_of(viewer)
    if 'payroll.view' not in granted:
        return None
    mine = set(branches_for(viewer).values_list('pk', flat=True))
    branches = [b for b in employee.branches.select_related('organization').order_by('organization__name', 'name') if b.pk in mine]
    month = timezone.localdate().replace(day=1)
    slips = {s.branch_id: s for s in Payslip.objects.filter(employee=employee, month=month, branch__in=branches).prefetch_related('payments')}
    rows = []
    for b, rule in salary.current_rules(employee, branches):
        s = slips.get(b.pk)
        rows.append({'branch': b, 'rule': rule, 'slip': s, 'st': salary.slip_status(s, b.organization.advance_percent) if s else None,
                     'adv_date': salary.advance_date(b.organization, month), 'end_date': salary.month_end(month)})
    return {'rows': rows, 'can_manage': 'payroll.manage' in granted, 'employee': employee, 'multi': len(rows) > 1}


class SalaryForm(forms.Form):
    branch = forms.ModelChoiceField(label='Filial', queryset=Branch.objects.none(), empty_label=None)
    effective_from = forms.DateField(label='Qaysi oydan', widget=forms.DateInput(attrs={'type': 'month'}, format='%Y-%m'),
                                     input_formats=['%Y-%m', '%Y-%m-%d'],
                                     help_text="Shu oydan boshlab amal qiladi; oldingi oylar hisobi o'zgarmaydi")

    def __init__(self, *args, branches=(), user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['branch'].queryset = Branch.objects.filter(pk__in=[b.pk for b in branches]).select_related('organization')
        self.fields['branch'].label_from_instance = lambda b: f'{b.organization.label} · {b.name}'
        add_fields(self, user, required=True)


def _next(request, default):
    url = request.POST.get('next') or request.GET.get('next') or ''
    return url if url and url_has_allowed_host_and_scheme(url, {request.get_host()}) else default


@panel_required('payroll.view')
def employee_salary(request, pk):
    """Bitta odamning oyligi: amaldagi qoida (filial bo'yicha), tarix, shu oy avans va yakuniy hisob; o'zgartirish formasi."""
    employee = get_object_or_404(salary.employees_qs(request.user), pk=pk)
    info = card(request.user, employee)
    branches = [r['branch'] for r in info['rows']]
    back = _next(request, '')
    form = None
    if info['can_manage'] and branches:
        first = info['rows'][0]['rule']
        initial = {'branch': branches[0], 'effective_from': timezone.localdate().replace(day=1)}
        if first:
            initial.update({'salary_kind': first.kind, 'salary_amount': int(first.amount) if first.kind == SalaryRule.Kind.FIXED else None,
                            'salary_percent': first.percent if first.kind == SalaryRule.Kind.PERCENT else None})
        form = SalaryForm(request.POST or None, branches=branches, user=request.user, initial=initial)
        if request.method == 'POST':
            data = check(form)
            if form.is_valid() and data:
                made = apply(request, employee, [form.cleaned_data['branch'].pk], data, form.cleaned_data['effective_from'])
                if made:
                    from finance import payroll
                    month = timezone.localdate().replace(day=1)
                    if made[0].effective_from <= month:            # shu oy hisobini darhol yangilaymiz
                        payroll.ensure_payslips(made[0].branch, month)
                    messages.success(request, f"Oylik saqlandi: {made[0].describe()} ({made[0].effective_from:%m.%Y} dan)")
                else:
                    messages.info(request, "O'zgarish yo'q — oylik avvalgidek")
                return redirect(back or request.path)
    history = list(SalaryRule.objects.filter(employee=employee, branch__in=branches).select_related('branch__organization'))
    return render(request, 'panel/employee_salary.html', {'nav': 'payroll', 'e': employee, 'info': info, 'form': form,
                                                          'history': history, 'back': back})
