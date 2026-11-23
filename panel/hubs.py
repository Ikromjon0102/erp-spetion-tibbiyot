"""Ro'yxat o'rniga kartalar (hub): minglab yozuv bir sahifaga to'kilmaydi.

Ikki daraja:
- ish maydoni bir nechta TASHKILOTni qamrasa — tashkilot kartalari (founder «Hammasi»da);
- bitta tashkilot, lekin bir nechta FILIAL bo'lsa — filial kartalari (masalan markaz direktori 5 filial bilan, yoki founder «Markaz»ni tanlaganda).
Kartani bossangiz o'sha tashkilot/filial tanlanadi va odatiy ro'yxat ochiladi. Qidiruv yoki filtr bo'lsa (`?q=...`) — ro'yxat darhol.
Har bo'lim o'z raqamini ko'rsatadi: o'quvchilar soni, shu oy tushumi, shu oy xarajati va hokazo."""
from collections import defaultdict
from decimal import Decimal
from functools import wraps

from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone


def _default():
    from org.models import default_branch
    b = default_branch()
    return b.organization_id, b.pk


# ---- har bo'lim: (queryset(user), filialga yo'l, hisob turi) --------------------------------------------------------------

def _q_students(user):
    from .views_core import real_students
    return real_students(user)


def _q_teachers(user):
    from .views_teachers import teachers_qs
    return teachers_qs(user)


def _q_staff(user):
    from org.scope import scope_staff
    from .models import StaffProfile
    return scope_staff(StaffProfile.objects.all(), user)


def _q_parents(user):
    from .views_parents import parents_qs
    return parents_qs(user)


def _q_groups(user):
    from academics.models import Group
    from org.scope import scope_groups
    return scope_groups(Group.objects.all(), user)


def _q_lessons(user):
    from academics.models import Lesson
    from org.scope import scope_via_group
    return scope_via_group(Lesson.objects.filter(active=True), user, 'teaching__group')


def _q_income(user):
    from billing.models import Payment
    from org.scope import scope_via_student
    d = timezone.localdate()
    return scope_via_student(Payment.objects.filter(voided=False, paid_on__year=d.year, paid_on__month=d.month), user)


def _q_expenses(user):
    from finance.models import Expense
    from org.scope import scope_by_branch
    d = timezone.localdate()
    return scope_by_branch(Expense.objects.filter(date__year=d.year, date__month=d.month), user)


def _q_news(user):
    from notices.models import Announcement
    from org.scope import scope_announcements
    return scope_announcements(Announcement.objects.exclude(title__startswith='[Sinov]'), user)


def _q_devices(user):
    from access.models import Device
    from org.scope import scope_devices
    return scope_devices(Device.objects.all(), user)


SPECS = {           # kalit: (queryset, filialga yo'l, hisob: count | distinct | sum)
    'students': (_q_students, 'branch', 'count'),
    'teachers': (_q_teachers, 'branches', 'distinct'),
    'staff': (_q_staff, 'user__branches', 'distinct'),
    'parents': (_q_parents, 'children__branch', 'distinct'),
    'groups': (_q_groups, 'branch', 'count'),
    'schedule': (_q_lessons, 'teaching__group__branch', 'count'),
    'finance': (_q_income, 'student__branch', 'sum'),
    'expenses': (_q_expenses, 'branch', 'sum'),
    'news': (_q_news, 'branch', 'count'),
    'devices': (_q_devices, 'branch', 'count'),
}


def counts(kind, user, level):
    """{tashkilot_id yoki filial_id: son} — `level` 'org' yoki 'branch'. Bir odam ikki filialda bo'lsa, har birida sanaladi,
    lekin tashkilot darajasida bir marta."""
    default_org, default_branch_id = _default()
    if kind == 'payroll':
        from finance.models import Payslip
        from org.scope import scope_by_branch
        month = timezone.localdate().replace(day=1)
        out = defaultdict(Decimal)
        for ps in scope_by_branch(Payslip.objects.filter(month=month).select_related('branch'), user).prefetch_related('payments'):
            out[ps.branch.organization_id if level == 'org' else ps.branch_id] += max(ps.remaining, Decimal(0))
        return {k: int(v) for k, v in out.items()}
    qs_fn, path, how = SPECS[kind]
    key = path + ('__organization' if level == 'org' else '')
    agg = {'count': Count('pk'), 'distinct': Count('pk', distinct=True), 'sum': Sum('amount')}[how]
    out = defaultdict(int)
    for row in qs_fn(user).values(key).annotate(n=agg).order_by():
        out[row[key] or (default_org if level == 'org' else default_branch_id)] += row['n'] or 0
    return dict(out)


