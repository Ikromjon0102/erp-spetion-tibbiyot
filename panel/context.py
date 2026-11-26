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
    owner = is_owner(user)
    scope = getattr(request, 'scope', None)
    from .models import ThreadMember
    from .views_inbox import unread_count
    return {'panel_access': True, 'panel_can': perms_of(user), 'panel_owner': owner, 'panel_position': position, 'scope': scope,
            # founder «Rahbariyat» rejimi: hamma tashkilot tanlanganda ixcham menyu (raqamlar, xabarlar, tashkilotlar, moliya)
            'founder_lean': bool(owner and scope is not None and scope.is_all and len(scope.tree) > 1),
            'inbox_unread': unread_count(user), 'inbox_has': owner or ThreadMember.objects.filter(user=user).exists()}
