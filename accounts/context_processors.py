def app_mode(request):
    """Barcha shablonlar uchun: joriy rejim (ustoz/ota-ona) va o'qilmagan e'lonlar soni (qo'ng'iroqdagi nuqta uchun)."""
    session = getattr(request, 'session', None)
    user = getattr(request, 'user', None)
    unread = 0
    if user is not None and user.is_authenticated and not user.is_school_admin:
        from notices.views import announcements_for
        unread = announcements_for(user).exclude(reads__user=user).count()
    return {'mode': session.get('mode') if session is not None else None, 'unread_news': unread}
