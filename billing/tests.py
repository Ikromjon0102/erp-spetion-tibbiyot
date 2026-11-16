import io
from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import load_workbook

from academics.models import Group
from accounts.models import Student, User
from panel.models import Position, StaffProfile

from . import exports, reports
from .models import BillingSettings, Charge, Discount, Payment, StudentDiscount
from .services import account, academic_months, ensure_charges, price_after, recalc_charges, summaries

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
TODAY = timezone.localdate()


def student(username, last, group, parent=None):
    u = User.objects.create_user(username=username, password='x', role='student', first_name='Ali', last_name=last)
    st = Student.objects.create(user=u, group=group)
    if parent:
        st.parents.add(parent)
    return st


def staff(username, position, perms=None):
    u = User.objects.create_user(username=username, password='x', role='staff', first_name=username.title())
    p = Position.objects.get(name=position)
    StaffProfile.objects.create(user=u, position=p, perms=list(p.default_perms) if perms is None else perms)
    return u


class RulesTests(TestCase):
    def setUp(self):
        self.g = Group.objects.create(name='5-A', year='2026')
        self.s = student('s1', 'Karimov', self.g)
        # Hisob joriy oydan boshlanadi (o'quv yili sentabr–iyun; yozda ham ishlashi uchun sana tanlab olinadi)
        self.today = date(2026, 11, 20)
        BillingSettings.objects.update_or_create(pk=1, defaults={'monthly_price': 1000000, 'due_day': 10, 'billing_start': date(2026, 9, 1)})

    def test_charges_for_academic_months_up_to_current(self):
        ensure_charges([self.s.pk], self.today)
        self.assertEqual([c.month for c in Charge.objects.order_by('month')], [date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)])
        ensure_charges([self.s.pk], self.today)                      # qayta chaqirish yangi yozuv qo'shmaydi
        self.assertEqual(Charge.objects.count(), 3)
        self.assertEqual(len(academic_months(2026)), 10)             # sentabr–iyun

    def test_no_charges_until_price_is_set(self):
        BillingSettings.objects.filter(pk=1).update(monthly_price=0)
        self.assertEqual(ensure_charges([self.s.pk], self.today), 0)

    def test_default_has_no_discount_and_largest_wins_without_stacking(self):
        ensure_charges([self.s.pk], self.today)
        self.assertEqual(Charge.objects.first().amount, Decimal(1000000))      # standart: chegirma yo'q
        a, b = Discount.objects.create(name="2+ farzand", percent=10), Discount.objects.create(name='Xodim farzandi', percent=25)
        StudentDiscount.objects.create(student=self.s, discount=a)
        StudentDiscount.objects.create(student=self.s, discount=b)
        recalc_charges(self.s)
        c = Charge.objects.get(student=self.s, month=date(2026, 11, 1))
        self.assertEqual((c.discount_percent, c.amount), (Decimal(25), Decimal(750000)))   # 25% (10 + 25 emas)
        self.assertIn('Xodim farzandi', c.discount_label)

    def test_discount_valid_period_and_inactive(self):
        d = Discount.objects.create(name='Vaqtinchalik', percent=50)
        StudentDiscount.objects.create(student=self.s, discount=d, valid_from=date(2026, 10, 1), valid_to=date(2026, 10, 1))
        ensure_charges([self.s.pk], self.today)
        recalc_charges(self.s)
        amounts = {c.month.month: c.amount for c in Charge.objects.filter(student=self.s)}
        self.assertEqual(amounts, {9: 1000000, 10: 500000, 11: 1000000})
        d.is_active = False
        d.save()
        recalc_charges(self.s)
        self.assertEqual(Charge.objects.get(month=date(2026, 10, 1)).amount, Decimal(1000000))

    def test_price_change_does_not_touch_old_months(self):
        ensure_charges([self.s.pk], self.today)
        BillingSettings.objects.filter(pk=1).update(monthly_price=2000000)
        ensure_charges([self.s.pk], self.today)
        self.assertEqual(set(Charge.objects.values_list('amount', flat=True)), {Decimal(1000000)})

    def test_partial_payment_overpayment_carries_over_and_overdue(self):
        Payment.objects.create(student=self.s, amount=1500000)
        info = account(self.s, self.today)
        self.assertEqual([r['status'] for r in info['rows']], ['paid', 'partial', 'unpaid'])
        self.assertEqual((info['paid'], info['debt'], info['advance']), (1500000, 1500000, 0))
        self.assertEqual(info['overdue'], Decimal(1500000))        # oktyabr qoldig'i va noyabr (10-kundan keyin) — jarimasiz
        Payment.objects.create(student=self.s, amount=2000000)      # ortiqcha
        info = account(self.s, self.today)
        self.assertEqual((info['debt'], info['advance']), (0, 500000))   # 3 oy = 3 000 000, to'langan 3 500 000

    def test_voided_payment_is_ignored(self):
        p = Payment.objects.create(student=self.s, amount=1000000)
        p.voided = True
        p.save()
        self.assertEqual(account(self.s, self.today)['paid'], 0)
        self.assertEqual(summaries([self.s.pk], self.today)[self.s.pk]['debt'], 3000000)

    def test_overdue_only_after_due_day(self):
        early = date(2026, 11, 5)                                  # 10-kundan oldin: noyabr hali muddati o'tmagan
        self.assertEqual(account(self.s, early)['overdue'], Decimal(2000000))
        self.assertEqual(account(self.s, self.today)['overdue'], Decimal(3000000))

    def test_receipt_number_and_price_rounding(self):
        p = Payment.objects.create(student=self.s, amount=10)
        self.assertRegex(p.receipt_no, r'^CH\d{4}-\d{5}$')
        self.assertEqual(price_after(1000000, Decimal('12.5')), Decimal(875000))


