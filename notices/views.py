from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .models import Announcement, AnnouncementRead
from .services import read_ids


def announcements_for(user):
    """Foydalanuvchiga tegishli e'lonlar. Ustoz bir vaqtda ota-ona ham bo'lsa, ikkala tomonning e'lonlarini ko'radi."""
    qs = Announcement.objects.select_related('author', 'group')
    if user.is_school_admin:
        return qs
    audiences, groups = {'all'}, set()
    if user.is_teacher:
        audiences.add('teachers')
        groups |= set(user.teachings.values_list('group_id', flat=True))
    if hasattr(user, 'student'):
        audiences.add('students')
        groups.add(user.student.group_id)
    if user.is_parent or user.has_children:
        audiences.add('parents')
        groups |= set(user.children.filter(user__is_active=True).values_list('group_id', flat=True))
    return qs.filter(audience__in=audiences).filter(Q(group__isnull=True) | Q(group_id__in=groups))


def with_read_flags(user, announcements):
    """E'lonlar ro'yxatiga `is_read` belgisini qo'shadi (o'qilmaganlar qizil nuqta bilan ko'rinadi)."""
    items = list(announcements)
    seen = read_ids(user, items)
    for a in items:
        a.is_read = a.pk in seen
    return items


@login_required
def announcement_list(request):
    return render(request, 'announcements.html', {'announcements': with_read_flags(request.user, announcements_for(request.user))})


@login_required
@require_POST
def mark_read(request, pk):
    """E'lon ochilganda chaqiriladi: kim va qachon o'qiganini saqlaydi (birinchi o'qilgan vaqt o'zgarmaydi)."""
    announcement = get_object_or_404(announcements_for(request.user), pk=pk)   # o'ziga tegishli bo'lmagan e'lon — 404
    if request.user.is_school_admin:   # ma'muriyat qabul qiluvchi emas, o'qildi deb sanalmaydi
        return JsonResponse({'ok': True, 'recorded': False})
    _, created = AnnouncementRead.objects.get_or_create(announcement=announcement, user=request.user)
    return JsonResponse({'ok': True, 'recorded': created})
