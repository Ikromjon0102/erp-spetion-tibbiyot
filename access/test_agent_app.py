"""Windows agent yadrosi (tools/spetion_agent/core.py): test serveri va soxta terminallar bilan to'liq tsikl."""
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from academics.models import Group
from access.models import Agent, AgentPairing, Device, FaceSync
from accounts.models import Student, User
from org.models import Branch, Organization
from tools.spetion_agent import core

MEDIA = tempfile.mkdtemp()
RELEASE = Path(tempfile.mkdtemp())

SADP_REPLY = b'''<?xml version="1.0" encoding="UTF-8"?><ProbeMatch><Uuid>X</Uuid><Types>inquiry</Types>
<DeviceType>DS-K1T343EFWX</DeviceType><DeviceSN>DSK1T343-123</DeviceSN><MAC>88-de-39-8e-19-83</MAC>
<IPv4Address>192.168.68.108</IPv4Address><HttpPort>80</HttpPort><Activated>true</Activated></ProbeMatch>'''


class Resp:
    def __init__(self, r):
        self.status_code, self.content = r.status_code, b''.join(r) if r.streaming else r.content

    def json(self):
        return json.loads(self.content)


def bridge(test, key):
    """AgentServer, lekin HTTP o'rniga Django test klienti."""
    class S(core.AgentServer):
        def _request(self, method, path, **kw):
            kw.pop('timeout', None)
            h = {'HTTP_AUTHORIZATION': f'Bearer {key}', 'HTTP_X_AGENT_VERSION': core.VERSION} if key else {}
            url = '/api/access/agent' + path
            if method == 'GET':
                return Resp(test.client.get(url, **h))
            return Resp(test.client.post(url, kw.get('data', ''), content_type='application/json', **h))
    return S('http://test', key)


class FakeTerminal:
    instances = {}

    def __init__(self, host):
        self.host, self.users, self.faces, self.deleted = host, {}, {}, []
        self.down = False

    @classmethod
    def factory(cls, host, password):
        t = cls.instances.setdefault(host, cls(host))
        if t.down:
            raise core.DeviceError("Qurilmaga ulanib bo'lmadi: ConnectTimeout")
        if password != 'pw':
            raise core.DeviceError("Login yoki parol noto'g'ri")
        return t

    def upsert_user(self, no, name):
        self.users[no] = name

    def set_face(self, no, jpeg):
        self.faces[no] = jpeg

    def delete_user(self, no):
        self.deleted.append(no)
        self.users.pop(no, None)
        self.faces.pop(no, None)

    def user_count(self):
        return len(self.users), len(self.faces)


