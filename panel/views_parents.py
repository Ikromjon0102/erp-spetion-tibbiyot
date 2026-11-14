from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Student, User
from accounts.passwords import issue_temp_password
from accounts.phone import to_digits
from accounts.student_import import _unique_username

from . import audit
from .access import panel_required, perms_of
from .forms import PhoneField
from .models import StaffProfile

PAGE_SIZE = 30


def parents_qs():
    """Ota-onalar: ota-ona hisoblari va farzandi bor ustozlar (sinov hisoblari chiqarib tashlanadi)."""
    return (User.objects.filter(is_demo=False).filter(Q(role=User.Role.PARENT) | Q(children__isnull=False))
            .exclude(username__startswith='sinov_').distinct())


class ParentForm(forms.Form):
    last_name = forms.CharField(label='Familiya', max_length=150, required=False)
    first_name = forms.CharField(label='Ism', max_length=150)
    phone = PhoneField(label='Telefon raqam (login)')

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        if instance is not None and 'initial' not in kwargs:
            kwargs['initial'] = {'last_name': instance.last_name, 'first_name': instance.first_name, 'phone': instance.phone}
        super().__init__(*args, **kwargs)

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        clash = User.objects.filter(phone_digits=to_digits(phone))
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        other = clash.first()
        if other:
            raise forms.ValidationError(f"Bu raqam boshqa hisobda: {other.get_full_name() or other.username} ({other.get_role_display()})")
        return phone


def _secret(request, text):
    messages.add_message(request, messages.SUCCESS, text, extra_tags='secret')


def _can_reset(user):
    return user.role == User.Role.PARENT and not user.is_superuser and not StaffProfile.objects.filter(user=user).exists()


@panel_required('parents.view')
def parents(request):
    q = request.GET.get('q', '').strip()
    qs = parents_qs().prefetch_related('children__user', 'children__group').order_by('last_name', 'first_name', 'username')
    if q:
        digits = ''.join(ch for ch in q if ch.isdigit())
        cond = (Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(children__user__last_name__icontains=q)
                | Q(children__user__first_name__icontains=q))
        if len(digits) >= 4:
            cond |= Q(phone_digits__contains=digits)
        qs = qs.filter(cond).distinct()
    if request.GET.get('holat') == 'farzandsiz':
        qs = qs.filter(children__isnull=True)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'panel/parents.html', {'nav': 'parents', 'page': page, 'q': q, 'holat': request.GET.get('holat', ''),
                                                  'total': parents_qs().count(), 'qs': params.urlencode()})


@panel_required('parents.add')
def parent_create(request):
    form = ParentForm(request.POST or None)
    link = Student.objects.select_related('user', 'group').filter(pk=request.GET.get('oquvchi') or 0).first()
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        digits = to_digits(d['phone'])
        user = User(username=_unique_username(digits), first_name=d['first_name'], last_name=d['last_name'], phone=d['phone'], role=User.Role.PARENT)
        user.set_unusable_password()
        user.save()
        link_id = request.POST.get('oquvchi')
        student = Student.objects.filter(pk=link_id).first() if link_id else None
        if student:
            student.parents.add(user)
        password = issue_temp_password(user)
        audit.log(request, "Ota-ona qo'shdi", user, label=user.get_full_name() or user.username,
                  details={'telefon': d['phone'], 'farzand': student.user.get_full_name() if student else '—'}, target_type='parent')
        _secret(request, f"{user.get_full_name()} qo'shildi. Login: {d['phone']} · bir martalik parol: {password}  (faqat hozir ko'rinadi; birinchi kirishda almashtiradi)")
        return redirect('panel:parent', pk=user.pk)
    return render(request, 'panel/parent_form.html', {'nav': 'parents', 'form': form, 'title': "Ota-ona qo'shish", 'link': link})


@panel_required('parents.view')
def parent_detail(request, pk):
    parent = get_object_or_404(parents_qs(), pk=pk)
    granted = perms_of(request.user)
    children = list(parent.children.select_related('user', 'group'))
    q = request.GET.get('q', '').strip()
    found = []
    if q and 'parents.change' in granted:
        from billing.reports import real_students
        found = list(real_students().select_related('user', 'group').filter(Q(user__last_name__icontains=q) | Q(user__first_name__icontains=q)
                                                                              | Q(group__name__icontains=q)).exclude(parents=parent)
                     .order_by('user__last_name', 'user__first_name')[:12])
    return render(request, 'panel/parent_detail.html', {'nav': 'parents', 'p': parent, 'children': children, 'q': q, 'found': found,
                                                        'can_reset': _can_reset(parent)})


@panel_required('parents.change')
def parent_edit(request, pk):
    parent = get_object_or_404(parents_qs(), pk=pk)
    before = {'Familiya': parent.last_name, 'Ism': parent.first_name, 'Telefon': parent.phone}
    form = ParentForm(request.POST or None, instance=parent)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        parent.last_name, parent.first_name, parent.phone = d['last_name'], d['first_name'], d['phone']
        parent.save()
        audit.log(request, "Ota-ona ma'lumotini o'zgartirdi", parent, label=parent.get_full_name() or parent.username,
                  details=audit.changes(before, {'Familiya': parent.last_name, 'Ism': parent.first_name, 'Telefon': parent.phone}, {k: k for k in before}),
                  target_type='parent')
        messages.success(request, 'Saqlandi')
        return redirect('panel:parent', pk=parent.pk)
    return render(request, 'panel/parent_form.html', {'nav': 'parents', 'form': form, 'title': 'Ota-onani tahrirlash', 'p': parent})


@require_POST
@panel_required('parents.change')
def parent_link(request, pk, student_id):
    parent = get_object_or_404(parents_qs(), pk=pk)
    student = get_object_or_404(Student.objects.select_related('user'), pk=student_id)
    student.parents.add(parent)
    audit.log(request, "Ota-ona biriktirdi", student, label=f"{student.user.get_full_name()} ← {parent.get_full_name() or parent.username}", target_type='student')
    messages.success(request, f'{student.user.get_full_name()} biriktirildi')
    return redirect('panel:parent', pk=parent.pk)


@require_POST
@panel_required('parents.change')
def parent_unlink(request, pk, student_id):
    parent = get_object_or_404(parents_qs(), pk=pk)
    student = get_object_or_404(parent.children, pk=student_id)
    student.parents.remove(parent)
    audit.log(request, "Ota-onani ajratdi", student, label=f"{student.user.get_full_name()} ← {parent.get_full_name() or parent.username}", target_type='student')
    messages.success(request, 'Farzand ajratildi')
    return redirect('panel:parent', pk=parent.pk)


@require_POST
@panel_required('parents.change')
def parent_password(request, pk):
    parent = get_object_or_404(parents_qs(), pk=pk)
    if not _can_reset(parent):
        messages.error(request, "Bu hisob ustoz yoki xodimga tegishli — parolini bu yerdan o'zgartirib bo'lmaydi")
    else:
        password = issue_temp_password(parent)
        audit.log(request, 'Bir martalik parol berdi', parent, label=parent.get_full_name() or parent.username, target_type='parent')
        _secret(request, f"{parent.get_full_name() or parent.username} — login: {parent.phone or parent.username} · bir martalik parol: {password}  (faqat hozir ko'rinadi)")
    return redirect('panel:parent', pk=parent.pk)
