"""ISUP shlyuzi prototipi: SDK va tarmoqsiz (FakeBackend, soxta terminal, Django test klienti)."""
import base64
import json
import logging
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from access.hikvision import Client, DeviceError
from access.models import AccessEvent, Device
from accounts.models import Student, User
from academics.models import Group

from .backend import FakeBackend, FakeTerminal, HikSdkBackend, SdkMissing
from .events import REJECTED, SENT, SPOOLED, UNKNOWN, Forwarder, employee_no, parse_alarm
from .faces import FaceStore
from .gateway import Gateway
from .isapi import PassthroughClient, RemoteClient, collision_report
from .registry import Entry, Registry, generate_key, valid_key

JPEG = b'\xff\xd8\xff\xe0' + b'x' * 500
TOKEN = 't' * 32


def setUpModule():
    logging.getLogger('isup').setLevel(logging.CRITICAL)     # kutilgan ogohlantirishlar test chiqishini to'ldirmasin


def tearDownModule():
    logging.getLogger('isup').setLevel(logging.NOTSET)


class RegistryTests(SimpleTestCase):
    def test_generated_key_is_valid_and_random(self):
        keys = {generate_key() for _ in range(20)}
        self.assertEqual(len(keys), 20)
        self.assertTrue(all(valid_key(k) and len(k) == 12 for k in keys))

    def test_rejects_bad_entries(self):
        for bad in (Entry('spt d1', 'abc12345', 'tok'), Entry('spt-d1', 'short1', 'tok'),
                    Entry('spt-d1', 'onlyletters', 'tok'), Entry('spt-d1', 'abc12345', '')):
            with self.assertRaises(ValueError):
                Registry([bad])
        with self.assertRaises(ValueError):
            Registry([Entry('spt-d1', 'abc12345', 'a'), Entry('spt-d1', 'abc12346', 'b')])

    def test_key_lookup(self):
        r = Registry.from_dicts([{'device_id': 'spt-d1', 'isup_key': 'abc12345', 'token': 'tok', 'name': 'Kirish-1'}])
        self.assertEqual(r.key_for('spt-d1'), 'abc12345')
        self.assertIsNone(r.key_for('spetionkirish01'))


class ParseAlarmTests(SimpleTestCase):
    def test_json_like_http_listening(self):
        raw = json.dumps({'dateTime': '2026-11-28T08:01:02+05:00', 'eventType': 'AccessControllerEvent',
                          'AccessControllerEvent': {'employeeNoString': '9001', 'subEventType': 75}}).encode() + b'\x00\x00'
        p = parse_alarm(raw)
        self.assertEqual((employee_no(p), p['dateTime']), ('9001', '2026-11-28T08:01:02+05:00'))

    def test_xml_event_notification_alert(self):
        xml = '''<?xml version="1.0" encoding="UTF-8"?>
        <EventNotificationAlert version="2.0" xmlns="http://www.isapi.org/ver20/XMLSchema">
          <dateTime>2026-11-28T08:01:02+05:00</dateTime><eventType>AccessControllerEvent</eventType>
          <AccessControllerEvent><majorEventType>5</majorEventType><subEventType>75</subEventType>
          <employeeNoString>7003</employeeNoString><name>Ustoz</name></AccessControllerEvent>
        </EventNotificationAlert>'''
        p = parse_alarm(xml)
        self.assertEqual(employee_no(p), '7003')
        self.assertEqual(p['AccessControllerEvent']['subEventType'], 75)

    def test_garbage(self):
        for raw in (b'', b'\x00', 'not json', '<broken'):
            self.assertIsNone(parse_alarm(raw))


class ForwarderTests(SimpleTestCase):
    def setUp(self):
        self.registry = Registry([Entry('spt-d1', 'abc12345', 'tok1')])
        self.spool = Path(tempfile.mkdtemp()) / 'spool.jsonl'
        self.sent, self.status = [], 200

        def post(token, body):
            if self.status is None:
                raise OSError('connection refused')
            self.sent.append((token, json.loads(body)))
            return self.status
        self.f = Forwarder(self.registry, post, self.spool)

    def test_sent_to_device_token(self):
        self.assertEqual(self.f.forward('spt-d1', {'a': 1}), SENT)
        self.assertEqual(self.sent, [('tok1', {'a': 1})])

    def test_spooled_when_django_down_then_flushed_in_order(self):
        self.status = None
        self.assertEqual(self.f.forward('spt-d1', {'n': 1}), SPOOLED)
        self.assertEqual(self.f.forward('spt-d1', {'n': 2}), SPOOLED)
        self.assertEqual(self.f.flush(), 0)
        self.assertEqual(self.f.pending(), 2)
        self.status = 200
        self.assertEqual(self.f.flush(), 2)
        self.assertEqual([p['n'] for _, p in self.sent], [1, 2])
        self.assertEqual(self.f.pending(), 0)

    def test_5xx_spooled_4xx_dropped_unknown_ignored(self):
        self.status = 502
        self.assertEqual(self.f.forward('spt-d1', {'n': 1}), SPOOLED)
        self.status = 404
        self.assertEqual(self.f.forward('spt-d1', {'n': 2}), REJECTED)
        self.assertEqual(self.f.pending(), 1)
        self.assertEqual(self.f.forward('begona', {'n': 3}), UNKNOWN)


