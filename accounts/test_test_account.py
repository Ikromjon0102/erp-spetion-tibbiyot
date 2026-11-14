import json
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from academics.models import Group, Lesson, Subject, Teaching
from access.models import AccessEvent, Device
from journal.models import Attendance, Grade
from notices.models import Announcement

from .models import Student, User

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


def run(*args):
    call_command('create_test_account', *args, stdout=StringIO())


@FAST
class TestAccountTests(TestCase):
    def setUp(self):
        cache.clear()
        Device.objects.create(name='Kirish-1', direction='in')
        Device.objects.create(name='Chiqish-1', direction='out')
        # haqiqiy ma'lumot: unga tegilmasligi kerak
        self.real_group = Group.objects.create(name='10-Sinf')
        self.real_teacher = User.objects.create_user(username='real', password='x', role='teacher', first_name='Real')
        Teaching.objects.create(teacher=self.real_teacher, subject=Subject.objects.create(name='Kimyo'), group=self.real_group)
        self.real_kid = Student.objects.create(user=User.objects.create_user(username='rk', password='x', role='student'),
                                               group=self.real_group)
        self.real_news = Announcement.objects.create(title='Haqiqiy', body='x', audience='all')

    def login(self, password):
        self.client.logout()
        return self.client.post('/login/', {'username': 'sinov', 'password': password})

    def test_creates_dual_role_account_that_logs_in_by_phone_or_username(self):
        run('--password', 'sinov-parol')
        u = User.objects.get(username='sinov')
        self.assertTrue(u.is_teacher and u.is_demo and u.has_children)
        self.assertFalse(u.must_change_password)
        self.assertEqual(u.children.count(), 4)  # 4 farzand: A sinfda 2 ta, B sinfda 2 ta
        for login in ('sinov', '+998 90 000-00-01', '900000001'):
            self.client.logout()
            self.assertEqual(self.client.post('/login/', {'username': login, 'password': 'sinov-parol'}).status_code, 302, login)
        self.assertRedirects(self.client.get('/'), '/ustoz/', fetch_redirect_response=False)  # majburiy parol almashtirish yo'q

    def test_idempotent_and_keeps_password_unless_given(self):
        run('--password', 'sinov-parol')
        before = (Student.objects.count(), Grade.objects.count(), Lesson.objects.count(), AccessEvent.objects.count(),
                  Attendance.objects.count(), Announcement.objects.count())
        run()
        self.assertEqual(before, (Student.objects.count(), Grade.objects.count(), Lesson.objects.count(),
                                  AccessEvent.objects.count(), Attendance.objects.count(), Announcement.objects.count()))
        self.assertEqual(self.login('sinov-parol').status_code, 302)          # parol o'zgarmadi
        run('--password', 'yangi-parol')
        self.assertEqual(self.login('sinov-parol').status_code, 200)
        self.assertEqual(self.login('yangi-parol').status_code, 302)

    def test_attendance_and_grades_work_at_any_time_and_any_day(self):
        run('--password', 'p1')
        self.login('p1')
        lesson = Lesson.objects.filter(teaching__teacher__username='sinov', period=1).first()
        kid = Student.objects.get(user__username='sinov_o1')
        old_day = (timezone.localdate() - timezone.timedelta(days=40)).isoformat()    # o'tgan kun
        future = (timezone.localdate() + timezone.timedelta(days=10)).isoformat()     # kelajak kun

        for day in (old_day, future, timezone.localdate().isoformat()):
            r = self.client.post(f'/ustoz/api/dars/{lesson.id}/saqlash/',
                                 json.dumps({'date': day, 'rows': [{'id': kid.id, 's': 'absent'}]}), content_type='application/json')
            self.assertTrue(r.json()['ok'], day)
            self.assertTrue(self.client.get(f'/ustoz/api/dars/{lesson.id}/?date={day}').json()['editable'])
            g = self.client.post(f'/ustoz/api/baho/{lesson.id}/saqlash/',
                                 json.dumps({'date': day, 'student': kid.id, 'score': 5}), content_type='application/json')
            self.assertTrue(g.json()['ok'], day)

    def test_all_day_lesson_makes_something_current_every_day_of_the_week(self):
        run()
        for weekday in range(6):
            self.assertTrue(Lesson.objects.filter(teaching__teacher__username='sinov', weekday=weekday,
                                                  start='00:00', end='23:59').exists(), weekday)

    def test_parent_side_shows_children_with_data_and_debt(self):
        run('--password', 'p1')
        self.login('p1')
        self.client.get('/?rejim=ota-ona')
        kid = Student.objects.get(user__username='sinov_o1')
        r = self.client.get(f'/oquvchi/{kid.pk}/')
        self.assertContains(r, 'data-tab="payments"')
        self.assertContains(r, 'Sinovov Aziz')
        self.assertTrue(kid.grades.exists() and kid.attendance.exists() and kid.fee_payments.exists())
        self.assertEqual(Student.objects.get(user__username='sinov_o2').access_events.filter(
            occurred_at__date=timezone.localdate()).count(), 0)  # ikkinchi farzand bugun hali kelmagan

    def test_test_news_visible_only_to_the_test_account(self):
        run('--password', 'p1')
        self.login('p1')
        titles = {a['title'] for a in self.client.get('/ustoz/api/elonlar/').json()['items']}
        self.assertTrue({"[Sinov] Hamma uchun e'lon (Sinov-sinf)", "[Sinov] Ustozlarga e'lon (Sinov-sinf B)",
                         "[Sinov] Ota-onalarga e'lon (Sinov-sinf B)", 'Haqiqiy'} <= titles)
        self.client.logout()
        self.client.login(username='real', password='x')                      # haqiqiy ustoz sinov e'lonlarini ko'rmaydi
        titles = {a['title'] for a in self.client.get('/ustoz/api/elonlar/').json()['items']}
        self.assertEqual(titles, {'Haqiqiy'})

    def test_regular_teacher_is_not_affected_by_demo_rules(self):
        run()
        self.client.login(username='real', password='x')
        lesson = Lesson.objects.create(teaching=Teaching.objects.get(teacher=self.real_teacher), weekday=0, period=1,
                                       start='08:30', end='09:15')
        far = (timezone.localdate() - timezone.timedelta(days=40)).isoformat()
        self.assertFalse(self.client.get(f'/ustoz/api/dars/{lesson.id}/?date={far}').json()['editable'])
        g = self.client.post(f'/ustoz/api/baho/{lesson.id}/saqlash/',
                             json.dumps({'date': (timezone.localdate() + timezone.timedelta(days=3)).isoformat(),
                                         'student': self.real_kid.id, 'score': 5}), content_type='application/json')
        self.assertEqual(g.json()['err'], 'time')

    def test_remove_cleans_everything_and_keeps_real_data(self):
        run()
        run('--remove')
        self.assertFalse(User.objects.filter(username__startswith='sinov').exists())
        self.assertFalse(Group.objects.filter(name__startswith='Sinov-sinf').exists())
        self.assertFalse(Lesson.objects.filter(teaching__subject__name__startswith='Sinov').exists())
        self.assertFalse(AccessEvent.objects.filter(employee_no__startswith='S9').exists())
        self.assertFalse(Announcement.objects.filter(title__startswith='[Sinov]').exists())
        self.assertEqual(Student.objects.count(), 1)                                   # faqat haqiqiy o'quvchi qoldi
        self.assertTrue(Announcement.objects.filter(pk=self.real_news.pk).exists())
        self.assertTrue(Group.objects.filter(name='10-Sinf').exists())


