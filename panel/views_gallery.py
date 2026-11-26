"""Galereya (bog'cha): albom yaratish, rasm yuklash, har rasmda qaysi bolalar borligini belgilash. Ota-ona ilovasida faqat o'z
farzandi belgilangan rasmlar chiqadi — belgilanmagan rasm hech bir ota-onaga ko'rinmaydi. Ruxsat: `gallery.view` / `gallery.manage`.
Tarbiyachilar xuddi shuni ustoz ilovasidan qiladi (`gallery/views.py`)."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from academics.models import Group
from gallery import services
from gallery.models import Album, Photo
from org.scope import branches_for, current_org, orgs_for, scope_by_branch

from . import audit
from .access import panel_required, perms_of


def _albums(user):
    return scope_by_branch(Album.objects.select_related('branch__organization', 'group'), user)


def _album_or_404(request, pk):
    return get_object_or_404(_albums(request.user), pk=pk)


def upload_messages(request, errors):
    for e in errors[:5]:
        messages.error(request, e)


@panel_required('gallery.view')
def gallery(request):
    org = current_org(request)
    ctx = {'nav': 'gallery', 'org': org, 'orgs': list(orgs_for(request.user)), 'can_manage': 'gallery.manage' in perms_of(request.user)}
    if org.gallery_enabled:
        ctx['albums'] = services.album_list(_albums(request.user).filter(branch__organization=org))
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


def create_album(request, form):
    """Forma to'g'ri bo'lsa albom va rasmlar; rasm tanlanmagan bo'lsa None (formaga xato yoziladi)."""
    if not request.FILES.getlist('photos'):
        form.add_error(None, 'Kamida bitta rasm tanlang')
        return None
    album = form.save(commit=False)
    album.branch, album.created_by = album.group.branch, request.user
    album.save()
    added, errors = services.save_uploads(request.FILES.getlist('photos'), album)
    upload_messages(request, errors)
    audit.log(request, "Galereyaga albom qo'shdi", album, label=f'{album.group} · {album.title}', details={'rasmlar': len(added)},
              target_type='gallery')
    messages.success(request, f"{len(added)} ta rasm yuklandi. Endi har rasmda kimlar borligini belgilang — ota-ona faqat "
                              "o'z farzandi belgilangan rasmni ko'radi.")
    return album


def handle_album_post(request, album, photos, children):
    """Albom sahifasidagi POST: yangi rasmlar yoki belgilarni saqlash (panel va ustoz ilovasi uchun umumiy)."""
    if request.FILES.getlist('photos'):
        added, errors = services.save_uploads(request.FILES.getlist('photos'), album)
        upload_messages(request, errors)
        messages.success(request, f"{len(added)} ta rasm qo'shildi. Ularda kimlar borligini belgilang.")
        return
    tagged = services.save_tags(album, photos, request.POST, children)
    audit.log(request, 'Galereyada bolalarni belgiladi', album, label=f'{album.group} · {album.title}',
              details={'belgilangan rasmlar': f'{tagged} / {len(photos)}'}, target_type='gallery')
    rest = len(photos) - tagged
    messages.success(request, 'Saqlandi' + (f". {rest} ta rasmda hech kim belgilanmagan — ularni ota-onalar ko'rmaydi." if rest else
                                            '. Ota-onalarga xabar yuborildi.'))


def album_context(album, photos, children, can_manage):
    for ph in photos:
        ph.ids = {c.pk for c in ph.children.all()}
    return {'album': album, 'photos': photos, 'children': children, 'can_manage': can_manage,
            'untagged': sum(1 for ph in photos if not ph.ids)}


@panel_required('gallery.manage')
def album_add(request):
    org = current_org(request)
    if not org.gallery_enabled:
        raise Http404
    branches = branches_for(request.user).filter(organization=org)
    groups = Group.objects.filter(branch__in=branches).select_related('branch').order_by('branch__name', 'name')
    form = AlbumForm(request.POST or None, groups=groups, initial={'date': timezone.localdate()})
    if request.method == 'POST' and form.is_valid():
        album = create_album(request, form)
        if album:
            return redirect('panel:album', pk=album.pk)
    return render(request, 'panel/gallery_add.html', {'nav': 'gallery', 'form': form, 'org': org})


@panel_required('gallery.view')
def album(request, pk):
    album = _album_or_404(request, pk)
    can_manage = 'gallery.manage' in perms_of(request.user)
    children = services.children_of(album)
    photos = list(album.photos.prefetch_related('children'))
    if request.method == 'POST':
        if not can_manage:
            raise PermissionDenied
        handle_album_post(request, album, photos, children)
        return redirect('panel:album', pk=album.pk)
    return render(request, 'panel/gallery_album.html', {'nav': 'gallery', **album_context(album, photos, children, can_manage)})


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
    audit.log(request, "Galereyadan albom o'chirdi", album, label=f'{album.group} · {album.title}', target_type='gallery')
    org = album.branch.organization_id
    services.delete_album(album)
    messages.success(request, "Albom o'chirildi")
    return redirect(f"{reverse('panel:gallery')}?org={org}")


@login_required
def photo_file(request, pk):
    """Rasm fayli: panel xodimi (ruxsat + filial), guruh tarbiyachisi yoki rasmda belgilangan bolaning ota-onasi. `?t=1` — eskiz."""
    ph = get_object_or_404(Photo.objects.select_related('album'), pk=pk)
    if not services.can_view_photo(request.user, ph):
        raise Http404
    f = ph.thumb if request.GET.get('t') else ph.image
    resp = FileResponse(f.open('rb'), content_type='image/jpeg')
    resp['Cache-Control'] = 'private, max-age=604800'
    return resp
