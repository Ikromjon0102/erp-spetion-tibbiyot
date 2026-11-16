from datetime import date
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from academics.models import Group
from accounts.models import Student
from billing import exports, reports
from billing.models import BillingSettings, Discount, Payment, StudentDiscount
from billing.services import account, first_of_month, recalc_charges, recalc_current_month, summaries

from . import audit
from .access import panel_required, perms_of


def real_students():
    return reports.real_students().select_related('user', 'group')


def debtor_ids():
    ids = list(reports.real_students().values_list('pk', flat=True))
    return [pk for pk, x in summaries(ids).items() if x['debt'] > 0]


def totals():
    """Bosh sahifa va to'lovlar bo'limi uchun umumiy raqamlar."""
    ids = list(reports.real_students().values_list('pk', flat=True))
    sums = summaries(ids)
    debt = [x for x in sums.values() if x['debt'] > 0]
    return {'debtors': len(debt), 'debt_total': sum((x['debt'] for x in debt), Decimal(0)),
            'overdue_total': sum((x['overdue'] for x in debt), Decimal(0))}


def _paid_sum(qs):
    return qs.filter(voided=False).exclude(student__user__username__startswith='sinov_').aggregate(t=Sum('amount'))['t'] or 0


class MoneyField(forms.IntegerField):
    """Summa: "1 500 000" ko'rinishida yoziladi (bo'shliqlar tashlab yuboriladi)."""
    widget = forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'off', 'data-money': ''})

    def to_python(self, value):
        if isinstance(value, str):
            value = ''.join(value.split()).replace('\xa0', '')
        return super().to_python(value)


class PaymentForm(forms.Form):
    amount = MoneyField(label="Summa (so'm)", min_value=1)
    method = forms.ChoiceField(label="To'lov usuli", choices=Payment.Method.choices)
    paid_on = forms.DateField(label="Sana", widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    note = forms.CharField(label='Izoh', max_length=200, required=False)

    def clean_paid_on(self):
        d = self.cleaned_data['paid_on']
        if d > timezone.localdate():
            raise forms.ValidationError("Kelajak sanasi bo'lishi mumkin emas")
        return d


class DiscountForm(forms.ModelForm):
    class Meta:
        model = Discount
        fields = ['name', 'percent', 'description', 'is_active']


class SettingsForm(forms.Form):
    monthly_price = forms.IntegerField(label="Oylik narx (so'm)", min_value=0)
    due_day = forms.IntegerField(label="To'lov muddati (oyning nechanchi kuni)", min_value=1, max_value=28,
                                 help_text="Shu kundan keyin to'lanmagan summa «muddati o'tgan» deb belgilanadi (jarima yo'q)")
    billing_start = forms.DateField(label="Hisob boshlanadigan oy", widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                                    help_text="Shu oydan boshlab o'quvchilarga hisob yoziladi. O'quv yili: sentabr–iyun")


@panel_required('payments.view')
def finance(request):
    today = timezone.localdate()
    q = request.GET.get('q', '').strip()
    found = []
    if q:
        qs = real_students().filter(Q(user__last_name__icontains=q) | Q(user__first_name__icontains=q) | Q(group__name__icontains=q))
        found = list(qs.order_by('user__last_name', 'user__first_name')[:15])
    recent = Payment.objects.exclude(student__user__username__startswith='sinov_').select_related('student__user', 'student__group', 'received_by')[:15]
    month_start = first_of_month(today)
    ctx = {'nav': 'finance', 'cfg': BillingSettings.get(), 'q': q, 'found': found, 'recent': recent, 'granted': perms_of(request.user),
           'today_sum': _paid_sum(Payment.objects.filter(paid_on=today)), 'month_sum': _paid_sum(Payment.objects.filter(paid_on__gte=month_start))}
    ctx.update(totals())
    return render(request, 'panel/finance.html', ctx)


@panel_required('payments.view')
def debtors(request):
    """Qarzdorlar ro'yxati: avval muddati o'tgan qarzi kattalar. Har qatordan to'lov qabul qilishga o'tiladi."""
    granted = perms_of(request.user)
    q, sinf, holat = request.GET.get('q', '').strip(), request.GET.get('sinf', ''), request.GET.get('holat', '')
    sums = summaries(list(reports.real_students().values_list('pk', flat=True)))
    owing = {pk: x for pk, x in sums.items() if x['debt'] > 0 and (holat != 'muddati' or x['overdue'] > 0)}
    qs = real_students().filter(pk__in=owing).prefetch_related('parents')
    if q:
        qs = qs.filter(Q(user__last_name__icontains=q) | Q(user__first_name__icontains=q))
    if sinf.isdigit():
        qs = qs.filter(group_id=int(sinf))
    rows = [{'s': s, 'debt': owing[s.pk]['debt'], 'overdue': owing[s.pk]['overdue'], 'parent': next(iter(s.parents.all()), None)} for s in qs]
    rows.sort(key=lambda r: (-r['overdue'], -r['debt'], r['s'].user.last_name, r['s'].user.first_name))
    page = Paginator(rows, 50).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'panel/debtors.html', {
        'nav': 'finance', 'page': page, 'groups': Group.objects.all(), 'q': q, 'sinf': sinf, 'holat': holat, 'qs': params.urlencode(),
        'count': len(rows), 'debt_total': sum((r['debt'] for r in rows), Decimal(0)),
        'overdue_total': sum((r['overdue'] for r in rows), Decimal(0)),
        'show_phone': 'sensitive.phones' in granted, 'can_accept': 'payments.accept' in granted, 'can_reports': 'payments.reports' in granted})


