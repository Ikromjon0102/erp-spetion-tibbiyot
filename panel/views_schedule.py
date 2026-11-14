import re
from collections import Counter

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from academics.models import Group, Lesson, Subject, Teaching
from accounts.models import User

from . import audit
from .access import panel_required

DAYS = list(Lesson.Weekday.choices)
TIME = forms.TimeInput(attrs={'type': 'time'}, format='%H:%M')


def _natural(name):
    m = re.match(r'\s*(\d+)', name or '')
    return (int(m.group(1)) if m else 999, name or '')


def teachers_active():
    return User.objects.filter(role=User.Role.TEACHER, is_active=True, is_demo=False).order_by('last_name', 'first_name')


class LessonForm(forms.Form):
    group = forms.ModelChoiceField(label='Sinf', queryset=Group.objects.all(), empty_label='— sinf —')
    subject = forms.ModelChoiceField(label='Fan', queryset=Subject.objects.all(), required=False, empty_label='— fan tanlang —')
    new_subject = forms.CharField(label='Yoki yangi fan nomi', max_length=100, required=False)
    teacher = forms.ModelChoiceField(label='Ustoz', queryset=User.objects.none(), required=False, empty_label='— ustozsiz —')
    weekday = forms.TypedChoiceField(label='Hafta kuni', choices=DAYS, coerce=int)
    period = forms.IntegerField(label='Dars soati (1–8)', min_value=1, max_value=8)
    start = forms.TimeField(label='Boshlanishi', widget=TIME)
    end = forms.TimeField(label='Tugashi', widget=TIME)
    room = forms.CharField(label='Xona', max_length=30, required=False)

    def __init__(self, *args, lesson=None, **kwargs):
        self.lesson = lesson
        super().__init__(*args, **kwargs)
        self.fields['teacher'].queryset = teachers_active()
        self.fields['teacher'].label_from_instance = lambda u: f'{u.last_name} {u.first_name}'.strip() or u.username

    def clean(self):
        d = super().clean()
        if self.errors:
            return d
        if not d.get('subject') and not (d.get('new_subject') or '').strip():
            self.add_error('subject', 'Fanni tanlang yoki yangi fan nomini yozing')
        if d['end'] <= d['start']:
            self.add_error('end', "Tugash vaqti boshlanishdan keyin bo'lsin")
            return d
        clash = Lesson.objects.filter(active=True, weekday=d['weekday'], start__lt=d['end'], end__gt=d['start'])
        if self.lesson is not None:
            clash = clash.exclude(pk=self.lesson.pk)
        same_group = clash.filter(teaching__group=d['group']).select_related('teaching__subject', 'teaching__teacher').first()
        if same_group:
            raise forms.ValidationError(f"Bu sinfda shu vaqtda dars bor: {same_group.teaching.subject} "
                                        f"({same_group.start:%H:%M}–{same_group.end:%H:%M})")
        if d.get('teacher'):
            busy = clash.filter(teaching__teacher=d['teacher']).select_related('teaching__group', 'teaching__subject').first()
            if busy:
                raise forms.ValidationError(f"Ustozda shu vaqtda boshqa dars bor: {busy.teaching.group} — {busy.teaching.subject} "
                                            f"({busy.start:%H:%M}–{busy.end:%H:%M})")
        return d


def _period_times():
    """Har bir dars soati uchun eng ko'p uchraydigan vaqt (formani oldindan to'ldirish uchun)."""
    seen = {}
    for p, s, e in Lesson.objects.filter(active=True).values_list('period', 'start', 'end'):
        seen.setdefault(p, Counter())[(s.strftime('%H:%M'), e.strftime('%H:%M'))] += 1
    return {p: c.most_common(1)[0][0] for p, c in seen.items()}