@FAST
class MultipleChildrenTests(TestCase):
    def setUp(self):
        cache.clear()
        Device.objects.create(name='Kirish-1', direction='in')
        Device.objects.create(name='Chiqish-1', direction='out')
        run('--password', 'p1')
        self.client.login(username='sinov', password='p1')

    def test_children_are_in_two_different_classes(self):
        u = User.objects.get(username='sinov')
        by_class = {}
        for kid in u.children.select_related('group', 'user'):
            by_class.setdefault(kid.group.name, []).append(kid.user.first_name)
        self.assertEqual(by_class, {'Sinov-sinf': ['Aziz', 'Madina'], 'Sinov-sinf B': ['Bobur', 'Zarina']})

    def test_parent_list_shows_all_children_with_own_status(self):
        r = self.client.get('/?rejim=ota-ona')
        self.assertEqual(r.status_code, 200)  # bir nechta farzand: ro'yxat sahifasi
        for name in ('Sinovov Aziz', 'Sinovova Madina', 'Sinovov Bobur', 'Sinovova Zarina'):
            self.assertContains(r, name)
        self.assertContains(r, 'Sinov-sinf B')

    def test_child_page_has_switcher_for_all_children_and_own_schedule(self):
        bobur = Student.objects.get(user__username='sinov_b1')
        r = self.client.get(f'/oquvchi/{bobur.pk}/')
        self.assertContains(r, 'Sinov (kun bo&#x27;yi)')            # B sinf jadvali ko'rinadi
        for username in ('sinov_o1', 'sinov_o2', 'sinov_b2'):
            self.assertContains(r, f'href="/oquvchi/{Student.objects.get(user__username=username).pk}/"')

    def test_teacher_page_shows_status_chips_for_all_children(self):
        r = self.client.get('/ustoz/')
        data = r.context['school']
        self.assertEqual(sorted(k['name'] for k in data['kids']),
                         ['Sinovov Aziz', 'Sinovov Bobur', 'Sinovova Madina', 'Sinovova Zarina'])
        states = {k['name']: k['state'] for k in data['kids']}
        self.assertIn(states['Sinovov Aziz'], {'in', 'out', 'none', 'wait', 'off'})  # 'off' — yakshanba

    def test_teacher_teaches_both_classes(self):
        classes = set(Lesson.objects.filter(teaching__teacher__username='sinov').values_list('teaching__group__name', flat=True))
        self.assertEqual(classes, {'Sinov-sinf', 'Sinov-sinf B'})

    def test_news_filtered_by_each_childs_class(self):
        run('--password', 'p1')  # takroriy ishga tushirish ham yangi e'lon yaratmaydi
        self.assertEqual(Announcement.objects.filter(title__startswith='[Sinov]').count(), 6)
        titles = {a.title for a in __import__('notices.views', fromlist=['x']).announcements_for(User.objects.get(username='sinov'))}
        self.assertIn("[Sinov] Ota-onalarga e'lon (Sinov-sinf B)", titles)


