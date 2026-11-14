import csv
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.admin.sites import AdminSite
from django.core.cache import cache
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from academics.models import Group

from .admin import SchoolUserAdmin
from .models import Student, User
from .passwords import issue_temp_password
from .phone import normalize_login

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


class NormalizeLoginTests(SimpleTestCase):
    def test_phone_formats_become_digits(self):
        for raw in ['+998 95 010-76-39', '95-010-76-39', '950107639', '998950107639', ' (95) 010 76 39 ']:
            self.assertEqual(normalize_login(raw), '998950107639', raw)

    def test_non_phone_logins_untouched(self):
        for raw in ['diyora', 'admin1', 'namuna_5_01', '20']:
            self.assertEqual(normalize_login(raw), raw)


@FAST
class ParentLoginFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.parent = User.objects.create(username='998950107639', role='parent', phone='+998 95 010-76-39',
                                          first_name='Xabibullaeva Fotima onasi')
        self.parent.set_unusable_password()
        self.parent.save()
        child = User.objects.create(username='kid', first_name='Fotima', last_name='Xabibullaeva', role='student')
        self.student = Student.objects.create(user=child, group=Group.objects.create(name='10-Sinf'))
        self.student.parents.add(self.parent)
        self.temp = issue_temp_password(self.parent)

    def login(self, username, password):
        return self.client.post('/login/', {'username': username, 'password': password})

    def test_phone_in_any_format_logs_in(self):
        for raw in ['+998 95 010-76-39', '95-010-76-39', '950107639', '998950107639']:
            self.client.logout()
            self.assertEqual(self.login(raw, self.temp).status_code, 302, raw)

    def test_wrong_temp_password(self):
        self.assertContains(self.login('950107639', 'nope'), "noto'g'ri")

    def test_first_login_forces_new_password(self):
        self.login('950107639', self.temp)
        for url in ['/', f'/oquvchi/{self.student.pk}/']:
            r = self.client.get(url)
            self.assertRedirects(r, '/parol/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/parol/').status_code, 200)

    def test_new_password_rules_and_success(self):
        self.login('950107639', self.temp)
        post = lambda pw: self.client.post('/parol/', {'new_password1': pw, 'new_password2': pw})
        self.assertContains(post('123456'), 'oddiy')                  # juda keng tarqalgan parol
        self.assertContains(post('abc'), '6')                         # qisqa
        self.assertContains(post(self.temp), 'farq qilishi kerak')    # bir martalik parolning o'zi
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.must_change_password)

        r = post('Yangi-parol-77')
        self.assertRedirects(r, '/', fetch_redirect_response=False)
        self.parent.refresh_from_db()
        self.assertFalse(self.parent.must_change_password)
        self.assertEqual(self.client.get('/', follow=True).status_code, 200)  # tizimdan chiqib ketmadi, sahifalar ochiq

        self.client.logout()
        self.assertEqual(self.login('950107639', self.temp).status_code, 200)          # eski parol endi ishlamaydi
        self.assertEqual(self.login('+998 95 010-76-39', 'Yangi-parol-77').status_code, 302)
        self.assertEqual(self.client.get('/', follow=True).status_code, 200)  # endi majburiy almashtirish so'ralmaydi

    def test_throttle_cannot_be_dodged_by_changing_phone_format(self):
        for raw in ['+998 95 010-76-39', '95-010-76-39', '950107639', '998950107639', '+998950107639']:
            self.login(raw, 'xato')
        r = self.login('95 010 76 39', self.temp)
        self.assertContains(r, 'Juda ko')


@FAST
class ParentPasswordCommandTests(TestCase):
    def setUp(self):
        cache.clear()
        self.p1 = User.objects.create(username='998901112233', role='parent', phone='+998 90 111-22-33', first_name='Bir')
        self.p2 = User.objects.create(username='998904445566', role='parent', phone='+998 90 444-55-66', first_name='Ikki')
        self.has = User.objects.create_user(username='998907778899', password='mening-parolim', role='parent', first_name='Uch')
        for p in (self.p1, self.p2):
            p.set_unusable_password()
            p.save()
        self.out = str(Path(tempfile.mkdtemp()) / 'out.csv')

    def run_cmd(self, *args):
        call_command('issue_parent_passwords', *args, '--output', self.out, stdout=StringIO())

    def rows(self):
        with open(self.out, encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))

    def test_only_unissued_parents_by_default_and_passwords_work(self):
        self.run_cmd()
        rows = self.rows()
        self.assertEqual({r['Login (telefon)'] for r in rows}, {'+998 90 111-22-33', '+998 90 444-55-66'})
        for r in rows:
            user = User.objects.get(phone=r['Login (telefon)'])
            self.assertTrue(user.check_password(r['Bir martalik parol']))
            self.assertTrue(user.must_change_password)
        self.has.refresh_from_db()
        self.assertTrue(self.has.check_password('mening-parolim'))    # paroli borga tegilmadi
        self.assertFalse(self.has.must_change_password)

    def test_second_run_does_nothing_and_phone_reissues_one(self):
        self.run_cmd()
        first = {r['Login (telefon)']: r['Bir martalik parol'] for r in self.rows()}
        self.run_cmd()  # hammasida parol bor: fayl qayta yozilmaydi
        self.assertEqual({r['Login (telefon)']: r['Bir martalik parol'] for r in self.rows()}, first)

        self.run_cmd('--phone', '90-111-22-33')
        (row,) = self.rows()
        self.assertEqual(row['Login (telefon)'], '+998 90 111-22-33')
        self.assertNotEqual(row['Bir martalik parol'], first['+998 90 111-22-33'])
        self.p2.refresh_from_db()
        self.assertTrue(self.p2.check_password(first['+998 90 444-55-66']))  # boshqasi o'zgarmadi


@FAST
class AdminActionTests(TestCase):
    def setUp(self):
        self.ma = SchoolUserAdmin(User, AdminSite())
        self.sent = []
        self.ma.message_user = lambda request, msg, **kw: self.sent.append(msg)

    def test_temp_password_action_flags_and_reports(self):
        p = User.objects.create(username='998901112233', role='parent', phone='+998 90 111-22-33', first_name='Ota')
        self.ma.temp_password(RequestFactory().post('/'), User.objects.filter(pk=p.pk))
        p.refresh_from_db()
        self.assertTrue(p.must_change_password)
        self.assertIn('+998 90 111-22-33', self.sent[0])
        pw = self.sent[0].split('parol: ')[1].strip()
        self.assertTrue(p.check_password(pw))

    def test_phone_password_action_skips_parents_but_serves_teachers(self):
        t = User.objects.create(username='t', role='teacher', phone='+998 94 604-80-62')
        p = User.objects.create(username='p', role='parent', phone='+998 90 111-22-33')
        p.set_password('keep')
        p.save()
        self.ma.password_from_phone(RequestFactory().post('/'), User.objects.all())
        t.refresh_from_db(); p.refresh_from_db()
        self.assertTrue(t.check_password('8062'))
        self.assertTrue(p.check_password('keep'))  # ota-onaga 4 xonali parol qo'yilmadi
