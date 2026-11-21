"""Bola sahifasi (ota-ona / o'quvchi) uchun ma'lumotlarni tayyorlash: baholar, davomat, jadval, to'lov, holat."""
from collections import Counter, defaultdict
from datetime import timedelta

from django.utils import timezone

from access.services import day_summaries, is_break_time
from academics.constants import DAY_CODES, DAY_NAMES
from academics.models import Lesson
from journal.models import Attendance, Homework, HomeworkRead
from notices.views import announcements_for, with_read_flags

STATUS_UI = {  # holat -> (yozuv, CSS sinf)
    Attendance.Status.PRESENT: ('Keldi', 'ok'),
    Attendance.Status.ABSENT: ('Kelmadi', 'bad'),
    Attendance.Status.LATE: ('Kech', 'late'),
    Attendance.Status.EXCUSED: ('Sababli', 'exc'),
}
ATT_DAYS = 30
HW_KEEP_DAYS = 30        # topshirish sanasi shundan eski vazifalar ko'rsatilmaydi
HW_PER_SUBJECT = 10


def homework_for(student, viewer, is_guardian):
    """Sinfdagi vazifalar fan bo'yicha. O'qilmaganlar (ota-ona/o'quvchi uchun) qizil nuqta bilan ko'rsatiladi."""
    if not student.group_id:
        return {}, 0
    today = timezone.localdate()
    items = list(Homework.objects.filter(teaching__group_id=student.group_id,
                                         due_date__gte=today - timedelta(days=HW_KEEP_DAYS))
                 .select_related('teaching__subject', 'teaching__teacher').order_by('-assigned_on', '-id'))
    track = is_guardian or viewer.is_student   # ustoz/admin ko'rganda nuqta kerak emas
    seen = set(HomeworkRead.objects.filter(user=viewer, homework__in=items).values_list('homework_id', flat=True)) if track else set()
    by_subject, unread = defaultdict(list), 0
    for h in items:
        name = h.teaching.subject.name
        if len(by_subject[name]) >= HW_PER_SUBJECT:
            continue
        read = h.pk in seen or not track
        unread += 0 if read else 1
        teacher = h.teaching.teacher
        by_subject[name].append({
            'id': h.pk, 'text': h.text, 'read': read, 'past': h.due_date < today,
            'due': h.due_date.strftime('%d.%m'), 'due_wd': (DAY_CODES + ['Ya'])[h.due_date.weekday()],
            'days_left': (h.due_date - today).days, 'assigned': h.assigned_on.strftime('%d.%m'),
            'teacher': (teacher.get_full_name() or teacher.username) if teacher else '',
        })
    return dict(by_subject), unread


def grade_class(avg):
    return 'g5' if avg >= 4.5 else 'g4' if avg >= 3.5 else 'g3' if avg >= 2.5 else 'g2'


def presence(student, now=None):
    """Bugungi holat: maktabdami, ketdimi yoki hali kelmaganmi (Hikvision kirish-chiqishidan)."""
    now = now or timezone.localtime()
    today = now.date()
    row = next((r for r in day_summaries(student, days=1) if r['date'] == today), None)
    if row and row['arrived'] and not row['left']:
        return {'state': 'in', 'text': f"Maktabda · {row['arrived']:%H:%M} dan beri", 'arrived': row['arrived'], 'left': None}
    if row and row['left'] and is_break_time(now):      # chiqish xabarlari vaqtidan oldin: tanaffus, uyga ketmagan
        sub = f"Kelgan: {row['arrived']:%H:%M}" if row['arrived'] else ''
        return {'state': 'out', 'text': f"Tashqarida · {row['left']:%H:%M} dan", 'sub': sub,
                'arrived': row['arrived'], 'left': None}
    if row and row['left']:
        sub = f"Kelgan: {row['arrived']:%H:%M}" if row['arrived'] else ''
        return {'state': 'out', 'text': f"Uyga ketdi · {row['left']:%H:%M}", 'sub': sub,
                'arrived': row['arrived'], 'left': row['left']}
    if today.weekday() == 6:
        return {'state': 'off', 'text': 'Bugun dam olish kuni'}
    if now.hour >= 9:
        return {'state': 'wait', 'text': 'Hali maktabga kelmagan'}
    return {'state': 'none', 'text': 'Hali kelganligi qayd etilmagan'}


def _average(scores):
    return sum(scores) / len(scores) if scores else None


def attendance_rate(student, today=None):
    today = today or timezone.localdate()
    counts = Counter(student.attendance.filter(date__gte=today - timedelta(days=ATT_DAYS - 1))
                     .values_list('status', flat=True))
    total = sum(counts.values())
    return round(100 * (total - counts[Attendance.Status.ABSENT]) / total) if total else None


def overview(student):
    """Bolalar ro'yxati kartasi uchun qisqa ma'lumot."""
    avg = _average(list(student.grades.values_list('score', flat=True)))
    return {'presence': presence(student), 'avg': f'{avg:.1f}' if avg is not None else None,
            'avg_class': grade_class(avg) if avg is not None else '', 'rate': attendance_rate(student)}


