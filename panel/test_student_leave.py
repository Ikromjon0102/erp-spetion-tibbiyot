from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from academics.models import Group
from accounts.models import Student, User
from billing.reports import real_students

from .tests import make_staff

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


@FAST
class StudentLeaveTests(TestCase):
    def setUp(self):
        cache.clear()
        make_staff('dir', 'Direktor')
        self.client.login(username='dir', password='x')
        self.g = Group.objects.create(name='6-Sinf', year=2026)
        u = User.objects.create(username='kid', first_name='Vali', last_name='Aliyev', role='student')
        self.s = Student.objects.create(user=u, group=self.g)
        self.parent = User.objects.create(username='par', role='parent')
        self.s.parents.add(self.parent)
        self.patch = mock.patch('panel.views_students.sync_in_background')
        self.sync = self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_leave_hides_student_keeps_data_and_syncs(self):
        r = self.client.post(f'/panel/oquvchilar/{self.s.pk}/chiqarish/')
        self.assertEqual(r.status_code, 302)
        self.s.refresh_from_db(); self.s.user.refresh_from_db()
        self.assertTrue(self.s.has_left)
        self.assertFalse(self.s.user.is_active)
        self.assertIsNone(self.s.group_id)
        self.assertEqual(self.s.left_group_name, '6-Sinf')
        self.assertNotIn(self.s, real_students())
        self.assertEqual(self.client.get('/panel/oquvchilar/').context['rows'].__len__(), 0)
        self.assertEqual(len(self.client.get('/panel/oquvchilar/?holat=chiqqan').context['rows']), 1)
        self.assertEqual(self.parent.children.filter(user__is_active=True).count(), 0)
        self.sync.assert_called()

    def test_restore_returns_to_class(self):
        self.s.leave()
        self.client.post(f'/panel/oquvchilar/{self.s.pk}/qaytarish/')
        self.s.refresh_from_db(); self.s.user.refresh_from_db()
        self.assertFalse(self.s.has_left)
        self.assertTrue(self.s.user.is_active)
        self.assertEqual(self.s.group, self.g)

    def test_delete_requires_leave_first_then_removes_only_student(self):
        self.client.post(f'/panel/oquvchilar/{self.s.pk}/ochirish/')
        self.assertTrue(Student.objects.filter(pk=self.s.pk).exists())          # chiqarilmagan: o'chirilmaydi
        self.s.leave()
        self.client.post(f'/panel/oquvchilar/{self.s.pk}/ochirish/')
        self.assertFalse(Student.objects.filter(pk=self.s.pk).exists())
        self.assertFalse(User.objects.filter(username='kid').exists())
        self.assertTrue(User.objects.filter(username='par').exists())           # ota-ona hisobi qoladi

    def test_detail_page_of_left_student_shows_actions(self):
        self.s.leave()
        html = self.client.get(f'/panel/oquvchilar/{self.s.pk}/').content.decode()
        self.assertIn('Butunlay o', html)
        self.assertIn('Qaytarish', html)


@FAST
class LeaveTimeSettingTests(TestCase):
    def setUp(self):
        cache.clear()
        make_staff('dir', 'Direktor')
        self.client.login(username='dir', password='x')

    def test_change_from_panel(self):
        from datetime import time
        from access.models import leave_from
        self.assertContains(self.client.get('/panel/qurilmalar/'), 'name="leave_from"')
        self.client.post('/panel/qurilmalar/chiqish-vaqti/', {'leave_from': '15:30'})
        self.assertEqual(leave_from(), time(15, 30))
        self.client.post('/panel/qurilmalar/chiqish-vaqti/', {'leave_from': 'xato'})
        self.assertEqual(leave_from(), time(15, 30))
