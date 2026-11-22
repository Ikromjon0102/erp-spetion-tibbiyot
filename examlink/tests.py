from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.child_data import child_context
from accounts.models import Student, User
from academics.models import Group
from org.models import default_branch
from panel.models import Position, StaffProfile

from . import client, matching
from .models import ExamLink

EXAM = [
    {'id': 1, 'full_name': "Aliyev Vali", 'username': 'aliyev.vali', 'class_name': '5-R', 'is_active': True},
    {'id': 2, 'full_name': "Xolmatov Jamshid", 'username': 'x.j', 'class_name': '5-R', 'is_active': True},
    {'id': 3, 'full_name': "Qodirov Sardor", 'username': 'q.s', 'class_name': '5-R', 'is_active': False},
]


class MatchingTests(TestCase):
    def test_spelling_variants_match(self):
        self.assertGreaterEqual(matching.similarity("Xolmatov Jamshid", "Holmatov Djamshid"), 0.85)
        self.assertGreaterEqual(matching.similarity("Aliyev Vali", "Vali Aliyev"), 0.99)
        self.assertGreaterEqual(matching.similarity("O'ktam G'ulomov", "Oktam Gulomov"), 0.99)
        self.assertLess(matching.similarity("Aliyev Vali", "Karimov Bobur"), 0.6)

    def test_propose_is_one_to_one_and_prefers_same_grade(self):
        exam = [{'id': 1, 'full_name': 'Aliyev Vali', 'class_name': '6-R'}, {'id': 2, 'full_name': 'Aliyev Vali', 'class_name': '5-R'}]
        out = matching.propose([(10, 'Aliyev Vali', '5-Sinf')], exam)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['exam']['id'], 2)
        self.assertTrue(out[0]['same_grade'])

    def test_grade_of(self):
        self.assertEqual(matching.grade_of('10-Sinf A'), 10)
        self.assertIsNone(matching.grade_of('Mayda guruh'))


@override_settings(EXAM_API_URL='http://exam.test', EXAM_API_KEY='k')
class ExamLinkFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.branch = default_branch()
        self.group = Group.objects.create(name='5-Sinf', branch=self.branch)
        u = User.objects.create_user('vali', password='x', role='student', first_name='Vali', last_name='Aliyev')
        self.kid = Student.objects.create(user=u, group=self.group)
        self.owner = User.objects.create_user('boss', password='x', role='staff', is_superuser=True, is_staff=True)
        self.client.force_login(self.owner)

    def test_confirm_creates_link_and_page_proposes(self):
        with mock.patch.object(client, 'fetch_students', return_value=EXAM):
            r = self.client.get(reverse('panel:examlink'))
            self.assertContains(r, 'Aliyev Vali')
            r = self.client.post(reverse('panel:examlink_confirm'), {'pair': [f'{self.kid.pk}:1', 'xx', '999:2']})
        self.assertEqual(r.status_code, 302)
        link = ExamLink.objects.get()
        self.assertEqual((link.student_id, link.exam_student_id), (self.kid.pk, 1))

    def test_same_exam_student_cannot_link_twice(self):
        ExamLink.objects.create(student=self.kid, exam_student_id=1)
        u = User.objects.create_user('v2', password='x', role='student')
        other = Student.objects.create(user=u, group=self.group)
        with mock.patch.object(client, 'fetch_students', return_value=EXAM):
            self.client.post(reverse('panel:examlink_confirm'), {'pair': [f'{other.pk}:1']})
        self.assertEqual(ExamLink.objects.count(), 1)

    def test_unlink(self):
        link = ExamLink.objects.create(student=self.kid, exam_student_id=1)
        self.client.post(reverse('panel:examlink_unlink', args=[link.pk]))
        self.assertFalse(ExamLink.objects.exists())

    def test_exam_down_does_not_break_child_page(self):
        ExamLink.objects.create(student=self.kid, exam_student_id=1)
        with mock.patch.object(client, '_get', side_effect=client.ExamUnavailable('x')):
            self.assertIsNone(child_context(self.kid, self.kid.user)['exam'])

    def test_dynamics_in_context_and_cached(self):
        ExamLink.objects.create(student=self.kid, exam_student_id=1)
        data = {'points': [{'x': 1}], 'overall': {'current_percent': 80}, 'subjects': [], 'quarters': [], 'school_year_start': 2026}
        with mock.patch.object(client, '_get', return_value=data) as g:
            self.assertEqual(child_context(self.kid, self.kid.user)['exam'], data)
            child_context(self.kid, self.kid.user)
        self.assertEqual(g.call_count, 1)

    def test_unlinked_has_no_exam(self):
        self.assertIsNone(child_context(self.kid, self.kid.user)['exam'])

    @override_settings(EXAM_API_URL='', EXAM_API_KEY='')
    def test_disabled(self):
        self.assertFalse(client.enabled())
        self.assertContains(self.client.get(reverse('panel:examlink')), 'sozlanmagan')
