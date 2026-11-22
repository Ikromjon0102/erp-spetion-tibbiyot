"""«Hammasi» ish maydonida ro'yxat o'rniga tashkilot kartalari (hub): minglab yozuv bir sahifaga to'kilmaydi.
Kartani bossangiz o'sha tashkilot tanlanadi va odatiy ro'yxat ochiladi. Qidiruv yoki filtr bo'lsa (`?q=...`) — hamma tashkilot bo'yicha ro'yxat."""
from functools import wraps

from django.db.models import Count
from django.db.models.functions import Coalesce
from django.shortcuts import render

HUBS = {
    'students': ("O'quvchilar", "o'quvchi", 'students'),
    'teachers': ('Ustozlar', 'ustoz', 'teachers'),
    'staff': ('Xodimlar', 'xodim', 'staff'),
    'parents': ('Ota-onalar', 'ota-ona', 'parents'),
}


def _counts(kind, user):
    """{tashkilot_id: son}, students uchun qo'shimcha {filial_id: son}."""
    from org.models import default_branch
    default_org = default_branch().organization_id
    by_branch = {}
    if kind == 'students':
        from .views_core import real_students
        rows = real_students(user).values('branch_id', 'branch__organization_id').annotate(n=Count('pk'))
        by_org = {}
        for r in rows:
            org = r['branch__organization_id'] or default_org
            by_org[org] = by_org.get(org, 0) + r['n']
            by_branch[r['branch_id'] or default_branch().pk] = r['n']
        return by_org, by_branch
    if kind == 'teachers':
        from .views_teachers import teachers_qs
        qs = teachers_qs(user).values('branches__organization_id').annotate(n=Count('pk', distinct=True))
        return {r['branches__organization_id']: r['n'] for r in qs}, {}
    if kind == 'staff':
        from org.scope import scope_staff
        from .models import StaffProfile
        qs = scope_staff(StaffProfile.objects.all(), user).values('user__branches__organization_id').annotate(n=Count('pk', distinct=True))
        return {r['user__branches__organization_id']: r['n'] for r in qs}, {}
    from .views_parents import parents_qs
    qs = parents_qs(user).values('children__branch__organization_id').annotate(n=Count('pk', distinct=True))
    return {r['children__branch__organization_id']: r['n'] for r in qs}, {}


def org_hub(kind):
    title, noun, nav = HUBS[kind]

    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            scope = getattr(request, 'scope', None)
            if scope is not None and scope.is_all and scope.multi_org and request.method == 'GET' and not (set(request.GET) - {'page'}):
                by_org, by_branch = _counts(kind, request.user)
                cards = []
                for o in scope.tree:
                    cards.append({'org': o['org'], 'n': by_org.get(o['org'].pk, 0),
                                  'branches': [{'branch': b, 'n': by_branch.get(b.pk, 0)} for b in o['branches']] if kind == 'students' and len(o['branches']) > 1 else []})
                return render(request, 'panel/hub.html', {'nav': nav, 'title': title, 'noun': noun, 'cards': cards,
                                                          'total': sum(c['n'] for c in cards), 'path': request.path})
            return view(request, *args, **kwargs)
        return wrapper
    return deco
