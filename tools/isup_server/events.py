"""Terminal hodisalari: ISUP alarm (JSON yoki XML) -> mavjud «HTTP listening» formati -> Django.

Django tomonida o'zgarish kerak emas: shlyuz hodisani qurilmaning mavjud manziliga yuboradi
(POST /api/access/hikvision/<Device.token>/). U yerda (qurilma, Face ID, vaqt) bo'yicha takror yozilmaydi, shuning uchun
o'tish davrida terminal hodisani ham HTTP listening, ham ISUP orqali yuborsa — bitta yozuv qoladi.

Django javob bermasa (qayta ishga tushirish, deploy) hodisa diskdagi navbatga (jsonl) yoziladi va keyin yuboriladi.
"""
import json
import logging
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

log = logging.getLogger('isup.events')

SENT, SPOOLED, REJECTED, UNKNOWN, FAILED = 'sent', 'spooled', 'rejected', 'unknown', 'failed'
MAX_SPOOL_LINES = 50000


def _strip_ns(tag):
    return tag.rsplit('}', 1)[-1]


def _xml_to_dict(node):
    children = list(node)
    if not children:
        return (node.text or '').strip()
    out = {}
    for ch in children:
        key, value = _strip_ns(ch.tag), _xml_to_dict(ch)
        if key in out:                       # takrorlangan teg -> ro'yxat
            out[key] = out[key] if isinstance(out[key], list) else [out[key]]
            out[key].append(value)
        else:
            out[key] = value
    return out


def _int_fields(ev):
    for k in ('majorEventType', 'subEventType'):
        if isinstance(ev.get(k), str) and ev[k].isdigit():
            ev[k] = int(ev[k])
    return ev


def parse_alarm(data):
    """ISUP alarm matni (bytes/str, JSON yoki XML EventNotificationAlert) -> dict (HTTP listening JSON bilan bir xil shakl).
    O'qib bo'lmasa None."""
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).rstrip(b'\x00').decode('utf-8', 'ignore')
    text = (data or '').strip()
    if not text:
        return None
    if text.startswith('<'):
        try:
            root = ET.fromstring(text.encode('utf-8'))
        except ET.ParseError:
            return None
        out = _xml_to_dict(root)
        if not isinstance(out, dict):
            return None
        if isinstance(out.get('AccessControllerEvent'), dict):
            _int_fields(out['AccessControllerEvent'])
        return out
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        out = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return out if isinstance(out, dict) else None


def employee_no(payload):
    ev = (payload or {}).get('AccessControllerEvent') or {}
    return str(ev.get('employeeNoString') or ev.get('employeeNo') or '').strip()


def http_poster(base_url, host_header='', timeout=10):
    """post(token, body) -> HTTP status. Ulanish xatosida OSError (navbatga yoziladi)."""
    base = base_url.rstrip('/')

    def post(token, body):
        req = urllib.request.Request(f'{base}/api/access/hikvision/{token}/', data=body, method='POST',
                                     headers={'Content-Type': 'application/json'})
        if host_header:
            req.add_header('Host', host_header)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code
    return post


class Forwarder:
    """Hodisalarni Django'ga yuboradi. 2xx — yuborildi; 4xx — rad etildi (token noto'g'ri / buzuq ma'lumot: qayta urinish
    foydasiz, log); 5xx yoki ulanish xatosi — navbatga, `flush()` keyin qayta yuboradi."""

    def __init__(self, registry, post, spool_path):
        self.registry, self.post, self.spool = registry, post, Path(spool_path)
        self._lock = threading.Lock()

    def _send(self, token, payload):
        status = self.post(token, json.dumps(payload, ensure_ascii=False).encode('utf-8'))
        if 200 <= status < 300:
            return SENT
        if 400 <= status < 500:
            return REJECTED
        raise OSError(f'HTTP {status}')

    def forward(self, device_id, payload):
        entry = self.registry.get(device_id)
        if entry is None:
            log.warning('Ro\'yxatda yo\'q qurilmadan hodisa: %s', device_id)
            return UNKNOWN
        try:
            result = self._send(entry.token, payload)
        except OSError as e:
            log.warning('Django javob bermadi (%s) — navbatga: %s', e, device_id)
            self._append(device_id, payload)
            return SPOOLED
        if result == REJECTED:
            log.error('Django hodisani rad etdi: %s %s', device_id, employee_no(payload))
        return result

    def heartbeat(self, device_id):
        """Bo'sh JSON — mavjud view qurilmaning «Oxirgi signal» vaqtini yangilaydi (panelda onlayn ko'rinadi)."""
        entry = self.registry.get(device_id)
        if entry is None:
            return UNKNOWN
        try:
            return self._send(entry.token, {})
        except OSError:
            return FAILED          # heartbeat navbatga yozilmaydi (keyingisi baribir keladi)

    def _append(self, device_id, payload):
        with self._lock:
            self.spool.parent.mkdir(parents=True, exist_ok=True)
            lines = self.spool.read_text(encoding='utf-8').splitlines() if self.spool.exists() else []
            if len(lines) >= MAX_SPOOL_LINES:
                log.error('Navbat to\'ldi (%s) — eng eskisi tashlandi', MAX_SPOOL_LINES)
                lines = lines[-(MAX_SPOOL_LINES - 1):]
            lines.append(json.dumps({'device_id': device_id, 'payload': payload}, ensure_ascii=False))
            self.spool.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    def pending(self):
        if not self.spool.exists():
            return 0
        return sum(1 for line in self.spool.read_text(encoding='utf-8').splitlines() if line.strip())

    def flush(self):
        """Navbatdagilarni tartib bilan qayta yuboradi; birinchi ulanish xatosida to'xtaydi. Yuborilganlar soni."""
        with self._lock:
            if not self.spool.exists():
                return 0
            lines = [x for x in self.spool.read_text(encoding='utf-8').splitlines() if x.strip()]
            done = 0
            for i, line in enumerate(lines):
                try:
                    item = json.loads(line)
                except ValueError:      # buzuq qator tashlab yuboriladi
                    continue
                entry = self.registry.get(item.get('device_id'))
                if entry is None:
                    continue
                try:
                    if self._send(entry.token, item.get('payload') or {}) == SENT:
                        done += 1
                except OSError:
                    rest = lines[i:]
                    self.spool.write_text('\n'.join(rest) + '\n', encoding='utf-8')
                    return done
            self.spool.unlink()
            return done
