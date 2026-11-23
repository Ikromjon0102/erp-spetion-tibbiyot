import json
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from academics.constants import DAY_CODES, DAY_NAMES, PERIODS
from academics.models import Lesson
from accounts.child_data import presence
from accounts.permissions import role_required
from notices.views import announcements_for, with_read_flags

from .models import Attendance, Grade, Homework
from .teacher_auth import teacher_required_json


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return timezone.localdate()


def _natural_key(name):
    digits = ''.join(ch for ch in name if ch.isdigit())
    return (int(digits) if digits else 0, name)


# ---------------------------------------------------------------- ustoz sahifasi (faqat kirgan ustoz uchun)

@role_required('teacher')
@ensure_csrf_cookie
def teacher_home(request):
    """Ustoz sahifasi: jadval ma'lumotlari sahifaga joylanadi. O'quvchilar ismi va baholari alohida API orqali olinadi."""
    request.session['mode'] = 'teacher'
    user = request.user
    from .teacher_data import lesson_item, lessons_for, meals_today, orgs_payload, teacher_branches
    branches = teacher_branches(user)          # faqat o'z tashkilotlari: boshqa tashkilot darslari yuklanmaydi
    orgs = orgs_payload(branches)
    center_orgs = {o['id'] for o in orgs if o['center']}
    data = [lesson_item(l) for l in lessons_for(user, branches) if l.weekday < len(DAY_CODES)]
    # markazda faqat o'z guruhlari, maktab/bog'chada — filialdagi barcha sinflar
    data = [d for d in data if d['org'] not in center_orgs or d['teacherId'] == user.id]
    seen, classes = set(), []
    for d in sorted(data, key=lambda d: _natural_key(d['class'])):
        if d['classKey'] not in seen:
            seen.add(d['classKey'])
            classes.append({'key': d['classKey'], 'name': d['class'], 'org': d['org'], 'branch': d['branch']})
    # Ustoz o'zi ham ota-ona bo'lsa: farzandlarining bugungi holati bosh sahifada ko'rinadi
    kids = []
    for c in user.children.filter(user__is_active=True).select_related('user', 'group'):
        p = presence(c)
        kids.append({'name': f'{c.user.last_name} {c.user.first_name}'.strip(), 'group': c.group.name if c.group else '',
                     'state': p['state'], 'text': p['text'], 'url': reverse('student_detail', args=[c.pk])})
    from accounts.templatetags.app_extras import photo_url
    school = {
        'me': {'id': user.id, 'name': user.get_full_name() or user.username, 'photo': photo_url(user)},
        'kids': kids,
        'orgs': orgs,
        'classes': classes,
        'lessons': data,
        'meals': meals_today(branches),
        'days': DAY_CODES,
        'dayNames': dict(zip(DAY_CODES, DAY_NAMES)),
        'periods': [{'period': p, 'start': s, 'end': e} for p, s, e in PERIODS],
        'csrf': get_token(request),
    }
    return render(request, 'teacher/schedule.html', {'school': school})


# ---------------------------------------------------------------- davomat va baho API (kirgan ustoz uchun)

@teacher_required_json
def api_status(request):
    """Tanlangan kun uchun qaysi darslarda davomat olingan (faqat sonlar, ismlarsiz)."""
    day = _parse_date(request.GET.get('date'))
    rows = (Attendance.objects.filter(date=day, lesson__teaching__teacher=request.user)     # faqat o'z darslari
            .values('lesson_id').annotate(absent=Count('id', filter=Q(status=Attendance.Status.ABSENT))))
    return JsonResponse({'marks': {r['lesson_id']: {'absent': r['absent']} for r in rows}})


def _own_lesson(request, pk):
    """Faqat token egasi (ustoz) o'z darsini ocha oladi."""
    return get_object_or_404(
        Lesson.objects.select_related('teaching__group', 'teaching__subject', 'teaching__teacher'),
        pk=pk, active=True, teaching__teacher=request.teacher)


def _student_name(s):
    return f'{s.user.last_name} {s.user.first_name}'.strip() or s.user.username


