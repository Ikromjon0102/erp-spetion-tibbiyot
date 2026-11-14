"""Ustoz sahifasi API'lari uchun himoya: faqat tizimga kirgan ustoz (login = telefon raqam) foydalana oladi."""
from functools import wraps

from django.http import JsonResponse


def teacher_required_json(view):
    """Kirmagan yoki ustoz bo'lmagan foydalanuvchiga 401 qaytaradi (sahifa buni ko'rib, kirish sahifasiga o'tkazadi)."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not (user.is_authenticated and user.is_active and user.is_teacher):
            return JsonResponse({'ok': False, 'err': 'auth'}, status=401)
        request.teacher = user
        return view(request, *args, **kwargs)
    return wrapper
