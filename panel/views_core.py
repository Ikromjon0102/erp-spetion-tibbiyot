from datetime import timedelta

from django.core.paginator import Paginator
from django.db.models import Count, F, Sum
from django.shortcuts import render
from django.utils import timezone

from access.models import AccessEvent, Device
from academics.models import Lesson
from accounts.models import Student
from journal.models import Attendance
from notices.models import Announcement
from org.scope import scope_announcements, scope_audit, scope_devices, scope_students, scope_via_group, scope_via_student
from notices.services import read_summary

from . import audit as audit_helpers
from .access import perms_of, panel_required
from .models import AuditLog

DEVICE_ALIVE = timedelta(minutes=10)


def real_students(user=None):
    """Panelda ko'rinadigan o'quvchilar: sinov hisobining namunaviy o'quvchilari (sinov_...) chiqarib tashlanadi.
    `user` berilsa, faqat uning filiallari o'quvchilari."""
    qs = Student.objects.exclude(user__username__startswith='sinov_').filter(user__is_active=True)
    return scope_students(qs, user) if user is not None else qs


def missing_attendance(today, now, user=None):
    """Boshlangan, lekin davomat olinmagan darslar (sinov ustozlarining darslari hisobga olinmaydi)."""
    if today.weekday() > 5:
        return []
    lessons = (Lesson.objects.filter(active=True, weekday=today.weekday(), start__lte=now.time(),
                                     teaching__group__students__isnull=False)
               .exclude(teaching__teacher__is_demo=True)
               .select_related('teaching__group', 'teaching__subject', 'teaching__teacher').distinct().order_by('start', 'period'))
    if user is not None:
        lessons = scope_via_group(lessons, user, 'teaching__group')
    taken = set(Attendance.objects.filter(date=today).values_list('lesson_id', flat=True))
    return [l for l in lessons if l.id not in taken]


def _units_summary(request, granted, today):
    """Bir nechta filial (yoki tashkilot) bilan ishlaydigan xodim uchun bosh sahifadagi jadval: har filial alohida —
    o'quvchilar, bugun kelganlar, shu oy tushumi va (ruxsat bo'lsa) xarajati. Qator bosilsa o'sha filial tanlanadi."""
    from .hubs import counts, hub_level
    level = hub_level(getattr(request, 'scope', None))
    if level is None:
        return None
    lv = level[0]
    units = ([{'pk': o['org'].pk, 'name': o['org'].label, 'color': o['org'].brand_color, 'scope': f"org-{o['org'].pk}"} for o in level[1]]
             if lv == 'org' else
             [{'pk': b.pk, 'name': b.name, 'color': level[1]['org'].brand_color, 'scope': f'branch-{b.pk}'} for b in level[1]['branches']])
    students = counts('students', request.user, lv)
    arrived = {}
    if 'monitoring.view' in granted:
        key = 'student__branch' + ('__organization' if lv == 'org' else '')
        events = scope_via_student(AccessEvent.objects.filter(direction='in', occurred_at__date=today, student__isnull=False), request.user)
        arrived = {r[key]: r['n'] for r in events.values(key).annotate(n=Count('student', distinct=True)).order_by()}
    income = counts('finance', request.user, lv) if 'payments.view' in granted else None
    expense = counts('expenses', request.user, lv) if 'expenses.view' in granted else None
    for u in units:
        u.update(students=students.get(u['pk'], 0), arrived=arrived.get(u['pk']) if arrived or 'monitoring.view' in granted else None,
                 income=income.get(u['pk'], 0) if income is not None else None, expense=expense.get(u['pk'], 0) if expense is not None else None)
    return {'level': lv, 'rows': units, 'monitoring': 'monitoring.view' in granted, 'income': income is not None, 'expense': expense is not None}


@panel_required()
def dashboard(request):
    from .access import is_owner
    if is_owner(request.user) and not request.GET.get('kunlik'):
        from .views_owner import owner_home
        return owner_home(request)
    granted = perms_of(request.user)
    today, now = timezone.localdate(), timezone.localtime()
    ctx = {'nav': 'dashboard', 'today': today, 'day_off': today.weekday() > 5}
    total = real_students(request.user).count()
    if 'students.view' in granted:
        ctx['students_total'] = total
    if 'monitoring.view' in granted:
        events = scope_via_student(AccessEvent.objects.filter(direction='in', occurred_at__date=today, student__isnull=False), request.user)
        arrived = set(events.exclude(student__user__username__startswith='sinov_').values_list('student_id', flat=True))
        ctx['arrived'], ctx['not_arrived'] = len(arrived), max(total - len(arrived), 0)
        missing = missing_attendance(today, now, request.user)
        ctx['missing_count'], ctx['missing'] = len(missing), missing[:8]
        ctx['devices'] = [{'device': d, 'ok': bool(d.is_active and d.last_seen and now - d.last_seen < DEVICE_ALIVE)}
                          for d in scope_devices(Device.objects.all(), request.user)]
        ctx['devices_down'] = sum(1 for d in ctx['devices'] if d['device'].is_active and not d['ok'])
    if 'payments.view' in granted:
        from .views_finance import totals
        ctx.update(totals(request.user))
    ctx['units'] = _units_summary(request, granted, today)
    if 'announcements.view' in granted:
        latest = scope_announcements(Announcement.objects.exclude(title__startswith='[Sinov]'), request.user).order_by('-created_at').first()
        if latest:
            total_r, read = read_summary(latest)
            ctx['latest_news'] = {'a': latest, 'total': total_r, 'read': read}
    return render(request, 'panel/dashboard.html', ctx)


@panel_required('audit.view')
def audit_list(request):
    from org.scope import hidden_actor_ids
    from .access import is_owner
    qs = scope_audit(AuditLog.objects.all(), request.user)
    who, verb = request.GET.get('kim', '').strip(), request.GET.get('amal', '').strip()
    hidden = set() if is_owner(request.user) else hidden_actor_ids()     # founder ismi boshqa xodimlarga ko'rinmaydi
    if who:
        qs = qs.filter(actor_name__icontains=who).exclude(actor_id__in=hidden)
    if verb:
        qs = qs.filter(verb__icontains=verb)
    page = Paginator(qs, 40).get_page(request.GET.get('page'))
    for entry in page:
        entry.lines = audit_helpers.lines(entry.details)
        if entry.actor_id in hidden:
            entry.actor_name = 'Rahbariyat'

    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'panel/audit.html', {'nav': 'audit', 'page': page, 'who': who, 'verb': verb, 'qs': params.urlencode()})
