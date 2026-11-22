from . import workspace


class WorkspaceScopeMiddleware:
    """Boshqaruv paneli (/panel/) uchun tanlangan tashkilot/filialni so'rovga qo'yadi: `request.scope`, `request.theme_org`
    va `user._scope_ids` (shu orqali `org.scope.branch_ids` hamma ro'yxatni tanlovga cheklaydi)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.scope = None
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and request.path.startswith('/panel'):
            from panel.access import has_panel
            if has_panel(user):
                scope = workspace.build_scope(user, request.session.get(workspace.SESSION_KEY))
                request.scope = scope
                ids = workspace.scope_branch_ids(scope)
                if ids is not None:
                    user._scope_ids = ids
                    request.theme_org = scope.org       # panel tanlangan tashkilot rangida
        return self.get_response(request)
