from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from accounts.models import User

from .models import Lesson
from .schedule_import import import_workbook, normalize_teacher, parse_cell

XLSX = Path(settings.BASE_DIR) / 'Dars_Jadvali(Noyabr).xlsx'


class ParseCellTests(SimpleTestCase):
    def test_cases(self):
        self.assertEqual(parse_cell('Ona tili(Diyora)'), ('Ona tili', 'Diyora', None))
        self.assertEqual(parse_cell("IT(Ulug'bek)"), ('IT', "Ulug'bek", None))
        self.assertEqual(parse_cell('Tarbiya'), ('Tarbiya', None, None))
        self.assertEqual(parse_cell('Jismoniy tarbiya(Bahodir),'), ('Jismoniy tarbiya', 'Bahodir', None))
        self.assertEqual(parse_cell('Tarix(Shuxratjon)+17:00'), ('Tarix', 'Shuxratjon', '17:00'))
        self.assertIsNone(parse_cell('-'))
        self.assertIsNone(parse_cell(None))

    def test_teacher_aliases_merge(self):
        self.assertEqual(normalize_teacher('Oychexra aya'), 'Oychexra')
        self.assertEqual(normalize_teacher('Ranoxon aya'), normalize_teacher('Ranoxon'))


class ImportWorkbookTests(TestCase):
    def setUp(self):
        if not XLSX.exists():
            self.skipTest('Excel fayl topilmadi')

    def test_import_counts_and_idempotency(self):
        r = import_workbook(XLSX)
        self.assertEqual((r['lessons_total'], r['created']), (276, 276))
        self.assertEqual(User.objects.filter(role='teacher').count(), 17)
        self.assertEqual(Lesson.objects.filter(weekday=5).count(), 36)  # shanba: 6 sinf x 6 soat

        again = import_workbook(XLSX)
        self.assertEqual((again['created'], again['updated'], again['deactivated']), (0, 0, 0))
        self.assertEqual(again['credentials'], [])  # parollar qayta yaratilmaydi
        self.assertEqual(Lesson.objects.count(), 276)

    def test_extra_17_00_lesson_and_unassigned_tarbiya(self):
        import_workbook(XLSX)
        late = Lesson.objects.get(teaching__group__name='10-Sinf', weekday=0, period=8)
        self.assertEqual((late.start.strftime('%H:%M'), late.end.strftime('%H:%M')), ('17:00', '17:45'))
        self.assertIsNone(Lesson.objects.get(teaching__group__name='5-Sinf', weekday=0, period=7).teaching.teacher)
