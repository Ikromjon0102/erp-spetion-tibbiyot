"""Maktab kompyuteri skripti (tools/push_faces.py) uchun API va skriptning o'zi (soxta server/terminal bilan)."""
import json
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from academics.models import Group
from accounts.models import Student, User
from access.models import Device, FaceSync
from org.models import Branch, Organization

MEDIA = tempfile.mkdtemp()
TOKEN = 'agent-secret'
AUTH = {'HTTP_AUTHORIZATION': f'Bearer {TOKEN}'}


@override_settings(MEDIA_ROOT=MEDIA, FACE_AGENT_TOKEN=TOKEN)
class AgentApiTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        org = Organization.objects.create(name='Test maktab', kind='school')
        self.br = Branch.objects.create(organization=org, name='Asosiy')
        other = Branch.objects.create(organization=org, name='Boshqa')
        g = Group.objects.create(name='5-A', branch=self.br)
        self.st = self.student('a1', g, '9001')
        self.st2 = self.student('a2', g, '9002')
        self.outsider = self.student('b1', Group.objects.create(name='5-B', branch=other), '9003')
        self.dev = Device.objects.create(name='Kirish-1', direction='in', branch=self.br)

    def student(self, username, group, acc):
        u = User.objects.create_user(username, password='x', role='student', first_name=username.upper(), last_name='Test')
        Student.objects.create(user=u, group=group, access_id=acc)
        u.photo.save(f'{username}.jpg', ContentFile(b'\xff\xd8jpeg-' + username.encode()), save=True)
        return u

    def test_requires_token(self):
        self.assertEqual(self.client.get(f'/api/access/agent/manifest/{self.dev.token}/').status_code, 401)
        self.assertEqual(self.client.get(f'/api/access/agent/manifest/{self.dev.token}/', HTTP_AUTHORIZATION='Bearer wrong').status_code, 401)
        with override_settings(FACE_AGENT_TOKEN=''):          # kalit sozlanmagan bo'lsa — hech kim kira olmaydi
            self.assertEqual(self.client.get('/api/access/agent/devices/', HTTP_AUTHORIZATION='Bearer ').status_code, 401)

    def test_manifest_only_branch_people(self):
        r = self.client.get(f'/api/access/agent/manifest/{self.dev.token}/', **AUTH).json()
        self.assertEqual({p['employee_no'] for p in r['people']}, {'9001', '9002'})
        self.assertTrue(all(not p['synced'] for p in r['people']))
        self.assertEqual(self.client.get(f'/api/access/agent/photo/{self.st.pk}/', **AUTH).content, b'\xff\xd8jpeg-a1')

    def test_script_sync_end_to_end(self):
        """tools/push_faces.sync_terminal: soxta terminalga yuboradi, natija serverga yoziladi, ikkinchi marta hech narsa yuborilmaydi."""
        import tools.push_faces as pf
        test = self

        class FakeServer(pf.Server):
            def __init__(self):
                pass

            def manifest(self, token):
                return test.client.get(f'/api/access/agent/manifest/{token}/', **AUTH).json()

            def photo(self, user_id):
                return test.client.get(f'/api/access/agent/photo/{user_id}/', **AUTH).content

            def report(self, token, payload):
                return test.client.post(f'/api/access/agent/report/{token}/', json.dumps(payload), content_type='application/json', **AUTH).json()

        class FakeTerminal:
            def __init__(self):
                self.users, self.faces, self.deleted = {}, {}, []

            def upsert_user(self, no, name):
                self.users[no] = name

            def set_face(self, no, jpeg):
                self.faces[no] = jpeg

            def delete_user(self, no):
                self.deleted.append(no)

        term, server, dev = FakeTerminal(), FakeServer(), {'token': self.dev.token}
        note = pf.sync_terminal(server, dev, term)
        self.assertIn('yuborildi 2', note)
        self.assertEqual(set(term.faces), {'9001', '9002'})
        self.assertEqual(FaceSync.objects.filter(device=self.dev, ok=True).count(), 2)
        self.dev.refresh_from_db()
        self.assertIn('Maktab kompyuteridan', self.dev.last_sync_note)
        from access.sync import pending_count
        self.assertEqual(pending_count(self.dev), 0)                       # panel: «hammasi yuborilgan»

        term2 = FakeTerminal()
        self.assertIn("o'zgarmagan 2", pf.sync_terminal(server, dev, term2))
        self.assertEqual(term2.faces, {})

        # o'quvchi nofaol bo'ldi -> terminaldan o'chiriladi, holat tozalanadi
        self.st2.is_active = False
        self.st2.save()
        term3 = FakeTerminal()
        self.assertIn("o'chirildi 1", pf.sync_terminal(server, dev, term3))
        self.assertEqual(term3.deleted, ['9002'])
        self.assertFalse(FaceSync.objects.filter(device=self.dev, user=self.st2).exists())

    def test_report_ignores_foreign_users(self):
        payload = {'results': [{'user_id': self.outsider.pk, 'employee_no': '9003', 'digest': 'x', 'ok': True}]}
        r = self.client.post(f'/api/access/agent/report/{self.dev.token}/', json.dumps(payload), content_type='application/json', **AUTH).json()
        self.assertEqual(r['saved'], 0)
        self.assertFalse(FaceSync.objects.exists())
