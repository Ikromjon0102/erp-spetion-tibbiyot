"""Spetion agent yadrosi (oynasiz qism): sozlama, maxfiy qiymatlarni shifrlash, server bilan aloqa,
terminallarni tarmoqdan topish va rasmlarni yuborish tsikli. Oyna va tray — app.py.

Ish tartibi:
  * har daqiqa serverga «tirikman» (heartbeat) + terminallar holati; javobda filial izi (stamp);
  * iz o'zgarsa (yangi rasm, chiqib ketgan o'quvchi ...) — barcha biriktirilgan terminallarga sync;
  * xato qolgan bo'lsa 30 daqiqadan keyin qayta urinadi; har 6 soatda baribir to'liq tekshiradi;
  * terminal IP si o'zgarsa — MAC bo'yicha qayta topadi (SADP, bo'lmasa ARP);
  * har 6 soatda yangi versiyani tekshiradi va o'zini yangilaydi (faqat exe holatida).
"""
import base64
import hashlib
import json
import logging
import os
import re
import socket
import struct
import sys
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from access.hikvision import Client, DeviceError  # noqa: E402
from tools.push_faces import FATAL, Terminal, arp_table, norm_mac, sweep, sync_terminal  # noqa: E402

VERSION = '0.1.1'
DEFAULT_URL = 'https://my.spetion.uz'
APP_DIR = Path(os.environ.get('SPETION_AGENT_DIR') or Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'SpetionAgent')

STATUS_EVERY = 300          # terminaldagi odam/yuz sonini shuncha soniyada bir so'raymiz
RETRY_FAILED = 1800         # xato qolgan bo'lsa qayta urinish
FULL_EVERY = 6 * 3600       # iz o'zgarmasa ham to'liq tekshiruv
DEVICES_EVERY = 600         # panel terminallari ro'yxatini yangilash
UPDATE_EVERY = 6 * 3600

log = logging.getLogger('spetion_agent')


# ---- maxfiy qiymatlar: Windows DPAPI (faqat shu foydalanuvchi va shu kompyuterda ochiladi) --------------------------------

def _dpapi(data, protect):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]

    buf = ctypes.create_string_buffer(data, len(data))
    src, out = Blob(len(data), buf), Blob()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    if not fn(ctypes.byref(src), None, None, None, None, 0x1, ctypes.byref(out)):   # 0x1: UI ko'rsatilmasin
        raise OSError('DPAPI xatosi')
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def protect(text):
    if not text:
        return ''
    if os.name == 'nt':
        return 'dpapi:' + base64.b64encode(_dpapi(text.encode(), True)).decode()
    return 'plain:' + base64.b64encode(text.encode()).decode()          # faqat sinov (Windows'dan tashqarida)


def unprotect(value):
    if not value:
        return ''
    kind, _, data = value.partition(':')
    raw = base64.b64decode(data)
    return (_dpapi(raw, False) if kind == 'dpapi' else raw).decode()


# ---- sozlama ---------------------------------------------------------------------------------------------------------------

class Config:
    """APP_DIR/config.json. Kalit va terminal paroli shifrlangan holda."""

    def __init__(self, path=None):
        self.path = Path(path or APP_DIR / 'config.json')
        self.data = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding='utf-8'))
            except ValueError:
                log.error('config.json buzilgan — yangidan boshlanadi')
        self.data.setdefault('server_url', DEFAULT_URL)
        self.data.setdefault('terminals', {})          # {qurilma tokeni: {'mac', 'ip', 'label'}}
        self._lock = threading.Lock()

    def save(self):
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding='utf-8')
            os.replace(tmp, self.path)

    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, **kw):
        self.data.update(kw)
        self.save()

    @property
    def key(self):
        return unprotect(self.data.get('key', ''))

    @property
    def password(self):
        return unprotect(self.data.get('password', ''))

    @property
    def paired(self):
        return bool(self.data.get('key'))

    def set_key(self, key, branch):
        self.set(key=protect(key), branch=branch, last_stamp='', last_full=0)

    def set_password(self, password):
        self.set(password=protect(password))

    def unpair(self):
        for k in ('key', 'branch', 'last_stamp'):
            self.data.pop(k, None)
        self.data['terminals'] = {}
        self.save()


# ---- server ---------------------------------------------------------------------------------------------------------------

class ServerError(requests.RequestException):
    """Server bilan muammo. requests xatosi sifatida: push_faces.sync_terminal rasm olinmaganini bitta odam xatosi deb hisoblaydi."""


class AuthError(ServerError):
    """Kalit noto'g'ri yoki paneldan uzilgan."""


