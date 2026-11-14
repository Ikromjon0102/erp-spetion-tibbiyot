from django.core.cache import cache
from django.test import TestCase, override_settings

from academics.models import Group, Subject, Teaching
from accounts.models import Student, User
from notices.models import Announcement


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TeacherNewsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(username='t1', password='x', role='teacher', first_name='Diyora')
        self.g5, self.g6 = Group.objects.create(name='5-Sinf'), Group.objects.create(name='6-Sinf')
        Teaching.objects.create(teacher=self.teacher, subject=Subject.objects.create(name='Ona tili'), group=self.g5)
        mk = lambda title, audience, group=None: Announcement.objects.create(title=title, body='matn', audience=audience, group=group)
        mk('Hamma uchun', 'all')
        mk('Ustozlarga', 'teachers')
        mk('Ota-onalarga', 'parents')
        mk('Mening sinfimga', 'teachers', self.g5)
        mk('Boshqa sinfga', 'teachers', self.g6)
        self.client.login(username='t1', password='x')

    def titles(self):
        return {a['title'] for a in self.client.get('/ustoz/api/elonlar/').json()['items']}

    def test_requires_login(self):
        self.client.logout()
        self.assertEqual(self.client.get('/ustoz/api/elonlar/').status_code, 401)

    def test_teacher_sees_only_relevant_announcements(self):
        self.assertEqual(self.titles(), {'Hamma uchun', 'Ustozlarga', 'Mening sinfimga'})
        item = next(a for a in self.client.get('/ustoz/api/elonlar/').json()['items'] if a['title'] == 'Mening sinfimga')
        self.assertEqual((item['group'], item['audience']), ('5-Sinf', 'Ustozlar'))

    def test_teacher_who_is_also_parent_sees_parent_announcements_too(self):
        kid = Student.objects.create(user=User.objects.create_user(username='k', password='x', role='student'), group=self.g6)
        kid.parents.add(self.teacher)
        self.assertEqual(self.titles(), {'Hamma uchun', 'Ustozlarga', 'Mening sinfimga', 'Ota-onalarga', 'Boshqa sinfga'})