@FAST
class TestAccountHomeworkTests(TestCase):
    def setUp(self):
        cache.clear()
        Device.objects.create(name='Kirish-1', direction='in')
        Device.objects.create(name='Chiqish-1', direction='out')
        run('--password', 'p1')

    def test_sample_homework_exists_once_per_class_and_parent_sees_unread(self):
        from journal.models import Homework
        self.assertEqual(Homework.objects.count(), 6)                    # 2 sinf x 3 ta
        run()
        self.assertEqual(Homework.objects.count(), 6)                    # takroriy ishga tushirishda ko'paymaydi
        self.client.login(username='sinov', password='p1')
        kid = Student.objects.get(user__username='sinov_o1')
        c = __import__('accounts.child_data', fromlist=['x']).child_context(kid, User.objects.get(username='sinov'))
        self.assertEqual(set(c['homework']), {'Sinov fani', "Sinov (kun bo'yi)"})
        self.assertEqual(c['hw_unread'], 3)

    def test_demo_teacher_can_edit_sample_homework_from_earlier_days(self):
        from journal.models import Homework
        old = Homework.objects.filter(assigned_on__lt=timezone.localdate()).first()      # kecha berilgan namuna
        lesson = Lesson.objects.filter(teaching=old.teaching, period=1).first()
        self.client.login(username='sinov', password='p1')
        r = self.client.post(f'/ustoz/api/vazifa/{lesson.id}/{old.id}/yangilash/',
                             json.dumps({'text': 'Tahrirlandi', 'due': (timezone.localdate() + timezone.timedelta(days=2)).isoformat()}),
                             content_type='application/json')
        self.assertTrue(r.json()['ok'])                                   # sinov hisobda kun oxiri cheklovi yo'q

    def test_remove_deletes_homework_too(self):
        from journal.models import Homework
        run('--remove')
        self.assertEqual(Homework.objects.count(), 0)
