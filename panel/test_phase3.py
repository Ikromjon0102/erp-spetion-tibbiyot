import io
import shutil
import tempfile
import zipfile
from datetime import time
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from academics.models import Group, Lesson, Subject, Teaching
from access import sync
from access.hikvision import DeviceError
from access.models import Device, FaceSync
from accounts import photos
from accounts.models import Student, User

from .models import AuditLog
from .tests import make_staff

MEDIA = tempfile.mkdtemp(prefix='test-media-')
FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], MEDIA_ROOT=MEDIA, FACE_SYNC_BACKGROUND=False)


def tearDownModule():
    shutil.rmtree(MEDIA, ignore_errors=True)


def jpeg(size=(640, 480), color=(120, 80, 60), fmt='JPEG', noisy=False):
    img = Image.new('RGB', size, color)
    if noisy:
        import random
        px = img.load()
        for x in range(0, size[0]):
            for y in range(0, size[1]):
                px[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    out = io.BytesIO()
    img.save(out, fmt)
    return out.getvalue()


def upload(data=None, name='face.jpg'):
    return SimpleUploadedFile(name, data or jpeg(), content_type='image/jpeg')


def mk_student(username, last, group=None, access_id=None):
    u = User.objects.create_user(username=username, password='x', role='student', first_name='Ali', last_name=last)
    return Student.objects.create(user=u, group=group, access_id=access_id)


@FAST
class ScheduleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.dir, self.hisob, self.zam = make_staff('dir', 'Direktor'), make_staff('hisob', 'Hisobchi'), make_staff('zam', "Zam (o'quv ishlari)")
        self.g1, self.g2 = Group.objects.create(name='5-A', year=2026), Group.objects.create(name='6-A', year=2026)
        self.math = Subject.objects.create(name='Matematika')
        self.t = User.objects.create_user(username='t1', role='teacher', first_name='Ali', last_name='Karimov', phone='+998 90 111-22-33')
        self.client.login(username='dir', password='x')

    def post(self, **kw):
        data = {'group': self.g1.pk, 'subject': self.math.pk, 'teacher': self.t.pk, 'weekday': 0, 'period': 1, 'start': '08:30', 'end': '09:15', 'room': '12'}
        data.update(kw)
        return self.client.post('/panel/jadval/yangi/', data)

    def test_add_shows_in_grid_and_creates_teaching(self):
        self.post()
        les = Lesson.objects.get()
        self.assertEqual((les.teaching.group, les.teaching.teacher, les.start), (self.g1, self.t, time(8, 30)))
        html = self.client.get(f'/panel/jadval/?sinf={self.g1.pk}').content.decode()
        self.assertIn('Matematika', html)
        self.assertIn('Karimov', self.client.get(f'/panel/jadval/?ustoz={self.t.pk}&sinf=').content.decode() or 'Karimov')
        self.assertTrue(AuditLog.objects.filter(verb="Dars qo'shdi").exists())

    def test_new_subject_by_name(self):
        self.post(subject='', new_subject='Biologiya')
        self.assertTrue(Subject.objects.filter(name='Biologiya').exists())
        self.assertEqual(Lesson.objects.count(), 1)

    def test_group_and_teacher_conflicts_rejected(self):
        self.post()
        self.post(start='09:00', end='09:45')                               # shu sinf, vaqt kesishadi
        self.assertEqual(Lesson.objects.count(), 1)
        self.post(group=self.g2.pk, start='09:00', end='09:45')            # shu ustoz boshqa sinfda band
        self.assertEqual(Lesson.objects.count(), 1)
        self.post(group=self.g2.pk, start='09:30', end='10:15', weekday=1)  # boshqa kun — mumkin
        self.assertEqual(Lesson.objects.count(), 2)
        self.post(start='10:00', end='09:00', weekday=3)                    # tugash boshlanishdan oldin
        self.assertEqual(Lesson.objects.count(), 2)

    def test_edit_and_soft_delete_keeps_history(self):
        self.post()
        les = Lesson.objects.get()
        self.client.post(f'/panel/jadval/{les.pk}/', {'group': self.g1.pk, 'subject': self.math.pk, 'teacher': self.t.pk, 'weekday': 2,
                                                       'period': 3, 'start': '10:30', 'end': '11:15', 'room': '5'})
        les.refresh_from_db()
        self.assertEqual((les.weekday, les.period, les.room), (2, 3, '5'))
        self.client.post(f'/panel/jadval/{les.pk}/olib-tashlash/')
        les.refresh_from_db()
        self.assertFalse(les.active)                                       # o'chmaydi, faqat yashirinadi
        self.assertEqual(self.client.get(f'/panel/jadval/{les.pk}/').status_code, 404)

    def test_permissions(self):
        self.client.login(username='hisob', password='x')
        self.assertEqual(self.client.get('/panel/jadval/').status_code, 403)
        self.client.login(username='zam', password='x')
        self.assertEqual(self.client.get('/panel/jadval/').status_code, 200)
        self.assertEqual(self.post().status_code, 302)
        self.client.login(username='dir', password='x')


@FAST
class ParentTests(TestCase):
    def setUp(self):
        cache.clear()
        self.dir, self.hisob, self.zam, self.rec = (make_staff('dir', 'Direktor'), make_staff('hisob', 'Hisobchi'),
                                                    make_staff('zam', "Zam (o'quv ishlari)"), make_staff('rec', 'Reception'))
        self.g = Group.objects.create(name='5-A', year=2026)
        self.kid = mk_student('k1', 'Aliyev', self.g)
        self.parent = User.objects.create_user(username='998901112233', role='parent', first_name='Ota', last_name='Aliyev', phone='+998 90 111-22-33')
        self.kid.parents.add(self.parent)
        self.client.login(username='dir', password='x')

    def test_list_and_search(self):
        User.objects.create_user(username='demo', role='parent', first_name='Sinov', is_demo=True)
        r = self.client.get('/panel/ota-onalar/')
        self.assertContains(r, 'Aliyev')
        self.assertNotContains(r, 'Sinov')
        self.assertContains(self.client.get('/panel/ota-onalar/?q=1112233'), 'Aliyev')
        self.assertNotContains(self.client.get('/panel/ota-onalar/?q=Zzz'), 'Ota Aliyev')

    def test_create_with_temp_password_and_child_link(self):
        r = self.client.post('/panel/ota-onalar/yangi/', {'last_name': 'Valiyev', 'first_name': 'Sher', 'phone': '+998 91 222-33-44', 'oquvchi': self.kid.pk})
        u = User.objects.get(phone_digits='998912223344')
        self.assertRedirects(r, f'/panel/ota-onalar/{u.pk}/')
        self.assertEqual(u.role, 'parent')
        self.assertTrue(u.must_change_password and u.has_usable_password())
        self.assertIn(u, self.kid.parents.all())

    def test_duplicate_phone_rejected(self):
        self.client.post('/panel/ota-onalar/yangi/', {'first_name': 'X', 'phone': '+998 90 111-22-33'})
        self.assertEqual(User.objects.filter(phone_digits='998901112233').count(), 1)

    def test_link_unlink_and_search_for_child(self):
        other = mk_student('k2', 'Soliyev', self.g)
        self.assertContains(self.client.get(f'/panel/ota-onalar/{self.parent.pk}/?q=Soliyev'), 'Biriktirish')
        self.client.post(f'/panel/ota-onalar/{self.parent.pk}/farzand/{other.pk}/')
        self.assertIn(self.parent, other.parents.all())
        self.client.post(f'/panel/ota-onalar/{self.parent.pk}/farzand/{other.pk}/ajratish/')
        self.assertNotIn(self.parent, other.parents.all())

    def test_password_reset_only_for_pure_parent_accounts(self):
        self.client.post(f'/panel/ota-onalar/{self.parent.pk}/parol/')
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.must_change_password)
        teacher = User.objects.create_user(username='tt', role='teacher', phone='+998 93 000-11-22')
        self.kid.parents.add(teacher)
        before = teacher.password
        self.client.post(f'/panel/ota-onalar/{teacher.pk}/parol/')
        teacher.refresh_from_db()
        self.assertEqual(teacher.password, before)                         # ustozning paroli bu yerdan o'zgarmaydi

    def test_permissions(self):
        self.client.login(username='hisob', password='x')
        self.assertEqual(self.client.get('/panel/ota-onalar/').status_code, 403)
        self.client.login(username='zam', password='x')                    # Zam: faqat ko'radi
        self.assertEqual(self.client.get('/panel/ota-onalar/').status_code, 200)
        self.assertEqual(self.client.get('/panel/ota-onalar/yangi/').status_code, 403)
        self.client.login(username='rec', password='x')                    # Reception: qo'shadi
        self.assertEqual(self.client.get('/panel/ota-onalar/yangi/').status_code, 200)


