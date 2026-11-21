"""Oyliklar: qoidalar (qat'iy yoki foiz), oy hisobi, avans/oylik to'lash. Ruxsat: `payroll.*` — faqat hisobchi va founder
(boshqalarga founder alohida beradi). Oylik to'langanda avtomatik «Maosh» xarajati yoziladi."""
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from finance import payroll
from finance.models import Method, Payslip, SalaryPayment, SalaryRule
from org.scope import branch_ids, branches_for, pick_branch, scope_by_branch

from . import audit
from .access import panel_required, perms_of
from .views_expenses import parse_month, shift_month
from .views_finance import MoneyField


def _money(v):
    return f'{v:,.0f}'.replace(',', ' ')


def _current_branch(request):
    """Oyliklar sahifasi bitta filial bo'yicha: `?filial=`, bo'lmasa xodimning birinchi filiali."""
    branches = list(branches_for(request.user))
    raw = request.GET.get('filial') or request.POST.get('filial') or ''
    chosen = next((b for b in branches if str(b.pk) == raw), None)
    return chosen or next((b for b in branches if b.pk == pick_branch(request.user).pk), branches[0] if branches else None), branches


def _slip_or_404(request, pk):
    return get_object_or_404(scope_by_branch(Payslip.objects.select_related('employee', 'branch'), request.user), pk=pk)


@panel_required('payroll.view')
def payroll_page(request):
    granted = perms_of(request.user)
    month = parse_month(request.GET.get('oy'))
    branch, branches = _current_branch(request)
    slips = list(Payslip.objects.filter(branch=branch, month=month).select_related('employee').prefetch_related('payments')) if branch else []
    totals = {'total': sum((s.total for s in slips), Decimal(0)), 'paid': sum((s.paid for s in slips), Decimal(0))}
    totals['remaining'] = totals['total'] - totals['paid']
    return render(request, 'panel/payroll.html', {
        'nav': 'payroll', 'month': month, 'prev_month': shift_month(month, -1), 'next_month': shift_month(month, 1),
        'branch': branch, 'branches': branches, 'slips': slips, 'totals': totals,
        'can_manage': 'payroll.manage' in granted, 'has_rules': bool(branch and SalaryRule.objects.filter(branch=branch).exists())})


@require_POST
@panel_required('payroll.manage')
def payroll_calculate(request):
    month = parse_month(request.POST.get('oy'))
    branch, _ = _current_branch(request)
    n = payroll.ensure_payslips(branch, month) if branch else 0
    audit.log(request, "Oyliklarni hisobladi", label=f'{branch} · {month:%m.%Y}: {n} ta xodim', target_type='payroll')
    messages.success(request, f"{n} ta xodimning oyligi hisoblandi" if n else "Qoidasi bor xodim yo'q — avval «Oylik qoidalari»ni kiriting")
    return redirect(f"{reverse('panel:payroll')}?oy={month:%Y-%m}&filial={branch.pk if branch else ''}")


class AdjustForm(forms.ModelForm):
    bonus = MoneyField(label='Mukofot (so\'m)', min_value=0, required=False)
    deduction = MoneyField(label='Ushlanma / jarima (so\'m)', min_value=0, required=False)

    class Meta:
        model = Payslip
        fields = ['bonus', 'deduction', 'note']

    def clean_bonus(self):
        return self.cleaned_data.get('bonus') or 0

    def clean_deduction(self):
        return self.cleaned_data.get('deduction') or 0


@panel_required('payroll.manage')
def payslip_edit(request, pk):
    slip = _slip_or_404(request, pk)
    form = AdjustForm(request.POST or None, instance=slip)
    if request.method == 'POST' and form.is_valid():
        form.save()
        audit.log(request, "Oylikni o'zgartirdi", slip, label=f'{slip.employee.get_full_name()} · {slip.month:%m.%Y}',
                  details={'mukofot': _money(slip.bonus), 'ushlanma': _money(slip.deduction)}, target_type='payroll')
        messages.success(request, 'Saqlandi')
        return redirect(f"{reverse('panel:payroll')}?oy={slip.month:%Y-%m}&filial={slip.branch_id}")
    return render(request, 'panel/payslip_form.html', {'nav': 'payroll', 'form': form, 'slip': slip})


