"""Galereya (bog'cha): albom yaratish, rasm yuklash, har rasmda qaysi bolalar borligini belgilash. Ota-ona ilovasida faqat o'z
farzandi belgilangan rasmlar chiqadi — belgilanmagan rasm hech bir ota-onaga ko'rinmaydi. Ruxsat: `gallery.view` / `gallery.manage`."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from academics.models import Group
from accounts.models import Student
from gallery import services
from gallery.models import Album, Photo
from org.scope import branches_for, current_org, orgs_for, scope_by_branch

from . import audit
from .access import panel_required, perms_of

MAX_FILES = 60


def _albums(user):
    return scope_by_branch(Album.objects.select_related('branch__organization', 'group'), user)


def _album_or_404(request, pk):
    return get_object_or_404(_albums(request.user), pk=pk)


def _children(album):
    qs = Student.objects.filter(user__is_active=True, branch=album.branch).select_related('user')
    if album.group_id:
        qs = qs.filter(group=album.group)
    return list(qs.order_by('user__last_name', 'user__first_name'))


def _save_uploads(request, album):
    added, errors = [], []
    for f in request.FILES.getlist('photos')[:MAX_FILES]:
        try:
            added.append(services.add_photo(album, f))
        except ValueError as e:
            errors.append(str(e))
    for e in errors[:5]:
        messages.error(request, e)
    return added


@panel_required('gallery.view')
def gallery(request):
    org = current_org(request)
    ctx = {'nav': 'gallery', 'org': org, 'orgs': list(orgs_for(request.user)), 'can_manage': 'gallery.manage' in perms_of(request.user)}
    if org.gallery_enabled:
        albums = list(_albums(request.user).filter(branch__organization=org)
                      .annotate(n=Count('photos', distinct=True),
                                untagged=Count('photos', filter=Q(photos__children__isnull=True), distinct=True)))
        covers = {}
        for ph in Photo.objects.filter(album__in=albums).order_by('album_id', 'id'):
            covers.setdefault(ph.album_id, ph)
        for a in albums:
            a.cover = covers.get(a.pk)
        ctx['albums'] = albums
    return render(request, 'panel/gallery.html', ctx)


class AlbumForm(forms.ModelForm):
    class Meta:
        model = Album
        fields = ['group', 'title', 'date']
        labels = {'group': 'Guruh', 'title': 'Albom nomi'}
        widgets = {'date': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'title': forms.TextInput(attrs={'placeholder': 'Masalan: Yangi yil bayrami'})}

    def __init__(self, *args, groups=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].queryset = groups
        self.fields['group'].required = True
        self.fields['group'].empty_label = '— guruhni tanlang —'
        self.fields['group'].label_from_instance = lambda g: f'{g.branch.name} · {g.name}' if g.branch_id else g.name


@panel_required('gallery.manage')
def album_add(request):
    org = current_org(request)
    if not org.gallery_enabled:
        raise Http404
    branches = branches_for(request.user).filter(organization=org)
    groups = Group.objects.filter(branch__in=branches).select_related('branch').order_by('branch__name', 'name')
    form = AlbumForm(request.POST or None, groups=groups, initial={'date': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        if not request.FILES.getlist('photos'):
            form.add_error(None, 'Kamida bitta rasm tanlang')
        else:
            album = form.save(commit=False)
            album.branch, album.created_by = album.group.branch, request.user
            album.save()
            added = _save_uploads(request, album)
            audit.log(request, "Galereyaga albom qo'shdi", album, label=f'{album.group} · {album.title}', details={'rasmlar': len(added)},
                      target_type='gallery')
            messages.success(request, f"{len(added)} ta rasm yuklandi. Endi har rasmda kimlar borligini belgilang — ota-ona faqat "
                                      "o'z farzandi belgilangan rasmni ko'radi.")
            return redirect('panel:album', pk=album.pk)
    return render(request, 'panel/gallery_add.html', {'nav': 'gallery', 'form': form, 'org': org})


@panel_required('gallery.view')
def album(request, pk):
    album = _album_or_404(request, pk)
    can_manage = 'gallery.manage' in perms_of(request.user)
    children = _children(album)
    photos = list(album.photos.prefetch_related('children'))
    if request.method == 'POST':
        if not can_manage:
            raise PermissionDenied
        if request.FILES.getlist('photos'):
            added = _save_uploads(request, album)
            messages.success(request, f"{len(added)} ta rasm qo'shildi. Ularda kimlar borligini belgilang.")
            return redirect('panel:album', pk=album.pk)
        allowed = {c.pk for c in children}
        tagged = 0
        for ph in photos:
            ids = {int(x) for x in request.POST.getlist(f'p{ph.pk}') if x.isdigit()} & allowed
            ph.children.set(ids)
            tagged += bool(ids)
        audit.log(request, 'Galereyada bolalarni belgiladi', album, label=f'{album.group} · {album.title}',
                  details={'belgilangan rasmlar': f'{tagged} / {len(photos)}'}, target_type='gallery')
        rest = len(photos) - tagged
        messages.success(request, 'Saqlandi' + (f". {rest} ta rasmda hech kim belgilanmagan — ularni ota-onalar ko'rmaydi." if rest else ''))
        return redirect('panel:album', pk=album.pk)
    for ph in photos:
        ph.ids = {c.pk for c in ph.children.all()}
    return render(request, 'panel/gallery_album.html', {'nav': 'gallery', 'album': album, 'photos': photos, 'children': children,
                                                        'can_manage': can_manage, 'untagged': sum(1 for ph in photos if not ph.ids)})


@require_POST
@panel_required('gallery.manage')
def photo_delete(request, pk):
    ph = get_object_or_404(Photo.objects.filter(album__in=_albums(request.user)), pk=pk)
    album = ph.album
    ph.delete_files()
    ph.delete()
    messages.success(request, "Rasm o'chirildi")
    return redirect('panel:album', pk=album.pk)


@require_POST
@panel_required('gallery.manage')
def album_delete(request, pk):
    album = _album_or_404(request, pk)
    for ph in album.photos.all():
        ph.delete_files()
    audit.log(request, "Galereyadan albom o'chirdi", album, label=f'{album.group} · {album.title}', target_type='gallery')
    org = album.branch.organization_id
    album.delete()
    messages.success(request, "Albom o'chirildi")
    return redirect(f"{reverse('panel:gallery')}?org={org}")


@login_required
def photo_file(request, pk):
    """Rasm fayli: panel xodimi (ruxsat + filial) yoki rasmda belgilangan bolaning ota-onasi. `?t=1` — eskiz."""
    ph = get_object_or_404(Photo.objects.select_related('album'), pk=pk)
    if not services.can_view_photo(request.user, ph):
        raise Http404
    f = ph.thumb if request.GET.get('t') else ph.image
    resp = FileResponse(f.open('rb'), content_type='image/jpeg')
    resp['Cache-Control'] = 'private, max-age=604800'
    return resp
