from django.core.cache import cache
from django.test import TestCase, override_settings

from academics.models import Group, Subject, Teaching
from accounts.models import Student, User

from .models import AuditLog
from .tests import make_staff

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


def teacher(username, last, phone, **kw):
    return User.objects.create_user(username=username, password='x', role='teacher', first_name='Ali', last_name=last, phone=phone, **kw)


@FAST
class TeacherPanelTests(TestCase):
    def setUp(self):
        cache.clear()
        self.dir = make_staff('dir', 'Direktor')
        self.zam = make_staff('zam', "Zam (o'quv ishlari)")
        self.rec = make_staff('rec', 'Reception')
        self.hisob = make_staff('hisob', 'Hisobchi')
        self.t1 = teacher('t1', 'Karimov', '+998 90 111-22-33')
        self.t2 = teacher('t2', 'Valiyev', '+998 91 222-33-44')
        self.demo = teacher('sinov_t', 'Sinov', '+998 90 000-00-00', is_demo=True)
        self.g = Group.objects.create(name='5-A', year=2026)
        self.math = Subject.objects.create(name='Matematika')
        Teaching.objects.create(teacher=self.t1, subject=self.math, group=self.g)

    def login(self, name):
        self.client.login(username=name, password='x')

    def test_list_search_and_hides_demo(self):
        self.login('dir')
        r = self.client.get('/panel/ustozlar/')
        self.assertContains(r, 'Karimov')
        self.assertNotContains(r, 'Sinov')
        self.assertContains(r, 'Matematika')
        self.assertNotContains(self.client.get('/panel/ustozlar/?q=Karim'), 'Valiyev')
        self.assertContains(self.client.get('/panel/ustozlar/?q=2223344'), 'Valiyev')       # telefon bo'yicha
        self.assertContains(self.client.get('/panel/ustozlar/?q=matem'), 'Karimov')         # fan bo'yicha

    def test_permissions(self):
        self.login('hisob')
        self.assertEqual(self.client.get('/panel/ustozlar/').status_code, 403)
        self.login('rec')                                                    # Reception faqat ko'radi
        self.assertEqual(self.client.get('/panel/ustozlar/').status_code, 200)
        self.assertEqual(self.client.get('/panel/ustozlar/yangi/').status_code, 403)
        self.assertEqual(self.client.post(f'/panel/ustozlar/{self.t1.pk}/parol/').status_code, 403)
        self.login('zam')                                                    # Zam: tahrirlaydi, qo'shmaydi
        self.assertEqual(self.client.get(f'/panel/ustozlar/{self.t1.pk}/tahrirlash/').status_code, 200)
        self.assertEqual(self.client.get('/panel/ustozlar/yangi/').status_code, 403)

    def test_add_teacher_gets_last4_password_and_must_change(self):
        self.login('dir')
        r = self.client.post('/panel/ustozlar/yangi/', {'last_name': 'Aliyev', 'first_name': 'Sardor', 'phone': '+998 93 555-66-77'})
        u = User.objects.get(phone_digits='998935556677')
        self.assertRedirects(r, f'/panel/ustozlar/{u.pk}/')
        self.assertEqual(u.role, 'teacher')
        self.assertTrue(u.check_password('6677') and u.must_change_password)
        self.assertTrue(AuditLog.objects.filter(verb="Ustoz qo'shdi").exists())
        self.assertTrue(self.client.login(username=u.username, password='6677'))

    def test_duplicate_phone_rejected_but_parent_account_is_merged(self):
        self.login('dir')
        self.client.post('/panel/ustozlar/yangi/', {'last_name': 'X', 'first_name': 'Y', 'phone': '+998 90 111-22-33'})
        self.assertEqual(User.objects.filter(phone_digits='998901112233').count(), 1)       # ustoz bor — rad etildi
        parent = User.objects.create_user(username='ota', role='parent', phone='+998 94 777-88-99')
        kid = Student.objects.create(user=User.objects.create_user(username='kid', role='student'), group=self.g)
        kid.parents.add(parent)
        self.client.post('/panel/ustozlar/yangi/', {'last_name': 'Ota', 'first_name': 'Bola', 'phone': '+998 94 777-88-99'})
        u = User.objects.get(phone_digits='998947778899')
        self.assertEqual(u.role, 'teacher')
        self.assertEqual(list(kid.parents.all()), [u])                                       # farzand yangi hisobga o'tdi

    def test_edit_assign_unassign_password_and_toggle(self):
        self.login('dir')
        self.client.post(f'/panel/ustozlar/{self.t2.pk}/tahrirlash/', {'last_name': 'Valiyeva', 'first_name': 'Nilufar', 'phone': '+998 91 222-33-44'})
        self.t2.refresh_from_db()
        self.assertEqual(self.t2.last_name, 'Valiyeva')
        sub = Subject.objects.create(name='Fizika')
        self.client.post(f'/panel/ustozlar/{self.t2.pk}/dars/', {'subject': sub.pk, 'group': self.g.pk})
        t = Teaching.objects.get(teacher=self.t2)
        self.client.post(f'/panel/ustozlar/{self.t2.pk}/dars/', {'subject': sub.pk, 'group': self.g.pk})   # takror — qo'shilmaydi
        self.assertEqual(Teaching.objects.filter(teacher=self.t2).count(), 1)
        self.client.post(f'/panel/ustozlar/{self.t2.pk}/dars/{t.pk}/olib-tashlash/')
        self.assertFalse(Teaching.objects.filter(teacher=self.t2).exists())
        self.client.post(f'/panel/ustozlar/{self.t2.pk}/parol/')
        self.t2.refresh_from_db()
        self.assertTrue(self.t2.check_password('3344') and self.t2.must_change_password)
        self.client.post(f'/panel/ustozlar/{self.t2.pk}/holat/')
        self.t2.refresh_from_db()
        self.assertFalse(self.t2.is_active)

    def test_detail_shows_children_when_teacher_is_parent(self):
        kid = Student.objects.create(user=User.objects.create_user(username='kid', role='student', last_name='Bola'), group=self.g)
        kid.parents.add(self.t1)
        self.login('dir')
        self.assertContains(self.client.get(f'/panel/ustozlar/{self.t1.pk}/'), 'Bola')
        self.assertEqual(self.client.get(f'/panel/ustozlar/{self.demo.pk}/').status_code, 404)   # sinov ustozi ko'rinmaydi
