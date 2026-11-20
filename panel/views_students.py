import csv
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from access.models import AccessEvent
from access.sync import sync_in_background
from access.services import day_summaries
from academics.models import Group
from accounts.models import Student, User
from accounts.passwords import issue_temp_password
from accounts.phone import to_digits
from accounts.student_import import _unique_username, group_name_from_filename, import_students
from journal.models import Attendance

from . import audit
from .models import StaffProfile
from .access import panel_required, perms_of
from .forms import ImportForm, ParentForm, StudentForm
from .views_core import real_students
from .views_devices import apply_photo, photo_ok as _photo_ok

PAGE_SIZE = 25


def _back(student):
    return redirect(reverse('panel:student', args=[student.pk]) + '#parents')


def _filtered(request, granted):
    holat = request.GET.get('holat', '')
    if holat == 'chiqqan' and 'students.change' in granted:      # maktabdan chiqqanlar (arxiv)
        qs = (Student.objects.exclude(user__username__startswith='sinov_').filter(user__is_active=False, left_at__isnull=False)
              .select_related('user', 'group'))
    else:
        qs = real_students().select_related('user', 'group')
    qs = qs.prefetch_related('parents').order_by('user__last_name', 'user__first_name')
    q = request.GET.get('q', '').strip()
    if q:
        name = Q()
        for token in q.split():
            name &= Q(user__first_name__icontains=token) | Q(user__last_name__icontains=token)
        cond = name | Q(access_id__icontains=q)
        digits = re.sub(r'\D', '', q)
        if len(digits) >= 4 and 'sensitive.phones' in granted:   # telefon bo'yicha qidirish faqat ruxsati borlarga
            cond |= Q(parents__phone_digits__contains=digits)
        qs = qs.filter(cond).distinct()
    group = request.GET.get('sinf', '')
    if group.isdigit():
        qs = qs.filter(group_id=int(group))
    today = timezone.localdate()
    if holat == 'kelmagan' and 'monitoring.view' in granted:
        arrived = AccessEvent.objects.filter(direction='in', occurred_at__date=today, student__isnull=False).values('student_id')
        qs = qs.exclude(pk__in=arrived)
    elif holat == 'qarz' and 'payments.view' in granted:
        from .views_finance import debtor_ids
        qs = qs.filter(pk__in=debtor_ids())
    return qs


def _presence_state(p, today, wait_label):
    """Bugungi holat: (nuqta klassi, matn). Yakshanba kuni kelmagan o'quvchi "kelmagan" emas — dam olish kuni."""
    if p and p['in'] and not p['out']:
        return 'in', 'Maktabda'
    if p and p['out']:
        return 'out', 'Ketdi'
    if today.weekday() > 5:
        return 'off', 'Dam olish kuni'
    return 'wait', wait_label


def _presence_map(student_ids, today):
    state = {}
    for e in AccessEvent.objects.filter(student_id__in=student_ids, occurred_at__date=today).order_by('occurred_at'):
        s = state.setdefault(e.student_id, {'in': None, 'out': None})
        if e.direction == 'in':
            s['in'] = s['in'] or timezone.localtime(e.occurred_at)
            s['out'] = None     # oxirgi skan kirish bo'lsa — maktabda
        else:
            s['out'] = timezone.localtime(e.occurred_at)
    return state


@panel_required('students.view')
def students(request):
    granted = perms_of(request.user)
    page = Paginator(_filtered(request, granted), PAGE_SIZE).get_page(request.GET.get('page'))
    ids = [s.pk for s in page]
    today = timezone.localdate()
    presence = _presence_map(ids, today) if 'monitoring.view' in granted else None
    debts = None
    if 'payments.view' in granted:
        from billing.services import summaries
        debts = {pk: x['debt'] for pk, x in summaries(ids).items()}
    rows = []
    for s in page:
        parents = list(s.parents.all())
        p = presence.get(s.pk) if presence is not None else None
        state = None
        if presence is not None:
            state = _presence_state(p, today, 'Kelmagan')
        rows.append({'s': s, 'parent': parents[0] if parents else None, 'extra_parents': max(len(parents) - 1, 0),
                     'state': state, 'debt': (debts or {}).get(s.pk, 0) if debts is not None else None})
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'panel/students.html', {
        'nav': 'students', 'page': page, 'rows': rows, 'groups': Group.objects.all(), 'q': request.GET.get('q', ''),
        'sinf': request.GET.get('sinf', ''), 'holat': request.GET.get('holat', ''), 'qs': params.urlencode(),
        'show_phone': 'sensitive.phones' in granted, 'can_change': 'students.change' in granted, 'show_state': presence is not None, 'show_debt': debts is not None,
    })


