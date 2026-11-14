import json
from datetime import datetime, time
from unittest import mock

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from academics.models import Group, Lesson, Subject, Teaching
from accounts.models import Student, User

from .models import Attendance, Grade

DAY = datetime(2026, 11, 16)  # dushanba


def at(hour, minute=0, day=DAY):
    return timezone.make_aware(day.replace(hour=hour, minute=minute))


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class TeacherApiTests(TestCase):
    def setUp(self):
        cache.clear()
        mk = lambda u, role, **kw: User.objects.create_user(username=u, password='x', role=role, **kw)
        self.teacher, self.other = mk('t1', 'teacher', first_name='Diyora'), mk('t2', 'teacher', first_name='Azizbek')
        self.parent = mk('p1', 'parent')
        group = Group.objects.create(name='5-Sinf')
        teaching = Teaching.objects.create(teacher=self.teacher, subject=Subject.objects.create(name='Ona tili'), group=group)
        self.lesson = Lesson.objects.create(teaching=teaching, weekday=0, period=1, start=time(8, 30), end=time(9, 15))
        self.students = [Student.objects.create(user=mk(f's{i}', 'student', first_name=f'Ism{i}', last_name='Fam'), group=group)
                         for i in range(3)]
        self.client.login(username='t1', password='x')

    # --- yordamchilar
    def get(self, url, now=None):
        with mock.patch('journal.views.timezone.localtime', return_value=now or at(9)):
            return self.client.get(url)

    def post(self, url, data, now=None):
        now = now or at(9)
        with mock.patch('journal.views.timezone.localtime', return_value=now), \
                mock.patch('journal.views.timezone.localdate', return_value=now.date()):
            return self.client.post(url, json.dumps(data), content_type='application/json')

    def att_url(self, suffix=''):
        return f'/ustoz/api/dars/{self.lesson.id}/{suffix}'

    def save_att(self, now, rows, day=None):
        return self.post(self.att_url('saqlash/'), {'date': str(day or now.date()), 'rows': rows}, now=now)

    # --- sahifa va kirish
    def test_page_requires_login_and_teacher_role(self):
        self.client.logout()
        r = self.client.get('/ustoz/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r['Location'])
        self.client.login(username='p1', password='x')
        self.assertEqual(self.client.get('/ustoz/').status_code, 403)

    def test_page_for_teacher_has_schedule_but_no_student_data(self):
        r = self.client.get('/ustoz/')
        self.assertContains(r, '"Ona tili"')
        self.assertContains(r, '"name": "Diyora"')
        self.assertNotContains(r, 'Ism0')

    def test_api_requires_logged_in_teacher(self):
        for url in (self.att_url(), f'/ustoz/api/baho/{self.lesson.id}/', '/ustoz/api/elonlar/', '/ustoz/api/status/'):
            self.client.logout()
            self.assertEqual(self.client.get(url).status_code, 401, url)
            self.client.login(username='p1', password='x')
            self.assertEqual(self.client.get(url).status_code, 401, url)  # ota-ona ustoz API'sidan foydalana olmaydi

    def test_other_teacher_cannot_open_lesson(self):
        self.client.login(username='t2', password='x')
        self.assertEqual(self.get(self.att_url()).status_code, 404)
        self.assertEqual(self.get(f'/ustoz/api/baho/{self.lesson.id}/').status_code, 404)

    def test_status_counts_absent(self):
        Attendance.objects.create(student=self.students[0], lesson=self.lesson, date=DAY.date(), status='absent')
        Attendance.objects.create(student=self.students[1], lesson=self.lesson, date=DAY.date(), status='present')
        r = self.client.get(f'/ustoz/api/status/?date={DAY.date()}')
        self.assertEqual(r.json()['marks'], {str(self.lesson.id): {'absent': 1}})

    # --- davomat
    def test_lists_students_default_present(self):
        d = self.get(self.att_url()).json()
        self.assertEqual(len(d['students']), 3)
        self.assertTrue(d['editable'])
        self.assertTrue(all(s['s'] == 'present' for s in d['students']))

    def test_cannot_edit_before_lesson_starts_or_other_day(self):
        self.assertFalse(self.get(self.att_url(), now=at(8, 0)).json()['editable'])
        row = [{'id': self.students[0].id, 's': 'absent'}]
        self.assertEqual(self.save_att(at(8, 0), row).json(), {'ok': False, 'err': 'time'})
        self.assertEqual(self.save_att(at(10), row, day=DAY.date().replace(day=13)).json()['err'], 'time')
        self.assertEqual(Attendance.objects.count(), 0)

    def test_save_reload_resave(self):
        s0, s1, s2 = (s.id for s in self.students)
        r = self.save_att(at(9), [{'id': s0, 's': 'absent'}, {'id': s1, 's': 'late'}, {'id': s2, 's': 'present'}])
        self.assertEqual(r.json(), {'ok': True, 'absent': 2})
        marks = {s['id']: s['s'] for s in self.get(self.att_url()).json()['students']}
        self.assertEqual(marks, {s0: 'absent', s1: 'late', s2: 'present'})
        self.save_att(at(9, 30), [{'id': s0, 's': 'excused'}])
        self.assertEqual(Attendance.objects.count(), 3)
        self.assertEqual(Attendance.objects.get(student_id=s0).status, 'excused')
        self.assertEqual(Attendance.objects.get(student_id=s0).marked_by, self.teacher)

    def test_invalid_status_and_foreign_student_rejected(self):
        self.assertEqual(self.save_att(at(9), [{'id': self.students[0].id, 's': 'hack'}]).status_code, 400)
        outsider = Student.objects.create(user=User.objects.create_user(username='z', password='x', role='student'),
                                          group=Group.objects.create(name='6-Sinf'))
        self.save_att(at(9), [{'id': outsider.id, 's': 'absent'}])
        self.assertEqual(Attendance.objects.count(), 0)

    # --- baho
    def grade_url(self, suffix=''):
        return f'/ustoz/api/baho/{self.lesson.id}/{suffix}'

    def give(self, student, score, lesson=None, now=None, **extra):
        lesson = lesson or self.lesson
        return self.post(f'/ustoz/api/baho/{lesson.id}/saqlash/',
                         {'date': str(DAY.date()), 'student': student.id, 'score': score, **extra}, now=now).json()

    def test_grade_save_links_to_lesson_and_shows_in_given(self):
        r = self.give(self.students[1], 5, kind='exam', comment="Zo'r")
        self.assertTrue(r['ok'] and r['created'])
        self.assertIsNone(r['previous'])
        g = Grade.objects.get()
        self.assertEqual((g.score, g.kind, g.created_by, g.teaching, g.lesson), (5, 'exam', self.teacher, self.lesson.teaching, self.lesson))
        data = self.get(self.grade_url() + f'?date={DAY.date()}').json()
        self.assertEqual(data['given'], {str(self.students[1].id): {'id': g.id, 'score': 5}})
        self.assertEqual(self.get(self.grade_url() + '?date=2026-11-10').json()['given'], {})  # boshqa kun

    def test_one_grade_per_lesson_second_save_replaces_it(self):
        first = self.give(self.students[0], 5)
        second = self.give(self.students[0], 3, kind='test')
        self.assertFalse(second['created'])
        self.assertEqual(second['previous'], 5)
        self.assertEqual(second['grade']['id'], first['grade']['id'])        # yangi yozuv emas, mavjudi almashdi
        g = Grade.objects.get()                                              # baribir bitta baho
        self.assertEqual((g.score, g.kind), (3, 'test'))
        given = self.get(self.grade_url() + f'?date={DAY.date()}').json()['given']
        self.assertEqual(given[str(self.students[0].id)]['score'], 3)

    def test_other_students_and_other_lessons_get_their_own_grade(self):
        lesson2 = Lesson.objects.create(teaching=self.lesson.teaching, weekday=0, period=2, start=time(9, 20), end=time(10, 5))
        self.give(self.students[0], 5)
        self.give(self.students[1], 4)                      # boshqa o'quvchi — alohida baho
        self.give(self.students[0], 2, lesson=lesson2, now=at(9, 30))  # xuddi shu kun va fan, lekin 2-soat — alohida baho
        self.assertEqual(Grade.objects.count(), 3)
        self.assertEqual(Grade.objects.filter(student=self.students[0]).count(), 2)

    def test_database_refuses_two_grades_for_same_student_lesson_day(self):
        Grade.objects.create(student=self.students[0], teaching=self.lesson.teaching, lesson=self.lesson, score=5, date=DAY.date())
        with self.assertRaises(IntegrityError), transaction.atomic():
            Grade.objects.create(student=self.students[0], teaching=self.lesson.teaching, lesson=self.lesson, score=4, date=DAY.date())

    def test_legacy_grades_without_lesson_do_not_block_or_show(self):
        Grade.objects.create(student=self.students[0], teaching=self.lesson.teaching, score=2, date=DAY.date())
        Grade.objects.create(student=self.students[0], teaching=self.lesson.teaching, score=3, date=DAY.date())  # eskida ko'p bo'lgan
        self.assertEqual(self.get(self.grade_url() + f'?date={DAY.date()}').json()['given'], {})
        self.assertTrue(self.give(self.students[0], 5)['created'])

    def test_undo_deletes_new_grade_and_restores_replaced_one(self):
        r = self.give(self.students[0], 5)
        self.assertTrue(self.post(self.grade_url('ochirish/'), {'id': r['grade']['id'], 'restore': None}).json()['ok'])
        self.assertFalse(Grade.objects.exists())                                   # yangi baho bekor qilindi -> o'chdi

        r1 = self.give(self.students[0], 5)
        r2 = self.give(self.students[0], 2)                                        # 5 -> 2 almashtirildi
        self.assertTrue(self.post(self.grade_url('ochirish/'), {'id': r2['grade']['id'], 'restore': r2['previous']}).json()['ok'])
        g = Grade.objects.get()
        self.assertEqual((g.id, g.score), (r1['grade']['id'], 5))                  # oldingi baho qaytdi

    def test_undo_rejects_bad_restore_and_foreign_grades(self):
        mine = Grade.objects.create(student=self.students[0], teaching=self.lesson.teaching, lesson=self.lesson,
                                    score=3, date=DAY.date(), created_by=self.teacher)
        foreign = Grade.objects.create(student=self.students[1], teaching=self.lesson.teaching, lesson=self.lesson,
                                       score=4, date=DAY.date(), created_by=self.other)
        self.assertEqual(self.post(self.grade_url('ochirish/'), {'id': mine.id, 'restore': 9}).json()['err'], 'bad_score')
        self.assertFalse(self.post(self.grade_url('ochirish/'), {'id': foreign.id, 'restore': None}).json()['ok'])
        self.assertTrue(Grade.objects.filter(pk=foreign.id).exists())
        self.assertEqual(self.post(self.grade_url('ochirish/'), {'id': 'x'}).status_code, 400)

    def test_other_teacher_cannot_undo(self):
        g = Grade.objects.create(student=self.students[0], teaching=self.lesson.teaching, lesson=self.lesson,
                                 score=3, date=DAY.date(), created_by=self.teacher)
        self.client.login(username='t2', password='x')
        self.assertEqual(self.post(self.grade_url('ochirish/'), {'id': g.id, 'restore': None}).status_code, 404)
        self.assertTrue(Grade.objects.filter(pk=g.id).exists())

    def test_grade_validation(self):
        base = {'date': str(DAY.date()), 'student': self.students[0].id, 'score': 4}
        self.assertEqual(self.post(self.grade_url('saqlash/'), {**base, 'score': 6}).json()['err'], 'bad_score')
        self.assertEqual(self.post(self.grade_url('saqlash/'), {**base, 'date': '2026-11-20'}).json()['err'], 'time')
        self.assertEqual(self.post(self.grade_url('saqlash/'), {**base, 'score': 'x'}).status_code, 400)
        outsider = Student.objects.create(user=User.objects.create_user(username='z', password='x', role='student'),
                                          group=Group.objects.create(name='6-Sinf'))
        self.assertEqual(self.post(self.grade_url('saqlash/'), {**base, 'student': outsider.id}).status_code, 404)
        self.assertEqual(Grade.objects.count(), 0)

    # --- baho ham davomat kabi faqat dars kuni va dars boshlangach
    def test_grades_follow_the_same_time_rule_as_attendance(self):
        row = {'date': str(DAY.date()), 'student': self.students[0].id, 'score': 5}
        # dars boshlanmagan (8:00 < 8:30): na davomat, na baho
        self.assertFalse(self.get(self.att_url(), now=at(8, 0)).json()['editable'])
        self.assertFalse(self.get(self.grade_url() + f'?date={DAY.date()}', now=at(8, 0)).json()['editable'])
        self.assertEqual(self.post(self.grade_url('saqlash/'), row, now=at(8, 0)).json(), {'ok': False, 'err': 'time'})
        # dars boshlangach ikkalasi mumkin
        self.assertTrue(self.get(self.grade_url() + f'?date={DAY.date()}', now=at(9)).json()['editable'])
        self.assertTrue(self.post(self.grade_url('saqlash/'), row, now=at(9)).json()['ok'])

    def test_cannot_grade_other_days_past_or_future(self):
        for day in ('2026-11-09', '2026-11-23'):   # o'tgan hafta va keyingi hafta
            r = self.post(self.grade_url('saqlash/'), {'date': day, 'student': self.students[0].id, 'score': 5}, now=at(9))
            self.assertEqual(r.json(), {'ok': False, 'err': 'time'}, day)
            self.assertFalse(self.get(self.grade_url() + f'?date={day}', now=at(9)).json()['editable'], day)
        self.assertEqual(Grade.objects.count(), 0)

    def test_cannot_undo_grade_of_another_day(self):
        old = Grade.objects.create(student=self.students[0], teaching=self.lesson.teaching, lesson=self.lesson,
                                   score=3, date=DAY.date().replace(day=9), created_by=self.teacher)
        r = self.post(self.grade_url('ochirish/'), {'id': old.id, 'restore': None}, now=at(9))
        self.assertEqual(r.json(), {'ok': False, 'err': 'time'})
        self.assertTrue(Grade.objects.filter(pk=old.id).exists())
