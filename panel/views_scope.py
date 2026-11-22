from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from org import workspace

from .access import panel_required


@panel_required()
def set_scope(request):
    """Ish maydonini tanlash (Hammasi / tashkilot / filial). Ruxsatsiz tanlov middleware'da 'Hammasi'ga qaytadi."""
    request.session[workspace.SESSION_KEY] = request.GET.get('s', 'all')
    nxt = request.GET.get('next') or '/panel/'
    if not (nxt.startswith('/panel') and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()})):
        nxt = '/panel/'
    return redirect(nxt)