class FaceStoreTests(SimpleTestCase):
    def test_put_get_expire_drop(self):
        now = [1000.0]
        s = FaceStore(ttl=60, clock=lambda: now[0])
        t = s.put(JPEG)
        self.assertGreaterEqual(len(t), 32)
        self.assertEqual(s.get(t), JPEG)
        now[0] += 61
        self.assertIsNone(s.get(t))
        t2 = s.put(JPEG)
        s.drop(t2)
        self.assertIsNone(s.get(t2))

    def test_rejects_non_jpeg_and_big(self):
        s = FaceStore()
        with self.assertRaises(ValueError):
            s.put(b'\x89PNG....')
        with self.assertRaises(ValueError):
            s.put(b'\xff\xd8' + b'x' * (201 * 1024))


class GatewayTests(SimpleTestCase):
    """Soxta terminal ISUP orqali ulanadi; foydalanuvchi va yuz shlyuz orqali yoziladi."""

    def setUp(self):
        self.registry = Registry([Entry('spt-d1', 'abc12345', 'tok1', 'Kirish-1'), Entry('spt-d2', 'xyz98765', 'tok2')])
        self.events = []
        self.forwarder = Forwarder(self.registry, lambda token, body: self.events.append((token, json.loads(body))) or 200,
                                   Path(tempfile.mkdtemp()) / 's.jsonl')
        self.backend = FakeBackend()
        self.gw = Gateway(self.backend, self.registry, self.forwarder, FaceStore(), 'https://my.spetion.uz/isup-face/', TOKEN)
        self.gw.start()
        self.term = FakeTerminal('spt-d1', 'abc12345', users={'101': 'Eduschool Odam'}, fetch=self.fetch)

    def fetch(self, url):
        """Terminal faceURL'ni yuklab oladi: nginx -> shlyuzning ochiq tinglovchisi."""
        prefix = 'https://my.spetion.uz'
        self.assertTrue(url.startswith(prefix + '/isup-face/'))
        status, ctype, data = self.gw.handle_public('GET', url[len(prefix):])
        return data if status == 200 else None

    def api(self, method, path, payload=None, token=TOKEN):
        return self.gw.handle_internal(method, path, {'Authorization': f'Bearer {token}'},
                                       json.dumps(payload).encode() if payload is not None else b'')

    def test_registration_requires_known_id_and_right_key(self):
        self.assertFalse(self.backend.connect(FakeTerminal('spetionkirish01', 'abc12345')))
        self.assertFalse(self.backend.connect(FakeTerminal('spt-d2', 'wrongkey1')))
        self.assertTrue(self.backend.connect(self.term))
        self.assertEqual(set(self.gw.online), {'spt-d1'})
        self.assertEqual(self.events, [('tok1', {})])          # ulanganda «tirik» signali

    def test_internal_api_needs_token(self):
        self.assertEqual(self.api('GET', '/health', token='nope')[0], 401)
        status, out = self.api('GET', '/health')
        self.assertEqual((status, out['registered'], out['online']), (200, 2, 0))

    def test_isapi_passthrough_and_path_guard(self):
        self.backend.connect(self.term)
        status, out = self.api('POST', '/isapi', {'device_id': 'spt-d1', 'method': 'GET', 'path': '/ISAPI/System/deviceInfo'})
        self.assertTrue(out['ok'])
        self.assertIn('DS-K1T341CM', out['text'])
        status, out = self.api('POST', '/isapi', {'device_id': 'spt-d1', 'method': 'GET', 'path': '/etc/passwd'})
        self.assertFalse(out['ok'])
        status, out = self.api('POST', '/isapi', {'device_id': 'spt-d2', 'method': 'GET', 'path': '/ISAPI/System/deviceInfo'})
        self.assertIn("ulanib bo'lmadi", out['error'])

    def test_user_and_face_via_faceurl_then_link_is_dead(self):
        self.backend.connect(self.term)
        c = self.gw.client('spt-d1')
        c.upsert_user('9001', 'Ali Valiyev')
        c.upsert_user('9001', 'Ali Valiyev (yangi)')               # AlreadyExist -> Modify
        c.set_face('9001', JPEG)
        self.assertEqual(self.term.users['9001'], 'Ali Valiyev (yangi)')
        self.assertEqual(self.term.faces['9001'], JPEG)
        self.assertEqual(len(self.gw.faces), 0)                    # bir martalik manzil o'chirildi
        self.assertEqual(c.user_count(), (2, 1))
        self.assertEqual(dict(c.list_users()), {'101': 'Eduschool Odam', '9001': 'Ali Valiyev (yangi)'})
        c.delete_user('9001')
        self.assertNotIn('9001', self.term.users)
        self.assertIn('101', self.term.users)                     # begona yozuvga tegilmadi

    def test_face_endpoint_and_failure(self):
        self.backend.connect(self.term)
        self.gw.client('spt-d1').upsert_user('9002', 'Madina')
        status, out = self.api('POST', '/face', {'device_id': 'spt-d1', 'employee_no': '9002',
                                                 'jpeg': base64.b64encode(JPEG).decode()})
        self.assertTrue(out['ok'], out)
        self.term.fetch = lambda url: None                         # terminal rasmni yuklay olmadi
        status, out = self.api('POST', '/face', {'device_id': 'spt-d1', 'employee_no': '9002',
                                                 'jpeg': base64.b64encode(JPEG).decode()})
        self.assertIn('downloadFaceFail', out['error'])
        self.assertEqual(self.api('POST', '/face', {'device_id': 'spt-d1', 'employee_no': '9', 'jpeg': '!!'})[0], 400)

    def test_scan_is_forwarded_and_offline(self):
        self.backend.connect(self.term)
        self.assertEqual(self.backend.scan('spt-d1', '9001', '2026-11-28T08:00:00+05:00'), SENT)
        self.assertEqual(employee_no(self.events[-1][1]), '9001')
        self.backend.disconnect('spt-d1')
        with self.assertRaises(DeviceError):
            self.gw.client('spt-d1').user_count()

    def test_public_listener_only_serves_tokens(self):
        for path in ('/', '/isup-face/', '/isup-face/abc.jpg', '/health'):
            self.assertEqual(self.gw.handle_public('GET', path)[0], 404)

    def test_passthrough_client_matches_lan_client(self):
        public = {n for n in dir(Client) if not n.startswith('_')}
        self.assertLessEqual(public, set(dir(PassthroughClient)))

    def test_remote_client_talks_to_gateway(self):
        """Django tomonidagi mijoz: urlopen o'rniga to'g'ridan-to'g'ri handle_internal."""
        self.backend.connect(self.term)
        gw = self.gw

        class Resp:
            def __init__(self, data):
                self.data = data

            def read(self):
                return self.data

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def urlopen(req, timeout=None):
            path = req.full_url.removeprefix('http://127.0.0.1:7690')
            status, out = gw.handle_internal(req.get_method(), path, dict(req.header_items()), req.data)
            return Resp(json.dumps(out).encode())

        rc = RemoteClient('http://127.0.0.1:7690', TOKEN, 'spt-d1', urlopen=urlopen)
        rc.upsert_user('8001', 'Direktor')
        rc.set_face('8001', JPEG)
        self.assertEqual(rc.user_count(), (2, 1))

    def test_bad_api_token_rejected_at_start(self):
        with self.assertRaises(ValueError):
            Gateway(self.backend, self.registry, self.forwarder, FaceStore(), 'https://x/', 'short')


