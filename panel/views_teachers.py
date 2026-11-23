from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from academics.models import Group, Lesson, Subject, Teaching
from accounts.models import User
from accounts.phone import to_digits
from accounts.student_import import _unique_username

from org.scope import scope_groups, scope_teachers

from . import audit
from .hubs import org_hub
from .access import panel_required, perms_of
from .forms import PhoneField
from .views_devices import apply_photo, next_teacher_id, photo_ok

PAGE_SIZE = 30


def teachers_qs(user):
    """Haqiqiy ustozlar (sinov hisobi chiqarib tashlanadi); xodim faqat o'z filiallaridagilarni ko'radi."""
    return scope_teachers(User.objects.filter(role=User.Role.TEACHER, is_demo=False), user)


class TeacherForm(forms.Form):
    last_name = forms.CharField(label='Familiya', max_length=150)
    first_name = forms.CharField(label='Ism', max_length=150)
    phone = PhoneField(label='Telefon raqam (login)')
    access_id = forms.CharField(label='Face ID (qurilmadagi ID)', max_length=32, required=False,
                                help_text="Bo'sh qoldirsangiz, rasm yuklanganda o'zi beriladi (7001 dan)")

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        if instance is not None and 'initial' not in kwargs:
            kwargs['initial'] = {'last_name': instance.last_name, 'first_name': instance.first_name, 'phone': instance.phone, 'access_id': instance.access_id}
        super().__init__(*args, **kwargs)

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        clash = User.objects.filter(phone_digits=to_digits(phone)).exclude(role=User.Role.PARENT)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise forms.ValidationError(f"Bu raqam boshqa hisobda: {clash.first().get_full_name() or clash.first().username}")
        return phone


    def clean_access_id(self):
        value = self.cleaned_data['access_id'].strip()
        if value:
            from accounts.models import Student
            taken = User.objects.filter(access_id=value)
            if self.instance is not None:
                taken = taken.exclude(pk=self.instance.pk)
            if taken.exists() or Student.objects.filter(access_id=value).exists():
                raise forms.ValidationError('Bu Face ID boshqa odamda')
        return value or None


class AssignForm(forms.Form):
    subject = forms.ModelChoiceField(label='Fan', queryset=Subject.objects.all(), empty_label='— fan —')
    group = forms.ModelChoiceField(label='Sinf', queryset=Group.objects.all(), empty_label='— sinf —')

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['group'].queryset = scope_groups(Group.objects.all(), user)


def _initial_password(user):
    """Boshlang'ich parol — telefonning oxirgi 4 raqami; birinchi kirishda almashtirish shart."""
    from accounts.passwords import initial_password
    return initial_password(user)


def _secret(request, text):
    messages.add_message(request, messages.SUCCESS, text, extra_tags='secret')


@panel_required('teachers.view')
@org_hub('teachers')
def teachers(request):
    q = request.GET.get('q', '').strip()
    qs = teachers_qs(request.user).prefetch_related('teachings__subject', 'teachings__group').order_by('last_name', 'first_name')
    if q:
        digits = ''.join(ch for ch in q if ch.isdigit())      # qisman raqam ham qidiriladi
        cond = Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(teachings__subject__name__icontains=q)
        if len(digits) >= 4:
            cond |= Q(phone_digits__contains=digits)
        qs = qs.filter(cond).distinct()
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get('page'))
    rows = []
    for u in page:
        ts = list(u.teachings.all())
        rows.append({'u': u, 'subjects': sorted({t.subject.name for t in ts}), 'groups': sorted({t.group.name for t in ts})})
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'panel/teachers.html', {'nav': 'teachers', 'page': page, 'rows': rows, 'q': q, 'total': teachers_qs(request.user).count(),
                                                   'granted': perms_of(request.user), 'qs': params.urlencode()})


@panel_required('teachers.add')
def teacher_add(request):
    from .branch_assign import chosen_branches, default_selection, follow_to, picker_groups
    form = TeacherForm(request.POST or None)
    upload = request.FILES.get('photo')
    selected = chosen_branches(request) if request.method == 'POST' else default_selection(request)
    picker_error = "Kamida bitta filialni belgilang" if request.method == 'POST' and not selected else ''
    if request.method == 'POST' and form.is_valid() and selected and photo_ok(form, upload):
        d = form.cleaned_data
        digits = to_digits(d['phone'])
        with transaction.atomic():
            user = User(username=_unique_username(digits), first_name=d['first_name'], last_name=d['last_name'], phone=d['phone'],
                        role=User.Role.TEACHER)
            user.save()      # bir xil raqamli ota-ona hisobi bo'lsa, o'zi birlashtiriladi
            user.branches.set(selected)          # faqat formada belgilangan filiallar
            password = _initial_password(user)
        audit.log(request, "Ustoz qo'shdi", user, label=user.get_full_name(), details={'telefon': d['phone']}, target_type='teacher')
        if not user.access_id:
            user.access_id = next_teacher_id()
            user.save(update_fields=['access_id'])
        if upload:
            apply_photo(request, user, upload, user.get_full_name())
        _secret(request, f"{user.get_full_name()} qo'shildi. Login: {d['phone']} · boshlang'ich parol: {password} (telefonning oxirgi 4 raqami; "
                         "birinchi kirishda yangi parol qo'yadi)")
        follow_to(request, selected)
        return redirect('panel:teacher', pk=user.pk)
    return render(request, 'panel/teacher_form.html', {'nav': 'teachers', 'form': form, 'title': "Ustoz qo'shish",
                                                       'picker': picker_groups(request.user, set(selected)), 'picker_error': picker_error})


