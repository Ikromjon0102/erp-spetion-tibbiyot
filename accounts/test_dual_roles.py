from datetime import time
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from academics.models import Group, Lesson, Subject, Teaching
from billing.models import BillingSettings, Payment

from .admin import SchoolUserAdmin
from .child_data import child_context
from .models import Student, User
from .phone import to_digits
from .student_import import import_students

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
XLSX = Path(settings.BASE_DIR) / "10-sinf o'quvchilari ro'yxati.xlsx"


class PhoneDigitsTests(SimpleTestCase):
    def test_to_digits(self):
        for raw in ['+998 94 604-80-62', '94-604-80-62', '946048062', '998946048062']:
            self.assertEqual(to_digits(raw), '998946048062', raw)
        self.assertEqual(to_digits('diyora'), '')
        self.assertEqual(to_digits(''), '')


@FAST
class TeacherPhoneLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create(username='ulugbek', role='teacher', first_name='Ulug\'bek',
                                           phone='+998 94 604-80-62')
        self.teacher.set_password('xxx')
        self.teacher.save()
        self.group = Group.objects.create(name='5-Sinf')
        teaching = Teaching.objects.create(teacher=self.teacher, subject=Subject.objects.create(name='IT'), group=self.group)
        Lesson.objects.create(teaching=teaching, weekday=0, period=1, start=time(8, 30), end=time(9, 15))

    def run_action(self, qs=None):
        ma = SchoolUserAdmin(User, AdminSite())
        ma.message_user = lambda *a, **k: None
        ma.password_from_phone(RequestFactory().post('/'), qs or User.objects.all())

    def test_initial_password_is_last_four_digits_and_must_be_changed(self):
        self.run_action()
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.check_password('8062'))
        self.assertTrue(self.teacher.must_change_password)

        for raw in ['+998 94 604-80-62', '94-604-80-62', '946048062']:  # istalgan formatdagi telefon bilan kiradi
            self.client.logout()
            self.assertEqual(self.client.post('/login/', {'username': raw, 'password': '8062'}).status_code, 302, raw)
        # birinchi kirishda yangi parol so'raladi
        self.assertRedirects(self.client.get('/', follow=False), '/parol/', fetch_redirect_response=False)
        r = self.client.post('/parol/', {'new_password1': 'Yangi-parol-5', 'new_password2': 'Yangi-parol-5'})
        self.assertRedirects(r, '/', fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/'), '/ustoz/', fetch_redirect_response=False)  # endi ustoz sahifasi
        self.assertEqual(self.client.get('/ustoz/').status_code, 200)

        self.client.logout()
        self.assertEqual(self.client.post('/login/', {'username': '946048062', 'password': '8062'}).status_code, 200)  # eski parol ishlamaydi
        self.assertEqual(self.client.post('/login/', {'username': '946048062', 'password': 'Yangi-parol-5'}).status_code, 302)

    def test_username_login_still_works(self):
        self.assertEqual(self.client.post('/login/', {'username': 'ulugbek', 'password': 'xxx'}).status_code, 302)

    def test_action_only_touches_teachers(self):
        admin = User.objects.create_superuser(username='boss', password='keep', phone='+998 90 000-11-22')
        student = User.objects.create(username='kid', role='student', phone='+998 90 000-33-44')
        self.run_action()
        admin.refresh_from_db(); student.refresh_from_db()
        self.assertTrue(admin.check_password('keep'))
        self.assertFalse(admin.must_change_password)
        self.assertFalse(student.must_change_password)


@FAST
class DualRoleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.group5, self.group7 = Group.objects.create(name='5-Sinf'), Group.objects.create(name='7-Sinf')
        subject = Subject.objects.create(name='Kimyo')
        self.teacher = User.objects.create_user(username='t1', password='x', role='teacher', first_name='Diyora',
                                                phone='+998 90 111-22-33')
        Teaching.objects.create(teacher=self.teacher, subject=subject, group=self.group5)
        self.other = User.objects.create_user(username='t2', password='x', role='teacher', first_name='Azizbek')
        Teaching.objects.create(teacher=self.other, subject=subject, group=self.group7)
        # Diyoraning o'z farzandi 7-sinfda o'qiydi (Diyora uni o'qitmaydi)
        self.kid = Student.objects.create(user=User.objects.create_user(username='kid', password='x', role='student',
                                                                         first_name='Madina', last_name='Karimova'),
                                          group=self.group7)
        self.kid.parents.add(self.teacher)
        BillingSettings.objects.update_or_create(pk=1, defaults={'monthly_price': 1000000, 'billing_start': timezone.localdate().replace(day=1)})

    # --- hisoblarni birlashtirish
    def test_parent_account_with_same_phone_is_merged_into_teacher(self):
        parent = User.objects.create(username='998905556677', role='parent', phone='+998 90 555-66-77')
        parent.set_unusable_password()
        parent.save()
        child = Student.objects.create(user=User.objects.create_user(username='k2', password='x', role='student'), group=self.group5)
        child.parents.add(parent)

        new_teacher = User.objects.create_user(username='t3', password='x', role='teacher', phone='90-555-66-77')
        self.assertFalse(User.objects.filter(pk=parent.pk).exists())            # alohida ota-ona hisobi qolmadi
        self.assertEqual(list(child.parents.all()), [new_teacher])               # farzand ustoz hisobiga o'tdi
        self.assertTrue(new_teacher.has_children)

    def test_merge_runs_when_phone_is_added_later(self):
        parent = User.objects.create(username='998905556677', role='parent', phone='+998 90 555-66-77')
        child = Student.objects.create(user=User.objects.create_user(username='k2', password='x', role='student'), group=self.group5)
        child.parents.add(parent)
        t = User.objects.create_user(username='t3', password='x', role='teacher')
        t.phone = '+998 90 555-66-77'
        t.save()  # admin ro'yxatida telefon keyin kiritildi
        self.assertFalse(User.objects.filter(pk=parent.pk).exists())
        self.assertEqual(list(child.parents.all()), [t])

    def test_non_matching_phone_does_not_merge(self):
        parent = User.objects.create(username='998901112299', role='parent', phone='+998 90 111-22-99')
        User.objects.create_user(username='t3', password='x', role='teacher', phone='+998 90 111-22-98')
        self.assertTrue(User.objects.filter(pk=parent.pk).exists())

    @FAST
    def test_import_reuses_existing_teacher_as_parent(self):
        if not XLSX.exists():
            self.skipTest('Excel fayl topilmadi')
        t = User.objects.create_user(username='t9', password='x', role='teacher', phone='95-010-76-39')  # Xabibullaeva Fotima onasi
        report = import_students(XLSX, '10-Sinf')
        self.assertEqual(report['parents_new'], 18)  # 19 tadan 1 tasi — allaqachon tizimdagi ustoz
        fotima = Student.objects.get(user__last_name='Xabibullaeva')
        self.assertEqual(list(fotima.parents.all()), [t])
        self.assertFalse(User.objects.filter(username='998950107639').exists())

    # --- ruxsatlar
    def test_teacher_sees_own_child_in_other_group_with_payments(self):
        self.client.login(username='t1', password='x')
        r = self.client.get(f'/oquvchi/{self.kid.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'data-tab="payments"')   # u bu bolaning ota-onasi
        self.assertEqual(child_context(self.kid, self.teacher)['debt'], 1000000)

    def test_other_teacher_cannot_see_the_child_or_payments(self):
        self.client.login(username='t2', password='x')
        # t2 shu bolani (7-sinf) o'qitadi — ko'ra oladi, lekin ota-ona emas, to'lov ko'rinmaydi
        r = self.client.get(f'/oquvchi/{self.kid.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'data-tab="payments"')
        # 5-sinf o'quvchisini t2 ko'ra olmaydi
        other_kid = Student.objects.create(user=User.objects.create_user(username='x', password='x', role='student'), group=self.group5)
        self.assertEqual(self.client.get(f'/oquvchi/{other_kid.pk}/').status_code, 403)

    # --- rejimlar va menyu
    def test_lands_on_teacher_page_then_remembers_parent_mode(self):
        self.client.login(username='t1', password='x')
        self.assertRedirects(self.client.get('/'), '/ustoz/', fetch_redirect_response=False)       # birinchi marta: ustoz
        self.assertRedirects(self.client.get('/?rejim=ota-ona'), f'/oquvchi/{self.kid.pk}/', fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/'), f'/oquvchi/{self.kid.pk}/', fetch_redirect_response=False)  # eslab qoldi
        self.client.get('/ustoz/')                                                                  # ustoz sahifasiga qaytdi
        self.assertRedirects(self.client.get('/'), '/ustoz/', fetch_redirect_response=False)

    def test_teacher_page_shows_children_status_and_mode_switch(self):
        self.client.login(username='t1', password='x')
        r = self.client.get('/ustoz/')
        self.assertContains(r, 'Karimova Madina')       # farzand kartasi (sahifa ma'lumotida)
        self.assertContains(r, 'class="menu-sw"')        # menyuda rejim almashtirgich
        self.assertContains(r, 'Farzandlarim')

    def test_plain_teacher_has_no_switch_and_no_children_block(self):
        self.client.login(username='t2', password='x')
        r = self.client.get('/ustoz/')
        self.assertNotContains(r, 'class="menu-sw"')
        self.assertContains(r, '"kids": []')

    def test_parent_page_of_dual_user_has_switch_back_to_teacher(self):
        self.client.login(username='t1', password='x')
        r = self.client.get(f'/oquvchi/{self.kid.pk}/')
        self.assertContains(r, 'class="menu-sw"')
        self.assertContains(r, 'Ustoz sahifasi')
