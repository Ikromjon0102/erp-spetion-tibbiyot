import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import Student, User
from academics.models import Group

from .models import AccessEvent, Device
from .services import day_summaries


def payload(employee_no='1001', when='2026-11-14T08:12:30+05:00', **extra):
    ev = {'employeeNoString': employee_no, 'name': 'Madina', 'subEventType': 75, 'majorEventType': 5}
    ev.update(extra)
    return {'ipAddress': '192.168.1.50', 'dateTime': when, 'eventType': 'AccessControllerEvent',
            'AccessControllerEvent': ev}


class HikvisionPushTests(TestCase):
    def setUp(self):
        self.entry = Device.objects.create(name='Kirish-1', direction='in')
        self.exit = Device.objects.create(name='Chiqish-1', direction='out')
        user = User.objects.create(username='s1', first_name='Madina', last_name='Aliyeva', role='student')
        self.student = Student.objects.create(user=user, group=Group.objects.create(name='5-Sinf'), access_id='1001')

    def push(self, device, data, multipart=False, token=None):
        url = f'/api/access/hikvision/{token or device.token}/'
        if multipart:  # Hikvision shunday yuboradi: JSON qism + rasm
            return self.client.post(url, {'event_log': json.dumps(data), 'Picture': ''})
        return self.client.post(url, json.dumps(data), content_type='application/json')

    def test_json_body_creates_event_with_direction_from_device(self):
        r = self.push(self.entry, payload())
        self.assertEqual(r.status_code, 200)
        e = AccessEvent.objects.get()
        self.assertEqual((e.student, e.direction, e.sub_type), (self.student, 'in', 75))
        self.assertEqual(timezone.localtime(e.occurred_at).strftime('%H:%M'), '08:12')

    def test_old_events_ignored_before_cutoff(self):
        with self.settings(ACCESS_IGNORE_EVENTS_BEFORE=timezone.make_aware(__import__('datetime').datetime(2026, 11, 16))):
            r = self.push(self.entry, payload(when='2026-08-30T11:41:13+00:00'))
            self.assertEqual(r.json().get('ignored'), 'old')
            self.push(self.entry, payload(when='2026-11-16T09:00:00+05:00'))
        self.assertEqual(AccessEvent.objects.count(), 1)

    def test_multipart_event_log(self):
        self.push(self.exit, payload(when='2026-11-14T15:40:00+05:00'), multipart=True)
        self.assertEqual(AccessEvent.objects.get().direction, 'out')

    def test_duplicate_is_ignored(self):
        self.push(self.entry, payload())
        self.push(self.entry, payload())
        self.assertEqual(AccessEvent.objects.count(), 1)

    def test_wrong_token_rejected(self):
        self.assertEqual(self.push(self.entry, payload(), token='nope').status_code, 404)
        self.assertEqual(AccessEvent.objects.count(), 0)

    def test_inactive_device_rejected(self):
        self.entry.is_active = False
        self.entry.save()
        self.assertEqual(self.push(self.entry, payload()).status_code, 404)

    def test_heartbeat_only_updates_last_seen(self):
        r = self.push(self.entry, {'eventType': 'heartBeat', 'dateTime': '2026-11-14T08:00:00+05:00'})
        self.assertTrue(r.json()['ignored'])
        self.entry.refresh_from_db()
        self.assertIsNotNone(self.entry.last_seen)
        self.assertEqual(AccessEvent.objects.count(), 0)

    def test_garbage_body_is_400(self):
        r = self.client.post(f'/api/access/hikvision/{self.entry.token}/', 'xx{not json}', content_type='text/plain')
        self.assertEqual(r.status_code, 400)

    def test_unknown_id_is_kept_and_linked_later(self):
        self.push(self.entry, payload(employee_no='777'))
        e = AccessEvent.objects.get()
        self.assertIsNone(e.student)
        self.student.access_id = '777'
        self.student.save()
        e.refresh_from_db()
        self.assertEqual(e.student, self.student)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(f'/api/access/hikvision/{self.entry.token}/').status_code, 405)

    def test_day_summary_first_in_last_out(self):
        today = timezone.localtime().replace(hour=8, minute=0, second=0, microsecond=0)
        for dev, delta in [(self.entry, 5), (self.entry, 1), (self.exit, 400), (self.exit, 420)]:
            AccessEvent.objects.create(device=dev, student=self.student, employee_no='1001', direction=dev.direction,
                                       occurred_at=today + timedelta(minutes=delta))
        (row,) = day_summaries(self.student)
        self.assertEqual(row['arrived'].strftime('%H:%M'), '08:01')  # birinchi kirish
        self.assertEqual(row['left'].strftime('%H:%M'), '15:00')     # oxirgi chiqish


