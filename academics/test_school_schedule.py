import datetime
import tempfile
from pathlib import Path

import openpyxl
from django.test import TestCase

from accounts.models import User
from org.models import Branch, Organization

from .models import Group, Lesson
from .school_schedule_import import import_schedule, parse_cell, read_schedule


class SchoolScheduleTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(organization=Organization.objects.create(name='Asosiy maktab'), name='Asosiy')
        for n in ('1-Red', '8-9-Huquq'):
            Group.objects.create(name=n, branch=self.branch)
        self.yusupov = User.objects.create(username='t1', last_name='Yusupov', first_name='Abdulvosid', role=User.Role.TEACHER)
        self.mina = User.objects.create(username='t2', last_name='Minadiyeva', first_name='Alime', role=User.Role.TEACHER)
        for u in (self.yusupov, self.mina):
            u.branches.set([self.branch])
        self.path = Path(tempfile.mkdtemp()) / 's.xlsx'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(['День недели', 'Урок', 'Время', '1-A\n(Рус.)', '8-A\n(Узб. / Право)'])
        ws.append(['Понедельник', 1, '08:30–09:15', 'Урок Будущего\n(Кл. руководитель)', 'Урок Будущего (Воспитание)\n(Вакант)'])
        ws.append(['Понедельник', 2, '09:20–10:05', 'Математика [ПАРА]\n(Минадиева Алиме)', 'Английский язык [ПАРА]\n(Юсупов Абдулбосит)'])
        ws.append(['Понедельник', 4, '11:00–11:45', 'ОБЕД', 'Восптание (Вакант)'])
        ws.append([None, None, None, None, None])
        wb.save(self.path)

    def test_parse_cell(self):
        self.assertEqual(parse_cell('Математика [ПАРА]\n(Минадиева Алиме)'), ('Matematika', 'Минадиева Алиме'))
        self.assertEqual(parse_cell('Воспитание ( Вакант)'), ('Tarbiya', None))
        self.assertIsNone(parse_cell('ОБЕД'))
        with self.assertRaises(ValueError):
            parse_cell('Астрономия\n(Кто-то)')

    def test_import_and_reimport(self):
        rows = read_schedule(self.path)
        self.assertEqual(len(rows), 5)                                      # tushlik dars emas
        r = import_schedule(rows, self.branch, class_teachers={'1-Red': 'Minadiyeva Alime Ibazerovna'})
        self.assertEqual(r['lessons'], 5)
        self.assertEqual(r['no_teacher'], {})
        eng = Lesson.objects.get(teaching__subject__name='Ingliz tili')
        self.assertEqual((eng.teaching.teacher, eng.teaching.group.name, eng.weekday, eng.period, eng.start),
                         (self.yusupov, '8-9-Huquq', 0, 2, datetime.time(9, 20)))
        self.assertEqual(Lesson.objects.get(teaching__subject__name='Kelajak darsi', teaching__group__name='1-Red').teaching.teacher, self.mina)
        self.assertIsNone(Lesson.objects.filter(teaching__subject__name='Tarbiya').first().teaching.teacher)
        again = import_schedule(read_schedule(self.path), self.branch, class_teachers={'1-Red': 'Minadiyeva Alime'})
        self.assertEqual(again['deactivated'], 5)
        self.assertEqual(Lesson.objects.filter(active=True).count(), 5)
