import os
from io import BytesIO

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.contrib.auth.views import redirect_to_login

from panel.access import can, perms_of

from .models import User

THUMB = 96


def _thumb_path(target):
    """Kichik (kvadrat) nusxa diskda saqlanadi: ro'yxatda ko'p rasm bir vaqtda yuklansa ham yengil bo'ladi."""
    name = os.path.basename(target.photo.name)
    path = os.path.join(settings.MEDIA_ROOT, 'faces_thumbs', name)
    if not os.path.exists(path):
        from PIL import Image, ImageOps
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with target.photo.open('rb') as f:
            img = ImageOps.fit(Image.open(f).convert('RGB'), (THUMB, THUMB), centering=(0.5, 0.25))
        tmp = path + '.tmp'
        img.save(tmp, 'JPEG', quality=80)
        os.replace(tmp, path)
    return path


def face_photo(request, pk):
    """Yuz rasmi: o'zi, farzandining ota-onasi yoki panelda tegishli ko'rish ruxsati bor xodim ko'ra oladi."""
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    target = User.objects.select_related('student').filter(pk=pk).first()
    if not target or not target.photo:
        raise Http404
    me = request.user
    student = getattr(target, 'student', None)
    allowed = (me.pk == target.pk or me.is_superuser or can(me, 'devices.view')
               or (student and (can(me, 'students.view') or student.parents.filter(pk=me.pk).exists()))
               or (target.is_teacher and can(me, 'teachers.view'))
               or (target.role == User.Role.STAFF and can(me, 'staff.view')))
    thumb = bool(request.GET.get('s'))
    if not allowed and thumb and perms_of(me):      # ro'yxatdagi kichik avatar: panelga kira oladigan har bir xodimga
        allowed = True
    if not allowed:
        raise PermissionDenied
    if thumb:
        resp = FileResponse(open(_thumb_path(target), 'rb'), content_type='image/jpeg')
        resp['Cache-Control'] = 'private, max-age=86400'
        return resp
    resp = FileResponse(target.photo.open('rb'), content_type='image/jpeg')
    resp['Cache-Control'] = 'private, max-age=300'
    return resp
