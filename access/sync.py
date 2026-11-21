"""Rasmlarni qurilmalar bilan sinxronlash: kimning rasmi o'zgargan bo'lsa, faqat o'shalar yuboriladi."""
import hashlib
import logging
import threading

from django.conf import settings
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from accounts.photos import photo_bytes

from .hikvision import Client, DeviceError
from .models import Device, FaceSync

log = logging.getLogger(__name__)
_lock = threading.Lock()


def eligible_users(device=None):
    """Qurilmada bo'lishi kerak odamlar: rasmi va Face ID si bor, faol o'quvchi/ustoz/xodimlar (sinov hisoblari emas).
    `device` berilsa, faqat shu qurilma filialining odamlari: o'quvchilar shu filialdan, ustoz/xodimlar shu filialda ishlaydiganlar."""
    users = (User.objects.filter(is_active=True, role__in=[User.Role.STUDENT, User.Role.TEACHER, User.Role.STAFF], is_demo=False)
             .exclude(photo='').exclude(photo__isnull=True).exclude(username__startswith='sinov_')
             .select_related('student'))
    if device is not None and device.branch_id:
        users = users.filter(Q(student__branch_id=device.branch_id) | Q(role__in=[User.Role.TEACHER, User.Role.STAFF], branches=device.branch_id)).distinct()
    return [u for u in users if u.device_id]


def _display_name(user):
    return (user.get_full_name() or user.username).strip()


def _digest(user, jpeg):
    return hashlib.sha256(f'{user.device_id}|{_display_name(user)}|'.encode() + jpeg).hexdigest()


def pending_count(device, people=None):
    people = eligible_users(device) if people is None else people
    done = {fs.user_id: fs.digest for fs in device.face_syncs.filter(ok=True)}
    n = 0
    for u in people:
        try:
            if done.get(u.pk) != _digest(u, photo_bytes(u)):
                n += 1
        except (OSError, ValueError):
            n += 1
    return n


def sync_device(device, only_user_id=None):
    """Bitta qurilma bilan sync. {'sent': n, 'skipped': n, 'removed': n, 'failed': n, 'error': matn|''}"""
    result = {'sent': 0, 'skipped': 0, 'removed': 0, 'failed': 0, 'error': ''}
    if not device.host:
        result['error'] = 'Qurilma manzili kiritilmagan'
        return result
    client = Client(device)
    people = eligible_users(device)
    wanted = {u.pk for u in people}
    states = {fs.user_id: fs for fs in device.face_syncs.all()}
    try:
        for u in people:
            if only_user_id and u.pk != only_user_id:
                continue
            try:
                jpeg = photo_bytes(u)
            except OSError:
                continue
            digest = _digest(u, jpeg)
            state = states.get(u.pk)
            if state and state.ok and state.digest == digest:
                result['skipped'] += 1
                continue
            emp = u.device_id
            try:
                if state and state.ok and state.employee_no != emp:      # Face ID o'zgargan: eski yozuv olib tashlanadi
                    client.delete_user(state.employee_no)
                client.upsert_user(emp, _display_name(u))
                client.set_face(emp, jpeg)
            except DeviceError as e:
                if 'ulanib bo' in str(e) or 'parol' in str(e):
                    raise
                FaceSync.objects.update_or_create(device=device, user=u, defaults={'employee_no': emp, 'digest': '', 'ok': False, 'error': str(e)[:300]})
                result['failed'] += 1
                continue
            FaceSync.objects.update_or_create(device=device, user=u, defaults={
                'employee_no': emp, 'digest': digest, 'ok': True, 'error': '', 'synced_at': timezone.now()})
            result['sent'] += 1
        if not only_user_id:       # rasmi olib tashlangan / nofaol bo'lganlar qurilmadan ham o'chiriladi
            for uid, state in states.items():
                if state.ok and uid not in wanted:
                    try:
                        client.delete_user(state.employee_no)
                    except DeviceError as e:
                        if 'ulanib bo' in str(e) or 'parol' in str(e):
                            raise
                    state.delete()
                    result['removed'] += 1
    except DeviceError as e:
        result['error'] = str(e)
    if not only_user_id or result['error']:
        note = result['error'] or (f"Yuborildi: {result['sent']}, o'zgarmagan: {result['skipped']}, "
                                   f"o'chirildi: {result['removed']}, xato: {result['failed']}")
        Device.objects.filter(pk=device.pk).update(last_sync_at=timezone.now(), last_sync_note=note[:300])
    return result


def sync_all(only_user_id=None):
    out = {}
    for device in Device.objects.filter(is_active=True).exclude(host=''):
        out[device.pk] = sync_device(device, only_user_id)
    return out


def sync_in_background(only_user_id=None):
    """Rasm yuklanganda so'rovni kutdirmasdan fonda yuboradi (qurilma yo'q bo'lsa — hech narsa qilmaydi)."""
    if not Device.objects.filter(is_active=True).exclude(host='').exists():
        return

    def work():
        with _lock:
            try:
                sync_all(only_user_id)
            except Exception:       # fon jarayoni hech qachon so'rovni buzmasligi kerak
                log.exception('Rasm sync xatosi')
            finally:
                close_old_connections()
    if getattr(settings, 'FACE_SYNC_BACKGROUND', True):
        threading.Thread(target=work, daemon=True).start()
    else:
        work()
