import datetime
import tempfile
from pathlib import Path

import openpyxl
from django.test import TestCase

from accounts.models import Student, User
from accounts.pay_sheet_import import class_name, import_pay_sheets, import_staff_sheet, read_pay_sheets, read_staff_sheet
from org.models import Branch, Organization
from panel.models import Position


def _pay_book(path):
    wb = openpyxl.Workbook()
    wb.active.title = 'Umumiy'
    for title, label, rows in [
        ('1-Green', 'Sinf:', [(1, 'Aliyev Vali', None, '94-590-59-06', '93-111-22-33', 2000000),
                              (2, 'Aliyeva Zuhra', None, '94-590-59-06', None, 1800000)]),
        ('3 Blue', 'Sinf', [(1, 'Karimov Sardor', None, None, None, 2000000),
                            (2, 'Ustozning Farzandi', None, '90-218-57-07', None, 2000000)]),
    ]:
        ws = wb.create_sheet(title)
        ws.append(["O'quvchilar to'lov jadvali"])
        ws.append([None, label, f'Sinf {title}', 'Sinf rahbari:', 'Yakubova Shoira'])
        ws.append(['№', "O'quvchi ism-familiyasi", 'Ota-ona', 'Telefon 1', 'Telefon 2', 'Oylik badal'])
        for r in rows:
            ws.append(list(r))
        ws.append([None, 'JAMI', "2 nafar o'quvchi"])
    wb.save(path)


def _staff_book(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['T/r', 'IFO', 'Fani', "Tug'ilgan sana", 'Telefon'])
    ws.append([1, 'Ergashev Ikromjon', 'Informatika', datetime.datetime(1995, 2, 1), '90-218-57-07'])
    ws.append([2, 'Mamatov Islomjon', 'Nazoratchi', '93-173-11-66'])
    ws.append([3, 'Boltaboyev Shamsiddin', 'Direktor', datetime.datetime(1987, 8, 1), '94-153-96-66'])
    ws.append([4, 'Asoschi Ismi', 'Asoschi', None, '99-493-11-11'])
    ws.append([5, 'Solijanov Shaxzod', 'Rus tili'])
    wb.save(path)


class PaySheetImportTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(organization=Organization.objects.create(name='Asosiy maktab'), name='Asosiy')
        Position.objects.get_or_create(name='Direktor', defaults={'default_perms': ['students.view']})
        self.tmp = Path(tempfile.mkdtemp())
        _pay_book(self.tmp / 'pay.xlsx')
        _staff_book(self.tmp / 'staff.xlsx')

    def test_class_name(self):
        self.assertEqual(class_name('Sinf 1-Green'), '1-Green')
        self.assertEqual(class_name('Sinf 3 Blue'), '3-Blue')
        self.assertEqual(class_name('Sinf 8-med rus'), '8-Med rus')
        self.assertEqual(class_name('Sinf 8-9-Huquq'), '8-9-Huquq')

    def test_import_and_rerun(self):
        staff = read_staff_sheet(self.tmp / 'staff.xlsx')
        self.assertEqual(staff[1], ('Mamatov Islomjon', 'Nazoratchi', None, '93-173-11-66'))   # sana o'rnida telefon
        r = import_staff_sheet(staff, self.branch)
        self.assertEqual((r['teachers'], r['staff']), (2, 2))
        self.assertEqual(r['skipped'], ['Asoschi Ismi (Asoschi)'])
        self.assertEqual(r['no_phone'], ['Solijanov Shaxzod'])
        teacher = User.objects.get(last_name='Ergashev')
        self.assertTrue(teacher.check_password('5707') and teacher.must_change_password)
        director = User.objects.get(last_name='Boltaboyev')
        self.assertTrue(director.staff_profile.is_active)
        self.assertFalse(User.objects.get(last_name='Mamatov').staff_profile.is_active)
        self.assertTrue(all(u.branches.filter(pk=self.branch.pk).exists() for u in User.objects.all()))

        sheets = read_pay_sheets(self.tmp / 'pay.xlsx')
        self.assertEqual(list(sheets), ['1-Green', '3-Blue'])
        r = import_pay_sheets(sheets, self.branch)
        self.assertEqual((r['groups'], r['created'], r['parents_new']), (2, 4, 2))
        self.assertEqual(r['no_phone'], ['3-Blue: Karimov Sardor'])
        vali = Student.objects.get(user__first_name='Vali')
        self.assertEqual(vali.parents.count(), 2)
        self.assertEqual(vali.branch, self.branch)
        mom = User.objects.get(phone_digits='998945905906')
        self.assertEqual(mom.children.count(), 2)                       # aka-singil bitta ota-onada
        self.assertIn(teacher, Student.objects.get(user__first_name='Farzandi').parents.all())   # ustoz = ota-ona
        self.assertEqual(teacher.role, User.Role.TEACHER)

        again = import_pay_sheets(read_pay_sheets(self.tmp / 'pay.xlsx'), self.branch)
        self.assertEqual((again['created'], again['parents_new'], again['parents_linked']), (0, 0, 0))
        self.assertEqual(import_staff_sheet(staff, self.branch)['existing'], 4)