@override_settings(MEDIA_ROOT=MEDIA, AGENT_RELEASE_DIR=RELEASE)
class AgentCoreTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)
        shutil.rmtree(RELEASE, ignore_errors=True)

    def setUp(self):
        cache.clear()
        FakeTerminal.instances = {}
        org = Organization.objects.create(name='Test maktab', kind='school')
        self.br = Branch.objects.create(organization=org, name='Asosiy')
        g = Group.objects.create(name='5-A', branch=self.br)
        self.st = self.student('a1', g, '9001')
        self.st2 = self.student('a2', g, '9002')
        self.d_in = Device.objects.create(name='Kirish-1', direction='in', branch=self.br)
        self.d_out = Device.objects.create(name='Chiqish-1', direction='out', branch=self.br)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cfg = core.Config(self.tmp / 'config.json')
        data = bridge(self, '').pair(AgentPairing.issue(self.br), 'OFIS-PC')
        self.cfg.set_key(data['key'], {'id': data['branch_id'], 'name': data['branch'], 'org': data['org']})
        self.cfg.set_password('pw')
        self.cfg.set(terminals={self.d_in.token: {'ip': '10.0.0.5', 'mac': '88:de:39:00:00:01', 'label': 'Kirish-1'},
                                self.d_out.token: {'ip': '10.0.0.6', 'mac': '88:de:39:00:00:02', 'label': 'Chiqish-1'}})
        self.worker = core.Worker(self.cfg, server=bridge(self, data['key']), client_factory=FakeTerminal.factory,
                                  discover=lambda: {'88:de:39:00:00:01': '10.0.0.9'})

    def student(self, username, group, acc):
        u = User.objects.create_user(username, password='x', role='student', first_name=username.upper(), last_name='Test')
        Student.objects.create(user=u, group=group, access_id=acc)
        u.photo.save(f'{username}.jpg', ContentFile(b'\xff\xd8jpeg-' + username.encode()), save=True)
        return u

    def test_secrets_encrypted_on_disk(self):
        raw = (self.tmp / 'config.json').read_text(encoding='utf-8')
        self.assertNotIn('spa_', raw)
        self.assertNotIn('"pw"', raw)
        self.assertEqual(core.Config(self.tmp / 'config.json').password, 'pw')
        self.assertTrue(core.Config(self.tmp / 'config.json').key.startswith('spa_'))

    def test_full_cycle(self):
        self.worker.cycle()
        t_in = FakeTerminal.instances['10.0.0.5']
        self.assertEqual(set(t_in.faces), {'9001', '9002'})
        self.assertEqual(set(FakeTerminal.instances['10.0.0.6'].faces), {'9001', '9002'})
        self.assertEqual(FaceSync.objects.filter(ok=True).count(), 4)
        agent = Agent.objects.get()
        self.assertEqual(agent.state[str(self.d_in.pk)]['users'], 2)       # sync dan keyingi heartbeat — yangi sonlar
        self.assertEqual(agent.version, core.VERSION)
        stamp = self.cfg.get('last_stamp')
        self.assertTrue(stamp)

        t_in.faces.clear()                               # o'zgarish yo'q -> qayta yuborilmaydi
        self.worker.cycle()
        self.assertEqual(t_in.faces, {})

        self.st.photo.save('a1-v2.jpg', ContentFile(b'\xff\xd8new'), save=True)       # yangi rasm -> iz o'zgaradi -> sync
        self.worker.cycle()
        self.assertEqual(set(t_in.faces), {'9001'})
        self.assertNotEqual(self.cfg.get('last_stamp'), stamp)

        self.st2.is_active = False                       # nofaol -> terminaldan o'chadi
        self.st2.save()
        self.worker.cycle()
        self.assertIn('9002', t_in.deleted)

    def test_ip_changed_found_by_mac(self):
        FakeTerminal.instances['10.0.0.5'] = FakeTerminal('10.0.0.5')
        FakeTerminal.instances['10.0.0.5'].down = True
        self.worker.cycle()                              # eski IP javob bermaydi -> MAC bo'yicha yangi IP -> shu tsiklda yuboriladi
        self.assertEqual(self.cfg.get('terminals')[self.d_in.token]['ip'], '10.0.0.9')
        self.assertEqual(set(FakeTerminal.instances['10.0.0.9'].faces), {'9001', '9002'})
        self.assertEqual(self.cfg.get('failed_at'), 0)

    def test_terminal_down_retried(self):
        self.worker.discover = lambda: {}
        FakeTerminal.instances['10.0.0.5'] = t = FakeTerminal('10.0.0.5')
        t.down = True
        self.worker.cycle()
        self.assertTrue(self.cfg.get('failed_at'))
        self.assertFalse(self.cfg.get('last_stamp'))
        self.assertEqual(set(FakeTerminal.instances['10.0.0.6'].faces), {'9001', '9002'})    # ikkinchisi ishladi
        self.assertIn('ulanib', self.worker.state['terminals'][self.d_in.token]['error'])
        t.down = False
        self.worker.wake(force_sync=True)
        self.worker.cycle()
        self.assertEqual(set(t.faces), {'9001', '9002'})
        self.assertEqual(self.cfg.get('failed_at'), 0)

    def test_wrong_password_shown(self):
        self.cfg.set_password('xato')
        self.worker.cycle()
        st = self.worker.state['terminals'][self.d_in.token]
        self.assertIn('parol', st['error'])
        self.assertFalse(any(t.faces for t in FakeTerminal.instances.values()))
        self.assertEqual(self.cfg.get('terminals')[self.d_in.token]['ip'], '10.0.0.5')     # parol xatosida IP qidirilmaydi

    def test_revoked_agent(self):
        Agent.objects.update(is_active=False)
        self.assertEqual(self.worker.cycle(), 300)
        self.assertFalse(self.worker.state['server_ok'])
        self.assertIn('uzilgan', self.worker.state['server'])

    def test_unmapped_device_skipped(self):
        self.cfg.set(terminals={self.d_in.token: self.cfg.get('terminals')[self.d_in.token]})
        self.worker.cycle()
        self.assertNotIn('10.0.0.6', FakeTerminal.instances)
        self.assertTrue(self.cfg.get('last_stamp'))

    def test_parse_sadp(self):
        d = core.parse_sadp(SADP_REPLY)
        self.assertEqual((d['ip'], d['mac'], d['model']), ('192.168.68.108', '88:de:39:8e:19:83', 'DS-K1T343EFWX'))
        self.assertIsNone(core.parse_sadp(b'<Probe/>'))
        self.assertIsNone(core.parse_sadp(b'not xml'))

    def test_release(self):
        self.assertIsNone(self.worker.server.release()['version'])
        exe = b'MZ fake exe'
        (RELEASE / 'SpetionAgent.exe').write_bytes(exe)
        (RELEASE / 'SpetionAgent.json').write_text(json.dumps({'version': '0.2.0', 'sha256': hashlib.sha256(exe).hexdigest()}))
        info = self.worker.server.release()
        self.assertEqual(info['version'], '0.2.0')
        self.assertEqual(self.worker.server.release_file(), exe)
        self.assertGreater(core.version_tuple('0.10.0'), core.version_tuple('0.9.3'))
        self.assertEqual(self.client.get('/api/access/agent/release/').status_code, 401)
        admin = User.objects.create_superuser('boss', password='x')
        self.client.force_login(admin)
        r = self.client.get('/panel/qurilmalar/agent/yuklab-olish/')
        self.assertEqual(b''.join(r.streaming_content), exe)
        (RELEASE / 'SpetionAgent.exe').unlink()
        (RELEASE / 'SpetionAgent.json').unlink()
