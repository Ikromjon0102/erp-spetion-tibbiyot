from datetime import time, timedelta

from django.test import TestCase
from django.utils import timezone

from access.models import AccessEvent, Device
from academics.models import Group, Lesson, Subject, Teaching
from journal.models import Attendance

from .models import Student, User


class ParentViewTests(TestCase):
    def setUp(self):
        mk = lambda u, role, **kw: User.objects.create_user(username=u, password='x', role=role, **kw)
        self.parent, self.stranger = mk('p1', 'parent'), mk('p2', 'parent')
        group = Group.objects.create(name='5-Sinf')
        self.child = Student.objects.create(user=mk('s1', 'student', first_name='Madina'), group=group, access_id='1001')
        self.child.parents.add(self.parent)
        teaching = Teaching.objects.create(teacher=mk('t1', 'teacher'), subject=Subject.objects.create(name='Kimyo'), group=group)
        lesson = Lesson.objects.create(teaching=teaching, weekday=0, period=2, start=time(9, 20), end=time(10, 5))
        Attendance.objects.create(student=self.child, lesson=lesson, status='absent')
        morning = timezone.localtime().replace(hour=8, minute=12, second=0, microsecond=0)
        for name, direction, dt in [('Kirish-1', 'in', morning), ('Chiqish-1', 'out', morning + timedelta(hours=7, minutes=28))]:
            dev = Device.objects.create(name=name, direction=direction)
            AccessEvent.objects.create(device=dev, student=self.child, employee_no='1001', direction=direction, occurred_at=dt)

    def test_parent_home_shows_today_arrival_and_departure(self):
        # vaqt qat'iy 18:00 (aks holda test 15:40 dan oldin yiqilardi: chiqish hali «kelajakda» bo'ladi)
        from types import SimpleNamespace
        from unittest import mock
        real = timezone.localtime
        evening = real().replace(hour=18, minute=0, second=0, microsecond=0)
        fake = SimpleNamespace(localtime=lambda *a, **k: real(*a, **k) if a else evening, localdate=lambda: evening.date())
        self.client.login(username='p1', password='x')
        with mock.patch('accounts.child_data.timezone', fake):
            r = self.client.get('/', follow=True)  # bitta farzand: to'g'ridan-to'g'ri uning sahifasi
        self.assertRedirects(r, f'/oquvchi/{self.child.pk}/')
        self.assertContains(r, 'Uyga ketdi · 15:40')
        self.assertContains(r, 'Kelgan: 08:12')

    def test_child_page_shows_access_log_and_lesson_attendance(self):
        self.client.login(username='p1', password='x')
        r = self.client.get(f'/oquvchi/{self.child.pk}/')
        self.assertContains(r, 'Maktabga kelish va ketish')
        self.assertContains(r, '08:12')
        self.assertContains(r, 'Kimyo')
        self.assertContains(r, '2-dars')
        self.assertContains(r, 'Kelmadi')

    def test_other_parent_forbidden(self):
        self.client.login(username='p2', password='x')
        self.assertEqual(self.client.get(f'/oquvchi/{self.child.pk}/').status_code, 403)


class LoginThrottleTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.u = User.objects.create_user(username='diyora', password='4321', role='teacher')

    def attempt(self, password):
        return self.client.post('/login/', {'username': 'diyora', 'password': password})

    def test_locks_after_five_failures_even_with_correct_password(self):
        for _ in range(5):
            self.assertContains(self.attempt('0000'), "noto'g'ri")
        r = self.attempt('4321')
        self.assertContains(r, 'Juda ko')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_success_resets_counter(self):
        for _ in range(4):
            self.attempt('0000')
        self.assertEqual(self.attempt('4321').status_code, 302)

    def test_admin_action_sets_password_from_phone(self):
        from accounts.admin import SchoolUserAdmin
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        self.u.phone = '+998 90 123-45-67'
        self.u.save()
        nophone = User.objects.create_user(username='nophone', password='keep', role='teacher')
        ma = SchoolUserAdmin(User, AdminSite())
        ma.message_user = lambda *a, **k: None
        ma.password_from_phone(RequestFactory().post('/'), User.objects.filter(role='teacher'))
        self.u.refresh_from_db(); nophone.refresh_from_db()
        self.assertTrue(self.u.check_password('4567'))
        self.assertTrue(nophone.check_password('keep'))  # telefonsiz foydalanuvchi o'zgarmadi