@panel_required('payments.accept')
def pay(request, pk):
    student = get_object_or_404(real_students(), pk=pk)
    bill = account(student)
    form = PaymentForm(request.POST or None, initial={'amount': int(bill['debt']) or None, 'method': 'cash', 'paid_on': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        p = Payment.objects.create(student=student, amount=d['amount'], method=d['method'], paid_on=d['paid_on'], note=d['note'],
                                   received_by=request.user)
        audit.log(request, "To'lov qabul qildi", student, label=f'{student} — {p.receipt_no}',
                  details={'summa': f'{p.amount:,}'.replace(',', ' '), 'usul': p.get_method_display(), 'chek': p.receipt_no},
                  target_type='student')
        messages.success(request, f"To'lov qabul qilindi. Chek: {p.receipt_no}")
        return redirect('receipt', pk=student.pk, pay=p.pk)
    monthly = bill['rows'][-1]['charge'].amount if bill['rows'] else bill['price']
    quick = [("To'liq qarz", bill['debt'])] if bill['debt'] else []
    if 0 < bill['overdue'] < bill['debt']:
        quick.append(("Muddati o'tgan", bill['overdue']))
    if monthly and monthly != bill['debt']:
        quick.append(('1 oylik', monthly))
    return render(request, 'panel/pay.html', {'nav': 'finance', 'student': student, 'bill': bill, 'form': form,
                                              'quick': [(label, int(v)) for label, v in quick]})


@require_POST
@panel_required('payments.void')
def payment_void(request, pk):
    p = get_object_or_404(Payment, pk=pk)
    reason = request.POST.get('reason', '').strip()[:200]
    if not p.voided:
        p.voided, p.voided_by, p.voided_at, p.void_reason = True, request.user, timezone.now(), reason
        p.save(update_fields=['voided', 'voided_by', 'voided_at', 'void_reason'])
        audit.log(request, "To'lovni bekor qildi", p.student, label=f'{p.student} — {p.receipt_no}',
                  details={'summa': f'{p.amount:,}'.replace(',', ' '), 'sabab': reason or '—'}, target_type='student')
        messages.success(request, f"{p.receipt_no} chek bekor qilindi")
    return redirect('panel:student', pk=p.student_id)


@panel_required('payments.view')
def discounts(request):
    rows = [{'d': d, 'count': d.assignments.count()} for d in Discount.objects.all()]
    return render(request, 'panel/discounts.html', {'nav': 'finance', 'rows': rows, 'granted': perms_of(request.user)})


@panel_required('payments.discounts')
def discount_edit(request, pk=None):
    obj = get_object_or_404(Discount, pk=pk) if pk else None
    form = DiscountForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        old = f'{obj.name} −{obj.percent:g}%' if obj else ''
        d = form.save()
        audit.log(request, 'Chegirmani o\'zgartirdi' if obj else "Chegirma qo'shdi", d, label=str(d),
                  details={'eski': old, 'yangi': str(d)} if obj else {'chegirma': str(d)}, target_type='discount')
        if obj:   # foiz o'zgargan bo'lsa, biriktirilgan o'quvchilar hisobi yangilanadi
            for sd in d.assignments.select_related('student'):
                recalc_charges(sd.student, sd.valid_from)
        messages.success(request, 'Saqlandi')
        return redirect('panel:discounts')
    return render(request, 'panel/discount_form.html', {'nav': 'finance', 'form': form, 'obj': obj,
                                                         'title': 'Chegirmani tahrirlash' if obj else 'Yangi chegirma'})


@require_POST
@panel_required('payments.discounts')
def discount_delete(request, pk):
    d = get_object_or_404(Discount, pk=pk)
    if d.assignments.exists():
        d.is_active = False
        d.save(update_fields=['is_active'])
        for sd in d.assignments.select_related('student'):
            recalc_charges(sd.student, sd.valid_from)
        messages.info(request, "Bu chegirma o'quvchilarga biriktirilgan — o'chirilmadi, faqat faolsiz qilindi")
    else:
        audit.log(request, "Chegirmani o'chirdi", label=str(d), target_type='discount')
        d.delete()
        messages.success(request, "Chegirma o'chirildi")
    return redirect('panel:discounts')


@require_POST
@panel_required('payments.discounts')
def student_discount_add(request, pk):
    student = get_object_or_404(real_students(), pk=pk)
    d = Discount.objects.filter(pk=request.POST.get('discount'), is_active=True).first()
    if not d:
        messages.error(request, 'Chegirmani tanlang')
        return redirect('panel:student', pk=pk)
    try:
        vf = date.fromisoformat(request.POST['valid_from'] + '-01') if request.POST.get('valid_from') else None
        vt = date.fromisoformat(request.POST['valid_to'] + '-01') if request.POST.get('valid_to') else None
    except ValueError:
        messages.error(request, "Oy noto'g'ri kiritilgan")
        return redirect('panel:student', pk=pk)
    sd = StudentDiscount.objects.create(student=student, discount=d, valid_from=vf, valid_to=vt,
                                        note=request.POST.get('note', '').strip()[:200], assigned_by=request.user)
    recalc_charges(student, vf)
    audit.log(request, "Chegirma biriktirdi", student, label=f'{student} — {d}', details={'chegirma': str(d), 'sabab': sd.note or '—'},
              target_type='student')
    messages.success(request, f'{d.name} chegirmasi biriktirildi. Bir nechta bo\'lsa, eng kattasi qo\'llanadi.')
    return redirect('panel:student', pk=pk)


@require_POST
@panel_required('payments.discounts')
def student_discount_remove(request, pk, sd_id):
    sd = get_object_or_404(StudentDiscount, pk=sd_id, student_id=pk)
    student, label, vf = sd.student, str(sd.discount), sd.valid_from
    sd.delete()
    recalc_charges(student, vf)
    audit.log(request, "Chegirmani olib tashladi", student, label=f'{student} — {label}', details={'chegirma': label}, target_type='student')
    messages.success(request, 'Chegirma olib tashlandi')
    return redirect('panel:student', pk=pk)


@panel_required('payments.settings')
def finance_settings(request):
    cfg = BillingSettings.get()
    form = SettingsForm(request.POST or None, initial={'monthly_price': int(cfg.monthly_price), 'due_day': cfg.due_day,
                                                       'billing_start': cfg.billing_start})
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        before = (int(cfg.monthly_price), cfg.due_day, cfg.billing_start)
        cfg.monthly_price, cfg.due_day, cfg.billing_start = d['monthly_price'], d['due_day'], first_of_month(d['billing_start'])
        cfg.save()
        n = recalc_current_month() if before[0] != d['monthly_price'] else 0
        audit.log(request, "To'lov sozlamalarini o'zgartirdi", label="Moliya sozlamalari", target_type='billing',
                  details={'oylik narx': audit.change(before[0], d['monthly_price']), "to'lov muddati": audit.change(before[1], d['due_day'])})
        messages.success(request, "Saqlandi" + (f". Joriy oy uchun {n} ta hisob yangilandi (o'tgan oylar o'zgarmadi)." if n else ''))
        return redirect('panel:finance')
    return render(request, 'panel/finance_settings.html', {'nav': 'finance', 'form': form})


@panel_required('payments.reports')
def reports_page(request):
    key = request.GET.get('r')
    report = None
    if key in reports.TITLES:
        report = reports.build(key, request.GET, with_phone='sensitive.phones' in perms_of(request.user))
        report['display'] = [[exports.display(v, k) for v, k in zip(r, report['kinds'])] for r in report['rows']]
        if report['totals']:
            report['totals_display'] = [exports.display(v, k) for v, k in zip(report['totals'], report['kinds'])]
        report['summary_display'] = [(a, exports.money(b)) for a, b in report['summary']]
    from academics.models import Group
    return render(request, 'panel/reports.html', {'nav': 'finance', 'catalog': reports.REPORTS, 'key': key, 'report': report,
                                                  'groups': Group.objects.all(), 'p': request.GET,
                                                  'today': timezone.localdate(), 'query': request.GET.urlencode()})


@panel_required('payments.reports')
def report_download(request, key, fmt):
    if key not in reports.TITLES or fmt not in ('xlsx', 'pdf'):
        return redirect('panel:reports')
    report = reports.build(key, request.GET, with_phone='sensitive.phones' in perms_of(request.user))
    audit.log(request, 'Hisobot yukladi', label=report['title'], details={'format': fmt.upper(), 'davr': report['subtitle']}, target_type='report')
    name = f"{key}-{timezone.localdate():%Y-%m-%d}.{fmt}"
    if fmt == 'xlsx':
        resp = HttpResponse(exports.xlsx_bytes(report), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        resp = HttpResponse(exports.pdf_bytes(report), content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="{name}"'
    return resp