@panel_required('students.view')
def students_csv(request):
    granted = perms_of(request.user)
    phones = 'sensitive.phones' in granted
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="oquvchilar.csv"'
    response.write('﻿')
    w = csv.writer(response)
    w.writerow(['Familiya', 'Ism', 'Sinf', 'Face ID'] + (['Ota-ona', 'Telefon'] if phones else []))
    for s in _filtered(request, granted):
        row = [s.user.last_name, s.user.first_name, s.group.name if s.group else '', s.access_id or '']
        if phones:
            p = next(iter(s.parents.all()), None)
            row += [p.get_full_name() if p else '', p.phone if p else '']
        w.writerow(row)
    audit.log(request, 'Ro\'yxatni yuklab oldi', label="O'quvchilar (CSV)", target_type='student')
    return response


@panel_required('students.view')
def student_detail(request, pk):
    granted = perms_of(request.user)
    student = get_object_or_404(Student.objects.select_related('user', 'group').prefetch_related('parents'), pk=pk)
    today = timezone.localdate()
    ctx = {'nav': 'students', 's': student, 'granted': granted, 'parents': list(student.parents.all()),
           'show_phone': 'sensitive.phones' in granted, 'can_change': 'students.change' in granted}

    since = today - timedelta(days=29)
    att = list(student.attendance.filter(date__gte=since).select_related('lesson__teaching__subject').order_by('-date', 'lesson__period'))
    counts = Counter(a.status for a in att)
    total = len(att)
    ctx['att'] = {'total': total, 'present': counts['present'], 'absent': counts['absent'], 'late': counts['late'],
                  'excused': counts['excused'], 'rate': round(100 * (total - counts['absent']) / total) if total else None,
                  'issues': [a for a in att if a.status != 'present'][:30]}
    if 'monitoring.view' in granted:
        ctx['access_days'] = day_summaries(student, days=14)
        p = _presence_map([student.pk], today).get(student.pk)
        ctx['presence'] = _presence_state(p, today, 'Bugun kelmagan')
    if 'sensitive.grades' in granted:
        by = defaultdict(list)
        for g in student.grades.select_related('teaching__subject').order_by('-date', '-id')[:200]:
            by[g.teaching.subject.name].append(g)
        ctx['grades'] = [{'subject': n, 'avg': round(sum(g.score for g in gs) / len(gs), 1), 'count': len(gs),
                          'last': [g.score for g in gs[:10]]} for n, gs in sorted(by.items())]
    if 'payments.view' in granted:
        from billing.models import Discount
        from billing.services import account
        ctx['bill'] = account(student)
        ctx['payments'] = ctx['bill']['rows']
        ctx['debt'] = ctx['bill']['debt']
        ctx['all_discounts'] = Discount.objects.filter(is_active=True)
    return render(request, 'panel/student_detail.html', ctx)


_STUDENT_LABELS = {'last_name': 'Familiya', 'first_name': 'Ism', 'group': 'Sinf', 'birth_date': "Tug'ilgan sana", 'access_id': 'Face ID'}


def _student_state(student):
    return {'last_name': student.user.last_name, 'first_name': student.user.first_name,
            'group': student.group.name if student.group else '', 'birth_date': student.birth_date, 'access_id': student.access_id}


def _attach_parent(request, student, name, phone):
    """Telefon bo'yicha ota-onani biriktiradi: hisob bor bo'lsa o'shani (ustoz ham ota-ona bo'lishi mumkin), bo'lmasa yangisini ochadi."""
    digits = to_digits(phone)
    existing = User.objects.filter(phone_digits=digits).order_by('id')
    user = existing.filter(role=User.Role.TEACHER).first() or existing.first()
    created = user is None
    if created:
        user = User(username=digits, role=User.Role.PARENT, first_name=name, phone=phone)
        user.set_unusable_password()
        user.save()
    student.parents.add(user)
    audit.log(request, "Ota-ona biriktirdi", student, label=f"{student.user.get_full_name()} ← {user.get_full_name() or user.username}",
              details={'telefon': phone, 'yangi hisob': 'ha' if created else "yo'q (mavjud hisob)"}, target_type='student')
    return user, created