class RepeatedScanTests(TestCase):
    """Tanaffusda o'quvchilar kirish/chiqish terminallarini ketma-ket skan qiladi: oxirgi skan hal qiladi."""

    def setUp(self):
        self.entry = Device.objects.create(name='Kirish-1', direction='in')
        self.exit = Device.objects.create(name='Chiqish-1', direction='out')
        user = User.objects.create(username='s2', first_name='Qobil', last_name='Yunus', role='student')
        self.student = Student.objects.create(user=user, group=Group.objects.create(name='7-Sinf'), access_id='1002')
        self.day = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)

    def scan(self, device, minute):
        AccessEvent.objects.create(device=device, employee_no='1002', student=self.student, direction=device.direction,
                                   occurred_at=self.day + timedelta(hours=9, minutes=minute))

    def row(self):
        return day_summaries(self.student, days=1)[0]

    def test_last_scan_in_means_still_at_school(self):
        for dev, m in ((self.exit, 0), (self.entry, 1), (self.entry, 2), (self.exit, 3), (self.entry, 4)):
            self.scan(dev, m)
        r = self.row()
        self.assertEqual(r['arrived'].minute, 1)
        self.assertIsNone(r['left'])

    def test_last_scan_out_means_left(self):
        for dev, m in ((self.entry, 0), (self.exit, 1), (self.entry, 2), (self.exit, 5)):
            self.scan(dev, m)
        self.assertEqual(self.row()['left'].minute, 5)


class HikvisionClientListTests(TestCase):
    def make_client(self):
        from .hikvision import Client
        return Client(Device(name='T', direction='in', host='1.2.3.4', username='admin', password='x'))

    @staticmethod
    def resp(body, status=200):
        from unittest import mock
        r = mock.Mock(status_code=status, text=json.dumps(body))
        r.json.return_value = body
        return r

    def test_list_users_pages_until_done(self):
        from unittest import mock
        pages = [
            self.resp({'UserInfoSearch': {'responseStatusStrg': 'MORE', 'UserInfo': [{'employeeNo': '9001', 'name': 'A'}, {'employeeNo': '9002', 'name': 'B'}]}}),
            self.resp({'UserInfoSearch': {'responseStatusStrg': 'OK', 'UserInfo': [{'employeeNo': '9003', 'name': 'C'}]}}),
        ]
        c = self.make_client()
        with mock.patch.object(c, '_req', side_effect=pages) as req:
            self.assertEqual(c.list_users(), [('9001', 'A'), ('9002', 'B'), ('9003', 'C')])
        self.assertEqual(json.loads(req.call_args_list[1].kwargs['data'])['UserInfoSearchCond']['searchResultPosition'], 2)

    def test_user_count(self):
        from unittest import mock
        c = self.make_client()
        with mock.patch.object(c, '_req', return_value=self.resp({'UserInfoCount': {'userNumber': 91, 'bindFaceUserNumber': 90}})):
            self.assertEqual(c.user_count(), (91, 90))


class PushFacesToolTests(TestCase):
    def test_arp_parsing_windows_and_linux_and_mac_normalising(self):
        import importlib.util, pathlib
        from unittest import mock
        spec = importlib.util.spec_from_file_location('push_faces', pathlib.Path(__file__).resolve().parent.parent / 'tools' / 'push_faces.py')
        tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)
        win = '  192.168.68.108       88-de-39-8e-19-83     dynamic   \n'
        nix = '? (192.168.68.109) at 88:DE:39:8E:19:50 [ether] on eth0\n'
        with mock.patch.object(tool.subprocess, 'run', return_value=mock.Mock(stdout=win + nix)):
            table = tool.arp_table()
        self.assertEqual(table['88:de:39:8e:19:83'], '192.168.68.108')
        self.assertEqual(table['88:de:39:8e:19:50'], '192.168.68.109')


class DeviceBranchPeopleTests(TestCase):
    """Qurilmaga faqat o'z filialining odamlari yuboriladi (bog'cha terminaliga markaz o'quvchilari tushmasin)."""

    def test_eligible_users_filtered_by_device_branch(self):
        from django.core.management import call_command
        from academics.models import Group
        from accounts.models import Student, User
        from org.models import Branch, Organization
        from .models import Device
        from .sync import eligible_users
        call_command('create_orgs', verbosity=0)
        kg = Branch.objects.get(organization=Organization.objects.get(name="Bog'cha"))
        c1 = Branch.objects.get(organization=Organization.objects.get(name="O'quv markaz"))

        def kid(name, br, aid):
            u = User.objects.create_user(name, password='x', role='student', photo='faces/x.jpg')
            Student.objects.create(user=u, branch=br, group=Group.objects.create(name=f'g{aid}', branch=br), access_id=str(aid))
            return u
        a, b = kid('kgkid', kg, 101), kid('ckid', c1, 102)
        t = User.objects.create_user('tch', password='x', role='teacher', photo='faces/t.jpg', access_id='7001')
        t.branches.set([kg])
        dev_kg = Device.objects.create(name='KG kirish', direction='in', branch=kg)
        names = {u.username for u in eligible_users(dev_kg)}
        self.assertEqual(names, {'kgkid', 'tch'})
        self.assertNotIn(b.username, names)
        self.assertEqual({u.username for u in eligible_users()}, {'kgkid', 'ckid', 'tch'})
