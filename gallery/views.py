"""Tarbiyachi (ustoz) ilovasidagi galereya: telefondan albom ochish, rasm yuklash va rasmdagi bolalarni belgilash.
Faqat o'zi dars beradigan, galereya yoqilgan tashkilotdagi guruhlar. Mantiq panel bilan umumiy (`panel/views_gallery.py`)."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.permissions import role_required
from panel.views_gallery import AlbumForm, album_context, create_album, handle_album_post

from . import services
from .models import Album, Photo


def _albums(user):
    return Album.objects.filter(group__in=services.teacher_groups(user)).select_related('group', 'branch')


@role_required('teacher')
def home(request):
    groups = list(services.teacher_groups(request.user))
    return render(request, 'teacher/gallery.html', {'albums': services.album_list(_albums(request.user)), 'groups': groups,
                                                    'back_url': reverse('journal:teacher_home')})


@role_required('teacher')
def add(request):
    groups = services.teacher_groups(request.user)
    form = AlbumForm(request.POST or None, groups=groups, initial={'date': timezone.localdate()})
    if groups.count() == 1:
        form.fields['group'].initial = groups.first().pk
    if request.method == 'POST' and form.is_valid():
        album = create_album(request, form)
        if album:
            return redirect('gallery:album', pk=album.pk)
    return render(request, 'teacher/gallery_add.html', {'form': form, 'back_url': reverse('gallery:home')})


@role_required('teacher')
def album(request, pk):
    album = get_object_or_404(_albums(request.user), pk=pk)
    children = services.children_of(album)
    photos = list(album.photos.prefetch_related('children'))
    if request.method == 'POST':
        handle_album_post(request, album, photos, children)
        return redirect('gallery:album', pk=album.pk)
    return render(request, 'teacher/gallery_album.html', {**album_context(album, photos, children, True),
                                                          'back_url': reverse('gallery:home')})


@require_POST
@role_required('teacher')
def photo_delete(request, pk):
    ph = get_object_or_404(Photo.objects.filter(album__in=_albums(request.user)), pk=pk)
    album_id = ph.album_id
    ph.delete_files()
    ph.delete()
    messages.success(request, "Rasm o'chirildi")
    return redirect('gallery:album', pk=album_id)
