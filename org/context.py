"""Barcha shablonlar uchun tashkilot brendi (`org_theme`): rang va CSS. Qaysi tashkilot ekanini so'rov belgilaydi:
bola sahifasida — bolaning tashkiloti (view `request.theme_org` ni qo'yadi), qolgan joyda — foydalanuvchining o'z tashkiloti."""
from django.utils.safestring import mark_safe

from . import theme
from .models import Organization, default_branch


def _user_org(user):
    if not user.is_authenticated:
        return None
    child = user.children.filter(user__is_active=True).select_related('branch__organization').first() if hasattr(user, 'children') else None
    if child and child.branch_id:
        return child.branch.organization
    student = getattr(user, 'student', None)
    if student is not None and student.branch_id:
        return student.branch.organization
    branch = user.branches.select_related('organization').first()
    return branch.organization if branch else None


def org_theme(request):
    user = getattr(request, 'user', None)
    org = getattr(request, 'theme_org', None)
    if org is None and user is not None and request.path.startswith('/panel') and user.is_authenticated:
        branch = user.branches.select_related('organization').first()      # panel: xodimning o'z tashkiloti
        org = branch.organization if branch else None
    if org is None and user is not None:
        org = _user_org(user)
    if org is None:
        branch = default_branch()
        org = branch.organization if branch else None
    color = org.brand_color if isinstance(org, Organization) else theme.DEFAULT_COLOR
    accent = color if theme.is_valid(color) else theme.DEFAULT_COLOR
    return {'org_theme': {'org': org, 'accent': accent.upper(), 'css': mark_safe(theme.css(color))}}