class CollisionTests(SimpleTestCase):
    def test_conflicts_foreign_same(self):
        terminal = [('9001', 'Ali Valiyev'), ('9002', 'Boshqa Odam'), ('55', 'Eduschool'), ('9003', '')]
        wanted = {'9001': "ali  valiyev", '9002': 'Madina', '9003': 'Sardor', '9004': 'Yangi'}
        r = collision_report(terminal, wanted)
        self.assertEqual(r['same'], ['9001'])
        self.assertEqual([c[0] for c in r['conflicts']], ['9002', '9003'])
        self.assertEqual(r['foreign'], [('55', 'Eduschool')])


class SdkBackendTests(SimpleTestCase):
    def test_missing_sdk_gives_clear_error(self):
        b = HikSdkBackend(tempfile.mkdtemp())
        self.assertEqual(b.missing_libs(), ['libHCISUPCMS.so', 'libHCISUPAlarm.so'])
        with self.assertRaises(SdkMissing):
            b.start(None)


class DjangoPipelineTests(TestCase):
    """Shlyuz hodisasi mavjud /api/access/hikvision/<token>/ ga tushadi: Django'da o'zgarish kerak emas."""

    def setUp(self):
        self.device = Device.objects.create(name='Kirish-1', direction='in')
        user = User.objects.create(username='s1', first_name='Ali', last_name='Valiyev', role='student')
        self.student = Student.objects.create(user=user, group=Group.objects.create(name='5-A'), access_id='9001')
        registry = Registry([Entry('spt-d1', 'abc12345', self.device.token)])

        def post(token, body):
            return self.client.post(f'/api/access/hikvision/{token}/', body, content_type='application/json').status_code
        self.backend = FakeBackend()
        self.gw = Gateway(self.backend, registry, Forwarder(registry, post, Path(tempfile.mkdtemp()) / 's.jsonl'),
                          FaceStore(), 'https://my.spetion.uz/isup-face/', TOKEN)
        self.gw.start()

    def test_scan_creates_event_once_and_heartbeat_marks_seen(self):
        self.assertTrue(self.backend.connect(FakeTerminal('spt-d1', 'abc12345')))
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_seen)
        self.backend.scan('spt-d1', '9001', '2026-11-28T08:00:00+05:00')
        self.backend.scan('spt-d1', '9001', '2026-11-28T08:00:00+05:00')   # ISUP + HTTP listening takrori
        e = AccessEvent.objects.get()
        self.assertEqual((e.student, e.direction), (self.student, 'in'))