@panel_required('students.add')
def student_add(request):
    form = StudentForm(request.POST or None)
    upload = request.FILES.get('photo')
    if request.method == 'POST' and form.is_valid() and _photo_ok(form, upload):
        d = form.cleaned_data
        with transaction.atomic():
            user = User(username=_unique_username(f"{d['last_name']}-{d['first_name']}"), first_name=d['first_name'],
                        last_name=d['last_name'], role=User.Role.STUDENT)
            user.set_unusable_password()
            user.save()
            student = Student.objects.create(user=user, group=d['group'], birth_date=d['birth_date'], access_id=d['access_id'])
        audit.log(request, "O'quvchi qo'shdi", student, label=user.get_full_name(), target_type='student')
        if d.get('parent_phone'):
            parent, created = _attach_parent(request, student, d['parent_name'].strip(), d['parent_phone'])
            who = parent.get_full_name() or parent.username
            messages.success(request, f"{user.get_full_name()} qo'shildi, ota-onasi biriktirildi: {who}"
                             + (" (yangi hisob; kirish uchun \"Ota-onalar\" yorlig'ida bir martalik parol bering)." if created else " (mavjud hisob)."))
        else:
            messages.success(request, f"{user.get_full_name()} qo'shildi. Endi ota-onasini biriktiring.")
        if upload:
            apply_photo(request, user, upload, user.get_full_name())
        return redirect('panel:student', pk=student.pk)
    return render(request, 'panel/student_form.html', {'nav': 'students', 'form': form, 'title': "Yangi o'quvchi"})


@panel_required('students.change')
def student_edit(request, pk):
    student = get_object_or_404(Student.objects.select_related('user', 'group'), pk=pk)
    form = StudentForm(request.POST or None, instance=student)
    if request.method == 'POST' and form.is_valid():
        before = _student_state(student)
        d = form.cleaned_data
        with transaction.atomic():
            student.user.first_name, student.user.last_name = d['first_name'], d['last_name']
            student.user.save()
            student.group, student.birth_date, student.access_id = d['group'], d['birth_date'], d['access_id']
            student.save()
        diff = audit.changes(before, _student_state(student), _STUDENT_LABELS)
        if diff:
            audit.log(request, "O'quvchini o'zgartirdi", student, label=student.user.get_full_name(), details=diff, target_type='student')
        messages.success(request, "Saqlandi.")
        return redirect('panel:student', pk=student.pk)
    return render(request, 'panel/student_form.html', {'nav': 'students', 'form': form, 'student': student,
                                                       'title': student.user.get_full_name()})


@panel_required('students.change')
@require_POST
def parent_add(request, pk):
    student = get_object_or_404(Student, pk=pk)
    form = ParentForm(request.POST)
    if not form.is_valid():
        messages.error(request, ' '.join(e for errs in form.errors.values() for e in errs))
        return _back(student)
    user, created = _attach_parent(request, student, form.cleaned_data['name'], form.cleaned_data['phone'])
    messages.success(request, f"{user.get_full_name() or user.username} biriktirildi" + (" (yangi hisob; kirish uchun bir martalik parol bering)." if created else '.'))
    return _back(student)


@panel_required('students.change')
@require_POST
def parent_remove(request, pk, parent_id):
    student = get_object_or_404(Student, pk=pk)
    parent = get_object_or_404(student.parents, pk=parent_id)
    student.parents.remove(parent)
    audit.log(request, "Ota-onani ajratdi", student, label=f"{student.user.get_full_name()} ← {parent.get_full_name() or parent.username}", target_type='student')
    messages.success(request, 'Ota-ona o\'quvchidan ajratildi.')
    return _back(student)


