"""Yuz rasmlarini Hikvision talablariga moslab tayyorlash: JPEG, ~200 KB gacha, tomonlari juda kichik emas."""
import hashlib
import secrets
from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD = 10 * 1024 * 1024     # yuklanadigan fayl
MAX_BYTES = 200 * 1024            # qurilmaga yuboriladigan rasm
MAX_SIDE = 1024
MIN_SIDE = 200


class PhotoError(ValueError):
    pass


def prepare(fileobj):
    """Yuklangan rasmni tekshiradi va qurilmaga mos JPEG baytlariga aylantiradi."""
    data = fileobj.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise PhotoError("Rasm hajmi 10 MB dan oshmasin")
    try:
        img = Image.open(BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise PhotoError("Bu rasm fayli emas yoki buzilgan (JPG yoki PNG yuklang)")
    img = ImageOps.exif_transpose(img)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    if min(img.size) < MIN_SIDE:
        raise PhotoError(f"Rasm juda kichik ({img.size[0]}×{img.size[1]}). Kamida {MIN_SIDE}×{MIN_SIDE} bo'lsin")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    for side in (MAX_SIDE, 800, 640, 480):
        if max(img.size) > side:
            img.thumbnail((side, side))
        for quality in (90, 80, 70, 60, 50):
            out = BytesIO()
            img.save(out, 'JPEG', quality=quality, optimize=True)
            if out.tell() <= MAX_BYTES:
                return out.getvalue()
    raise PhotoError("Rasmni kichraytirib bo'lmadi, boshqa rasm tanlang")


def save_photo(user, fileobj):
    """Foydalanuvchining rasmini almashtiradi (eski fayl o'chiriladi)."""
    jpeg = prepare(fileobj)
    if user.photo:
        user.photo.delete(save=False)
    user.photo.save(f'{user.pk}-{secrets.token_hex(6)}.jpg', ContentFile(jpeg), save=False)
    user.save(update_fields=['photo'])
    return jpeg


def remove_photo(user):
    if user.photo:
        user.photo.delete(save=False)
        user.photo = None
        user.save(update_fields=['photo'])


def photo_bytes(user):
    with user.photo.open('rb') as f:
        return f.read()


def photo_hash(user):
    return hashlib.sha256(photo_bytes(user)).hexdigest()
