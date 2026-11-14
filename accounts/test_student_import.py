from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from academics.models import Group

from .models import Student, User
from .student_import import clean_text, group_name_from_filename, import_students, normalize_phone, split_name

XLSX = Path(settings.BASE_DIR) / "10-sinf o'quvchilari ro'yxati.xlsx"


class CleanTests(SimpleTestCase):
    def test_cyrillic_lookalikes_and_apostrophes(self):
        self.assertEqual(clean_text('Аbdukarimov  Mirziyod'), 'Abdukarimov Mirziyod')  # birinchi "А" kirillcha
        self.assertEqual(clean_text('Gʼulomjonova Farzona'), "G'ulomjonova Farzona")
        self.assertEqual(clean_text('Joʼraev Ulugʼbek'), "Jo'raev Ulug'bek")

    def test_real_cyrillic_text_is_untouched(self):
        self.assertEqual(clean_text('Тошкент'), 'Тошкент')

    def test_split_name(self):
        self.assertEqual(split_name('Rustamov M-ziyo'), ('Rustamov', 'M-ziyo'))
        self.assertEqual(split_name('Karimov Ali Valiyevich'), ('Karimov', 'Ali Valiyevich'))

    def test_phone(self):
        self.assertEqual(normalize_phone('95-010-76-39'), '+998 95 010-76-39')
        self.assertEqual(normalize_phone('+998 94 604-80-62'), '+998 94 604-80-62')
        self.assertIsNone(normalize_phone('19'))
        self.assertIsNone(normalize_phone(None))

    def test_group_from_filename(self):
        self.assertEqual(group_name_from_filename("10-sinf o'quvchilari ro'yxati.xlsx"), '10-Sinf')
        self.assertIsNone(group_name_from_filename('royxat.xlsx'))


class ImportStudentsTests(TestCase):
    def setUp(self):
        if not XLSX.exists():
            self.skipTest('Excel fayl topilmadi')

    def test_import_is_clean_and_idempotent(self):
        r = import_students(XLSX, '10-Sinf')
        self.assertEqual((r['created'], r['parents_new'], r['parents_linked']), (20, 19, 19))  # "Jami" qatori kirmaydi
        self.assertEqual(r['no_phone'], ['Abdukarimov Mirziyod'])
        self.assertEqual(Student.objects.count(), 20)
        self.assertFalse(User.objects.filter(last_name='20').exists())
        names = ' '.join(f'{u.last_name}{u.first_name}' for u in User.objects.all())
        self.assertTrue(all(ord(c) < 0x250 for c in names))  # kirill/g'alati belgilar qolmadi

        again = import_students(XLSX, '10-Sinf')
        self.assertEqual((again['created'], again['parents_new'], again['parents_linked']), (0, 0, 0))
        self.assertEqual(Student.objects.count(), 20)

    def test_parent_is_linked_with_phone_and_cannot_log_in_yet(self):
        import_students(XLSX, '10-Sinf')
        child = Student.objects.get(user__last_name='Xabibullaeva')
        (parent,) = child.parents.all()
        self.assertEqual((parent.role, parent.phone), ('parent', '+998 95 010-76-39'))
        self.assertFalse(parent.has_usable_password())

    def test_shared_phone_links_siblings_to_one_parent(self):
        import_students(XLSX, '10-Sinf')
        sibling_user = User.objects.create(username='sib', first_name='Aka', last_name='Xabibullaev', role='student')
        sibling = Student.objects.create(user=sibling_user, group=Group.objects.get(name='10-Sinf'))
        parent = User.objects.get(username='998950107639')
        sibling.parents.add(parent)
        self.assertEqual(parent.children.count(), 2)


class MockStudentsTests(TestCase):
    def run_cmd(self, *args):
        call_command('mock_students', *args, stdout=StringIO())

    def test_adds_only_to_empty_groups_and_can_be_removed(self):
        empty, filled = Group.objects.create(name='5-Sinf'), Group.objects.create(name='10-Sinf')
        real = User.objects.create(username='real', first_name='Haqiqiy', last_name='Oquvchi', role='student')
        Student.objects.create(user=real, group=filled)

        self.run_cmd()
        self.assertEqual(empty.students.count(), 10)
        self.assertEqual(filled.students.count(), 1)  # haqiqiy o'quvchisi bor sinfga tegilmadi
        self.assertEqual(len({s.user.username for s in empty.students.all()}), 10)

        self.run_cmd('--remove')
        self.assertEqual(empty.students.count(), 0)
        self.assertEqual(filled.students.count(), 1)  # haqiqiy o'quvchi o'chmadi
        self.assertTrue(User.objects.filter(username='real').exists())