@FAST
class ViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.g = Group.objects.create(name='5-A', year='2026')
        self.parent = User.objects.create_user(username='ota', password='x', role='parent', first_name='Ota')
        self.s = student('s1', 'Karimov', self.g, self.parent)
        self.other_parent = User.objects.create_user(username='ota2', password='x', role='parent')
        self.rec, self.acc = staff('rec', 'Reception'), staff('hisob', 'Hisobchi')
        self.dir = staff('dir', 'Direktor')
        BillingSettings.objects.update_or_create(pk=1, defaults={'monthly_price': 1000000, 'due_day': 10,
                                                                 'billing_start': TODAY.replace(day=1)})

    def login(self, name):
        self.client.login(username=name, password='x')

    def test_reception_accepts_payment_and_gets_receipt(self):
        self.login('rec')
        r = self.client.post(f'/panel/tolovlar/oquvchi/{self.s.pk}/', {'amount': 400000, 'method': 'card', 'paid_on': TODAY.isoformat(), 'note': ''})
        p = Payment.objects.get()
        self.assertRedirects(r, f'/oquvchi/{self.s.pk}/chek/{p.pk}/')
        self.assertEqual((p.amount, p.method, p.received_by), (400000, 'card', self.rec))
        self.assertContains(self.client.get(f'/oquvchi/{self.s.pk}/chek/{p.pk}/'), p.receipt_no)

    def test_amount_with_spaces_and_receipt_leads_back_to_lists_not_to_the_form(self):
        self.login('rec')
        url = f'/panel/tolovlar/oquvchi/{self.s.pk}/'
        page = self.client.get(url)
        self.assertEqual(page.context['quick'][0], ("To'liq qarz", int(summaries([self.s.pk])[self.s.pk]['debt'])))
        r = self.client.post(url, {'amount': '400 000', 'method': 'cash', 'paid_on': TODAY.isoformat(), 'note': ''})
        p = Payment.objects.get()
        self.assertEqual(p.amount, 400000)
        receipt = self.client.get(r.url, HTTP_REFERER='http://testserver' + url)
        self.assertEqual(receipt.context['back'], '/panel/tolovlar/')                      # formaga qaytarmaydi
        self.assertContains(receipt, 'href="/panel/tolovlar/qarzdorlar/"')
        self.client.logout()
        self.client.login(username='ota', password='x')                                    # ota-onada panel havolalari yo'q
        self.assertNotContains(self.client.get(r.url), '/panel/')

    def test_debtors_list_shows_debt_and_pay_link_by_permission(self):
        paid_up = student('s2', 'Aliyev', self.g, self.other_parent)
        Payment.objects.create(student=paid_up, amount=summaries([paid_up.pk])[paid_up.pk]['debt'])
        self.login('rec')
        r = self.client.get('/panel/tolovlar/qarzdorlar/')
        self.assertEqual([row['s'] for row in r.context['page']], [self.s])                 # qarzi yo'q o'quvchi chiqmaydi
        self.assertEqual(r.context['debt_total'], summaries([self.s.pk])[self.s.pk]['debt'])
        self.assertContains(r, f'/panel/tolovlar/oquvchi/{self.s.pk}/')
        self.assertEqual(self.client.get('/panel/tolovlar/qarzdorlar/?q=yoq').context['count'], 0)
        self.assertEqual(self.client.get(f'/panel/tolovlar/qarzdorlar/?sinf={self.g.pk}').context['count'], 1)
        self.login('hisob')                                                                # hisobchi ko'radi, lekin qabul qila olmaydi
        self.assertNotContains(self.client.get('/panel/tolovlar/qarzdorlar/'), f'/panel/tolovlar/oquvchi/{self.s.pk}/')

    def test_accountant_cannot_accept_but_can_report(self):
        self.login('hisob')
        self.assertEqual(self.client.post(f'/panel/tolovlar/oquvchi/{self.s.pk}/', {'amount': 1, 'method': 'cash', 'paid_on': TODAY.isoformat()}).status_code, 403)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(self.client.get('/panel/tolovlar/hisobotlar/?r=sinflar').status_code, 200)

    def test_reception_cannot_download_reports_or_edit_settings(self):
        self.login('rec')
        self.assertEqual(self.client.get('/panel/tolovlar/hisobotlar/').status_code, 403)
        self.assertEqual(self.client.get('/panel/tolovlar/sozlamalar/').status_code, 403)
        self.assertEqual(self.client.post('/panel/tolovlar/chegirmalar/yangi/', {'name': 'x', 'percent': 5}).status_code, 403)

    def test_future_date_and_zero_amount_rejected(self):
        self.login('rec')
        url = f'/panel/tolovlar/oquvchi/{self.s.pk}/'
        self.client.post(url, {'amount': 0, 'method': 'cash', 'paid_on': TODAY.isoformat()})
        self.client.post(url, {'amount': 5, 'method': 'cash', 'paid_on': date(2999, 1, 1).isoformat()})
        self.assertEqual(Payment.objects.count(), 0)

    def test_receipt_visible_to_own_parent_not_others(self):
        p = Payment.objects.create(student=self.s, amount=5)
        url = f'/oquvchi/{self.s.pk}/chek/{p.pk}/'
        self.login('ota2')
        self.assertEqual(self.client.get(url).status_code, 403)
        self.login('ota')
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)       # kirish sahifasiga

    def test_void_needs_permission_and_is_logged(self):
        p = Payment.objects.create(student=self.s, amount=100000)
        self.login('rec')
        self.assertEqual(self.client.post(f'/panel/tolovlar/{p.pk}/bekor/', {'reason': 'xato'}).status_code, 403)
        self.login('dir')
        self.client.post(f'/panel/tolovlar/{p.pk}/bekor/', {'reason': '  '})            # sababsiz bekor qilinmaydi
        p.refresh_from_db()
        self.assertFalse(p.voided)
        self.client.post(f'/panel/tolovlar/{p.pk}/bekor/', {'reason': 'xato kiritilgan'})
        p.refresh_from_db()
        self.assertTrue(p.voided and p.voided_by == self.dir)
        self.assertEqual(account(self.s)['paid'], 0)

    def test_assign_discount_changes_charge_and_parent_sees_note(self):
        d = Discount.objects.create(name="2+ farzand", percent=10, description='Oilada 2 va undan ko\'p farzand')
        ensure_charges([self.s.pk])
        self.login('dir')
        self.client.post(f'/panel/oquvchilar/{self.s.pk}/chegirma/', {'discount': d.pk, 'note': 'Ikki farzand'})
        self.assertEqual(Charge.objects.get(student=self.s).amount, Decimal(900000))
        self.login('ota')
        html = self.client.get(f'/oquvchi/{self.s.pk}/').content.decode()
        self.assertIn('2+ farzand', html)
        self.assertIn('Ikki farzand', html)
        self.login('dir')
        sd = StudentDiscount.objects.get()
        self.client.post(f'/panel/oquvchilar/{self.s.pk}/chegirma/{sd.pk}/olib-tashlash/')
        self.assertEqual(Charge.objects.get(student=self.s).amount, Decimal(1000000))

    def test_used_discount_is_deactivated_not_deleted(self):
        d = Discount.objects.create(name='X', percent=5)
        StudentDiscount.objects.create(student=self.s, discount=d)
        self.login('dir')
        self.client.post(f'/panel/tolovlar/chegirmalar/{d.pk}/ochirish/')
        d.refresh_from_db()
        self.assertFalse(d.is_active)
        free = Discount.objects.create(name='Y', percent=5)
        self.client.post(f'/panel/tolovlar/chegirmalar/{free.pk}/ochirish/')
        self.assertFalse(Discount.objects.filter(pk=free.pk).exists())

    def test_settings_change_updates_current_month_only(self):
        old = Charge.objects.create(student=self.s, month=date(2025, 9, 1), base_price=1000000, amount=1000000)
        self.login('dir')
        self.client.post('/panel/tolovlar/sozlamalar/', {'monthly_price': 1200000, 'due_day': 12, 'billing_start': TODAY.replace(day=1).isoformat()})
        ensure_charges([self.s.pk])
        old.refresh_from_db()
        self.assertEqual(old.amount, Decimal(1000000))
        self.assertEqual(BillingSettings.get().due_day, 12)

    def test_parent_sees_debt_history_and_receipt_link(self):
        p = Payment.objects.create(student=self.s, amount=300000, method='cash')
        self.login('ota')
        html = self.client.get(f'/oquvchi/{self.s.pk}/').content.decode()
        self.assertIn(p.receipt_no, html)
        self.assertIn(f'/oquvchi/{self.s.pk}/chek/{p.pk}/', html)
        self.assertIn('700 000', html)                                  # qarz

    def test_test_students_excluded_from_reports(self):
        sinov = student('sinov_1', 'Sinov', self.g)
        self.assertNotIn(sinov.pk, [s.pk for s in reports.real_students()])