class AvatarThumbTests(TestCase):
    def test_avatar_tag_uses_thumb_when_photo_and_initials_otherwise(self):
        from django.template import Context, Template
        u = User.objects.create(username='a1', first_name='Vali', last_name='Aliyev', role='teacher')
        html = Template('{% load app_extras %}{% avatar u %}').render(Context({'u': u}))
        self.assertIn('>AV<', html)
        u.photo.name = 'faces/5-abc123.jpg'
        html = Template('{% load app_extras %}{% avatar u %}').render(Context({'u': u}))
        self.assertIn(f'/rasm/{u.pk}/?s=1&amp;v=5-abc123', html)


class ParentSeesChildPhotoTests(TestCase):
    def test_parent_gets_child_thumb_and_stranger_does_not(self):
        import io, tempfile
        from PIL import Image
        from django.test import override_settings
        from academics.models import Group
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp, override_settings(MEDIA_ROOT=tmp):
            from accounts.photos import save_photo
            ku = User.objects.create(username='kid', first_name='Vali', last_name='Aliyev', role='student')
            kid = Student.objects.create(user=ku, group=Group.objects.create(name='5-Sinf'), access_id='9901')
            buf = io.BytesIO(); Image.new('RGB', (400, 500), (120, 90, 60)).save(buf, 'JPEG'); buf.seek(0)
            save_photo(ku, buf)
            parent = User.objects.create(username='p1', role='parent'); kid.parents.add(parent)
            other = User.objects.create(username='p2', role='parent')
            self.client.force_login(parent)
            r = self.client.get(f'/rasm/{ku.pk}/?s=1')
            self.assertEqual((r.status_code, r['Content-Type']), (200, 'image/jpeg'))
            r.close()
            self.client.force_login(other)
            self.assertEqual(self.client.get(f'/rasm/{ku.pk}/?s=1').status_code, 403)


class SeoTests(__import__('django.test', fromlist=['TestCase']).TestCase):
    """Qidiruv tizimlari: faqat my.spetion.uz indekslanadi, ichki sahifalar yopiq; bosh sahifa kirmaganga kirish sahifasi (200)."""

    def test_robots_canonical_and_other_hosts(self):
        from django.test import override_settings
        with override_settings(ALLOWED_HOSTS=['my.spetion.uz', 'med-new.spetion.uz']):
            r = self.client.get('/robots.txt', HTTP_HOST='my.spetion.uz')
            self.assertContains(r, 'Disallow: /panel/')
            self.assertContains(r, 'Sitemap: https://my.spetion.uz/sitemap.xml')
            r = self.client.get('/robots.txt', HTTP_HOST='med-new.spetion.uz')
            self.assertEqual(r.content.decode().strip().splitlines()[-1], 'Disallow: /')
            self.assertContains(self.client.get('/sitemap.xml', HTTP_HOST='my.spetion.uz'), '<loc>https://my.spetion.uz/</loc>')

    def test_home_is_login_page_for_search(self):
        from django.test import override_settings
        with override_settings(ALLOWED_HOSTS=['my.spetion.uz']):
            r = self.client.get('/', HTTP_HOST='my.spetion.uz')
            self.assertEqual(r.status_code, 200)
            body = r.content.decode()
            self.assertIn('My Spetion', body)
            self.assertIn('content="index, follow"', body)
            self.assertIn('rel="canonical" href="https://my.spetion.uz/"', body)
            self.assertIn('application/ld+json', body)

    def test_inner_pages_noindex(self):
        from accounts.models import User
        u = User.objects.create_user('p1', password='x', role='parent')
        self.client.force_login(u)
        self.assertContains(self.client.get('/elonlar/'), 'noindex, nofollow')


class GoogleFileTests(__import__('django.test', fromlist=['TestCase']).TestCase):
    def test_only_configured_token(self):
        from django.test import override_settings
        with override_settings(GOOGLE_HTML_TOKEN='74e779e242cab715'):
            self.assertContains(self.client.get('/google74e779e242cab715.html'), 'google-site-verification: google74e779e242cab715.html')
            self.assertEqual(self.client.get('/googleabcdef0123456789.html').status_code, 404)
