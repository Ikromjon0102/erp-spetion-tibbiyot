from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    def deco(view):
        @wraps(view)
        def wrapper(request, *a, **kw):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *a, **kw)
        return wrapper
    return deco


def can_view_student(user, student):
    if user.is_school_admin:
        from org.scope import can_access_branch
        return can_access_branch(user, student.branch_id)
    if student.parents.filter(pk=user.pk).exists():  # ota-ona (ustoz bo'lsa ham o'z farzandini ko'ra oladi)
        return True
    if user.is_student:
        return student.user_id == user.id
    if user.is_teacher and student.group_id:
        return user.teachings.filter(group_id=student.group_id).exists()
    return False
