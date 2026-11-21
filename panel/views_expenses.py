"""Xarajatlar, takroriy xarajatlar va kirim-chiqim-foyda hisoboti. Ruxsat: `expenses.*`; ma'lumot filial bo'yicha ajratiladi."""
from datetime import date
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from billing.models import Payment
from finance.models import Expense, ExpenseCategory, RecurringExpense
from org.scope import branches_for, pick_branch, scope_by_branch, scope_via_student

from . import audit
from .access import panel_required, perms_of
from .views_finance import MoneyField

MAX_RECEIPT = 8 * 1024 * 1024


def parse_month(raw):
    """'2026-11' -> date(2026, 11, 1); noto'g'ri bo'lsa joriy oy."""
    try:
        y, m = (int(x) for x in (raw or '').split('-'))
        return date(y, m, 1)
    except (ValueError, TypeError):
        return timezone.localdate().replace(day=1)


def shift_month(d, n):
    idx = d.year * 12 + d.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def _branch_filter(request, qs_branches):
    """`?filial=<id>` — faqat o'zi ko'ra oladigan filiallardan."""
    raw = request.GET.get('filial', '')
    return next((b for b in qs_branches if str(b.pk) == raw), None)


def _income(request, month, branch):
    qs = Payment.objects.filter(voided=False, paid_on__year=month.year, paid_on__month=month.month).exclude(student__user__username__startswith='sinov_')
    qs = scope_via_student(qs, request.user)
    if branch:
        qs = qs.filter(student__branch=branch)
    return qs.aggregate(t=Sum('amount'))['t'] or Decimal(0)


@panel_required('expenses.view')
def expenses(request):
    granted = perms_of(request.user)
    month = parse_month(request.GET.get('oy'))
    branches = list(branches_for(request.user))
    branch = _branch_filter(request, branches)
    category = request.GET.get('kategoriya', '')
    base = scope_by_branch(Expense.objects.filter(date__year=month.year, date__month=month.month), request.user)
    if branch:
        base = base.filter(branch=branch)
    total = base.aggregate(t=Sum('amount'))['t'] or Decimal(0)
    by_cat = [{'name': r['category__name'], 'sum': r['t'], 'pct': round(100 * r['t'] / total) if total else 0}
              for r in base.values('category__name').annotate(t=Sum('amount')).order_by('-t')]
    qs = base.select_related('category', 'branch', 'created_by')
    if category.isdigit():
        qs = qs.filter(category_id=int(category))
    page = Paginator(qs, 50).get_page(request.GET.get('page'))
    income = _income(request, month, branch)
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'panel/expenses.html', {
        'nav': 'expenses', 'page': page, 'month': month, 'prev_month': shift_month(month, -1), 'next_month': shift_month(month, 1),
        'branches': branches, 'branch': branch, 'categories': ExpenseCategory.objects.all(), 'category': category,
        'total': total, 'income': income, 'profit': income - total, 'by_cat': by_cat, 'qs': params.urlencode(),
        'can_add': 'expenses.add' in granted, 'can_change': 'expenses.change' in granted, 'can_manage': 'expenses.manage' in granted,
        'can_payroll': 'payroll.view' in granted})


class ExpenseForm(forms.ModelForm):
    amount = MoneyField(label="Summa (so'm)", min_value=1)

    class Meta:
        model = Expense
        fields = ['branch', 'category', 'date', 'amount', 'payee', 'method', 'note', 'receipt']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['branch'].queryset = branches_for(user)
        self.fields['branch'].empty_label = None
        self.fields['category'].queryset = ExpenseCategory.objects.filter(is_system=False)
        if self.instance.pk and self.instance.category.is_system:       # «Maosh» xarajati oyliklar bo'limidan boshqariladi
            self.fields['category'].queryset = ExpenseCategory.objects.all()

    def clean_date(self):
        d = self.cleaned_data['date']
        if d > timezone.localdate():
            raise forms.ValidationError("Kelajak sanasi bo'lishi mumkin emas")
        return d

    def clean_receipt(self):
        f = self.cleaned_data.get('receipt')
        if f and hasattr(f, 'size') and f.size > MAX_RECEIPT:
            raise forms.ValidationError("Rasm 8 MB dan katta bo'lmasin")
        return f


def _expense_or_404(request, pk):
    return get_object_or_404(scope_by_branch(Expense.objects.select_related('category', 'branch'), request.user), pk=pk)


