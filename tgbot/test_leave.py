from datetime import time
from io import StringIO
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from access.models import AccessEvent, AccessSettings, Device, PresenceNotice, leave_from
from accounts.child_data import presence
from academics.models import Group
from accounts.models import Student, User

EARLY, LATE = time(0, 0), time(23, 59)      # "chiqish vaqti allaqachon keldi" / "hali kelmadi"


class LeaveNoticeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.entry = Device.objects.create(name='K', direction='in')
        self.exit = Device.objects.create(name='C', direction='out')
        u = User.objects.create(username='k1', first_name='Vali', last_name='Aliyev', role='student')
        self.s = Student.objects.create(user=u, group=Group.objects.create(name='5-Sinf'), access_id='1')
        self.parent = User.objects.create(username='p', role='parent')
        self.s.parents.add(self.parent)
        p = mock.patch('tgbot.signals.notify'); self.notify = p.start(); self.addCleanup(p.stop)

    def scan(self, device, seconds=0):
        return AccessEvent.objects.create(device=device, employee_no='1', student=self.s, direction=device.direction,
                                          occurred_at=timezone.now() + timezone.timedelta(seconds=seconds))

    def texts(self):
        return [c.args[1] for c in self.notify.call_args_list]

    def test_arrival_notified_once_even_with_many_scans(self):
        for i in range(5):
            self.scan(self.entry, i)
        self.assertEqual(len(self.texts()), 1)
        self.assertIn('maktabga keldi', self.texts()[0])

    def test_exit_before_leave_time_is_silent_break(self):
        with mock.patch('tgbot.signals.leave_from', return_value=LATE), mock.patch('access.services.leave_from', return_value=LATE):
            self.scan(self.entry); self.notify.reset_mock()
            self.scan(self.exit, 1); self.scan(self.exit, 2)
            self.assertEqual(self.notify.call_count, 0)
            self.assertEqual(presence(self.s)['text'].split(' · ')[0], 'Tashqarida')

    def test_exit_after_leave_time_notifies_once(self):
        with mock.patch('tgbot.signals.leave_from', return_value=EARLY), mock.patch('access.services.leave_from', return_value=EARLY):
            self.scan(self.entry); self.notify.reset_mock()
            for i in range(4):
                self.scan(self.exit, i + 1)
            self.assertEqual(len(self.texts()), 1)
            self.assertIn('maktabdan chiqdi', self.texts()[0])
            self.assertTrue(presence(self.s)['text'].startswith('Uyga ketdi'))

    def test_command_sends_pending_break_exit_once_when_time_comes(self):
        with mock.patch('tgbot.signals.leave_from', return_value=LATE), mock.patch('access.services.leave_from', return_value=LATE):
            self.scan(self.entry); self.scan(self.exit, 1)
        self.notify.reset_mock()
        with mock.patch('tgbot.management.commands.send_leave_notices.leave_from', return_value=LATE):
            call_command('send_leave_notices', stdout=StringIO())
        self.assertEqual(self.notify.call_count, 0)                 # vaqt hali kelmagan
        with mock.patch('tgbot.management.commands.send_leave_notices.leave_from', return_value=EARLY):
            call_command('send_leave_notices', stdout=StringIO())
            call_command('send_leave_notices', stdout=StringIO())   # takror ishga tushsa ham bitta
        self.assertEqual(len(self.texts()), 1)
        self.assertEqual(PresenceNotice.objects.filter(kind='left').count(), 1)

    def test_command_skips_student_who_came_back(self):
        with mock.patch('tgbot.signals.leave_from', return_value=LATE):
            self.scan(self.entry); self.scan(self.exit, 1); self.scan(self.entry, 2)
        self.notify.reset_mock()
        with mock.patch('tgbot.management.commands.send_leave_notices.leave_from', return_value=EARLY):
            call_command('send_leave_notices', stdout=StringIO())
        self.assertEqual(self.notify.call_count, 0)


class LeaveSettingTests(TestCase):
    def test_default_and_change(self):
        cache.clear()
        self.assertEqual(leave_from(), time(16, 0))
        s = AccessSettings.get(); s.leave_notify_from = time(15, 30); s.save()
        self.assertEqual(leave_from(), time(15, 30))