@panel_required('teachers.view')
def teacher_detail(request, pk):
    user = get_object_or_404(teachers_qs(request.user), pk=pk)
    granted = perms_of(request.user)
    teachings = list(user.teachings.select_related('subject', 'group').order_by('group__name', 'subject__name'))
    lessons = Lesson.objects.filter(teaching__teacher=user, active=True).count()
    ctx = {'nav': 'teachers', 'u': user, 'teachings': teachings, 'lessons': lessons, 'granted': granted,
           'children': list(user.children.select_related('user', 'group')) if user.has_children else [],
           'assign': AssignForm(user=request.user)}
    from .branch_assign import branch_choices
    ctx.update({'branch_target': user, 'branch_action': reverse('panel:teacher_branches', args=[user.pk]),
                'branch_groups': branch_choices(request.user, user) if 'teachers.change' in granted else None})
    return render(request, 'panel/teacher_detail.html', ctx)


@panel_required('teachers.change')
def teacher_edit(request, pk):
    user = get_object_or_404(teachers_qs(request.user), pk=pk)
    before = {'Familiya': user.last_name, 'Ism': user.first_name, 'Telefon': user.phone}
    form = TeacherForm(request.POST or None, instance=user)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        user.last_name, user.first_name, user.phone, user.access_id = d['last_name'], d['first_name'], d['phone'], d['access_id']
        user.save()
        after = {'Familiya': user.last_name, 'Ism': user.first_name, 'Telefon': user.phone}
        audit.log(request, "Ustoz ma'lumotini o'zgartirdi", user, label=user.get_full_name(),
                  details=audit.changes(before, after, {k: k for k in before}), target_type='teacher')
        messages.success(request, 'Saqlandi')
        return redirect('panel:teacher', pk=user.pk)
    return render(request, 'panel/teacher_form.html', {'nav': 'teachers', 'form': form, 'title': 'Ustozni tahrirlash', 'u': user})


@require_POST
@panel_required('teachers.change')
def teacher_assign(request, pk):
    user = get_object_or_404(teachers_qs(request.user), pk=pk)
    form = AssignForm(request.POST, user=request.user)
    if form.is_valid():
        t, created = Teaching.objects.get_or_create(teacher=user, subject=form.cleaned_data['subject'], group=form.cleaned_data['group'])
        if created:
            audit.log(request, "Ustozga dars biriktirdi", user, label=f'{user.get_full_name()} — {t.subject} / {t.group}', target_type='teacher')
            messages.success(request, f'{t.subject} — {t.group} biriktirildi')
        else:
            messages.info(request, 'Bu dars allaqachon biriktirilgan')
    else:
        messages.error(request, 'Fan va sinfni tanlang')
    return redirect('panel:teacher', pk=user.pk)


@require_POST
@panel_required('teachers.change')
def teacher_unassign(request, pk, teaching_id):
    user = get_object_or_404(teachers_qs(request.user), pk=pk)
    t = get_object_or_404(Teaching, pk=teaching_id, teacher=user)
    label = f'{user.get_full_name()} — {t.subject} / {t.group}'
    t.delete()
    audit.log(request, "Ustozdan darsni olib tashladi", user, label=label, target_type='teacher')
    messages.success(request, 'Dars olib tashlandi')
    return redirect('panel:teacher', pk=user.pk)


@require_POST
@panel_required('teachers.change')
def teacher_password(request, pk):
    user = get_object_or_404(teachers_qs(request.user), pk=pk)
    if not user.phone_digits:
        messages.error(request, "Telefon raqam yo'q — avval raqamni kiriting")
    else:
        password = _initial_password(user)
        audit.log(request, 'Boshlang\'ich parol berdi', user, label=user.get_full_name(), target_type='teacher')
        _secret(request, f"{user.get_full_name()} — login: {user.phone} · parol: {password} (telefonning oxirgi 4 raqami; birinchi kirishda almashtiradi)")
    return redirect('panel:teacher', pk=user.pk)


@require_POST
@panel_required('teachers.change')
def teacher_toggle(request, pk):
    user = get_object_or_404(teachers_qs(request.user), pk=pk)
    if user.pk == request.user.pk:
        messages.error(request, "O'zingizni nofaol qilib bo'lmaydi")
    else:
        user.is_active = not user.is_active
        user.save(update_fields=['is_active'])
        audit.log(request, 'Ustozni faollashtirdi' if user.is_active else 'Ustozni nofaol qildi', user, label=user.get_full_name(), target_type='teacher')
        messages.success(request, 'Ustoz faol' if user.is_active else "Ustoz nofaol qilindi — tizimga kira olmaydi")
    return redirect('panel:teacher', pk=user.pk)
