from io import BytesIO
import uuid

from django.core.files.base import ContentFile

from .models import Photo

FULL_SIDE, THUMB_SIDE = 1600, 480
MAX_UPLOAD = 25 * 1024 * 1024


def add_photo(album, upload):
    """Telefon rasmini 1600 px gacha kichraytirib (va 480 px eskiz) JPEG qilib saqlaydi. Rasm bo'lmasa ValueError."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    if upload.size > MAX_UPLOAD:
        raise ValueError(f"{upload.name}: fayl juda katta (25 MB dan oshmasin)")
    try:
        img = ImageOps.exif_transpose(Image.open(upload)).convert('RGB')
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


def can_view_photo(user, photo):
    """Panel xodimi (gallery.view + filial ruxsati) yoki rasmda belgilangan bolaning ota-onasi / o'zi."""
    if not user.is_authenticated:
        return False
    from panel.access import perms_of
    from org.scope import can_access_branch
    if 'gallery.view' in perms_of(user) and can_access_branch(user, photo.album.branch_id):
        return True
    kids = photo.children.all()
    return kids.filter(parents=user).exists() or kids.filter(user=user).exists()


def photos_for_child(student, limit=120):
    return list(Photo.objects.filter(children=student).select_related('album').order_by('-album__date', '-album_id', 'id')[:limit])
