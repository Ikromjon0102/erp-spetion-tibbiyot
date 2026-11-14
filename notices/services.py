"""E'lonlar: kimga yo'naltirilgani va kim o'qiganini hisoblash (Telegramdagi kabi: yuborildi ✓ / o'qildi ✓✓)."""
from django.db.models import Q

from accounts.models import User

from .models import AnnouncementRead


def recipients_of(announcement):
    """E'lon yo'naltirilgan, tizimga kira oladigan foydalanuvchilar (admin, nofaol va paroli yo'q hisoblar — masalan
    hali kirmagan o'quvchilar — hisobga olinmaydi). Ham ustoz, ham ota-ona bo'lgan hisob bir marta sanaladi."""
    base = (User.objects.filter(is_active=True).exclude(role=User.Role.ADMIN)
            .exclude(password__startswith='!'))  # '!' — Django'da "parol o'rnatilmagan"
    a, ids = announcement, set()
    if a.audience in ('all', 'teachers'):
        teachers = base.filter(role=User.Role.TEACHER)
        if a.group_id:
            teachers = teachers.filter(teachings__group_id=a.group_id)
        ids |= set(teachers.values_list('pk', flat=True))
    if a.audience in ('all', 'parents'):
        if a.group_id:
            parents = base.filter(children__group_id=a.group_id)
        else:
            parents = base.filter(Q(role=User.Role.PARENT) | Q(children__isnull=False))
        ids |= set(parents.values_list('pk', flat=True))
    if a.audience in ('all', 'students'):
        students = base.filter(student__isnull=False)
        if a.group_id:
            students = students.filter(student__group_id=a.group_id)
        ids |= set(students.values_list('pk', flat=True))
    return list(User.objects.filter(pk__in=ids).order_by('role', 'last_name', 'first_name', 'username'))


def read_times(announcement):
    """{foydalanuvchi_id: o'qilgan vaqt}"""
    return dict(AnnouncementRead.objects.filter(announcement=announcement).values_list('user_id', 'read_at'))


def read_summary(announcement):
    """(jami qabul qiluvchilar, ulardan o'qiganlar)"""
    recipients = recipients_of(announcement)
    times = read_times(announcement)
    return len(recipients), sum(1 for u in recipients if u.pk in times)


def read_ids(user, announcements):
    """Foydalanuvchi o'qigan e'lonlar identifikatorlari (berilgan e'lonlar ichidan)."""
    ids = [a.pk for a in announcements]
    return set(AnnouncementRead.objects.filter(user=user, announcement_id__in=ids).values_list('announcement_id', flat=True))
