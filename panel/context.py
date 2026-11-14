from .access import has_panel, is_owner, perms_of, profile_of


def panel_context(request):
    """Barcha shablonlar uchun: foydalanuvchida panel bormi, qaysi ruxsatlari bor va lavozimi (menyu uchun)."""
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {'panel_access': False, 'panel_can': set(), 'panel_owner': False, 'panel_position': ''}
    if not has_panel(user):
        return {'panel_access': False, 'panel_can': set(), 'panel_owner': False, 'panel_position': ''}
    profile = profile_of(user)
    position = 'Texnik administrator' if user.is_superuser and not profile else (profile.position.name if profile else '')
    return {'panel_access': True, 'panel_can': perms_of(user), 'panel_owner': is_owner(user), 'panel_position': position}
