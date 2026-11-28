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
        Branch.objects.create(organization=Organization.objects.create(name="O'quv markaz"), name='40-maktab')   # «birinchi filial»
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
        self.assertTrue(director.check_password('9666') and director.must_change_password)
        self.assertFalse(User.objects.get(last_name='Mamatov').staff_profile.is_active)
        self.assertTrue(all(list(u.branches.all()) == [self.branch] for u in User.objects.all()))   # markaz filiali qo'shilmadi

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
        self.assertTrue(mom.check_password('5906') and mom.must_change_password)
        self.assertIn(teacher, Student.objects.get(user__first_name='Farzandi').parents.all())   # ustoz = ota-ona
        self.assertEqual(teacher.role, User.Role.TEACHER)

        again = import_pay_sheets(read_pay_sheets(self.tmp / 'pay.xlsx'), self.branch)
        self.assertEqual((again['created'], again['parents_new'], again['parents_linked']), (0, 0, 0))
        self.assertEqual(import_staff_sheet(staff, self.branch)['existing'], 4)

        # ro'yxat yangilandi: telefon bir xil, ism tuzatildi; telefonsiz xodimga telefon yozildi; yangi ustoz
        updated = [('Ergashev Ikromjon IT', 'Informatika', None, '90-218-57-07'),
                   ('Solijanov Shaxzod', 'Rus tili', None, '94-458-29-99'),
                   ('Xalikova Gulnora', "Boshlang'ich", None, '94-590-59-06')]   # telefoni ota-ona sifatida bor edi
        r = import_staff_sheet(updated, self.branch)
        self.assertEqual((r['existing'], r['teachers']), (2, 1))
        mom = User.objects.get(phone_digits='998945905906')
        self.assertEqual((mom.last_name, mom.first_name, mom.role), ('Xalikova', 'Gulnora', User.Role.TEACHER))
        self.assertEqual(mom.children.count(), 2)
        self.assertEqual(r['renamed'], ['Ergashev Ikromjon -> Ergashev Ikromjon IT'])
        self.assertEqual(r['phone_added'], ['Solijanov Shaxzod'])
        sol = User.objects.get(last_name='Solijanov')
        self.assertTrue(sol.check_password('2999') and sol.must_change_password)
        self.assertEqual(User.objects.filter(last_name='Solijanov').count(), 1)


class PayHistoryTests(TestCase):
    """Founder qoidalari: badal 2 mln, kami chegirma; Grand — o'sha oylar 100%; Free — muddatsiz 100%;
    «N(bol)» — oy summasi N; «tibbiyot» — shu oydan hisob bekor va chiqariladi; tushunarsiz belgi — ko'rib chiqishga."""

    def setUp(self):
        from billing.models import BillingSettings
        self.branch = Branch.objects.create(organization=Organization.objects.create(name='Asosiy maktab'), name='Asosiy')
        BillingSettings.get(self.branch.organization)
        path = Path(tempfile.mkdtemp()) / 'pay.xlsx'
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = '5-Blue'
        ws.append(['jadval'])
        ws.append([None, 'Sinf:', 'Sinf 5-Blue', 'Sinf rahbari:', 'X'])
        ws.append(['№', 'Ism', 'Ota-ona', 'Tel1', 'Tel2', 'Badal', 'Sen', 'Okt', 'Noy', 'Dek'])
        ws.append([1, 'Chegirmali Ali', None, '94-111-11-11', None, 1800000, 1800000, 1800000, 'Grand', 'Grand'])
        ws.append([2, 'Хасанова Севинч', None, '94-222-22-22', None, 'Free', 'Free', 'Free', 'Free', 'Free'])
        ws.append([3, 'KASAL VALI', None, '94-333-33-33', None, 2000000, 2000000, '1300000(bol)', 2000000, 2000000])
        ws.append([4, "O'tgan Sobir", None, '94-444-44-44', None, 2000000, 2000000, 2000000, 'tibbiyot'])
        ws.append([5, 'Belgili Jasur', None, '94-555-55-55', None, None, 'spravka', 46346, '25-da'])
        wb.save(path)
        self.path = path

    def test_rules_and_rerun(self):
        from billing.models import BillingSettings, Charge, Payment
        from billing.pay_sheet_history import import_pay_history
        today = datetime.date(2026, 11, 28)
        sheets = read_pay_sheets(self.path)
        import_pay_sheets(sheets, self.branch)
        self.assertTrue(Student.objects.filter(user__last_name='Xasanova', user__first_name='Sevinch').exists())
        self.assertTrue(Student.objects.filter(user__last_name='Kasal', user__first_name='Vali').exists())
        r = import_pay_history(sheets, self.branch, today=today)
        self.assertEqual(BillingSettings.get(self.branch.organization).monthly_price, 2000000)

        def charges(first):
            s = Student.objects.get(user__first_name=first)
            return [(c.month.month, int(c.amount), c.cancelled) for c in s.charges.order_by('month')], s
        ali, s = charges('Ali')
        self.assertEqual(ali, [(9, 1800000, False), (10, 1800000, False), (11, 0, False)])   # 10% + grant noyabr
        self.assertEqual(s.discounts.get(discount__percent=100).valid_to, datetime.date(2026, 12, 1))
        self.assertEqual([c[1] for c in charges('Sevinch')[0]], [0, 0, 0])
        vali, s = charges('Vali')
        self.assertEqual(vali[1], (10, 1300000, False))
        self.assertEqual(sum(p.amount for p in s.fee_payments.all()), 2000000 + 1300000 + 2000000 + 2000000)
        self.assertEqual(s.fee_payments.get(note__endswith='dekabr').paid_on, datetime.date(2026, 11, 1))   # oldindan to'lov
        sobir, s = charges('Sobir')
        self.assertEqual(sobir[2], (11, 2000000, True))
        self.assertTrue(s.has_left)
        self.assertEqual(s.left_at, datetime.date(2026, 11, 1))
        self.assertEqual(len([x for x in r['review'] if 'Belgili' in x]), 4)      # badalsiz, spravka, sana, 25-da
        self.assertFalse(Payment.objects.filter(amount__lt=100000).exists())

        again = import_pay_history(read_pay_sheets(self.path), self.branch, today=today)
        self.assertEqual((again['payments'], again['missing']), (0, []))
        import_pay_sheets(read_pay_sheets(self.path), self.branch)
        self.assertEqual(Student.objects.count(), 5)                               # chiqqan o'quvchi qayta yaratilmadi
        self.assertEqual(Charge.objects.filter(student__user__first_name='Ali').count(), 3)


