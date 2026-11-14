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