class AgentServer:
    """Server API (access/agent.py). tools/push_faces.sync_terminal kutadigan manifest/photo/report usullari bilan."""

    def __init__(self, url, key=''):
        self.url = url.rstrip('/') + '/api/access/agent'
        self.s = requests.Session()
        self.s.headers['X-Agent-Version'] = VERSION
        if key:
            self.s.headers['Authorization'] = f'Bearer {key}'

    def _request(self, method, path, **kw):
        try:
            r = self.s.request(method, self.url + path, timeout=kw.pop('timeout', 30), **kw)
        except requests.RequestException as e:
            raise ServerError(f'Serverga ulanib bo\'lmadi: {e.__class__.__name__}')
        return r

    def _call(self, method, path, **kw):
        r = self._request(method, path, **kw)
        if r.status_code == 401:
            raise AuthError("Kalit noto'g'ri yoki agent paneldan uzilgan. Qayta ulang.")
        if r.status_code >= 400:
            try:
                msg = r.json().get('error')
            except ValueError:
                msg = None
            raise ServerError(msg or f'Server xatosi (HTTP {r.status_code})')
        return r

    def _post_json(self, path, payload):
        return self._call('POST', path, data=json.dumps(payload), headers={'Content-Type': 'application/json'}, timeout=60)

    def pair(self, code, name):
        r = self._request('POST', '/pair/', data=json.dumps({'code': code, 'name': name, 'version': VERSION}),
                          headers={'Content-Type': 'application/json'})
        try:
            data = r.json()
        except ValueError:
            data = {}
        if r.status_code != 200 or not data.get('ok'):
            raise ServerError(data.get('error') or f'Server xatosi (HTTP {r.status_code})')
        return data

    def heartbeat(self, terminals):
        return self._post_json('/heartbeat/', {'terminals': terminals}).json()

    def devices(self):
        return self._call('GET', '/devices/').json()

    def manifest(self, token):
        return self._call('GET', f'/manifest/{token}/').json()

    def photo(self, user_id):
        return self._call('GET', f'/photo/{user_id}/').content

    def report(self, token, payload):
        return self._post_json(f'/report/{token}/', payload).json()

    def release(self):
        return self._call('GET', '/release/').json()

    def release_file(self):
        return self._call('GET', '/release/file/', timeout=300).content


# ---- terminallarni tarmoqdan topish ----------------------------------------------------------------------------------------

SADP_GROUP, SADP_PORT = '239.255.255.250', 37020


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('192.0.2.1', 9))
        return s.getsockname()[0]
    finally:
        s.close()


def parse_sadp(payload):
    """Hikvision SADP javobi (XML) -> {'ip', 'mac', 'model', 'serial', 'port', 'activated'} yoki None."""
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return None
    if root.tag != 'ProbeMatch':
        return None
    get = lambda tag: (root.findtext(tag) or '').strip()          # noqa: E731
    ip, mac = get('IPv4Address'), get('MAC')
    if not ip or not mac:
        return None
    serial = get('DeviceSN')
    model = device_model(serial, get('DeviceDescription'), get('DeviceType'))
    return {'ip': ip, 'mac': norm_mac(mac), 'model': model, 'serial': serial, 'port': int(get('HttpPort') or 80),
            'activated': get('Activated').lower() != 'false', 'terminal': is_terminal(model)}


def device_model(serial, *names):
    """Qurilma modeli. Ko'p qurilmada DeviceType raqam kodi (852140), haqiqiy model esa seriya boshida:
    'DS-K1T341CM20260119V03...' -> 'DS-K1T341CM' (sanadan oldingi qism)."""
    m = re.match(r'(.+?)20\d{6}', serial or '')
    if m:
        return m.group(1)
    return next((n for n in names if n and not n.isdigit()), '') or next((n for n in names if n), '')


def is_terminal(model):
    """Hikvision kirish nazorati / yuz terminali (DS-K1T..., DS-K5...), kamera va registrator emas."""
    return (model or '').upper().startswith('DS-K')


def sadp_probe(timeout=3.0):
    """Tarmoqdagi Hikvision qurilmalari (SADP multicast so'rovi). Parol kerak emas."""
    found = {}
    me = local_ip()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(('', SADP_PORT))
        except OSError:
            s.bind(('', 0))                                      # port band (masalan SADP Tool ochiq)
        try:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, struct.pack('4s4s', socket.inet_aton(SADP_GROUP), socket.inet_aton(me)))
        except OSError:
            pass
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(me))
        probe = (f'<?xml version="1.0" encoding="utf-8"?><Probe><Uuid>{str(uuid.uuid4()).upper()}</Uuid>'
                 '<Types>inquiry</Types></Probe>').encode()
        s.sendto(probe, (SADP_GROUP, SADP_PORT))
        end = time.monotonic() + timeout
        while (left := end - time.monotonic()) > 0:
            s.settimeout(left)
            try:
                data, _ = s.recvfrom(65535)
            except (socket.timeout, OSError):
                break
            dev = parse_sadp(data)
            if dev:
                found[dev['mac']] = dev
    finally:
        s.close()
    return list(found.values())