class TelegramPhotoTests(TestCase):
    """Telegram eksportidan rasm biriktirish: yozilish farqlari mos keladi, ism bir xil-familiya boshqa — yo'q."""

    def test_match_rules(self):
        from accounts.telegram_photos import color_of, grade_of, match
        students = [(1, 'Turdiyev', 'Xumoyun', '7-Blue'), (2, "G'ofurjonova", 'Sevinchoy', '8-Red'),
                    (3, 'Daminjanova', 'Mubina', '1-Green'), (4, 'Baxtiyarova', 'Shodiya', '1-Blue'),
                    (5, 'Ikromjanov', 'Imronbek', '1-Blue'), (6, 'Ikromov', 'Imronbek', '2-Red'),
                    (7, 'Baxtiyorova', 'Binafsha Baxtiyor qizi', '4-Blue')]
        entries = [(Path(f'p{i}.jpg'), name, label, i, '') for i, (name, label) in enumerate([
            ('Turdiyev Xumoyin', '7b uzb'), ('Gafurjanova Sevinch', '9r Rus'), ('Komiljonova Mubina', '1g'),
            ('Bahtiyorova Shoira', '1b uzb'), ('Ikromjonov Imronbek', '1b uzb'), ('Bahtiyorova Binavsha', '4b uzbek')])]
        r = match(entries, students)
        self.assertEqual(sorted(r['matched']), [1, 2, 5, 7])
        self.assertEqual(sorted(e[0][1] for e in r['unmatched']), ['Bahtiyorova Shoira', 'Komiljonova Mubina'])
        self.assertEqual((grade_of('8-9 huquq'), color_of('7b uzb'), color_of('10 huquq')), (8, 'blue', None))

    def test_command_attaches_photo(self):
        import json
        from io import BytesIO, StringIO

        from django.core.management import call_command
        from PIL import Image

        from academics.models import Group
        branch = Branch.objects.create(organization=Organization.objects.create(name='Asosiy maktab'), name='Asosiy')
        g = Group.objects.create(name='7-Blue', branch=branch)
        u = User.objects.create(username='s1', first_name='Xumoyun', last_name='Turdiyev', role=User.Role.STUDENT)
        st = Student.objects.create(user=u, group=g, branch=branch)
        u2 = User.objects.create(username='s2', first_name='Ali', last_name='Valiyev', role=User.Role.STUDENT)
        Student.objects.create(user=u2, group=g, branch=branch)
        folder = Path(tempfile.mkdtemp())
        (folder / 'photos').mkdir()
        Image.new('RGB', (600, 800), (200, 180, 160)).save(folder / 'photos' / 'a.jpg')
        (folder / 'result.json').write_text(json.dumps({'messages': [
            {'id': 1, 'type': 'message', 'photo': 'photos/a.jpg', 'text': 'Turdiyev Xumoyin\n\n7b uzb'}]}), encoding='utf-8')
        out = StringIO()
        with self.settings(MEDIA_ROOT=tempfile.mkdtemp()):
            call_command('attach_telegram_photos', branch=branch.pk, export=str(folder), stdout=out)
            u.refresh_from_db()
            st.refresh_from_db()
            self.assertTrue(u.photo)
            self.assertTrue(st.access_id)
            self.assertIn('7-Blue: 1 / 2 rasmsiz', out.getvalue())
            self.assertIn('Valiyev Ali', out.getvalue())
