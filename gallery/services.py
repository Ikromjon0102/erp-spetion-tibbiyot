from io import BytesIO
import uuid

from django.core.files.base import ContentFile
from django.db.models import Count, Q

from .models import Album, GalleryNotice, Photo

FULL_SIDE, THUMB_SIDE = 1600, 480
MAX_UPLOAD = 25 * 1024 * 1024
MAX_FILES = 60


def add_photo(album, upload):
    """Telefon rasmini 1600 px gacha kichraytirib (va 480 px eskiz) JPEG qilib saqlaydi. Rasm bo'lmasa ValueError."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    if upload.size > MAX_UPLOAD:
        raise ValueError(f"{upload.name}: fayl juda katta (25 MB dan oshmasin)")
    try:
        src = Image.open(upload)
        if src.format == 'JPEG':
            src.draft('RGB', (FULL_SIDE, FULL_SIDE))      # telefon rasmini (12 MP) kichraytirib o'qiydi — bir necha marta tez, kam xotira
        img = ImageOps.exif_transpose(src).convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise ValueError(f"{upload.name}: rasm fayli emas yoki buzilgan")
    name = uuid.uuid4().hex
    photo = Photo(album=album)
    for field, side, q in (('image', FULL_SIDE, 82), ('thumb', THUMB_SIDE, 75)):
        copy = img.copy()
        copy.thumbnail((side, side))
        buf = BytesIO()
        copy.save(buf, 'JPEG', quality=q, optimize=True)
        getattr(photo, field).save(f'{name}.jpg', ContentFile(buf.getvalue()), save=False)
    photo.save()
    return photo


def save_uploads(files, album):
    """-> (qo'shilgan rasmlar, xatolar)."""
    added, errors = [], []
    for f in list(files)[:MAX_FILES]:
        try:
            added.append(add_photo(album, f))
        except ValueError as e:
            errors.append(str(e))
    return added, errors


def children_of(album):
    from accounts.models import Student
    qs = Student.objects.filter(user__is_active=True, branch=album.branch).select_related('user')
    if album.group_id:
        qs = qs.filter(group=album.group)
    return list(qs.order_by('user__last_name', 'user__first_name'))


def save_tags(album, photos, data, children):
    """Formadagi belgilar (`p<rasm id>` -> bola id lari). Faqat albom guruhidagi bolalar. -> belgilangan rasmlar soni.
    Saqlangach yangi belgilangan bolalarning ota-onalariga xabar ketadi."""
    allowed = {c.pk for c in children}
    tagged = 0
    for ph in photos:
        ids = {int(x) for x in data.getlist(f'p{ph.pk}') if x.isdigit()} & allowed
        ph.children.set(ids)
        tagged += bool(ids)
    notify_parents(album)
    return tagged


def notify_parents(album):
    """Albomda belgilangan, hali xabar olmagan har bola uchun ota-onasiga bitta Telegram xabari:
    «📸 Bobur — «Kuzgi sayr»: 3 ta yangi rasm». Keyin shu albomga rasm qo'shilsa qayta yozilmaydi."""
    from accounts.models import Student
    from tgbot.services import esc, notify
    done = set(GalleryNotice.objects.filter(album=album).values_list('student_id', flat=True))
    counts = (Photo.objects.filter(album=album).values('children').annotate(n=Count('id')).exclude(children=None))
    fresh = {r['children']: r['n'] for r in counts if r['children'] not in done}
    if not fresh:
        return 0
    group = f' ({esc(album.group.name)})' if album.group_id else ''
    for st in Student.objects.filter(pk__in=fresh).select_related('user').prefetch_related('parents'):
        GalleryNotice.objects.get_or_create(album=album, student=st)
        notify(list(st.parents.all()),
               f"📸 <b>{esc(st.user.first_name)}</b> — «{esc(album.title)}»{group}: {fresh[st.pk]} ta yangi rasm",
               f'/oquvchi/{st.pk}/#gallery')
    return len(fresh)


def teacher_groups(user):
    """Ustoz (tarbiyachi) dars beradigan, galereya yoqilgan tashkilotdagi guruhlar."""
    from academics.models import Group
    if not (user.is_authenticated and user.is_teacher):
        return Group.objects.none()
    return Group.objects.filter(teachings__teacher=user, branch__organization__gallery_enabled=True,
                                branch__is_active=True).select_related('branch').distinct()


def can_view_photo(user, photo):
    """Panel xodimi (gallery.view + filial ruxsati), albom guruhining tarbiyachisi yoki rasmda belgilangan bolaning ota-onasi / o'zi."""
    if not user.is_authenticated:
        return False
    from panel.access import perms_of
    from org.scope import can_access_branch
    if 'gallery.view' in perms_of(user) and can_access_branch(user, photo.album.branch_id):
        return True
    if photo.album.group_id and teacher_groups(user).filter(pk=photo.album.group_id).exists():
        return True
    kids = photo.children.all()
    return kids.filter(parents=user).exists() or kids.filter(user=user).exists()


def photos_for_child(student, limit=120):
    return list(Photo.objects.filter(children=student).select_related('album').order_by('-album__date', '-album_id', 'id')[:limit])


def album_list(albums):
    """Albomlar: rasm soni, belgilanmaganlar soni va muqova."""
    albums = list(albums.annotate(n=Count('photos', distinct=True),
                                  untagged=Count('photos', filter=Q(photos__children__isnull=True), distinct=True)))
    covers = {}
    for ph in Photo.objects.filter(album__in=albums).order_by('album_id', 'id'):
        covers.setdefault(ph.album_id, ph)
    for a in albums:
        a.cover = covers.get(a.pk)
    return albums


def delete_album(album):
    for ph in album.photos.all():
        ph.delete_files()
    album.delete()
