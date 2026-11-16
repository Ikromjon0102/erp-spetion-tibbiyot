import io
import tempfile
import zipfile
from pathlib import Path

import openpyxl
from django.test import TestCase

from academics.models import Group
from accounts.models import Student, User
from accounts.school_import import import_staff, import_student_file, pretty_name, read_staff_docx
from panel.models import StaffProfile


def _xlsx(tmp):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(['', '"SPETION"'])
    ws.append(['5-SINF'])
    ws.append(['N', 'I.F.O', 'Sana', 'TUL', 'TEL'])
    ws.append([1, 'JUMABOYEV JAVOXIR', '', '', '77-160-84-10'])
    ws.append([2, "NE'MATJONOVA SHOHISTA", '', '', ''])
    ws.append(['', 'Jami', '', '', ''])
    ws.append(['', "o'-12. q-7", '', '', ''])
    path = Path(tmp) / 'o.xlsx'
    wb.save(path)
    return path


def _docx(tmp, rows):
    body = ''.join('<w:tr>' + ''.join(f'<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>' for c in r) + '</w:tr>' for r in rows)
    xml = f'<?xml version="1.0"?><w:document xmlns:w="x"><w:body><w:tbl>{body}</w:tbl></w:body></w:document>'
    path = Path(tmp) / 'x.docx'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('word/document.xml', xml)
    return path


class SchoolImportTests(TestCase):
    def test_oquvchilar_hisobot_qatorlarisiz(self):
        with tempfile.TemporaryDirectory() as tmp:
            reports = import_student_file(_xlsx(tmp))
        self.assertEqual(Student.objects.count(), 2)          # 'Jami' va "o'-12. q-7" o'quvchi emas
        self.assertEqual(reports[0]['group'], '5-Sinf')
        self.assertEqual(reports[0]['no_phone'], ["Ne'matjonova Shohista"])
        self.assertEqual(Group.objects.get().name, '5-Sinf')

    def test_qayta_yuklash_takrorlamaydi(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = _xlsx(tmp)
            import_student_file(p)
            import_student_file(p)
        self.assertEqual(Student.objects.count(), 2)

    def test_xodimlar_rollari(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = read_staff_docx(_docx(tmp, [['T/r', 'Ism', 'Lavozimi', 'Telefon'],
                                               ['', 'Yusupov Umidjon', 'Direktor', '94-600-34-00'],
                                               ['', 'Yakubova Nigora', 'Kimyo', '93-677-45-86'],
                                               ['', 'Raimjonov Akramjon', 'Oshpaz', '99-607-45-44']]))
        r = import_staff(rows)
        self.assertEqual((r['teachers'], r['panel'], r['other']), (1, 1, 1))
        teacher = User.objects.get(role=User.Role.TEACHER)
        self.assertTrue(teacher.must_change_password and teacher.access_id)
        self.assertTrue(StaffProfile.objects.get(position__name='Direktor').is_active)
        self.assertFalse(StaffProfile.objects.get(position__name='Oshpaz').is_active)   # panelga kirmaydi

    def test_ism_chiroyli(self):
        self.assertEqual(pretty_name("NE'MATJONOVA  SHOHISTA"), "Ne'matjonova Shohista")