def _group_students(lesson):
    return list(lesson.teaching.group.students.select_related('user').order_by('user__last_name', 'user__first_name'))


def _editable(lesson, day, user=None):
    """Davomat faqat dars kuni va dars boshlangandan keyin belgilanadi (sinov hisob uchun cheklov yo'q)."""
    if user is not None and user.is_demo:
        return True
    now = timezone.localtime()
    return day == now.date() and now.time() >= lesson.start


@teacher_required_json
def api_lesson(request, pk):
    lesson = _own_lesson(request, pk)
    day = _parse_date(request.GET.get('date'))
    marks = dict(Attendance.objects.filter(lesson=lesson, date=day).values_list('student_id', 'status'))
    return JsonResponse({
        'ok': True,
        'students': [{'id': s.id, 'name': _student_name(s), 's': marks.get(s.id, Attendance.Status.PRESENT)}
                     for s in _group_students(lesson)],
        'saved': bool(marks),
        'editable': _editable(lesson, day, request.teacher),
    })


@require_POST
@teacher_required_json
def api_lesson_save(request, pk):
    lesson = _own_lesson(request, pk)
    try:
        body = json.loads(request.body)
        rows = {int(r['id']): r['s'] for r in body['rows']}
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'ok': False, 'err': 'bad_rows'}, status=400)
    day = _parse_date(body.get('date'))
    if not _editable(lesson, day, request.teacher):
        return JsonResponse({'ok': False, 'err': 'time'})
    if not set(rows.values()) <= set(Attendance.Status.values):
        return JsonResponse({'ok': False, 'err': 'bad_rows'}, status=400)

    group_students = set(lesson.teaching.group.students.values_list('id', flat=True))
    with transaction.atomic():
        for sid, status in rows.items():
            if sid in group_students:
                Attendance.objects.update_or_create(
                    student_id=sid, lesson=lesson, date=day,
                    defaults={'status': status, 'marked_by': request.teacher})
    absent = sum(1 for s, st in rows.items() if s in group_students and st != Attendance.Status.PRESENT)
    return JsonResponse({'ok': True, 'absent': absent})


@teacher_required_json
def api_news(request):
    """Ustozga yo'naltirilgan e'lonlar (hamma / ustozlar; guruhga biriktirilgan bo'lsa — faqat o'z guruhlari)."""
    items = with_read_flags(request.teacher, announcements_for(request.teacher)[:30])
    return JsonResponse({'ok': True, 'items': [{
        'id': a.id, 'title': a.title, 'body': a.body, 'audience': a.get_audience_display(),
        'group': a.group.name if a.group else '',
        'date': timezone.localtime(a.created_at).strftime('%d.%m.%Y'),
        'read': a.is_read,
    } for a in items]})


def _grade_json(g):
    return {'id': g.id, 'student': _student_name(g.student), 'score': g.score, 'kind': g.get_kind_display(),
            'date': g.date.isoformat(), 'comment': g.comment}


# Darsda yo'q o'quvchi (kelmadi yoki sababli) — unga baho qo'yilmaydi. Kechikkan o'quvchi darsda hisoblanadi.
NOT_IN_CLASS = (Attendance.Status.ABSENT, Attendance.Status.EXCUSED)


@teacher_required_json
def api_grade(request, pk):
    lesson = _own_lesson(request, pk)
    day = _parse_date(request.GET.get('date'))
    away = dict(Attendance.objects.filter(lesson=lesson, date=day, status__in=NOT_IN_CLASS)
                .values_list('student_id', 'status'))
    # shu dars soatida qo'yilgan baholar: o'quvchi -> {id, score} (bir darsda bitta baho)
    given = {g.student_id: {'id': g.id, 'score': g.score}
             for g in Grade.objects.filter(lesson=lesson, date=day)}
    return JsonResponse({
        'ok': True,
        'students': [{'id': s.id, 'name': _student_name(s)} for s in _group_students(lesson)],
        'given': given,
        'away': away,          # darsda yo'q o'quvchilar: o'quvchi -> holat (ularga baho qo'yib bo'lmaydi)
        'editable': _editable(lesson, day, request.teacher),  # davomat bilan bir xil qoida
    })


