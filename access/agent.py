"""Binodagi kompyuter (agent yoki tools/push_faces.py) uchun API: kimni qaysi terminalga yuborish kerak, rasmlar, natija.

Server maktabning ichki tarmog'iga yeta olmaydi, shuning uchun rasmlarni terminallarga o'sha bino tarmog'idagi kompyuter yuboradi.

  POST /api/access/agent/pair/                         — bir martalik ulash kodi bilan agentni filialga bog'lash (kalit qaytadi)
  POST /api/access/agent/heartbeat/                    — «tirikman» + terminallar holati; javobda filial izi (o'zgarsa — sync)
  GET  /api/access/agent/devices/                      — filial terminallari
  GET  /api/access/agent/manifest/<qurilma tokeni>/    — shu terminalda bo'lishi kerak odamlar (Face ID, ism, rasm xeshi) va holat
  GET  /api/access/agent/photo/<user id>/              — rasm (JPEG)
  POST /api/access/agent/report/<qurilma tokeni>/      — yuborish natijasi (FaceSync va qurilma izohi yangilanadi)

Kirish: `Authorization: Bearer <kalit>`.
  * Filial kaliti (Agent, panelda ulash kodi orqali olinadi) — faqat o'z filialining terminallari va odamlari. Asosiy usul.
  * FACE_AGENT_TOKEN (.env) — hamma filial; faqat server administratori uchun, maktab kompyuterlariga tarqatilmaydi.
"""
import hmac
import json

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from accounts.models import User
from accounts.photos import photo_bytes

from .models import Agent, AgentPairing, Device, FaceSync, hash_secret
from .sync import _digest, _display_name, branch_stamp, eligible_users

GLOBAL = object()
HEARTBEAT_SECONDS = 60
PAIR_TRIES_PER_HOUR = 10


def client_ip(request):
    fwd = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (fwd.split(',')[0].strip() if fwd else request.META.get('REMOTE_ADDR', ''))[:64]


def _resolve(request):
    """GLOBAL (server administratori kaliti), Agent (filial kaliti) yoki None."""
    got = request.headers.get('Authorization', '').removeprefix('Bearer ').strip()
    if not got:
        return None
    expected = getattr(settings, 'FACE_AGENT_TOKEN', '')
    if expected and hmac.compare_digest(got, expected):
        return GLOBAL
    agent = Agent.objects.select_related('branch__organization').filter(key_hash=hash_secret(got), is_active=True).first()
    if agent is None:
        return None
    now = timezone.now()
    version = request.headers.get('X-Agent-Version', '')[:20]
    if not agent.last_seen_at or (now - agent.last_seen_at).total_seconds() > 20 or version != agent.version:
        Agent.objects.filter(pk=agent.pk).update(last_seen_at=now, last_ip=client_ip(request), version=version or agent.version)
        agent.last_seen_at = now
    return agent


def _guard(view):
    def wrapper(request, *args, **kwargs):
        who = _resolve(request)
        if who is None:
            return JsonResponse({'ok': False, 'error': 'token'}, status=401)
        request.agent = None if who is GLOBAL else who
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def _devices(request):
    qs = Device.objects.filter(is_active=True).select_related('branch__organization')
    return qs.filter(branch_id=request.agent.branch_id) if request.agent else qs


def _device(request, token):
    return get_object_or_404(_devices(request), token=token)


# ---- ulash ---------------------------------------------------------------------------------------------------------------

@csrf_exempt
@require_POST
def pair(request):
    """{'code': '1234-5678', 'name': 'kompyuter nomi'} -> {'key': ..., 'branch': ..., 'org': ...}. Kalit faqat shu javobda ko'rinadi."""
    ip_key = f'agent-pair:{client_ip(request)}'
    tries = cache.get(ip_key, 0)
    if tries >= PAIR_TRIES_PER_HOUR:
        return JsonResponse({'ok': False, 'error': "Juda ko'p urinish. 1 soatdan keyin qayta urinib ko'ring."}, status=429)
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        data = {}
    digits = ''.join(ch for ch in str(data.get('code', '')) if ch.isdigit())
    now = timezone.now()
    pairing = AgentPairing.objects.select_related('branch__organization').filter(
        code_hash=hash_secret(digits), used_at__isnull=True, expires_at__gt=now).first() if len(digits) == 8 else None
    if pairing is None:
        cache.set(ip_key, tries + 1, 3600)
        return JsonResponse({'ok': False, 'error': "Kod noto'g'ri yoki muddati o'tgan. Paneldan yangi kod oling."}, status=400)
    import secrets
    key = 'spa_' + secrets.token_urlsafe(32)
    agent = Agent.objects.create(branch=pairing.branch, name=str(data.get('name', ''))[:100], key_hash=hash_secret(key),
                                 key_hint=key[-4:], created_by=pairing.created_by, last_seen_at=now, last_ip=client_ip(request),
                                 version=str(data.get('version', ''))[:20])
    pairing.used_at, pairing.agent = now, agent
    pairing.save(update_fields=['used_at', 'agent'])
    br = pairing.branch
    return JsonResponse({'ok': True, 'key': key, 'agent_id': agent.pk, 'branch_id': br.pk, 'branch': br.name,
                         'org': br.organization.label})


# ---- ish ----------------------------------------------------------------------------------------------------------------

@csrf_exempt
@require_POST
@_guard
def heartbeat(request):
    """{'terminals': [{'device': <token>, 'ip', 'mac', 'online', 'users', 'faces', 'error'}]} ->
    {'stamp': filial izi, 'interval': soniya}. Agent iz o'zgarganda (yoki xato qolgan bo'lsa) sync qiladi."""
    if request.agent is None:
        raise Http404
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'ok': False, 'error': 'json'}, status=400)
    tokens = {d.token: d.pk for d in _devices(request)}
    now = timezone.now().isoformat()
    state = {}
    for t in data.get('terminals', [])[:50]:
        pk = tokens.get(str(t.get('device', '')))
        if pk:
            state[str(pk)] = {'ip': str(t.get('ip', ''))[:45], 'mac': str(t.get('mac', ''))[:17], 'online': bool(t.get('online')),
                              'users': t.get('users') if isinstance(t.get('users'), int) else None,
                              'faces': t.get('faces') if isinstance(t.get('faces'), int) else None,
                              'error': str(t.get('error', ''))[:200], 'at': now}
    if 'terminals' in data:
        Agent.objects.filter(pk=request.agent.pk).update(state=state)
    return JsonResponse({'ok': True, 'stamp': branch_stamp(request.agent.branch_id), 'interval': HEARTBEAT_SECONDS})


@require_GET
@_guard
def devices(request):
    rows = [{'id': d.pk, 'name': d.name, 'token': d.token, 'direction': d.direction, 'branch_id': d.branch_id,
             'branch': str(d.branch) if d.branch_id else ''} for d in _devices(request)]
    out = {'ok': True, 'devices': rows}
    if request.agent:
        out['branch'] = {'id': request.agent.branch_id, 'name': request.agent.branch.name, 'org': request.agent.branch.organization.label}
    return JsonResponse(out)


@require_GET
@_guard
def manifest(request, token):
    device = _device(request, token)
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
    users = User.objects.filter(is_active=True)
    if request.agent:              # filial kaliti: faqat o'z filialining odamlari
        b = request.agent.branch_id
        users = users.filter(Q(student__branch_id=b) | Q(role__in=[User.Role.TEACHER, User.Role.STAFF], branches=b)).distinct()
    user = get_object_or_404(users, pk=user_id)
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
    device = _device(request, token)
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