@panel_required('students.change')
@require_POST
def parent_password(request, pk, parent_id):
    """Ota-onaga bir martalik parol (login — telefon raqami). Parol faqat shu yerda bir marta ko'rsatiladi."""
    student = get_object_or_404(Student, pk=pk)
    parent = get_object_or_404(student.parents, pk=parent_id)
    if parent.role != User.Role.PARENT or StaffProfile.objects.filter(user=parent).exists():
        messages.error(request, "Bu hisob ustoz yoki xodimga tegishli, uning parolini bu yerdan o'zgartirib bo'lmaydi.")
        return _back(student)
    password = issue_temp_password(parent)
    audit.log(request, 'Bir martalik parol berdi', parent, label=parent.get_full_name() or parent.username, target_type='user')
    messages.add_message(request, messages.SUCCESS,
                         f"{parent.get_full_name() or parent.username} — login: {parent.phone or parent.username} · bir martalik parol: {password}  "
                         "(faqat hozir ko'rinadi, ota-onaga yetkazing)", extra_tags='secret')
    return _back(student)


@panel_required('students.import')
def students_import(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    report = None
    if request.method == 'POST' and form.is_valid():
        upload = form.cleaned_data['file']
        group = form.cleaned_data['group'].strip() or group_name_from_filename(upload.name)
        if not group:
            form.add_error('group', "Sinf nomini yozing (fayl nomidan aniqlab bo'lmadi)")
        else:
            fd, path = tempfile.mkstemp(suffix='.xlsx')
            try:
                with os.fdopen(fd, 'wb') as out:
                    for chunk in upload.chunks():
                        out.write(chunk)
                report = import_students(path, group)
            except (ValueError, OSError, KeyError) as e:
                form.add_error('file', f"Faylni o'qib bo'lmadi: {e}")
            finally:
                os.unlink(path)
            if report:
                audit.log(request, "Excel'dan o'quvchilar yukladi", label=f"{group}: {report['created']} ta yangi", target_type='student',
                          details={'yangi': report['created'], 'oldindan bor': report['existing'], 'yangi ota-ona hisobi': report['parents_new']})
    return render(request, 'panel/students_import.html', {'nav': 'students', 'form': form, 'report': report})


# ------------------------------------------------------------------ maktabdan chiqarish / o'chirish

@require_POST
@panel_required('students.change')
def student_leave(request, pk):
    student = get_object_or_404(Student.objects.select_related('user', 'group'), pk=pk)
    if student.has_left:
        return redirect('panel:student', pk=pk)
    label, group = student.user.get_full_name(), student.group.name if student.group_id else ''
    student.leave()
    audit.log(request, "O'quvchini maktabdan chiqardi", student, label=label, target_type='student', details={'sinf': group})
    sync_in_background()
    messages.success(request, f"{label} maktabdan chiqarildi: ro'yxatlar va terminallardan olinadi. Ma'lumotlari saqlandi (Holat → Chiqqanlar).")
    return redirect('panel:students')


@require_POST
@panel_required('students.change')
def student_restore(request, pk):
    student = get_object_or_404(Student.objects.select_related('user'), pk=pk)
    if student.has_left:
        label = student.user.get_full_name()
        student.restore()
        audit.log(request, "O'quvchini qaytardi", student, label=label, target_type='student')
        sync_in_background()
        messages.success(request, f"{label} qaytarildi" + ('' if student.group_id else " (sinfi topilmadi, sinfni tanlang)") + '.')
    return redirect('panel:student', pk=pk)


@require_POST
@panel_required('students.change')
def student_delete(request, pk):
    """Butunlay o'chirish: faqat avval maktabdan chiqarilgan o'quvchi. Baho, davomat va to'lov tarixi ham o'chadi."""
    student = get_object_or_404(Student.objects.select_related('user'), pk=pk)
    if not student.has_left:
        messages.error(request, "Avval o'quvchini maktabdan chiqaring, so'ng butunlay o'chirish mumkin.")
        return redirect('panel:student', pk=pk)
    label, user = student.user.get_full_name(), student.user
    gone = {'baho': student.grades.count(), 'davomat': student.attendance.count(), "to'lov": student.fee_payments.count()}
    with transaction.atomic():
        if user.photo:
            user.photo.delete(save=False)
        user.delete()                    # Student va unga bog'liq yozuvlar ham o'chadi; ota-ona hisoblari qoladi
    audit.log(request, "O'quvchini butunlay o'chirdi", label=label, target_type='student', details=gone)
    sync_in_background()
    messages.success(request, f"{label} butunlay o'chirildi.")
    return redirect('panel:students')
