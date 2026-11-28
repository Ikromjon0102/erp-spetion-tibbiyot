from datetime import time, timedelta

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from access.models import AccessEvent, Device
from academics.models import Group, Lesson, Subject, Teaching
from journal.models import Attendance, Grade
from billing.models import BillingSettings, Payment
from notices.models import Announcement

from .child_data import child_context, grade_class, presence
from .models import Student, User
from .templatetags.app_extras import initials, money, wd

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


class FilterTests(SimpleTestCase):
    def test_money(self):
        self.assertEqual(money(1500000), '1 500 000')
        self.assertEqual(money(0), '0')

    def test_initials_and_weekday(self):
        self.assertEqual(initials(User(first_name='Fotima', last_name='Xabibullaeva')), 'XF')
        self.assertEqual(initials(User(username='ota')), 'O')
        self.assertEqual(wd(timezone.datetime(2026, 11, 15)), 'Ya')
        self.assertEqual(wd(timezone.datetime(2026, 11, 14)), 'Sh')

    def test_grade_class_thresholds(self):
        self.assertEqual([grade_class(x) for x in (5, 4.5, 4.4, 3.5, 3.4, 2.5, 2.4, 1)],
                         ['g5', 'g5', 'g4', 'g4', 'g3', 'g3', 'g2', 'g2'])


