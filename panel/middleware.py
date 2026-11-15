from django.http import JsonResponse


class ModalRedirectMiddleware:
    """Modal oynadan (fetch) kelgan so'rovda yo'naltirishni (302) JSON'ga aylantiradi.

    Aks holda fetch yo'naltirilgan sahifani o'zi yuklab, "saqlandi" xabarini (messages) o'qib yo'qotib yuborardi.
    Brauzer JSON'dagi manzilga o'zi o'tadi va xabar o'sha sahifada ko'rinadi.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.headers.get('X-Modal') and 300 <= response.status_code < 400 and response.headers.get('Location'):
            return JsonResponse({'redirect': response.headers['Location']})
        return response
