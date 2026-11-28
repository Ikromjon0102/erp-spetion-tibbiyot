"""ISUP shlyuzi: backend (SDK) + qurilmalar ro'yxati + hodisalarni Django'ga yuborish + ichki API.

Ikki HTTP tinglovchi:
  * ichki API — faqat 127.0.0.1:7690, `Authorization: Bearer <ISUP_API_TOKEN>` (Django shu orqali terminalga ISAPI yuboradi)
      GET  /health                      {'ok', 'online': n, 'spool': n}
      GET  /devices                     [{'device_id', 'name', 'online', 'since'}]
      POST /isapi  {device_id, method, path, body, timeout}       -> {'ok', 'text'}
      POST /face   {device_id, employee_no, jpeg (base64)}        -> {'ok'}  (rasm vaqtincha manzilga, terminalga faceURL)
  * rasm berish — 127.0.0.1:7691, nginx `location /isup-face/` orqali tashqariga: GET /isup-face/<token>.jpg (tokensiz — 404)
"""
import base64
import binascii
import hmac
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from access.hikvision import DeviceError

from .events import parse_alarm
from .isapi import PassthroughClient, check_request

log = logging.getLogger('isup.gateway')
FACE_PREFIX = '/isup-face/'
MAX_BODY = 1024 * 1024


