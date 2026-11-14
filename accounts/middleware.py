from django.shortcuts import redirect

EXEMPT_PREFIXES = ('/parol/', '/logout/', '/static/', '/api/')


class ForcePasswordChangeMiddleware:
    """Bir martalik parol bilan kirgan foydalanuvchi yangi parol qo'ymaguncha boshqa sahifaga o'ta olmaydi."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and user.must_change_password and not request.path.startswith(EXEMPT_PREFIXES):
            return redirect('change_password')
        return self.get_response(request)
