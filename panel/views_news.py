from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from notices.models import Announcement
from notices.services import read_summary, read_times, recipients_of

from . import audit
from .access import panel_required, perms_of
from .forms import AnnouncementForm


def _visible():
    return Announcement.objects.exclude(title__startswith='[Sinov]').select_related('author', 'group')


@panel_required('announcements.view')
def news(request):
    page = Paginator(_visible().order_by('-created_at'), 20).get_page(request.GET.get('page'))
    rows = []
    for a in page:
        total, read = read_summary(a)
        rows.append({'a': a, 'total': total, 'read': read})
    return render(request, 'panel/news.html', {'nav': 'news', 'page': page, 'rows': rows, 'granted': perms_of(request.user)})


@panel_required('announcements.view')
def news_detail(request, pk):
    a = get_object_or_404(_visible(), pk=pk)
    recipients, times = recipients_of(a), read_times(a)
    rows = sorted(({'u': u, 'read_at': timezone.localtime(times[u.pk]) if u.pk in times else None,
                    'both': u.is_teacher and u.has_children} for u in recipients),
                  key=lambda r: (r['read_at'] is None, r['read_at'] or 0, r['u'].last_name, r['u'].first_name))
    read = sum(1 for r in rows if r['read_at'])
    return render(request, 'panel/news_detail.html', {'nav': 'news', 'a': a, 'rows': rows, 'read': read, 'total': len(rows),
                                                      'granted': perms_of(request.user)})


@panel_required('announcements.add')
def news_add(request):
    form = AnnouncementForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        a = form.save(commit=False)
        a.author = request.user
        a.save()
        audit.log(request, "E'lon yubordi", a, label=a.title,
                  details={'kimlar uchun': a.get_audience_display(), 'sinf': a.group.name if a.group else 'hamma'},
                  target_type='announcement')
        messages.success(request, "E'lon yuborildi. Kim o'qiganini shu sahifada kuzatasiz.")
        return redirect('panel:news_detail', pk=a.pk)
    return render(request, 'panel/news_form.html', {'nav': 'news', 'form': form, 'title': "Yangi e'lon"})


@panel_required('announcements.change')
def news_edit(request, pk):
    a = get_object_or_404(_visible(), pk=pk)
    form = AnnouncementForm(request.POST or None, instance=a)
    if request.method == 'POST' and form.is_valid():
        changed = form.changed_data
        form.save()
        audit.log(request, "E'lonni o'zgartirdi", a, label=a.title, details={"o'zgargan maydonlar": changed},
                  target_type='announcement')
        messages.success(request, 'Saqlandi.')
        return redirect('panel:news_detail', pk=a.pk)
    return render(request, 'panel/news_form.html', {'nav': 'news', 'form': form, 'a': a, 'title': "E'lonni tahrirlash"})


@panel_required('announcements.change')
@require_POST
def news_delete(request, pk):
    a = get_object_or_404(_visible(), pk=pk)
    label = a.title
    a.delete()
    audit.log(request, "E'lonni o'chirdi", label=label, target_type='announcement')
    messages.success(request, "E'lon o'chirildi.")
    return redirect('panel:news')
