from io import BytesIO
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from academics.models import Group
from accounts.models import Student, User

from .tests import make_staff

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


def jpg(size=300):
    b = BytesIO()
    Image.new('RGB', (size, size), (120, 160, 120)).save(b, 'JPEG')
    return SimpleUploadedFile('f.jpg', b.getvalue(), content_type='image/jpeg')


@FAST
class AddWithPhotoTests(TestCase):
    def setUp(self):
        cache.clear()
        make_staff('dir', 'Direktor')
        self.client.login(username='dir', password='x')
        self.g = Group.objects.create(name='5-Sinf', year=2026)

    def test_student_with_and_without_photo(self):
        with mock.patch('panel.views_devices.sync_in_background') as sync:
            r = self.client.post('/panel/oquvchilar/yangi/', {'last_name': 'Aliyev', 'first_name': 'Vali', 'group': self.g.pk, 'photo': jpg()})
            self.assertEqual(r.status_code, 302, getattr(r, 'content', b'')[:300])
            u = User.objects.get(last_name='Aliyev')
            self.assertTrue(u.photo)
            sync.assert_called_once()
            r = self.client.post('/panel/oquvchilar/yangi/', {'last_name': 'Bobiyev', 'first_name': 'Sher', 'group': self.g.pk})
            self.assertEqual(r.status_code, 302)
            self.assertFalse(User.objects.get(last_name='Bobiyev').photo)

    def test_bad_photo_creates_nothing(self):
        bad = SimpleUploadedFile('x.jpg', b'not an image', content_type='image/jpeg')
        r = self.client.post('/panel/oquvchilar/yangi/', {'last_name': 'Xato', 'first_name': 'Rasm', 'group': self.g.pk, 'photo': bad})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(last_name='Xato').exists())

    def test_teacher_with_photo_gets_face_id(self):
        with mock.patch('panel.views_devices.sync_in_background'):
            r = self.client.post('/panel/ustozlar/yangi/', {'last_name': 'Karimov', 'first_name': 'Ali', 'phone': '+998 90 123-45-67', 'photo': jpg()})
            self.assertEqual(r.status_code, 302, getattr(r, 'content', b'')[:300])
        u = User.objects.get(last_name='Karimov')
        self.assertTrue(u.photo)
        self.assertTrue(u.access_id)


@FAST
class ModalTests(TestCase):
    def setUp(self):
        cache.clear()
        make_staff('dir', 'Direktor')
        self.client.login(username='dir', password='x')

    def test_modal_post_gets_json_redirect_and_message_survives(self):
        r = self.client.post('/panel/sinflar/yangi/', {'name': '9-Sinf', 'year': 2026}, headers={'X-Modal': '1'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('redirect', r.json())
        self.assertTrue(Group.objects.filter(name='9-Sinf').exists())

    def test_plain_post_still_redirects(self):
        r = self.client.post('/panel/sinflar/yangi/', {'name': '8-Sinf', 'year': 2026})
        self.assertEqual(r.status_code, 302)

    def test_add_links_are_modal_and_dialog_present(self):
        r = self.client.get('/panel/sinflar/')
        self.assertContains(r, 'data-modal')
        self.assertContains(r, 'id="mdlOv"')


@FAST
class AutoFaceIdTests(TestCase):
    def setUp(self):
        cache.clear()
        make_staff('dir', 'Direktor')
        self.client.login(username='dir', password='x')
        self.g = Group.objects.create(name='5-Sinf', year=2026)

    def add(self, last, **extra):
        return self.client.post('/panel/oquvchilar/yangi/', {'last_name': last, 'first_name': 'X', 'group': self.g.pk, **extra})

    def test_students_get_sequential_ids_from_9001(self):
        self.add('Bir'); self.add('Ikki')
        ids = [Student.objects.get(user__last_name=n).access_id for n in ('Bir', 'Ikki')]
        self.assertEqual(ids, ['9001', '9002'])

    def test_manual_id_kept_and_next_continues_after_max(self):
        self.add('Qolda', access_id='9500')
        self.add('Avto')
        self.assertEqual(Student.objects.get(user__last_name='Qolda').access_id, '9500')
        self.assertEqual(Student.objects.get(user__last_name='Avto').access_id, '9501')

    def test_blank_on_edit_keeps_existing_id(self):
        self.add('Eski')
        st = Student.objects.get(user__last_name='Eski')
        r = self.client.post(f'/panel/oquvchilar/{st.pk}/tahrirlash/', {'last_name': 'Eski', 'first_name': 'X', 'group': self.g.pk, 'access_id': ''})
        self.assertEqual(r.status_code, 302)
        st.refresh_from_db()
        self.assertEqual(st.access_id, '9001')

    def test_teachers_from_7001_do_not_clash_with_students(self):
        self.add('Talaba')
        with mock.patch('panel.views_devices.sync_in_background'):
            self.client.post('/panel/ustozlar/yangi/', {'last_name': 'Ustoz', 'first_name': 'A', 'phone': '+998 90 111-22-33'})
        self.assertEqual(User.objects.get(last_name='Ustoz').access_id, '7001')
        self.assertEqual(Student.objects.get(user__last_name='Talaba').access_id, '9001')

    def test_demo_student_gets_no_auto_id(self):
        u = User.objects.create_user(username='sinov_x', password='x', role='student', is_demo=True)
        self.assertIsNone(Student.objects.create(user=u, group=self.g).access_id)