class PayForm(forms.Form):
    amount = MoneyField(label="Summa (so'm)", min_value=1)
    kind = forms.ChoiceField(label='Turi', choices=SalaryPayment.Kind.choices, initial='salary')
    paid_on = forms.DateField(label='Sana', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    method = forms.ChoiceField(label="To'lov usuli", choices=Method.choices)

    def clean_paid_on(self):
        d = self.cleaned_data['paid_on']
        if d > timezone.localdate():
            raise forms.ValidationError("Kelajak sanasi bo'lishi mumkin emas")
        return d


@panel_required('payroll.manage')
def payslip_pay(request, pk):
    slip = _slip_or_404(request, pk)
    form = PayForm(request.POST or None, initial={'amount': int(slip.remaining) if slip.remaining > 0 else None, 'paid_on': timezone.localdate(),
                                                  'method': 'cash'})
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        p = payroll.pay(slip, d['amount'], d['kind'], d['paid_on'], d['method'], request.user)
        audit.log(request, "Oylik to'ladi", slip, label=f'{slip.employee.get_full_name()} · {slip.month:%m.%Y}',
                  details={'summa': _money(p.amount), 'turi': p.get_kind_display()}, target_type='payroll')
        messages.success(request, f"{_money(p.amount)} so'm to'landi (xarajatlarga «Maosh» sifatida yozildi)")
        return redirect(f"{reverse('panel:payroll')}?oy={slip.month:%Y-%m}&filial={slip.branch_id}")
    return render(request, 'panel/payslip_pay.html', {'nav': 'payroll', 'form': form, 'slip': slip, 'payments': slip.payments.all()})


@require_POST
@panel_required('payroll.manage')
def payment_delete(request, pk):
    p = get_object_or_404(SalaryPayment.objects.filter(payslip__in=scope_by_branch(Payslip.objects.all(), request.user)), pk=pk)
    slip = p.payslip
    audit.log(request, "Oylik to'lovini bekor qildi", slip, label=f'{slip.employee.get_full_name()} · {_money(p.amount)}', target_type='payroll')
    payroll.delete_payment(p)
    messages.success(request, "To'lov bekor qilindi, «Maosh» xarajati ham o'chirildi")
    return redirect('panel:payslip_pay', pk=slip.pk)


# ------------------------------------------------------------------ qoidalar

@panel_required('payroll.view')
def salary_rules(request):
    rules = list(scope_by_branch(SalaryRule.objects.select_related('employee', 'branch'), request.user))
    latest = {}
    for r in rules:      # ro'yxat yangidan eskiga: har (xodim, filial) uchun birinchisi — amaldagi
        latest.setdefault((r.employee_id, r.branch_id), r.pk)
    rows = [{'r': r, 'current': latest[(r.employee_id, r.branch_id)] == r.pk} for r in rules]
    return render(request, 'panel/salary_rules.html', {'nav': 'payroll', 'rows': rows, 'can_manage': 'payroll.manage' in perms_of(request.user)})


class RuleForm(forms.ModelForm):
    amount = MoneyField(label="Oylik (so'm)", min_value=0, required=False, help_text="Qat'iy oylik uchun")

    class Meta:
        model = SalaryRule
        fields = ['employee', 'branch', 'effective_from', 'kind', 'amount', 'percent']
        widgets = {'effective_from': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}
        help_texts = {'effective_from': "Shu oydan boshlab amal qiladi; eski oylarning hisobi o'zgarmaydi",
                      'percent': "Foiz turi uchun: xodimning o'quvchilari shu oy qilgan to'lovdan"}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        ids = branch_ids(user)
        people = User.objects.filter(role__in=[User.Role.TEACHER, User.Role.STAFF], is_active=True, is_demo=False)
        if ids is not None:
            people = people.filter(branches__in=ids).distinct()
        self.fields['employee'].queryset = people.order_by('last_name', 'first_name')
        self.fields['employee'].label_from_instance = lambda u: f'{u.last_name} {u.first_name}'.strip() or u.username
        self.fields['branch'].queryset = branches_for(user)
        self.fields['branch'].empty_label = None

    def clean(self):
        d = super().clean()
        if d.get('kind') == SalaryRule.Kind.FIXED:
            if not d.get('amount'):
                self.add_error('amount', "Qat'iy oylik summasini kiriting")
        d['amount'] = d.get('amount') or 0
        return d


@panel_required('payroll.manage')
def salary_rule_add(request):
    form = RuleForm(request.POST or None, user=request.user,
                    initial={'branch': pick_branch(request.user), 'effective_from': timezone.localdate().replace(day=1), 'percent': 40})
    if request.method == 'POST' and form.is_valid():
        r = form.save(commit=False)
        r.created_by = request.user
        r.save()
        audit.log(request, "Oylik qoidasi qo'shdi", r, label=f'{r.employee.get_full_name()} — {r.describe()}',
                  details={'filial': str(r.branch), 'kuchga kiradi': f'{r.effective_from:%d.%m.%Y}'}, target_type='payroll')
        messages.success(request, "Qoida qo'shildi. Oyni «Hisoblash» tugmasi bilan yangilang.")
        return redirect('panel:salary_rules')
    return render(request, 'panel/salary_rule_form.html', {'nav': 'payroll', 'form': form})


@require_POST
@panel_required('payroll.manage')
def salary_rule_delete(request, pk):
    r = get_object_or_404(scope_by_branch(SalaryRule.objects.all(), request.user), pk=pk)
    audit.log(request, "Oylik qoidasini o'chirdi", r, label=f'{r.employee.get_full_name()} — {r.describe()}', target_type='payroll')
    r.delete()
    messages.success(request, "Qoida o'chirildi")
    return redirect('panel:salary_rules')
