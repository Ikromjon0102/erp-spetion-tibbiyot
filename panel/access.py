"""Panelga kirish va ruxsatlarni tekshirish."""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from .perms import ALL_PERMS

_UNSET = object()


def profile_of(user):
    """Foydalanuvchining faol xodim profili (yoki None). So'rov davomida bir marta olinadi."""
    cached = getattr(user, '_panel_profile', _UNSET)
    if cached is not _UNSET:
        return cached
    profile = None
    if user.is_authenticated and user.is_active:
        from .models import StaffProfile
        profile = StaffProfile.objects.select_related('position').filter(user=user, is_active=True).first()
    user._panel_profile = profile
    return profile


def is_owner(user):
    """To'liq ruxsatli: texnik administrator (superuser) yoki "maktab egasi" lavozimidagi xodim."""
    if not (user.is_authenticated and user.is_active):
        return False
    if user.is_superuser:
        return True
    profile = profile_of(user)
    return bool(profile and profile.position.is_owner)


def has_panel(user):
    return bool(user.is_authenticated and user.is_active and (user.is_superuser or profile_of(user)))


def perms_of(user):
    if not has_panel(user):
        return set()
    if is_owner(user):
        return set(ALL_PERMS)
    return set(profile_of(user).perms) & set(ALL_PERMS)


def can(user, code):
    return code in perms_of(user)


def panel_required(*codes):
    """Panelga kirgan va barcha ko'rsatilgan ruxsatlarga ega xodim uchun. Ruxsat yo'q bo'lsa — 403 sahifa."""
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not has_panel(user):
                raise PermissionDenied
            request.session['mode'] = 'panel'   # keyingi kirishda ham shu rejimda ochiladi
            granted = perms_of(user)
            if any(code not in granted for code in codes):
                return render(request, 'panel/forbidden.html', {'need': codes}, status=403)
            return view(request, *args, **kwargs)
        return wrapper
    return deco
