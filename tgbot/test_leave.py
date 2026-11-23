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
        self.assertIn('da keldi', self.texts()[0])

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
            self.assertIn('da chiqdi', self.texts()[0])
            self.assertTrue(presence(self.s)['text'].startswith('Uyga ketdi'))

    def test_command_sends_pending_break_exit_once_when_time_comes(self):
        with mock.patch('tgbot.signals.leave_from', return_value=LATE), mock.patch('access.services.leave_from', return_value=LATE):
            self.scan(self.entry); self.scan(self.exit, 1)
        self.notify.reset_mock()
        with mock.patch('tgbot.management.commands.send_leave_notices.leave_from', return_value=LATE), mock.patch('tgbot.management.commands.send_leave_notices.earliest_leave_from', return_value=LATE):
            call_command('send_leave_notices', stdout=StringIO())
        self.assertEqual(self.notify.call_count, 0)                 # vaqt hali kelmagan
        with mock.patch('tgbot.management.commands.send_leave_notices.leave_from', return_value=EARLY), mock.patch('tgbot.management.commands.send_leave_notices.earliest_leave_from', return_value=EARLY):
            call_command('send_leave_notices', stdout=StringIO())
            call_command('send_leave_notices', stdout=StringIO())   # takror ishga tushsa ham bitta
        self.assertEqual(len(self.texts()), 1)
        self.assertEqual(PresenceNotice.objects.filter(kind='left').count(), 1)

    def test_command_skips_student_who_came_back(self):
        with mock.patch('tgbot.signals.leave_from', return_value=LATE):
            self.scan(self.entry); self.scan(self.exit, 1); self.scan(self.entry, 2)
        self.notify.reset_mock()
        with mock.patch('tgbot.management.commands.send_leave_notices.leave_from', return_value=EARLY), mock.patch('tgbot.management.commands.send_leave_notices.earliest_leave_from', return_value=EARLY):
            call_command('send_leave_notices', stdout=StringIO())
        self.assertEqual(self.notify.call_count, 0)


class LeaveSettingTests(TestCase):
    def test_default_and_change(self):
        cache.clear()
        self.assertEqual(leave_from(), time(16, 0))
        s = AccessSettings.get(); s.leave_notify_from = time(15, 30); s.save()
        self.assertEqual(leave_from(), time(15, 30))


class OrgLeaveTimeTests(TestCase):
    """Chiqish xabari vaqti tashkilot bo'yicha: tashkilotda o'z vaqti bo'lsa — shu, bo'lmasa umumiy."""

    def setUp(self):
        cache.clear()
        from org.models import default_branch
        self.org = default_branch().organization
        self.exit = Device.objects.create(name='C', direction='out')
        u = User.objects.create(username='k2', first_name='Gul', last_name='Karimova', role='student')
        self.s = Student.objects.create(user=u, group=Group.objects.create(name='Quyosh'), access_id='2')
        self.s.parents.add(User.objects.create(username='p2', role='parent'))
        p = mock.patch('tgbot.signals.notify'); self.notify = p.start(); self.addCleanup(p.stop)

    def test_org_override_and_fallback(self):
        s = AccessSettings.get(); s.leave_notify_from = time(16, 0); s.save()
        self.assertEqual(leave_from(self.org), time(16, 0))           # o'z vaqti yo'q — umumiy
        self.org.leave_notify_from = time(12, 30); self.org.save()
        self.assertEqual(leave_from(self.org), time(12, 30))
        self.assertEqual(leave_from(), time(16, 0))                    # umumiy o'zgarmadi

    def test_exit_after_org_time_is_left_even_before_global_time(self):
        s = AccessSettings.get(); s.leave_notify_from = LATE; s.save()     # umumiy: hali vaqt emas
        self.org.leave_notify_from = EARLY; self.org.save()                # bu tashkilotda: vaqt keldi
        AccessEvent.objects.create(device=self.exit, employee_no='2', student=self.s, direction='out', occurred_at=timezone.now())
        self.assertEqual(len(self.notify.call_args_list), 1)
        self.assertIn('da chiqdi', self.notify.call_args_list[0].args[1])

    def test_panel_saves_time_for_selected_org(self):
        from django.urls import reverse
        boss = User.objects.create_user('boss', password='x', role='staff', is_superuser=True, is_staff=True)
        self.client.force_login(boss)
        self.client.get(reverse('panel:set_scope'), {'s': f'org-{self.org.pk}', 'next': '/panel/'})
        self.client.post(reverse('panel:access_settings'), {'leave_from': '13:15'})
        self.org.refresh_from_db()
        self.assertEqual(self.org.leave_notify_from, time(13, 15))
        self.assertEqual(AccessSettings.get().leave_notify_from, time(16, 0))   # umumiy tegilmadi