@panel_required('schedule.view')
def schedule(request):
    groups = sorted(Group.objects.all(), key=lambda g: _natural(g.name))
    teachers = list(teachers_active())
    sinf, ustoz = request.GET.get('sinf', ''), request.GET.get('ustoz', '')
    group = next((g for g in groups if str(g.pk) == sinf), None)
    teacher = next((t for t in teachers if str(t.pk) == ustoz), None) if not group else None
    if not group and not teacher and groups:
        group = groups[0]
    qs = Lesson.objects.filter(active=True).select_related('teaching__subject', 'teaching__group', 'teaching__teacher')
    qs = qs.filter(teaching__group=group) if group else qs.filter(teaching__teacher=teacher) if teacher else qs.none()
    cells, periods = {}, set()
    for les in qs.order_by('weekday', 'period', 'start'):
        cells.setdefault((les.period, les.weekday), []).append(les)
        periods.add(les.period)
    times = _period_times()
    grid = [{'period': p, 'time': times.get(p), 'days': [cells.get((p, d), []) for d, _ in DAYS]} for p in sorted(periods)]
    return render(request, 'panel/schedule.html', {'nav': 'schedule', 'groups': groups, 'teachers': teachers, 'group': group, 'teacher': teacher,
                                                   'grid': grid, 'days': DAYS, 'total': sum(len(v) for v in cells.values())})


def _teaching_for(d):
    subject = d['subject'] or Subject.objects.get_or_create(name=d['new_subject'].strip())[0]
    teaching, _ = Teaching.objects.get_or_create(teacher=d.get('teacher') or None, subject=subject, group=d['group'])
    return teaching


@panel_required('schedule.change')
def lesson_edit(request, pk=None):
    lesson = get_object_or_404(Lesson.objects.select_related('teaching__subject', 'teaching__group', 'teaching__teacher'), pk=pk, active=True) if pk else None
    initial = {}
    if lesson:
        t = lesson.teaching
        initial = {'group': t.group, 'subject': t.subject, 'teacher': t.teacher, 'weekday': lesson.weekday, 'period': lesson.period,
                   'start': lesson.start, 'end': lesson.end, 'room': lesson.room}
    else:
        for key, field in (('sinf', 'group'), ('ustoz', 'teacher'), ('kun', 'weekday'), ('soat', 'period')):
            if request.GET.get(key):
                initial[field] = request.GET[key]
        times = _period_times().get(int(initial['period'])) if str(initial.get('period', '')).isdigit() else None
        if times:
            initial['start'], initial['end'] = times
    form = LessonForm(request.POST or None, initial=initial, lesson=lesson)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        teaching = _teaching_for(d)
        values = {'teaching': teaching, 'weekday': d['weekday'], 'period': d['period'], 'start': d['start'], 'end': d['end'], 'room': d['room']}
        if lesson:
            before = f'{lesson.teaching.subject} · {lesson.get_weekday_display()} {lesson.period}-soat {lesson.start:%H:%M}'
            for k, v in values.items():
                setattr(lesson, k, v)
            lesson.save()
            audit.log(request, "Darsni o'zgartirdi", lesson, label=f'{teaching.group} — {teaching.subject}', details={'eski': before}, target_type='lesson')
        else:
            lesson = Lesson.objects.create(**values)
            audit.log(request, "Dars qo'shdi", lesson, label=f'{teaching.group} — {teaching.subject}', target_type='lesson')
        messages.success(request, 'Saqlandi')
        return redirect(f"{redirect('panel:schedule').url}?sinf={teaching.group_id}")
    return render(request, 'panel/lesson_form.html', {'nav': 'schedule', 'form': form, 'lesson': lesson, 'period_times': _period_times(),
                                                      'title': 'Darsni tahrirlash' if lesson else "Dars qo'shish"})


@require_POST
@panel_required('schedule.change')
def lesson_delete(request, pk):
    lesson = get_object_or_404(Lesson.objects.select_related('teaching__subject', 'teaching__group'), pk=pk, active=True)
    group_id = lesson.teaching.group_id
    lesson.active = False            # davomat va baholar tarixi saqlanishi uchun o'chirilmaydi, faqat jadvaldan chiqariladi
    lesson.save(update_fields=['active'])
    audit.log(request, "Darsni jadvaldan olib tashladi", lesson, label=f'{lesson.teaching.group} — {lesson.teaching.subject}', target_type='lesson')
    messages.success(request, "Dars jadvaldan olib tashlandi (davomat va baho tarixi saqlanadi)")
    return redirect(f"{redirect('panel:schedule').url}?sinf={group_id}")
