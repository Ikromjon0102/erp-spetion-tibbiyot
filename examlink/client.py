"""Exam platformasining o'qish API'siga so'rovlar (server-server, `X-Integration-Key`).
Sozlama: EXAM_API_URL (masalan https://exam.spetion.uz), EXAM_API_KEY. Bo'sh bo'lsa integratsiya o'chiq."""
import requests
from django.conf import settings
from django.core.cache import cache

TIMEOUT = 5
DYNAMICS_TTL = 600


class ExamUnavailable(Exception):
    pass


def enabled():
    return bool(getattr(settings, 'EXAM_API_URL', '') and getattr(settings, 'EXAM_API_KEY', ''))


def _get(path, **params):
    if not enabled():
        raise ExamUnavailable('Exam integratsiyasi sozlanmagan')
    try:
        r = requests.get(settings.EXAM_API_URL.rstrip('/') + '/api/v1/integration' + path, params=params or None,
                         headers={'X-Integration-Key': settings.EXAM_API_KEY}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ExamUnavailable(str(e))
    if r.status_code != 200:
        raise ExamUnavailable(f'Exam javobi: {r.status_code}')
    return r.json()


def fetch_students():
    return _get('/students')


def fetch_dynamics(exam_student_id, school_year=None):
    """Bitta o'quvchi dinamikasi (10 daqiqa keshlanadi); exam ishlamasa None."""
    key = f'examlink:dyn:{exam_student_id}:{school_year}'
    data = cache.get(key)
    if data is None:
        try:
            params = {'school_year': school_year} if school_year else {}
            data = _get(f'/students/{exam_student_id}/dynamics', **params)
        except (ExamUnavailable, ValueError):
            return None
        cache.set(key, data, DYNAMICS_TTL)
    return data