class PhotoPrepTests(TestCase):
    def test_large_image_shrinks_under_limit(self):
        data = photos.prepare(io.BytesIO(jpeg((3000, 2400), noisy=False)))
        self.assertLessEqual(len(data), photos.MAX_BYTES)
        img = Image.open(io.BytesIO(data))
        self.assertEqual(img.format, 'JPEG')
        self.assertLessEqual(max(img.size), photos.MAX_SIDE)

    def test_noisy_image_still_fits(self):
        self.assertLessEqual(len(photos.prepare(io.BytesIO(jpeg((1200, 900), noisy=True)))), photos.MAX_BYTES)

    def test_rejects_tiny_and_non_images(self):
        with self.assertRaises(photos.PhotoError):
            photos.prepare(io.BytesIO(jpeg((100, 100))))
        with self.assertRaises(photos.PhotoError):
            photos.prepare(io.BytesIO(b'not an image'))

    def test_png_converted_to_jpeg(self):
        data = photos.prepare(io.BytesIO(jpeg((400, 400), fmt='PNG')))
        self.assertEqual(Image.open(io.BytesIO(data)).format, 'JPEG')


class FakeClient:
    calls = []
    fail_connect = False
    fail_user = set()

    def __init__(self, device):
        self.device = device

    def _go(self, *a):
        if FakeClient.fail_connect:
            raise DeviceError("Qurilmaga ulanib bo'lmadi: Timeout")
        FakeClient.calls.append(a)

    def info(self):
        self._go('info')

    def upsert_user(self, emp, name):
        if emp in FakeClient.fail_user:
            raise DeviceError('Foydalanuvchini yozish: xato')
        self._go('user', emp, name)

    def set_face(self, emp, jpg):
        self._go('face', emp, len(jpg))

    def delete_user(self, emp):
        self._go('del', emp)