JOURNAL_DATES = 12


@teacher_required_json
def api_journal(request, pk):
    """Baholar jurnali: shu sinf va fan bo'yicha oxirgi baho qo'yilgan kunlar ustunlarda, o'quvchilar qatorlarda. Faqat ko'rish."""
    lesson = _own_lesson(request, pk)
    grades = list(Grade.objects.filter(teaching=lesson.teaching).order_by('date', 'id').values('student_id', 'date', 'score', 'kind'))
    dates = sorted({g['date'] for g in grades})[-JOURNAL_DATES:]
    cells, totals = {}, {}
    for g in grades:
        t = totals.setdefault(g['student_id'], [0, 0])
        t[0] += g['score']
        t[1] += 1
        if g['date'] in dates:
            cells.setdefault(g['student_id'], {}).setdefault(g['date'].isoformat(), []).append({'s': g['score'], 'k': g['kind']})
    students = []
    for s in _group_students(lesson):
        total, count = totals.get(s.id, (0, 0))
        students.append({'id': s.id, 'name': _student_name(s), 'count': count, 'avg': round(total / count, 1) if count else None,
                         'g': cells.get(s.id, {})})
    return JsonResponse({'ok': True, 'dates': [{'d': d.isoformat(), 'label': d.strftime('%d.%m')} for d in dates], 'students': students})


@require_POST
@teacher_required_json
def api_grade_delete(request, pk):
    """Bahoni bekor qilish. `restore` berilsa — bahoni oldingi qiymatga qaytaradi (almashtirilgan bo'lsa),
    bo'lmasa o'chiradi. Faqat shu ustoz o'z darsida qo'ygan bahoga va faqat dars kuni (davomat qoidasi bilan bir xil)."""
    lesson = _own_lesson(request, pk)
    try:
        body = json.loads(request.body)
        grade_id = int(body['id'])
        restore = body.get('restore')
        restore = None if restore is None else int(restore)
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'ok': False, 'err': 'bad_rows'}, status=400)
    grades = Grade.objects.filter(pk=grade_id, teaching=lesson.teaching, created_by=request.teacher)
    grade = grades.first()
    if grade is None:
        return JsonResponse({'ok': False})
    if not _editable(lesson, grade.date, request.teacher):
        return JsonResponse({'ok': False, 'err': 'time'})
    if restore is None:
        deleted, _ = grades.delete()
        return JsonResponse({'ok': bool(deleted)})
    if not 1 <= restore <= 5:
        return JsonResponse({'ok': False, 'err': 'bad_score'})
    return JsonResponse({'ok': bool(grades.update(score=restore))})


@require_POST
@teacher_required_json
def api_grade_save(request, pk):
    """Baho qo'yadi. Bir darsda o'quvchiga faqat bitta baho: qayta qo'yilsa, mavjud baho almashadi."""
    lesson = _own_lesson(request, pk)
    try:
        body = json.loads(request.body)
        score, student_id = int(body['score']), int(body['student'])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'ok': False, 'err': 'bad_rows'}, status=400)
    if not 1 <= score <= 5:
        return JsonResponse({'ok': False, 'err': 'bad_score'})
    day = _parse_date(body.get('date'))
    if not _editable(lesson, day, request.teacher):   # davomat bilan bir xil: faqat dars kuni va dars boshlangach
        return JsonResponse({'ok': False, 'err': 'time'})
    student = get_object_or_404(lesson.teaching.group.students.select_related('user'), pk=student_id)
    if Attendance.objects.filter(student=student, lesson=lesson, date=day, status__in=NOT_IN_CLASS).exists():
        return JsonResponse({'ok': False, 'err': 'absent'})   # darsda yo'q o'quvchiga baho qo'yilmaydi
    kind = body.get('kind')
    kind = kind if kind in Grade.Kind.values else Grade.Kind.CURRENT
    with transaction.atomic():
        grade, created = Grade.objects.select_for_update().get_or_create(
            student=student, lesson=lesson, date=day,
            defaults={'teaching': lesson.teaching, 'score': score, 'kind': kind, 'created_by': request.teacher,
                      'comment': str(body.get('comment') or '')[:200]})
        previous = None
        if not created:
            previous = grade.score
            grade.score, grade.kind = score, kind
            grade.save(update_fields=['score', 'kind'])
    return JsonResponse({'ok': True, 'grade': _grade_json(grade), 'created': created, 'previous': previous})