class Gateway:
    def __init__(self, backend, registry, forwarder, faces, face_base_url, api_token, clock=time.time):
        if not api_token or len(api_token) < 24:
            raise ValueError('ISUP_API_TOKEN kamida 24 belgi bo\'lsin')
        self.backend, self.registry, self.forwarder, self.faces = backend, registry, forwarder, faces
        self.face_base = face_base_url.rstrip('/') + '/'
        self.api_token, self.clock = api_token, clock
        self.online = {}                       # device_id -> ulanish vaqti (unix)
        self._locks = {}
        self._locks_guard = threading.Lock()

    def start(self):
        self.backend.start(self)

    # ---- backend chaqiradi ----------------------------------------------------------------------------------------------

    def on_register(self, device_id, info=None):
        if device_id not in self.registry:
            log.warning("Ro'yxatda yo'q terminal ulanmoqchi: %r %s", device_id, info or '')
            return False
        return True

    def on_auth(self, device_id):
        return self.registry.key_for(device_id)

    def on_online(self, device_id):
        self.online[device_id] = self.clock()
        log.info('Terminal ulandi: %s', device_id)
        self.forwarder.heartbeat(device_id)

    def on_offline(self, device_id):
        if self.online.pop(device_id, None) is not None:
            log.warning('Terminal uzildi: %s', device_id)

    def on_alarm(self, device_id, data):
        payload = parse_alarm(data)
        if payload is None:
            log.warning("Hodisani o'qib bo'lmadi: %s %r", device_id, bytes(data[:120]) if isinstance(data, bytes) else data[:120])
            return None
        return self.forwarder.forward(device_id, payload)

    # ---- terminalga ISAPI -------------------------------------------------------------------------------------------------

    def _lock(self, device_id):
        with self._locks_guard:
            return self._locks.setdefault(device_id, threading.Lock())

    def isapi(self, device_id, method, path, body=None, timeout=10):
        check_request(method, path)
        if device_id not in self.online:
            raise DeviceError(f"Qurilmaga ulanib bo'lmadi: {device_id} ISUP orqali ulanmagan")
        with self._lock(device_id):            # terminal bir vaqtda bitta so'rovni yaxshi ko'radi
            return self.backend.passthrough(device_id, method, path, body, timeout)

    def _stage(self, jpeg):
        token = self.faces.put(jpeg)
        return f'{self.face_base}{token}.jpg', (lambda: self.faces.drop(token))

    def client(self, device_id):
        return PassthroughClient(self.isapi, device_id, stage=self._stage)

    def tick(self):
        """Har daqiqa: ulangan terminallar uchun «tirik» signali va navbatdagi hodisalarni qayta yuborish."""
        for device_id in list(self.online):
            self.forwarder.heartbeat(device_id)
        return self.forwarder.flush()

    # ---- HTTP -----------------------------------------------------------------------------------------------------------

    def _authorized(self, headers):
        got = (headers.get('Authorization') or '').removeprefix('Bearer ').strip()
        return bool(got) and hmac.compare_digest(got, self.api_token)

    def handle_internal(self, method, path, headers, body):
        """-> (HTTP status, dict)."""
        if not self._authorized(headers):
            return 401, {'ok': False, 'error': 'token'}
        if (method, path) == ('GET', '/health'):
            return 200, {'ok': True, 'online': len(self.online), 'registered': len(self.registry),
                         'spool': self.forwarder.pending()}
        if (method, path) == ('GET', '/devices'):
            return 200, {'ok': True, 'devices': [
                {'device_id': e.device_id, 'name': e.name, 'online': e.device_id in self.online,
                 'since': self.online.get(e.device_id)} for e in self.registry]}
        if method != 'POST' or path not in ('/isapi', '/face'):
            return 404, {'ok': False, 'error': 'not_found'}
        try:
            data = json.loads(body or b'{}')
        except ValueError:
            return 400, {'ok': False, 'error': 'json'}
        device_id = str(data.get('device_id', ''))
        if device_id not in self.registry:
            return 404, {'ok': False, 'error': "Qurilma ISUP ro'yxatida yo'q"}
        try:
            if path == '/isapi':
                text = self.isapi(device_id, str(data.get('method', '')), str(data.get('path', '')), data.get('body'),
                                  min(int(data.get('timeout') or 10), 60))
                return 200, {'ok': True, 'text': text}
            jpeg = base64.b64decode(str(data.get('jpeg', '')), validate=True)
            self.client(device_id).set_face(str(data.get('employee_no', '')), jpeg)
            return 200, {'ok': True}
        except (ValueError, binascii.Error) as e:
            return 400, {'ok': False, 'error': str(e)[:200]}
        except DeviceError as e:
            return 200, {'ok': False, 'error': str(e)[:300]}

    def handle_public(self, method, path):
        """-> (status, content_type, bytes). Faqat GET /isup-face/<token>.jpg."""
        if method != 'GET' or not path.startswith(FACE_PREFIX) or not path.endswith('.jpg'):
            return 404, 'text/plain', b'not found'
        jpeg = self.faces.get(path[len(FACE_PREFIX):-4])
        if jpeg is None:
            return 404, 'text/plain', b'not found'
        return 200, 'image/jpeg', jpeg


def _handler(dispatch):
    class H(BaseHTTPRequestHandler):
        server_version = 'isup-gateway'

        def _run(self):
            n = int(self.headers.get('Content-Length') or 0)
            if n > MAX_BODY:
                self.send_error(413)
                return
            status, ctype, data = dispatch(self.command, self.path, self.headers, self.rfile.read(n) if n else b'')
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_DELETE = _run

        def log_message(self, fmt, *args):      # rasm tokenlari jurnalga yozilmasin
            log.debug('%s %s', self.command, self.path.split('?')[0][:40])
    return H


def serve(gateway, internal=('127.0.0.1', 7690), public=('127.0.0.1', 7691)):
    """Ikkala tinglovchini fon oqimlarida ishga tushiradi; serverlarni qaytaradi (to'xtatish: .shutdown())."""
    def internal_dispatch(method, path, headers, body):
        status, out = gateway.handle_internal(method, path, headers, body)
        return status, 'application/json', json.dumps(out, ensure_ascii=False).encode('utf-8')

    def public_dispatch(method, path, headers, body):
        return gateway.handle_public(method, path)

    servers = [ThreadingHTTPServer(internal, _handler(internal_dispatch)), ThreadingHTTPServer(public, _handler(public_dispatch))]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    return servers
