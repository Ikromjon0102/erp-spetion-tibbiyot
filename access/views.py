import json
import logging
from datetime import datetime

from django.db import IntegrityError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.models import Student

from .models import AccessEvent, Device

log = logging.getLogger(__name__)


def _extract_json(request):
    """Hikvision 'HTTP listening' hodisani yo'nalishga qarab ikki xil yuboradi:
    multipart (event_log nomli JSON qism + rasm) yoki oddiy JSON tanasi."""
    if (request.content_type or '').startswith('multipart'):
        text = request.POST.get('event_log')
        if text is None:  # qism nomi boshqacha bo'lsa, JSONga o'xshagan birinchi maydonni olamiz
            text = next((v for v in request.POST.values() if v.lstrip().startswith('{')), None)
    else:
        text = request.body.decode('utf-8', 'ignore')
    if not text:
        return None
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        return None
    return json.loads(text[start:end + 1])


def _parse_time(value):
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return timezone.now()
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


@csrf_exempt
@require_POST
def hikvision_push(request, token):
    try:
        device = Device.objects.get(token=token, is_active=True)
    except Device.DoesNotExist:
        return JsonResponse({'ok': False}, status=404)

    try:
        data = _extract_json(request)
    except ValueError:
        log.warning('Hikvision: JSON o\'qib bo\'lmadi (%s)', device)
        return JsonResponse({'ok': False, 'error': 'bad_json'}, status=400)

    device.last_seen = timezone.now()
    device.save(update_fields=['last_seen'])  # heartbeat ham qurilma "tirik"ligini ko'rsatadi

    ev = (data or {}).get('AccessControllerEvent') or {}
    employee_no = str(ev.get('employeeNoString') or ev.get('employeeNo') or '').strip()
    if not employee_no:  # heartbeat yoki shaxs aniqlanmagan hodisa
        return JsonResponse({'ok': True, 'ignored': True})

    event, created = None, False
    try:
        event, created = AccessEvent.objects.get_or_create(
            device=device, employee_no=employee_no, occurred_at=_parse_time(data.get('dateTime')),
            defaults={
                'student': Student.objects.filter(access_id=employee_no).first(),
                'person_name': str(ev.get('name') or '')[:100],
                'direction': device.direction,
                'sub_type': ev.get('subEventType') if isinstance(ev.get('subEventType'), int) else None,
                'raw': json.dumps(data, ensure_ascii=False)[:4000],
            })
    except IntegrityError:  # bir vaqtda kelgan takror so'rov
        pass
    return JsonResponse({'ok': True, 'created': created})
