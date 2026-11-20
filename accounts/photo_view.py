from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.contrib.auth.views import redirect_to_login

from panel.access import can

from .models import User


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
    if not allowed:
        raise PermissionDenied
    resp = FileResponse(target.photo.open('rb'), content_type='image/jpeg')
    resp['Cache-Control'] = 'private, max-age=300'
    return resp