@FAST
class ReportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.g = Group.objects.create(name='5-A', year='2026')
        self.s1, self.s2 = student('a', 'Aliyev', self.g), student('b', 'Valiyev', self.g)
        BillingSettings.objects.update_or_create(pk=1, defaults={'monthly_price': 1000000, 'billing_start': TODAY.replace(day=1)})
        Payment.objects.create(student=self.s1, amount=1000000, method='cash')
        self.dir = staff('dir', 'Direktor')
        self.client.login(username='dir', password='x')

    def test_debtors_report_lists_only_those_in_debt(self):
        rep = reports.qarzdorlar()
        self.assertEqual([r[0] for r in rep['rows']], ['Valiyev Ali'])
        self.assertEqual(rep['totals'][5], Decimal(1000000))

    def test_cash_report_by_method(self):
        rep = reports.tushum(TODAY, TODAY)
        self.assertEqual(len(rep['rows']), 1)
        self.assertEqual(rep['summary'], [("Naqd bo'yicha", Decimal(1000000))])

    def test_class_report_collection_percent(self):
        rep = reports.sinflar()
        self.assertEqual((rep['rows'][0][2], rep['rows'][0][3], rep['rows'][0][6]), (2000000, 1000000, 50))

    def test_excel_and_pdf_download(self):
        r = self.client.get('/panel/tolovlar/hisobotlar/qarzdorlar.xlsx')
        self.assertEqual(r.status_code, 200)
        ws = load_workbook(io.BytesIO(r.content)).active
        self.assertEqual(ws.cell(5, 1).value, "O'quvchi")
        self.assertEqual(ws.cell(6, 1).value, 'Valiyev Ali')
        for key in ('tushum', 'sinflar', 'chegirmalar', 'qarzdorlar'):
            pdf = self.client.get(f'/panel/tolovlar/hisobotlar/{key}.pdf')
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.content.startswith(b'%PDF'))
        self.assertEqual(self.client.get('/panel/tolovlar/hisobotlar/yoq.pdf').status_code, 302)

    def test_old_payments_migrated_shape(self):
        """exports.display formatlari."""
        self.assertEqual(exports.money(1234567), '1 234 567')


@FAST
class PanelStudentCardTests(TestCase):
    """O'quvchi kartasidagi "To'lov" yorlig'i: qabul qilish, chek va chegirma havolalari to'g'ri chiqadimi."""
    def test_card_renders_pay_tab_with_actions(self):
        g = Group.objects.create(name='5-A', year='2026')
        s = student('s1', 'Karimov', g)
        BillingSettings.objects.update_or_create(pk=1, defaults={'monthly_price': 1000000, 'billing_start': TODAY.replace(day=1)})
        p = Payment.objects.create(student=s, amount=300000)
        Discount.objects.create(name='X', percent=5)
        staff('dir', 'Direktor')
        self.client.login(username='dir', password='x')
        html = self.client.get(f'/panel/oquvchilar/{s.pk}/').content.decode()
        self.assertIn(f'/panel/tolovlar/oquvchi/{s.pk}/', html)
        self.assertIn(f'/oquvchi/{s.pk}/chek/{p.pk}/', html)
        self.assertIn(f'/panel/tolovlar/{p.pk}/bekor/', html)
