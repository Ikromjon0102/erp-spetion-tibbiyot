"""Filial kaliti (binodagi agent): ulash kodi, faqat o'z filiali, heartbeat izi, uzish, panel va ogohlantirish."""
import json
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from academics.models import Group
from access.models import Agent, AgentPairing, Device
from access.sync import eligible_users
from accounts.models import Student, User
from org.models import Branch, Organization

MEDIA = tempfile.mkdtemp()
TOKEN = 'agent-secret'
AUTH = {'HTTP_AUTHORIZATION': f'Bearer {TOKEN}'}
JSON = 'application/json'


@override_settings(MEDIA_ROOT=MEDIA, FACE_AGENT_TOKEN=TOKEN)
class BranchAgentTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        cache.clear()
        org = Organization.objects.create(name='Test maktab', kind='school')
        self.br = Branch.objects.create(organization=org, name='Asosiy')
        self.other = Branch.objects.create(organization=org, name='Boshqa')
        self.st = self.student('a1', Group.objects.create(name='5-A', branch=self.br), '9001')
        self.outsider = self.student('b1', Group.objects.create(name='5-B', branch=self.other), '9003')
        self.dev = Device.objects.create(name='Kirish-1', direction='in', branch=self.br)
        self.dev_other = Device.objects.create(name='Kirish-1', direction='in', branch=self.other)

    def student(self, username, group, acc):
        u = User.objects.create_user(username, password='x', role='student', first_name=username.upper(), last_name='Test')
        Student.objects.create(user=u, group=group, access_id=acc)
        u.photo.save(f'{username}.jpg', ContentFile(b'\xff\xd8jpeg-' + username.encode()), save=True)
        return u

    def pair(self, code):
        return self.client.post('/api/access/agent/pair/', json.dumps({'code': code, 'name': 'OFIS-PC'}), content_type=JSON)

    def key(self):
        r = self.pair(AgentPairing.issue(self.br))
        self.assertEqual(r.status_code, 200)
        return {'HTTP_AUTHORIZATION': f"Bearer {r.json()['key']}"}

    def beat(self, auth, body=None, **extra):
        return self.client.post('/api/access/agent/heartbeat/', json.dumps(body or {}), content_type=JSON, **auth, **extra)

    def test_pair_once(self):
        code = AgentPairing.issue(self.br)
        r = self.pair(code).json()
        self.assertEqual((r['branch_id'], r['branch']), (self.br.pk, 'Asosiy'))
        agent = Agent.objects.get()
        self.assertNotEqual(r['key'], agent.key_hash)               # kalit ochiq saqlanmaydi
        self.assertEqual(agent.name, 'OFIS-PC')
        self.assertEqual(self.pair(code).status_code, 400)          # ikkinchi marta ishlamaydi
        self.assertEqual(self.pair('0000-0000').status_code, 400)

    def test_pair_expired_and_rate_limited(self):
        code = AgentPairing.issue(self.br)
        AgentPairing.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.pair(code).status_code, 400)
        for _ in range(10):
            self.pair('1111-2222')
        self.assertEqual(self.pair(AgentPairing.issue(self.br)).status_code, 429)   # to'g'ri kod ham: urinishlar tugagan

    def test_new_code_replaces_unused(self):
        old = AgentPairing.issue(self.br)
        AgentPairing.issue(self.br)
        self.assertEqual(self.pair(old).status_code, 400)

    def test_key_sees_only_own_branch(self):
        auth = self.key()
        devs = self.client.get('/api/access/agent/devices/', **auth).json()
        self.assertEqual([d['token'] for d in devs['devices']], [self.dev.token])
        self.assertEqual(devs['branch']['id'], self.br.pk)
        self.assertEqual(self.client.get(f'/api/access/agent/manifest/{self.dev.token}/', **auth).status_code, 200)
        self.assertEqual(self.client.get(f'/api/access/agent/manifest/{self.dev_other.token}/', **auth).status_code, 404)
        self.assertEqual(self.client.get(f'/api/access/agent/photo/{self.st.pk}/', **auth).status_code, 200)
        self.assertEqual(self.client.get(f'/api/access/agent/photo/{self.outsider.pk}/', **auth).status_code, 404)
        r = self.client.post(f'/api/access/agent/report/{self.dev_other.token}/', '{}', content_type=JSON, **auth)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(len(self.client.get('/api/access/agent/devices/', **AUTH).json()['devices']), 2)   # administrator kaliti

    def test_multi_branch_teacher_on_both(self):
        t = User.objects.create_user('t1', password='x', role='teacher', first_name='T', access_id='7001')
        t.photo.save('t1.jpg', ContentFile(b'\xff\xd8t1'), save=True)
        t.branches.add(self.br, self.other)
        self.assertIn(t, eligible_users(self.dev))
        self.assertIn(t, eligible_users(self.dev_other))
        self.assertEqual(self.client.get(f'/api/access/agent/photo/{t.pk}/', **self.key()).status_code, 200)

    def test_heartbeat_state_and_stamp(self):
        auth = self.key()
        body = {'terminals': [{'device': self.dev.token, 'ip': '192.168.1.20', 'mac': '88:de:39:00:00:01', 'online': True, 'users': 5, 'faces': 5},
                              {'device': self.dev_other.token, 'ip': '10.0.0.1', 'online': True}]}
        stamp = self.beat(auth, body, HTTP_X_AGENT_VERSION='0.1.0').json()['stamp']
        agent = Agent.objects.get()
        self.assertEqual(list(agent.state), [str(self.dev.pk)])     # begona filial terminali yozilmaydi
        self.assertEqual(agent.state[str(self.dev.pk)]['users'], 5)
        self.assertEqual(agent.version, '0.1.0')
        self.assertTrue(agent.online)
        self.assertEqual(stamp, self.beat(auth).json()['stamp'])
        self.st.photo.save('a1-new.jpg', ContentFile(b'\xff\xd8new'), save=True)
        changed = self.beat(auth).json()['stamp']
        self.assertNotEqual(stamp, changed)
        self.outsider.photo.save('b1-new.jpg', ContentFile(b'\xff\xd8new'), save=True)     # boshqa filial: iz o'zgarmaydi
        self.assertEqual(changed, self.beat(auth).json()['stamp'])
        self.assertEqual(self.beat(AUTH).status_code, 404)          # administrator kaliti heartbeat yubormaydi

    def test_revoked_key_rejected(self):
        auth = self.key()
        Agent.objects.update(is_active=False)
        self.assertEqual(self.client.get('/api/access/agent/devices/', **auth).status_code, 401)

    def test_panel_code_and_revoke(self):
        admin = User.objects.create_superuser('boss', password='x')
        self.client.force_login(admin)
        self.client.get(f'/panel/maydon/?s=branch-{self.br.pk}')            # ish maydoni: shu filial
        r = self.client.post('/panel/qurilmalar/agent/kod/', {'branch': self.br.pk}, follow=True)
        code = r.context['new_code']['code']
        self.assertContains(r, code)
        self.assertNotContains(self.client.get('/panel/qurilmalar/'), code)       # bir marta ko'rsatiladi
        self.assertEqual(self.pair(code).status_code, 200)
        page = self.client.get('/panel/qurilmalar/')
        self.assertContains(page, 'OFIS-PC')
        self.assertContains(page, 'onlayn')
        agent = Agent.objects.get()
        self.client.post(f'/panel/qurilmalar/agent/{agent.pk}/uzish/')
        agent.refresh_from_db()
        self.assertFalse(agent.is_active)

    def test_check_agents_alert_once(self):
        self.key()
        Agent.objects.update(last_seen_at=timezone.now() - timedelta(hours=2))
        with mock.patch('access.management.commands.check_agents._send') as send:
            call_command('check_agents', '--any-time')
            call_command('check_agents', '--any-time')
            self.assertEqual(send.call_count, 1)
            self.assertIn('aloqaga chiqmadi', send.call_args[0][0])
            Agent.objects.update(last_seen_at=timezone.now())
            call_command('check_agents', '--any-time')
            self.assertIn('qayta ulandi', send.call_args[0][0])
        self.assertFalse(Agent.objects.get().offline_alerted)