def child_context(student, viewer):
    now = timezone.localtime()
    today = now.date()

    # --- baholar
    grades = list(student.grades.select_related('teaching__subject').order_by('-date', '-id')[:300])
    by_subject = defaultdict(list)
    for g in grades:
        by_subject[g.teaching.subject.name].append(g)
    subjects = []
    for name in sorted(by_subject):
        items = by_subject[name]
        avg = _average([g.score for g in items])
        subjects.append({
            'name': name, 'avg': f'{avg:.1f}', 'avg_class': grade_class(avg), 'count': len(items),
            'recent': [g.score for g in items[:8]],
            'items': [{'date': g.date, 'score': g.score, 'kind': g.get_kind_display(), 'comment': g.comment}
                      for g in items],
        })
    overall = _average([g.score for g in grades])
    recent_grades = [{'subject': g.teaching.subject.name, 'score': g.score, 'date': g.date, 'kind': g.get_kind_display()}
                     for g in grades[:5]]

    # --- darslardagi davomat (so'nggi 30 kun)
    att = list(student.attendance.filter(date__gte=today - timedelta(days=ATT_DAYS - 1))
               .select_related('lesson__teaching__subject').order_by('-date', 'lesson__period'))
    counts = Counter(a.status for a in att)
    total = len(att)
    absent = counts[Attendance.Status.ABSENT]
    att_stats = {
        'total': total, 'absent': absent, 'late': counts[Attendance.Status.LATE],
        'excused': counts[Attendance.Status.EXCUSED], 'present': counts[Attendance.Status.PRESENT],
        'rate': round(100 * (total - absent) / total) if total else None,
    }
    issues = [{'date': a.date, 'period': a.lesson.period, 'subject': a.lesson.teaching.subject.name,
               'label': STATUS_UI[a.status][0], 'cls': STATUS_UI[a.status][1]}
              for a in att if a.status != Attendance.Status.PRESENT][:40]
    marks_today = {a.lesson_id: a.status for a in att if a.date == today}

    # --- dars jadvali
    days = [{'idx': i, 'code': c, 'name': n, 'lessons': [], 'is_today': i == today.weekday()}
            for i, (c, n) in enumerate(zip(DAY_CODES, DAY_NAMES))]
    if student.group_id:
        lessons = (Lesson.objects.filter(teaching__group=student.group_id, active=True)
                   .select_related('teaching__subject', 'teaching__teacher').order_by('weekday', 'period'))
        for l in lessons:
            if l.weekday >= len(days):
                continue
            teacher = l.teaching.teacher
            mark = marks_today.get(l.id) if l.weekday == today.weekday() else None
            days[l.weekday]['lessons'].append({
                'id': l.id, 'period': l.period, 'start': f'{l.start:%H:%M}', 'end': f'{l.end:%H:%M}',
                'subject': l.teaching.subject.name, 'room': l.room,
                'teacher': (teacher.get_full_name() or teacher.username) if teacher else '',
                'mark': STATUS_UI[mark] if mark else None,
            })
    today_idx = today.weekday() if today.weekday() < len(days) else None
    is_guardian = student.parents.filter(pk=viewer.pk).exists()
    homework, hw_unread = homework_for(student, viewer, is_guardian)
    for day in days:
        for lesson in day['lessons']:
            hws = homework.get(lesson['subject'], [])
            lesson['hw'] = len(hws)
            lesson['hw_unread'] = sum(1 for h in hws if not h['read'])

    # --- to'lov: faqat ota-ona va ma'muriyatga
    bill, payments, debt = None, None, 0
    if is_guardian or viewer.is_school_admin:
        from billing.services import account
        bill = account(student)
        payments, debt = bill['rows'], bill['debt']

    # --- e'lonlar va aka-uka almashtirgich
    news = []
    if is_guardian or viewer.is_parent or viewer.is_student:
        news = [{'id': a.pk, 'read': a.is_read, 'title': a.title, 'body': a.body, 'date': a.created_at, 'group': a.group}
                for a in with_read_flags(viewer, announcements_for(viewer)[:3])]
    siblings = []
    if is_guardian:
        siblings = list(viewer.children.filter(user__is_active=True).select_related('user', 'branch__organization'))
        siblings = siblings if len(siblings) > 1 else []

    return {
        'student': student, 'today': today, 'presence': presence(student, now),
        'avg': f'{overall:.1f}' if overall is not None else None,
        'avg_class': grade_class(overall) if overall is not None else '',
        'n_grades': len(grades), 'subjects': subjects, 'recent_grades': recent_grades,
        'att_stats': att_stats, 'issues': issues, 'access_days': day_summaries(student),
        'days': days, 'today_idx': today_idx, 'default_day': today_idx if today_idx is not None else 0,
        'today_lessons': days[today_idx]['lessons'] if today_idx is not None else [],
        'payments': payments, 'debt': debt, 'bill': bill, 'news': news, 'siblings': siblings,
        'homework': homework, 'hw_unread': hw_unread,
    }