# ---------------------------------------------------------------- uy vazifasi (matn; ota-ona ko'radi)

HW_MAX_LEN = 2000


def _hw_editable(hw, user):
    """Vazifani berilgan kunning oxirigacha tahrirlash/o'chirish mumkin (sinov hisob uchun cheklov yo'q)."""
    return user.is_demo or hw.assigned_on == timezone.localdate()


def _hw_json(hw, user):
    return {'id': hw.id, 'text': hw.text, 'due': hw.due_date.isoformat(), 'assigned': hw.assigned_on.isoformat(),
            'editable': _hw_editable(hw, user)}


def _next_lesson_date(teaching):
    """Shu fan shu sinfda keyingi marta qachon o'tilishi (topshirish sanasi uchun taklif)."""
    weekdays = set(Lesson.objects.filter(teaching=teaching, active=True).values_list('weekday', flat=True))
    today = timezone.localdate()
    for n in range(1, 15):
        d = today + timedelta(days=n)
        if d.weekday() in weekdays:
            return d
    return today + timedelta(days=1)


def _parse_hw(body, earliest):
    """(matn, topshirish sanasi, xato) — xato bo'lsa birinchi ikkitasi None."""
    text = str(body.get('text') or '').strip()
    if not text or len(text) > HW_MAX_LEN:
        return None, None, 'bad_text'
    try:
        due = date.fromisoformat(str(body.get('due')))
    except ValueError:
        return None, None, 'bad_date'
    if due < earliest:
        return None, None, 'past_date'
    return text, due, None


@teacher_required_json
def api_hw(request, pk):
    lesson = _own_lesson(request, pk)
    items = Homework.objects.filter(teaching=lesson.teaching)[:15]
    return JsonResponse({'ok': True, 'items': [_hw_json(h, request.teacher) for h in items],
                         'suggested': _next_lesson_date(lesson.teaching).isoformat()})


@require_POST
@teacher_required_json
def api_hw_save(request, pk):
    lesson = _own_lesson(request, pk)
    try:
        body = json.loads(request.body)
    except ValueError:
        return JsonResponse({'ok': False, 'err': 'bad_rows'}, status=400)
    today = timezone.localdate()
    text, due, err = _parse_hw(body, today)
    if err:
        return JsonResponse({'ok': False, 'err': err})
    hw = Homework.objects.create(teaching=lesson.teaching, text=text, due_date=due, assigned_on=today,
                                 created_by=request.teacher)
    return JsonResponse({'ok': True, 'item': _hw_json(hw, request.teacher)})


@require_POST
@teacher_required_json
def api_hw_update(request, pk, hid):
    lesson = _own_lesson(request, pk)
    hw = get_object_or_404(Homework, pk=hid, teaching=lesson.teaching)
    if not _hw_editable(hw, request.teacher):
        return JsonResponse({'ok': False, 'err': 'locked'})
    try:
        body = json.loads(request.body)
    except ValueError:
        return JsonResponse({'ok': False, 'err': 'bad_rows'}, status=400)
    text, due, err = _parse_hw(body, hw.assigned_on)
    if err:
        return JsonResponse({'ok': False, 'err': err})
    hw.text, hw.due_date = text, due
    hw.save(update_fields=['text', 'due_date', 'updated_at'])
    return JsonResponse({'ok': True, 'item': _hw_json(hw, request.teacher)})


@require_POST
@teacher_required_json
def api_hw_delete(request, pk, hid):
    lesson = _own_lesson(request, pk)
    hw = get_object_or_404(Homework, pk=hid, teaching=lesson.teaching)
    if not _hw_editable(hw, request.teacher):
        return JsonResponse({'ok': False, 'err': 'locked'})
    hw.delete()
    return JsonResponse({'ok': True})