#   kalit: (sarlavha, birlik, izoh, nav, qidiruv bormi)
HUBS = {
    'students': ("O'quvchilar", "o'quvchi", '', 'students', True),
    'teachers': ('Ustozlar', 'ustoz', '', 'teachers', True),
    'staff': ('Xodimlar', 'xodim', '', 'staff', False),
    'parents': ('Ota-onalar', 'ota-ona', '', 'parents', True),
    'groups': ('Sinflar va guruhlar', 'sinf/guruh', '', 'groups', False),
    'schedule': ('Dars jadvali', 'dars (haftasiga)', '', 'schedule', False),
    'finance': ("To'lovlar", "so'm", "shu oy kassaga kirgan pul", 'finance', False),
    'expenses': ('Xarajatlar', "so'm", 'shu oy chiqqan pul', 'expenses', False),
    'payroll': ('Oyliklar', "so'm", "shu oy to'lanmagan oyliklar", 'payroll', False),
    'news': ("E'lonlar", "e'lon", '', 'news', False),
    'devices': ('Qurilmalar (terminallar)', 'qurilma', '', 'devices', False),
}


def _total(kind, user, cards):
    """Jami: odamlar (ustoz, xodim, ota-ona) ikki joyda ishlasa ham bir marta sanaladi."""
    if kind != 'payroll' and SPECS[kind][2] == 'distinct':
        return SPECS[kind][0](user).distinct().count()
    return sum(c['n'] for c in cards)


def hub_level(scope):
    """('org', [tashkilot daraxti]) | ('branch', org, [filiallar]) | None — ish maydoniga qarab."""
    if scope is None or scope.kind == 'branch':
        return None
    tree = scope.tree if scope.is_all else [o for o in scope.tree if o['org'].pk == scope.org.pk]
    if len(tree) > 1:
        return ('org', tree)
    if tree and len(tree[0]['branches']) > 1:
        return ('branch', tree[0])
    return None


def org_hub(kind):
    title, unit, caption, nav, searchable = HUBS[kind]

    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            scope = getattr(request, 'scope', None)
            level = hub_level(scope) if request.method == 'GET' and not (set(request.GET) - {'page'}) else None
            if level is None:
                return view(request, *args, **kwargs)
            if level[0] == 'org':
                by = counts(kind, request.user, 'org')
                by_branch = counts(kind, request.user, 'branch') if kind == 'students' else {}
                cards = [{'org': o['org'], 'n': by.get(o['org'].pk, 0), 'scope': f"org-{o['org'].pk}", 'name': o['org'].label,
                          'branches': [{'branch': b, 'n': by_branch.get(b.pk, 0)} for b in o['branches']]
                          if kind == 'students' and len(o['branches']) > 1 else []} for o in level[1]]
                heading, lead = title, "Tashkilotni tanlang — shu tashkilot bo'yicha ro'yxat ochiladi."
            else:
                org = level[1]['org']
                by = counts(kind, request.user, 'branch')
                cards = [{'org': org, 'n': by.get(b.pk, 0), 'scope': f'branch-{b.pk}', 'name': b.name, 'branches': []}
                         for b in level[1]['branches']]
                heading, lead = f'{title} · {org.label}', "Filialni tanlang — shu filial bo'yicha ro'yxat ochiladi."
            return render(request, 'panel/hub.html', {
                'nav': nav, 'title': heading, 'lead': lead, 'unit': unit, 'caption': caption, 'cards': cards,
                'searchable': searchable, 'total': _total(kind, request.user, cards), 'path': request.path, 'level': level[0]})
        return wrapper
    return deco