def arp_lookup():
    """{mac: ip} — tarmoqni qisqa skanerlab (port 80), keyin ARP jadvalidan."""
    try:
        sweep(local_ip().rsplit('.', 1)[0])
    except OSError:
        pass
    return arp_table()


def mac_for_ip(ip, password=''):
    """Qo'lda kiritilgan IP uchun MAC: avval ARP, bo'lmasa terminalning o'zidan (deviceInfo, parol kerak)."""
    try:
        socket.create_connection((ip, 80), timeout=2).close()
    except OSError:
        raise DeviceError(f"{ip}: javob yo'q")
    for mac, addr in arp_table().items():
        if addr == ip:
            return mac
    if password:
        m = re.search(r'<macAddress>([^<]+)</macAddress>', Client(Terminal(ip, password)).info())
        if m:
            return norm_mac(m.group(1))
    return ''


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r'\d+', v or '0'))


# ---- ish tsikli ------------------------------------------------------------------------------------------------------------

class Worker:
    """Fon ishi. Oyna `state` ni o'qiydi, `wake()` bilan darhol tsiklni chaqiradi."""

    def __init__(self, config, server=None, client_factory=None, discover=None):
        self.cfg = config
        self._server = server
        self.client_factory = client_factory or (lambda host, password: Client(Terminal(host, password)))
        self.discover = discover or self._discover
        self.devices = []
        self.state = {'server': '', 'server_ok': False, 'syncing': False, 'last_sync': '', 'terminals': {}, 'update': ''}
        self._status_at = {}
        self._devices_at = 0
        self._update_at = 0
        self._force = False
        self._wake = threading.Event()
        self.stop_event = threading.Event()
        self.restart_requested = False

    @property
    def server(self):
        if self._server is None:
            self._server = AgentServer(self.cfg.get('server_url'), self.cfg.key)
        return self._server

    def reset_server(self):
        self._server = None

    def wake(self, force_sync=False):
        self._force = self._force or force_sync
        self._wake.set()

    # -- terminallar --
    def _discover(self):
        found = {d['mac']: d['ip'] for d in sadp_probe()}
        if not found:
            found = arp_lookup()
        return found

    def refresh_ips(self):
        """Biriktirilgan terminallarning IP sini MAC bo'yicha yangilaydi (DHCP o'zgartirgan bo'lishi mumkin)."""
        mapped = self.cfg.get('terminals')
        if not any(t.get('mac') for t in mapped.values()):
            return
        table = self.discover()
        changed = False
        for t in mapped.values():
            ip = table.get(norm_mac(t['mac'])) if t.get('mac') else None
            if ip and ip != t.get('ip'):
                log.info("%s: IP o'zgardi %s -> %s", t.get('label') or t['mac'], t.get('ip'), ip)
                t['ip'], changed = ip, True
        if changed:
            self.cfg.save()

    def _terminal_status(self, token, t, force=False):
        st = self.state['terminals'].get(token) or {}
        if not force and time.monotonic() - self._status_at.get(token, -1e9) < STATUS_EVERY and st:
            return st
        self._status_at[token] = time.monotonic()
        st = {'ip': t.get('ip', ''), 'mac': t.get('mac', ''), 'online': False, 'users': None, 'faces': None, 'error': '',
              'note': st.get('note', '')}
        if not self.cfg.password:
            st['error'] = 'Terminal paroli kiritilmagan'
        elif t.get('ip'):
            try:
                st['users'], st['faces'] = self.client_factory(t['ip'], self.cfg.password).user_count()
                st['online'] = True
            except DeviceError as e:
                st['error'] = str(e)
        self.state['terminals'][token] = st
        return st

    def heartbeat(self):
        mapped = self.cfg.get('terminals')
        known = {d['token'] for d in self.devices}
        rows = []
        for token, t in mapped.items():
            if known and token not in known:
                continue
            st = self._terminal_status(token, t)
            rows.append({'device': token, 'ip': st['ip'], 'mac': st['mac'], 'online': st['online'],
                         'users': st['users'], 'faces': st['faces'], 'error': st['error']})
        if any(not r['online'] and 'ulanib bo' in r['error'] for r in rows) and any(t.get('mac') for t in mapped.values()):
            self.refresh_ips()
        return self.server.heartbeat(rows)

    def sync_all(self):
        """Barcha biriktirilgan terminallarga sync. True — hammasi xatosiz."""
        mapped = self.cfg.get('terminals')
        password = self.cfg.password
        if not password:
            log.warning('Terminal paroli kiritilmagan — rasm yuborilmaydi')
            return False
        ok = True
        self.state['syncing'] = True
        try:
            for dev in self.devices:
                t = mapped.get(dev['token'])
                if not t or not t.get('ip'):
                    continue
                st = self.state['terminals'].setdefault(dev['token'], {})
                try:
                    note = sync_terminal(self.server, dev, self.client_factory(t['ip'], password))
                    st['note'], st['error'] = note, ''
                    log.info('%s: %s', dev['name'], note)
                    if not note.endswith('xato 0'):
                        ok = False
                except DeviceError as e:
                    ok = False
                    st['error'] = str(e)
                    log.error('%s: %s', dev['name'], e)
                    if any(f in str(e) for f in FATAL):
                        self._status_at.pop(dev['token'], None)
                self._status_at.pop(dev['token'], None)      # keyingi heartbeat'da yangi sonlar
        finally:
            self.state['syncing'] = False
        self.state['last_sync'] = time.strftime('%d.%m %H:%M')
        return ok

    def check_update(self):
        if not getattr(sys, 'frozen', False):
            return
        info = self.server.release()
        new = info.get('version')
        if not new or version_tuple(new) <= version_tuple(VERSION):
            return
        log.info('Yangi versiya %s — yuklab olinmoqda', new)
        data = self.server.release_file()
        if hashlib.sha256(data).hexdigest() != info.get('sha256'):
            log.error('Yangi versiya fayli buzilgan (sha256 mos emas) — o\'rnatilmadi')
            return
        exe = Path(sys.executable)
        tmp = exe.with_suffix('.new')
        tmp.write_bytes(data)
        old = exe.with_suffix('.old')
        if old.exists():
            old.unlink()
        os.replace(exe, old)              # ishlab turgan exe ni qayta nomlash mumkin
        os.replace(tmp, exe)
        self.state['update'] = new
        self.restart_requested = True
        self.stop_event.set()
        self._wake.set()

    def cycle(self):
        """Bitta aylanish. Qaytaradi: keyingi aylanishgacha soniya."""
        now = time.time()
        try:
            if not self.devices or time.monotonic() - self._devices_at > DEVICES_EVERY:
                info = self.server.devices()
                self.devices = info['devices']
                if info.get('branch'):
                    self.cfg.data['branch'] = info['branch']
                self._devices_at = time.monotonic()
            beat = self.heartbeat()
            self.state['server_ok'], self.state['server'] = True, ''
        except AuthError as e:
            self.state['server_ok'], self.state['server'] = False, str(e)
            return 300
        except ServerError as e:
            self.state['server_ok'], self.state['server'] = False, str(e)
            log.warning('%s', e)
            return 60
        stamp = beat.get('stamp', '')
        last_ok = self.cfg.get('last_stamp') == stamp
        failed_at = self.cfg.get('failed_at', 0)
        due = (self._force or not last_ok or now - self.cfg.get('last_full', 0) > FULL_EVERY
               or (failed_at and now - failed_at > RETRY_FAILED))
        if due and self.cfg.get('terminals'):
            self._force = False
            try:
                ok = self.sync_all()
            except ServerError as e:
                log.warning('Sync to\'xtadi: %s', e)
                ok = False
            if ok:
                self.cfg.set(last_stamp=stamp, last_full=now, failed_at=0)
            else:
                self.cfg.set(failed_at=now)
            try:
                self.heartbeat()          # panelda yangi sonlar darhol ko'rinsin
            except ServerError:
                pass
        if time.monotonic() - self._update_at > UPDATE_EVERY:
            self._update_at = time.monotonic()
            try:
                self.check_update()
            except (ServerError, OSError) as e:
                log.warning('Yangilanishni tekshirib bo\'lmadi: %s', e)
        return int(beat.get('interval') or 60)

    def run(self):
        while not self.stop_event.is_set():
            if not self.cfg.paired:
                wait = 5
            else:
                try:
                    wait = self.cycle()
                except Exception:                    # fon ishi hech qachon to'xtab qolmasin
                    log.exception('Kutilmagan xato')
                    wait = 60
            self._wake.wait(wait)
            self._wake.clear()
