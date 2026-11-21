"""Ma'lumotlarni tashkilot/filial bo'yicha ajratish.

Qoida: «maktab egasi» va superuser hamma filialni ko'radi; boshqa xodim va ustoz faqat `user.branches` dagi filiallarni.
Ota-ona va o'quvchi bu yerdagi qoidalarga bo'ysunmaydi: ular faqat o'z farzandi/o'z ma'lumotini ko'radi.
"""
from .models import Branch


def _is_all(user):
    from panel.access import is_owner
    return is_owner(user)


def branch_ids(user):
    """Foydalanuvchi ko'ra oladigan filial id lari; None — hammasi."""
    if not (user.is_authenticated and user.is_active):
        return []
    if _is_all(user):
        return None
    cached = getattr(user, '_branch_ids', None)
    if cached is None:
        cached = user._branch_ids = list(user.branches.filter(is_active=True).values_list('pk', flat=True))
    return cached


def branches_for(user):
    ids = branch_ids(user)
    return Branch.objects.filter(is_active=True) if ids is None else Branch.objects.filter(pk__in=ids)


def _filter(qs, user, lookup):
    ids = branch_ids(user)
    return qs if ids is None else qs.filter(**{f'{lookup}__in': ids})


def scope_groups(qs, user):
    return _filter(qs, user, 'branch')


def scope_students(qs, user):
    return _filter(qs, user, 'branch')


def scope_devices(qs, user):
    return _filter(qs, user, 'branch')


def scope_announcements(qs, user):
    return _filter(qs, user, 'branch')


def scope_via_student(qs, user, path='student'):
    """O'quvchiga bog'langan yozuvlar (to'lov, hisob, davomat, baho, kirish-chiqish)."""
    return _filter(qs, user, f'{path}__branch')


def scope_via_group(qs, user, path='group'):
    return _filter(qs, user, f'{path}__branch')


def scope_teachers(qs, user):
    """Ustozlar: shu foydalanuvchining filiallaridan kamida bittasida ishlaydiganlar."""
    ids = branch_ids(user)
    return qs if ids is None else qs.filter(branches__in=ids).distinct()


def can_access_branch(user, branch_id):
    ids = branch_ids(user)
    return ids is None or branch_id in ids


def scope_staff(qs, user):
    """Panel xodimlari (StaffProfile): kamida bitta umumiy filiali bor xodimlar."""
    ids = branch_ids(user)
    return qs if ids is None else qs.filter(user__branches__in=ids).distinct()


def scope_audit(qs, user):
    ids = branch_ids(user)
    return qs if ids is None else qs.filter(actor__branches__in=ids).distinct()


def pick_branch(user, group=None):
    """Yangi yozuv (o'quvchi, qurilma, guruh, e'lon) qaysi filialga tushishi: guruhniki, bo'lmasa xodimning birinchi filiali."""
    from .models import default_branch
    if group is not None and group.branch_id:
        return group.branch
    ids = branch_ids(user)
    if ids:
        return Branch.objects.filter(pk=ids[0]).first()
    return default_branch()