@FAST
class ChildAppTests(TestCase):
    def setUp(self):
        mk = lambda u, role, **kw: User.objects.create_user(username=u, password='x', role=role, **kw)
        self.parent, self.other_parent = mk('p1', 'parent'), mk('p2', 'parent')
        self.teacher = mk('t1', 'teacher', first_name='Diyora')
        self.group = Group.objects.create(name='10-Sinf')
        self.kid = Student.objects.create(user=mk('k1', 'student', first_name='Fotima', last_name='Xabibullaeva'),
                                          group=self.group, access_id='1001')
        self.kid.parents.add(self.parent)
        self.subject = Subject.objects.create(name='Kimyo')
        self.teaching = Teaching.objects.create(teacher=self.teacher, subject=self.subject, group=self.group)
        today = timezone.localdate()
        self.lesson = Lesson.objects.create(teaching=self.teaching, weekday=today.weekday() % 6, period=1,
                                            start=time(8, 30), end=time(9, 15))
        for score in (5, 5, 4, 2):
            Grade.objects.create(student=self.kid, teaching=self.teaching, score=score, date=today)
        BillingSettings.objects.update_or_create(pk=1, defaults={'monthly_price': 1500000, 'billing_start': today.replace(day=1)})
        Payment.objects.create(student=self.kid, amount=500000)

    # --- ma'lumotlar
    def test_grades_average_and_subjects(self):
        ctx = child_context(self.kid, self.parent)
        self.assertEqual((ctx['avg'], ctx['n_grades']), ('4.0', 4))
        (subj,) = ctx['subjects']
        self.assertEqual((subj['name'], subj['avg'], subj['avg_class'], subj['count']), ('Kimyo', '4.0', 'g4', 4))

    def test_attendance_rate_counts_late_as_present(self):
        today = timezone.localdate()
        for i, st in enumerate(['present', 'present', 'late', 'absent']):
            Attendance.objects.create(student=self.kid, lesson=self.lesson, date=today - timedelta(days=i), status=st)
        stats = child_context(self.kid, self.parent)['att_stats']
        self.assertEqual((stats['total'], stats['absent'], stats['late'], stats['rate']), (4, 1, 1, 75))
        self.assertEqual(len(child_context(self.kid, self.parent)['issues']), 2)  # kech + kelmadi

    def test_presence_states(self):
        now = timezone.localtime().replace(hour=11, minute=0, second=0, microsecond=0)
        din, dout = Device.objects.create(name='K', direction='in'), Device.objects.create(name='C', direction='out')
        if now.weekday() != 6:
            self.assertEqual(presence(self.kid, now)['state'], 'wait')
        make = lambda dev, h: AccessEvent.objects.create(device=dev, student=self.kid, employee_no='1001',
                                                         direction=dev.direction, occurred_at=now.replace(hour=h, minute=5))
        make(din, 8)
        self.assertEqual(presence(self.kid, now)['state'], 'in')
        self.assertIn('08:05 dan beri', presence(self.kid, now)['text'])
        make(dout, 10)
        p = presence(self.kid, now)
        self.assertEqual((p['state'], p['text']), ('out', 'Tashqarida · 10:05 dan'))      # 16:00 dan oldin: tanaffus
        p = presence(self.kid, now.replace(hour=17))
        self.assertEqual((p['state'], p['text']), ('out', 'Uyga ketdi · 10:05'))          # 16:00 dan keyin: uyga ketdi

    # --- ruxsatlar va ko'rinish
    def test_payments_visible_only_to_parent_and_admin(self):
        self.assertIsNotNone(child_context(self.kid, self.parent)['payments'])
        self.assertEqual(child_context(self.kid, self.parent)['debt'], 1000000)
        self.assertIsNone(child_context(self.kid, self.teacher)['payments'])
        self.assertIsNone(child_context(self.kid, self.kid.user)['payments'])

    def test_student_page_has_no_payment_tab_but_parent_has(self):
        self.client.login(username='p1', password='x')
        r = self.client.get(f'/oquvchi/{self.kid.pk}/')
        self.assertContains(r, 'data-tab="payments"')
        self.assertContains(r, '1 000 000')
        self.client.login(username='k1', password='x')
        r = self.client.get(f'/oquvchi/{self.kid.pk}/')
        self.assertNotContains(r, 'data-tab="payments"')
        self.assertNotContains(r, '1 000 000')

    def test_page_renders_all_tabs_and_today_lesson(self):
        self.client.login(username='p1', password='x')
        r = self.client.get(f'/oquvchi/{self.kid.pk}/')
        for marker in ('id="tab-home"', 'id="tab-grades"', 'id="tab-attendance"', 'id="tab-schedule"', 'Bugungi darslar',
                       'Xabibullaeva Fotima', 'Diyora'):
            self.assertContains(r, marker)

    def test_multiple_children_list_and_switcher(self):
        sib_user = User.objects.create_user(username='k2', password='x', role='student', first_name='Aziz', last_name='Xabibullaev')
        sib = Student.objects.create(user=sib_user, group=self.group)
        sib.parents.add(self.parent)
        self.client.login(username='p1', password='x')
        r = self.client.get('/')
        self.assertEqual(r.status_code, 200)  # bir nechta farzand: ro'yxat sahifasi
        self.assertContains(r, 'Xabibullaeva Fotima')
        self.assertContains(r, 'Xabibullaev Aziz')
        page = self.client.get(f'/oquvchi/{self.kid.pk}/')
        self.assertContains(page, f'href="/oquvchi/{sib.pk}/"')  # aka-uka almashtirgichi

    def test_no_children_message(self):
        self.client.login(username='p2', password='x')
        self.assertContains(self.client.get('/'), 'hali farzand biriktirilmagan')

    def test_announcements_page_and_login_page_render(self):
        Announcement.objects.create(title='Yig\'ilish', body='Juma kuni', audience='parents')
        self.client.login(username='p1', password='x')
        page = self.client.get('/elonlar/')
        self.assertContains(page, 'Yig&#x27;ilish')
        self.assertContains(page, '<details class="nw" data-nid=')   # sarlavha ko'rinadi, matn bosilganda ochiladi va o'qildi deb belgilanadi
        self.assertContains(page, '<div class="body">Juma kuni</div>')
        self.client.logout()
        r = self.client.get('/login/')
        self.assertContains(r, 'Telefon raqam yoki login')
        self.assertContains(r, 'autocapitalize')


class WeekLabelTests(TestCase):
    def test_week_label(self):
        import datetime
        from accounts.child_data import _week_label
        self.assertEqual(_week_label(datetime.date(2026, 11, 30), datetime.date(2026, 12, 5)), '30-noyabr – 5-dekabr')
        self.assertEqual(_week_label(datetime.date(2026, 12, 7), datetime.date(2026, 12, 12)), '7–12-dekabr')