@panel_required('expenses.add')
def expense_add(request):
    form = ExpenseForm(request.POST or None, request.FILES or None, user=request.user,
                       initial={'branch': pick_branch(request.user), 'date': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        e = form.save(commit=False)
        e.created_by = request.user
        e.save()
        audit.log(request, "Xarajat qo'shdi", e, label=f'{e.category} — {e.amount:,.0f}'.replace(',', ' '),
                  details={'filial': str(e.branch), 'kimga': e.payee or '—'}, target_type='expense')
        messages.success(request, "Xarajat qo'shildi")
        return redirect(f"{reverse('panel:expenses')}?oy={e.date:%Y-%m}")
    return render(request, 'panel/expense_form.html', {'nav': 'expenses', 'form': form, 'title': "Yangi xarajat", 'multi': len(form.fields['branch'].queryset) > 1})


@panel_required('expenses.change')
def expense_edit(request, pk):
    e = _expense_or_404(request, pk)
    if hasattr(e, 'salary_payment'):
        messages.info(request, "Bu xarajat oylik to'lovidan yaratilgan: «Oyliklar» bo'limida o'zgartiriladi")
        return redirect('panel:expenses')
    before = (e.category_id, e.amount, e.date, e.payee)
    form = ExpenseForm(request.POST or None, request.FILES or None, instance=e, user=request.user)
    if request.method == 'POST' and form.is_valid():
        e = form.save()
        audit.log(request, "Xarajatni o'zgartirdi", e, label=f'{e.category} — {e.amount:,.0f}'.replace(',', ' '),
                  details={'oldin': f'{before[2]:%d.%m.%Y} · {before[1]:,.0f}'.replace(',', ' ')}, target_type='expense')
        messages.success(request, 'Saqlandi')
        return redirect(f"{reverse('panel:expenses')}?oy={e.date:%Y-%m}")
    return render(request, 'panel/expense_form.html', {'nav': 'expenses', 'form': form, 'title': "Xarajatni tahrirlash", 'e': e,
                                                       'multi': len(form.fields['branch'].queryset) > 1})


@require_POST
@panel_required('expenses.change')
def expense_delete(request, pk):
    e = _expense_or_404(request, pk)
    if hasattr(e, 'salary_payment'):
        messages.error(request, "Oylik to'lovidan yaratilgan xarajatni «Oyliklar» bo'limidan bekor qiling")
        return redirect('panel:expenses')
    label = f'{e.category} — {e.amount:,.0f}'.replace(',', ' ')
    month = e.date
    if e.receipt:
        e.receipt.delete(save=False)
    e.delete()
    audit.log(request, "Xarajatni o'chirdi", label=label, target_type='expense')
    messages.success(request, "Xarajat o'chirildi")
    return redirect(f"{reverse('panel:expenses')}?oy={month:%Y-%m}")


@panel_required('expenses.view')
def expense_receipt(request, pk):
    """Chek rasmi: faqat xarajatni ko'rish ruxsati va filiali bor xodimga."""
    e = _expense_or_404(request, pk)
    if not e.receipt:
        raise Http404
    return FileResponse(e.receipt.open('rb'))


# ------------------------------------------------------------------ takroriy xarajatlar

class RecurringForm(forms.ModelForm):
    amount = MoneyField(label="Summa (so'm)", min_value=1)

    class Meta:
        model = RecurringExpense
        fields = ['branch', 'category', 'amount', 'payee', 'day', 'method', 'start_month', 'end_month', 'is_active']
        widgets = {'start_month': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'end_month': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['branch'].queryset = branches_for(user)
        self.fields['branch'].empty_label = None
        self.fields['category'].queryset = ExpenseCategory.objects.filter(is_system=False)


@panel_required('expenses.manage')
def recurring(request):
    rows = scope_by_branch(RecurringExpense.objects.select_related('branch', 'category'), request.user)
    return render(request, 'panel/recurring.html', {'nav': 'expenses', 'rows': rows, 'today': timezone.localdate()})


@panel_required('expenses.manage')
def recurring_edit(request, pk=None):
    obj = get_object_or_404(scope_by_branch(RecurringExpense.objects.all(), request.user), pk=pk) if pk else None
    form = RecurringForm(request.POST or None, instance=obj, user=request.user,
                         initial={'branch': pick_branch(request.user), 'start_month': timezone.localdate().replace(day=1)})
    if request.method == 'POST' and form.is_valid():
        r = form.save()
        audit.log(request, "Takroriy xarajatni o'zgartirdi" if obj else "Takroriy xarajat qo'shdi", r, label=str(r), target_type='expense')
        messages.success(request, 'Saqlandi')
        return redirect('panel:recurring')
    return render(request, 'panel/recurring_form.html', {'nav': 'expenses', 'form': form, 'title': 'Takroriy xarajat'})


@require_POST
@panel_required('expenses.manage')
def recurring_delete(request, pk):
    r = get_object_or_404(scope_by_branch(RecurringExpense.objects.all(), request.user), pk=pk)
    audit.log(request, "Takroriy xarajatni o'chirdi", r, label=str(r), target_type='expense')
    r.delete()      # allaqachon yozilgan xarajatlar qoladi
    messages.success(request, "O'chirildi (yozilgan xarajatlar saqlanadi)")
    return redirect('panel:recurring')


@require_POST
@panel_required('expenses.manage')
def recurring_generate(request):
    """Joriy oy uchun takroriy xarajatlarni yozadi (oyda bir marta; qayta bosish xavfsiz)."""
    month = timezone.localdate().replace(day=1)
    made = 0
    for r in scope_by_branch(RecurringExpense.objects.all(), request.user):
        made += bool(r.create_for(month, request.user))
    audit.log(request, "Takroriy xarajatlarni yozdi", label=f'{month:%m.%Y}: {made} ta', target_type='expense')
    messages.success(request, f"{made} ta xarajat yozildi" if made else "Bu oy uchun yozilmagan takroriy xarajat yo'q")
    return redirect('panel:recurring')
