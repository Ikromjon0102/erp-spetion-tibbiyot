"""Ustoz sahifasi tashkilot bo'yicha (2026-11-23): faqat o'z tashkilotlari; maktabda — filialning barcha sinflari, markazda — faqat o'z guruhlari."""
import json
from datetime import time

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from academics.models import Group, Lesson, Subject, Teaching
from accounts.models import User
from journal.models import Attendance
from org.models import Branch, Organization


class TeacherOrgTests(TestCase):
    def setUp(self):
        call_command('create_orgs', verbosity=0)
        self.school = Organization.objects.get(name='Asosiy maktab')
        self.center = Organization.objects.get(name="O'quv markaz")
        self.med = Organization.objects.get(name='Tibbiyot maktabi')
        b_school = Branch.objects.get(organization=self.school)
        b_center = Branch.objects.get(organization=self.center, name='Filial 1')
        b_med = Branch.objects.filter(organization=self.med).first()
        mk = lambda u, **kw: User.objects.create_user(u, password='x', role='teacher', **kw)
        self.t = mk('t1', first_name='Nilufar', last_name='Karimova')
        self.other = mk('t2', first_name='Boshqa', last_name='Ustoz')
        subj = Subject.objects.create(name='Ingliz tili')

        def lesson(teacher, group, wd, h1, h2, period=1):
            te, _ = Teaching.objects.get_or_create(teacher=teacher, subject=subj, group=group)
            return Lesson.objects.create(teaching=te, weekday=wd, period=period, start=time(h1, 0), end=time(h2, 0))
        g7 = Group.objects.create(name='7-A', branch=b_school)
        g8 = Group.objects.create(name='8-B', branch=b_school)          # bu sinfda ustozimiz dars bermaydi
        a2 = Group.objects.create(name='Ingliz A2', branch=b_center)
        b1 = Group.objects.create(name='Ingliz B1', branch=b_center)    # markazda boshqa ustozning guruhi
        gm = Group.objects.create(name='9-Med', branch=b_med)           # boshqa tashkilot
        self.l_own_school = lesson(self.t, g7, 0, 9, 10)
        lesson(self.other, g8, 0, 10, 11)
        for wd in (0, 2, 4):
            lesson(self.t, a2, wd, 8, 9, period=1)
            lesson(self.t, a2, wd, 9, 10, period=2)                     # ketma-ket: 08:00–10:00 bo'lib birlashadi
        lesson(self.other, b1, 1, 13, 15)
        self.l_med = lesson(self.other, gm, 0, 9, 10)
        self.t.branches.set([b_school, b_center])

    def payload(self, user=None):
        self.client.force_login(user or self.t)
        r = self.client.get(reverse('journal:teacher_home'))
        self.assertEqual(r.status_code, 200)
        return json.loads(r.context['school'] and json.dumps(r.context['school']))

    def test_only_own_organizations(self):
        p = self.payload()
        self.assertEqual({o['label'] for o in p['orgs']}, {self.school.label, self.center.label})
        names = {l['class'] for l in p['lessons']}
        self.assertNotIn('9-Med', names)                                  # boshqa tashkilot darslari yuklanmaydi

    def test_school_shows_all_branch_classes_center_only_own_groups(self):
        p = self.payload()
        classes = {c['name'] for c in p['classes']}
        self.assertIn('7-A', classes)
        self.assertIn('8-B', classes)                                    # maktab: filialning barcha sinflari
        self.assertIn('Ingliz A2', classes)
        self.assertNotIn('Ingliz B1', classes)                           # markaz: faqat o'z guruhlari
        center = next(o for o in p['orgs'] if o['label'] == self.center.label)
        self.assertTrue(center['center'])
        self.assertTrue(all(l['org'] in {o['id'] for o in p['orgs']} for l in p['lessons']))

    def test_status_api_only_own_lessons(self):
        student_user = User.objects.create_user('s1', password='x', role='student')
        from accounts.models import Student
        st = Student.objects.create(user=student_user, group=self.l_med.teaching.group)
        Attendance.objects.create(student=st, lesson=self.l_med, date='2026-11-23', status='absent')
        self.client.force_login(self.t)
        marks = self.client.get('/ustoz/api/status/?date=2026-11-23').json()['marks']
        self.assertNotIn(str(self.l_med.pk), marks)

    def test_meals_for_org_with_menu(self):
        from django.utils import timezone
        from meals import services
        from meals.models import MealType
        org = self.school
        org.meals_enabled = True
        org.save()
        plan = services.get_plan(org)
        plan.weekdays = '0,1,2,3,4,5,6'
        plan.set_today(1)
        plan.save()
        services.set_entry(org, 1, MealType.objects.get(organization=org, name='Tushlik'), ['Osh', 'Non'])
        p = self.payload()
        week = p['menus'][str(org.pk)] if str(org.pk) in p['menus'] else p['menus'][org.pk]
        day = next(iter(week.values()))
        self.assertEqual(day[0]['type'], 'Tushlik')
        self.assertEqual([d['name'] for d in day[0]['dishes']], ['Osh', 'Non'])
        self.assertEqual(day[0]['start'], '12:30')
        self.assertIn(str(org.pk), {str(k) for k in p['themes']})                 # tanlanganda sahifa rangi uchun
        self.client.force_login(self.t)
        r = self.client.get('/ustoz/api/taomnoma/?date=' + timezone.localdate().isoformat()).json()
        self.assertTrue(r['menus'])

    def test_teacher_page_renders_theme_toggle_and_photo_slot(self):
        self.client.force_login(self.t)
        body = self.client.get(reverse('journal:teacher_home')).content.decode()
        self.assertIn('themebtn', body)
        self.assertIn('id="orgChips"', body)