@FAST
class PhotoUploadTests(TestCase):
    def setUp(self):
        cache.clear()
        self.dir, self.hisob = make_staff('dir', 'Direktor'), make_staff('hisob', 'Hisobchi')
        self.g = Group.objects.create(name='5-A', year=2026)
        self.kid = mk_student('k1', 'Aliyev', self.g, access_id='1001')
        self.t = User.objects.create_user(username='t1', role='teacher', first_name='Ali', last_name='Karimov', phone='+998 90 111-22-33')
        self.client.login(username='dir', password='x')

    def test_student_photo_upload_replace_delete(self):
        r = self.client.post(f'/panel/oquvchilar/{self.kid.pk}/rasm/', {'photo': upload()})
        self.assertEqual(r.status_code, 302)
        self.kid.user.refresh_from_db()
        first = self.kid.user.photo.name
        self.assertTrue(first)
        self.client.post(f'/panel/oquvchilar/{self.kid.pk}/rasm/', {'photo': upload(jpeg((500, 500), (1, 2, 3)))})
        self.kid.user.refresh_from_db()
        self.assertNotEqual(self.kid.user.photo.name, first)
        self.client.post(f'/panel/oquvchilar/{self.kid.pk}/rasm/ochirish/')
        self.kid.user.refresh_from_db()
        self.assertFalse(self.kid.user.photo)

    def test_bad_upload_rejected(self):
        self.client.post(f'/panel/oquvchilar/{self.kid.pk}/rasm/', {'photo': SimpleUploadedFile('x.jpg', b'junk', content_type='image/jpeg')})
        self.kid.user.refresh_from_db()
        self.assertFalse(self.kid.user.photo)

    def test_teacher_gets_face_id_on_first_photo(self):
        self.client.post(f'/panel/ustozlar/{self.t.pk}/rasm/', {'photo': upload()})
        self.t.refresh_from_db()
        self.assertTrue(self.t.photo)
        self.assertEqual(self.t.access_id, '7001')
        t2 = User.objects.create_user(username='t2', role='teacher', phone='+998 91 000-00-01')
        self.client.post(f'/panel/ustozlar/{t2.pk}/rasm/', {'photo': upload()})
        t2.refresh_from_db()
        self.assertEqual(t2.access_id, '7002')

    def test_face_id_unique_across_students_and_teachers(self):
        r = self.client.post(f'/panel/ustozlar/{self.t.pk}/tahrirlash/', {'last_name': 'K', 'first_name': 'A', 'phone': '+998 90 111-22-33', 'access_id': '1001'})
        self.assertEqual(r.status_code, 200)                                # o'quvchida shu ID bor — rad etildi
        self.t.refresh_from_db()
        self.assertIsNone(self.t.access_id)

    def test_photo_view_permissions(self):
        self.client.post(f'/panel/oquvchilar/{self.kid.pk}/rasm/', {'photo': upload()})
        url = f'/rasm/{self.kid.user.pk}/'
        self.assertEqual(self.client.get(url).status_code, 200)             # direktor
        make_staff('zavxoz', 'Zavxoz', perms=['groups.view'])
        self.client.login(username='zavxoz', password='x')
        self.assertEqual(self.client.get(url).status_code, 403)             # o'quvchilarni ko'rish ruxsati yo'q xodim
        parent = User.objects.create_user(username='ota', password='x', role='parent')
        stranger = User.objects.create_user(username='kimdir', password='x', role='parent')
        self.kid.parents.add(parent)
        self.client.login(username='ota', password='x')
        self.assertEqual(self.client.get(url).status_code, 200)             # o'z farzandi
        self.client.login(username='kimdir', password='x')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_zip_upload_matches_by_face_id(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('1001.jpg', jpeg())
            z.writestr('papka/9999.png', jpeg(fmt='PNG'))
            z.writestr('readme.txt', 'x')
        self.client.post('/panel/qurilmalar/rasmlar-zip/', {'zip': SimpleUploadedFile('f.zip', buf.getvalue())})
        self.kid.user.refresh_from_db()
        self.assertTrue(self.kid.user.photo)
        self.assertEqual(User.objects.exclude(photo='').exclude(photo__isnull=True).count(), 1)

    def test_devices_page_permissions(self):
        self.assertEqual(self.client.get('/panel/qurilmalar/').status_code, 200)
        self.client.login(username='hisob', password='x')
        self.assertEqual(self.client.get('/panel/qurilmalar/').status_code, 403)


@FAST
class SyncTests(TestCase):
    def setUp(self):
        FakeClient.calls, FakeClient.fail_connect, FakeClient.fail_user = [], False, set()
        patcher = mock.patch('access.sync.Client', FakeClient)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dev = Device.objects.create(name='K1', direction='in', host='192.168.1.64', username='admin', password='pw')
        self.g = Group.objects.create(name='5-A', year=2026)
        self.s1, self.s2 = mk_student('a', 'Aliyev', self.g, '1001'), mk_student('b', 'Valiyev', self.g, '1002')
        for s in (self.s1, self.s2):
            photos.save_photo(s.user, io.BytesIO(jpeg()))
        self.noid = mk_student('c', 'Idsiz', self.g)
        photos.save_photo(self.noid.user, io.BytesIO(jpeg()))

    def kinds(self):
        return [c[0] for c in FakeClient.calls]

    def test_sends_only_people_with_photo_and_face_id_then_skips_unchanged(self):
        r = sync.sync_device(self.dev)
        self.assertEqual((r['sent'], r['failed'], r['error']), (2, 0, ''))
        self.assertEqual(sorted(c[1] for c in FakeClient.calls if c[0] == 'user'), ['1001', '1002'])
        FakeClient.calls.clear()
        r = sync.sync_device(self.dev)
        self.assertEqual((r['sent'], r['skipped']), (0, 2))                 # o'zgarmagan — qayta yuborilmaydi
        self.assertEqual(FakeClient.calls, [])
        self.assertEqual(sync.pending_count(self.dev), 0)

    def test_changed_photo_or_name_is_resent(self):
        sync.sync_device(self.dev)
        FakeClient.calls.clear()
        photos.save_photo(self.s1.user, io.BytesIO(jpeg((500, 500), (9, 9, 9))))
        self.assertEqual(sync.pending_count(self.dev), 1)
        sync.sync_device(self.dev)
        self.assertEqual([c[1] for c in FakeClient.calls if c[0] == 'user'], ['1001'])
        FakeClient.calls.clear()
        self.s2.user.last_name = 'Yangi'
        self.s2.user.save()
        sync.sync_device(self.dev)
        self.assertEqual([c[1] for c in FakeClient.calls if c[0] == 'user'], ['1002'])

    def test_removed_photo_or_inactive_user_is_deleted_from_device(self):
        sync.sync_device(self.dev)
        FakeClient.calls.clear()
        photos.remove_photo(self.s1.user)
        self.s2.user.is_active = False
        self.s2.user.save()
        r = sync.sync_device(self.dev)
        self.assertEqual(r['removed'], 2)
        self.assertEqual(sorted(c[1] for c in FakeClient.calls if c[0] == 'del'), ['1001', '1002'])
        self.assertEqual(FaceSync.objects.count(), 0)

    def test_connection_error_aborts_and_is_reported(self):
        FakeClient.fail_connect = True
        r = sync.sync_device(self.dev)
        self.assertIn("ulanib bo'lmadi", r['error'])
        self.dev.refresh_from_db()
        self.assertIn("ulanib bo'lmadi", self.dev.last_sync_note)
        self.assertEqual(FaceSync.objects.filter(ok=True).count(), 0)

    def test_one_persons_error_does_not_stop_others(self):
        FakeClient.fail_user = {'1001'}
        r = sync.sync_device(self.dev)
        self.assertEqual((r['sent'], r['failed']), (1, 1))
        self.assertFalse(FaceSync.objects.get(user=self.s1.user).ok)
        FakeClient.fail_user = set()
        r = sync.sync_device(self.dev)                                      # keyingi safar qayta uriniladi
        self.assertEqual(r['sent'], 1)

    def test_no_host_means_nothing_to_do(self):
        self.dev.host = ''
        self.dev.save()
        self.assertEqual(sync.sync_device(self.dev)['sent'], 0)
        sync.sync_in_background()
        self.assertEqual(FakeClient.calls, [])

    def test_upload_triggers_sync_to_device(self):
        make_staff('dir', 'Direktor')
        self.client.login(username='dir', password='x')
        self.client.post(f'/panel/oquvchilar/{self.noid.pk}/tahrirlash/', {'last_name': 'Idsiz', 'first_name': 'Ali', 'group': self.g.pk, 'access_id': '1003'})
        FakeClient.calls.clear()
        self.client.post(f'/panel/oquvchilar/{self.noid.pk}/rasm/', {'photo': upload()})
        self.assertIn('1003', [c[1] for c in FakeClient.calls if c[0] == 'user'])

    def test_panel_test_and_sync_buttons(self):
        make_staff('dir', 'Direktor')
        self.client.login(username='dir', password='x')
        with mock.patch('panel.views_devices.Client', FakeClient):
            r = self.client.post(f'/panel/qurilmalar/{self.dev.pk}/tekshirish/', follow=True)
            self.assertContains(r, 'ulanish muvaffaqiyatli')
            FakeClient.fail_connect = True
            self.assertContains(self.client.post(f'/panel/qurilmalar/{self.dev.pk}/tekshirish/', follow=True), "ulanib bo&#x27;lmadi")
        FakeClient.fail_connect = False
        self.assertContains(self.client.post(f'/panel/qurilmalar/{self.dev.pk}/sync/', follow=True), 'yuborildi 2')
        self.assertTrue(self.client.get('/panel/qurilmalar/').status_code == 200)
