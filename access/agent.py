"""Maktabdagi kompyuter (tools/push_faces.py) uchun API: kimni qaysi terminalga yuborish kerak, rasmlar, natija.

Server maktabning ichki tarmog'iga yeta olmaydi, shuning uchun rasmlarni terminallarga maktab tarmog'idagi kompyuter yuboradi.
Avval u server bazasining nusxasini (sqlite) olardi; yangi server PostgreSQL'da, va natija serverga qaytmasdi (panelda
«yuborilishi kerak» soni noto'g'ri qolardi). Endi skript shu API bilan ishlaydi:

  GET  /api/access/agent/manifest/<qurilma tokeni>/   — shu terminalda bo'lishi kerak odamlar (Face ID, ism, rasm xeshi) va holat
  GET  /api/access/agent/photo/<user id>/              — rasm (JPEG)
  POST /api/access/agent/report/<qurilma tokeni>/      — yuborish natijasi (FaceSync va qurilma izohi yangilanadi)

Kirish: `Authorization: Bearer <FACE_AGENT_TOKEN>` (.env). Qurilma — terminalga yozilgan push tokeni bilan aniqlanadi.
"""
import hmac
import json

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from accounts.models import User
from accounts.photos import photo_bytes

from .models import Device, FaceSync
from .sync import _digest, _display_name, eligible_users


def _authorized(request):
    expected = getattr(settings, 'FACE_AGENT_TOKEN', '')
    got = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    return bool(expected) and hmac.compare_digest(got, expected)


def _guard(view):
    def wrapper(request, *args, **kwargs):
        if not _authorized(request):
            return JsonResponse({'ok': False, 'error': 'token'}, status=401)
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


@require_GET
@_guard
def manifest(request, token):
    device = get_object_or_404(Device.objects.select_related('branch__organization'), token=token, is_active=True)
    states = {fs.user_id: fs for fs in device.face_syncs.all()}
    people = []
    for u in eligible_users(device):
        try:
            digest = _digest(u, photo_bytes(u))
        except (OSError, ValueError):
            continue
        st = states.get(u.pk)
        people.append({'user_id': u.pk, 'employee_no': u.device_id, 'name': _display_name(u), 'digest': digest,
                       'synced': bool(st and st.ok and st.digest == digest),
                       'old_employee_no': st.employee_no if st and st.ok and st.employee_no != u.device_id else ''})
    wanted = {p['user_id'] for p in people}
    remove = [{'user_id': uid, 'employee_no': st.employee_no} for uid, st in states.items() if st.ok and uid not in wanted]
    return JsonResponse({'ok': True, 'device': {'name': device.name, 'direction': device.direction,
                                                'branch': str(device.branch) if device.branch_id else ''},
                         'people': people, 'remove': remove})


@require_GET
@_guard
def photo(request, user_id):
    user = get_object_or_404(User, pk=user_id, is_active=True)
    try:
        data = photo_bytes(user)
    except (OSError, ValueError):
        return JsonResponse({'ok': False, 'error': 'rasm yo\'q'}, status=404)
    resp = HttpResponse(data, content_type='image/jpeg')
    resp['Cache-Control'] = 'no-store'
    return resp


@csrf_exempt
@require_POST
@_guard
def report(request, token):
    """{'results': [{'user_id', 'employee_no', 'digest', 'ok', 'error'}], 'removed': [user_id], 'note': '...'}"""
    device = get_object_or_404(Device, token=token, is_active=True)
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'json'}, status=400)
    allowed = {u.pk for u in eligible_users(device)}
    now = timezone.now()
    saved = 0
    for r in data.get('results', [])[:5000]:
        uid = r.get('user_id')
        if uid not in allowed:
            continue
        ok = bool(r.get('ok'))
        FaceSync.objects.update_or_create(device=device, user_id=uid, defaults={
            'employee_no': str(r.get('employee_no', ''))[:32], 'digest': (r.get('digest') or '')[:64] if ok else '',
            'ok': ok, 'error': '' if ok else str(r.get('error', ''))[:300], 'synced_at': now if ok else None})
        saved += 1
    removed = [uid for uid in data.get('removed', []) if isinstance(uid, int)]
    FaceSync.objects.filter(device=device, user_id__in=removed).exclude(user_id__in=allowed).delete()
    note = str(data.get('note', ''))[:300]
    if note:
        Device.objects.filter(pk=device.pk).update(last_sync_at=now, last_sync_note=note)
    return JsonResponse({'ok': True, 'saved': saved})


@require_GET
@_guard
def devices(request):
    """Faol terminallar: skript ularni terminals.json dagi nom (va filial) bo'yicha topadi."""
    rows = [{'name': d.name, 'token': d.token, 'direction': d.direction, 'branch_id': d.branch_id,
             'branch': str(d.branch) if d.branch_id else ''} for d in Device.objects.filter(is_active=True).select_related('branch__organization')]
    return JsonResponse({'ok': True, 'devices': rows})
