"""«Hammasi» ish maydonida ro'yxat o'rniga tashkilot kartalari (hub): minglab yozuv bir sahifaga to'kilmaydi.
Kartani bossangiz o'sha tashkilot tanlanadi va odatiy ro'yxat ochiladi. Qidiruv yoki filtr bo'lsa (`?q=...`) — hamma tashkilot bo'yicha ro'yxat.
Har bo'lim o'z raqamini ko'rsatadi: o'quvchilar soni, shu oy tushumi, shu oy xarajati va hokazo."""
from collections import defaultdict
from decimal import Decimal
from functools import wraps

from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone


def _default_org():
    from org.models import default_branch
    b = default_branch()
    return b.organization_id, b.pk


def _by_org(rows, org_key, value='n'):
    """[{org_key: id|None, value: n}] -> {org_id: n} (tashkilotsiz yozuv asosiy tashkilotga)."""
    default_org, _ = _default_org()
    out = defaultdict(int)
    for r in rows:
        out[r[org_key] or default_org] += r[value] or 0
    return dict(out)


# ---- hisoblagichlar: user -> (by_org {org_id: son}, by_branch {branch_id: son}) ----

def _students(user):
    from .views_core import real_students
    default_org, default_branch_id = _default_org()
    by_org, by_branch = defaultdict(int), {}
    for r in real_students(user).values('branch_id', 'branch__organization_id').annotate(n=Count('pk')):
        by_org[r['branch__organization_id'] or default_org] += r['n']
        by_branch[r['branch_id'] or default_branch_id] = r['n']
    return dict(by_org), by_branch


def _teachers(user):
    from .views_teachers import teachers_qs
    rows = teachers_qs(user).values('branches__organization_id').annotate(n=Count('pk', distinct=True))
    return _by_org(rows, 'branches__organization_id'), {}


def _staff(user):
    from org.scope import scope_staff
    from .models import StaffProfile
    rows = scope_staff(StaffProfile.objects.all(), user).values('user__branches__organization_id').annotate(n=Count('pk', distinct=True))
    return _by_org(rows, 'user__branches__organization_id'), {}


def _parents(user):
    from .views_parents import parents_qs
    rows = parents_qs(user).values('children__branch__organization_id').annotate(n=Count('pk', distinct=True))
    return _by_org(rows, 'children__branch__organization_id'), {}


def _groups(user):
    from academics.models import Group
    from org.scope import scope_groups
    rows = scope_groups(Group.objects.all(), user).values('branch__organization_id').annotate(n=Count('pk'))
    return _by_org(rows, 'branch__organization_id'), {}


def _lessons(user):
    from academics.models import Lesson
    from org.scope import scope_via_group
    rows = (scope_via_group(Lesson.objects.filter(active=True), user, 'teaching__group')
            .values('teaching__group__branch__organization_id').annotate(n=Count('pk')))
    return _by_org(rows, 'teaching__group__branch__organization_id'), {}


def _income(user):
    from billing.models import Payment
    from org.scope import scope_via_student
    d = timezone.localdate()
    qs = scope_via_student(Payment.objects.filter(voided=False, paid_on__year=d.year, paid_on__month=d.month), user)
    return _by_org(qs.values('student__branch__organization_id').annotate(n=Sum('amount')), 'student__branch__organization_id'), {}


def _expenses(user):
    from finance.models import Expense
    from org.scope import scope_by_branch
    d = timezone.localdate()
    qs = scope_by_branch(Expense.objects.filter(date__year=d.year, date__month=d.month), user)
    return _by_org(qs.values('branch__organization_id').annotate(n=Sum('amount')), 'branch__organization_id'), {}


def _payroll(user):
    from finance.models import Payslip
    from org.scope import scope_by_branch
    d = timezone.localdate().replace(day=1)
    out = defaultdict(Decimal)
    for ps in scope_by_branch(Payslip.objects.filter(month=d).select_related('branch'), user).prefetch_related('payments'):
        out[ps.branch.organization_id] += max(ps.remaining, Decimal(0))
    return {k: int(v) for k, v in out.items()}, {}


def _news(user):
    from notices.models import Announcement
    from org.scope import scope_announcements
    rows = (scope_announcements(Announcement.objects.exclude(title__startswith='[Sinov]'), user)
            .values('branch__organization_id').annotate(n=Count('pk')))
    return _by_org(rows, 'branch__organization_id'), {}


def _devices(user):
    from access.models import Device
    from org.scope import scope_devices
    rows = scope_devices(Device.objects.all(), user).values('branch__organization_id').annotate(n=Count('pk'))
    return _by_org(rows, 'branch__organization_id'), {}


#   kalit: (sarlavha, birlik, izoh, nav, hisoblagich, filiallar ko'rsatilsinmi, qidiruv bormi)
HUBS = {
    'students': ("O'quvchilar", "o'quvchi", '', 'students', _students, True, True),
    'teachers': ('Ustozlar', 'ustoz', '', 'teachers', _teachers, False, True),
    'staff': ('Xodimlar', 'xodim', '', 'staff', _staff, False, False),
    'parents': ('Ota-onalar', 'ota-ona', '', 'parents', _parents, False, True),
    'groups': ('Sinflar va guruhlar', 'sinf/guruh', '', 'groups', _groups, False, False),
    'schedule': ('Dars jadvali', 'dars (haftasiga)', '', 'schedule', _lessons, False, False),
    'finance': ("To'lovlar", "so'm", "shu oy kassaga kirgan pul", 'finance', _income, False, False),
    'expenses': ('Xarajatlar', "so'm", 'shu oy chiqqan pul', 'expenses', _expenses, False, False),
    'payroll': ('Oyliklar', "so'm", "shu oy to'lanmagan oyliklar", 'payroll', _payroll, False, False),
    'news': ("E'lonlar", "e'lon", '', 'news', _news, False, False),
    'devices': ('Qurilmalar', 'qurilma', '', 'devices', _devices, False, False),
}


def org_hub(kind):
    title, unit, caption, nav, counter, with_branches, searchable = HUBS[kind]

    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            scope = getattr(request, 'scope', None)
            if scope is not None and scope.is_all and scope.multi_org and request.method == 'GET' and not (set(request.GET) - {'page'}):
                by_org, by_branch = counter(request.user)
                cards = [{'org': o['org'], 'n': by_org.get(o['org'].pk, 0),
                          'branches': [{'branch': b, 'n': by_branch.get(b.pk, 0)} for b in o['branches']]
                          if with_branches and len(o['branches']) > 1 else []} for o in scope.tree]
                return render(request, 'panel/hub.html', {
                    'nav': nav, 'title': title, 'unit': unit, 'caption': caption, 'cards': cards, 'searchable': searchable,
                    'total': sum(c['n'] for c in cards), 'path': request.path})
            return view(request, *args, **kwargs)
        return wrapper
    return deco
