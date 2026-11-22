"""Xarajatlar va oyliklar: ruxsatlar (faqat hisobchi va founder), filial ajratilishi, hisob-kitob."""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from academics.models import Group, Subject, Teaching
from accounts.models import Student, User
from billing.models import Payment
from finance import payroll
from finance.models import Expense, ExpenseCategory, Payslip, RecurringExpense, SalaryPayment, SalaryRule
from org.models import Branch, Organization, default_branch
from panel.access import can
from panel.models import Position, StaffProfile

import shutil
import tempfile

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
TODAY = date.today()
MONTH = TODAY.replace(day=1)


def staff(username, position, branch, perms=None):
    user = User.objects.create_user(username=username, password='x', role='staff', first_name=username.title())
    p = Position.objects.get(name=position)
    StaffProfile.objects.create(user=user, position=p, perms=list(p.default_perms) if perms is None else perms)
    user.branches.set([branch])
    return user


def png():
    from PIL import Image
    buf = BytesIO()
    Image.new('RGB', (4, 4), 'red').save(buf, 'PNG')
    return SimpleUploadedFile('chek.png', buf.getvalue(), content_type='image/png')


@FAST
class PermissionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.med = default_branch()
        self.owner = staff('egasi', 'Maktab egasi', self.med)
        self.accountant = staff('hisob', 'Hisobchi', self.med)
        self.director = staff('dir', 'Direktor', self.med)
        self.reception = staff('rec', 'Reception', self.med)

    def test_only_founder_and_accountant_have_money_permissions(self):
        for code in ('expenses.view', 'expenses.add', 'expenses.change', 'expenses.manage', 'payroll.view', 'payroll.manage'):
            self.assertTrue(can(self.owner, code), code)
            self.assertTrue(can(self.accountant, code), code)
            self.assertFalse(can(self.director, code), f'direktor: {code}')
            self.assertFalse(can(self.reception, code), f'reception: {code}')

    def test_directors_cannot_open_pages(self):
        self.client.force_login(self.director)
        for name in ('panel:expenses', 'panel:expense_add', 'panel:payroll', 'panel:salary_rules', 'panel:recurring'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_founder_can_grant_permission_to_anyone(self):
        profile = StaffProfile.objects.get(user=self.reception)
        self.client.force_login(self.owner)
        self.client.post(reverse('panel:staff_detail', args=[profile.pk]),
                         {'position': profile.position_id, 'perms': ['expenses.view', 'payroll.view'], 'is_active': 'on'})
        profile.refresh_from_db()
        self.assertIn('expenses.view', profile.perms)
        self.client.force_login(self.reception)
        self.assertEqual(self.client.get(reverse('panel:expenses')).status_code, 200)
        self.assertEqual(self.client.get(reverse('panel:payroll')).status_code, 200)
        self.assertEqual(self.client.get(reverse('panel:expense_add')).status_code, 403)       # faqat ko'rish berilgan

    def test_nav_hidden_without_permission(self):
        self.client.force_login(self.director)
        self.assertNotIn(reverse('panel:expenses'), self.client.get(reverse('panel:dashboard')).content.decode())
        self.client.force_login(self.accountant)
        self.assertIn(reverse('panel:expenses'), self.client.get(reverse('panel:dashboard')).content.decode())


@FAST
class ExpenseTests(TestCase):
    def setUp(self):
        cache.clear()
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.med = default_branch()
        org2 = Organization.objects.create(name='Markaz', kind='center')
        self.center = Branch.objects.create(organization=org2, name='Filial 1')
        self.owner = staff('egasi', 'Maktab egasi', self.med)
        self.acc_med = staff('hmed', 'Hisobchi', self.med)
        self.acc_c = staff('hc', 'Hisobchi', self.center)
        self.cat = ExpenseCategory.objects.get(name='Ijara')

    def add(self, user, **kw):
        self.client.force_login(user)
        data = {'branch': self.med.pk, 'category': self.cat.pk, 'date': TODAY.isoformat(), 'amount': '1 500 000', 'payee': 'Ijarachi', 'method': 'cash'}
        data.update(kw)
        return self.client.post(reverse('panel:expense_add'), data)

    def test_add_expense_and_receipt(self):
        r = self.add(self.acc_med, receipt=png())
        self.assertEqual(r.status_code, 302)
        e = Expense.objects.get()
        self.assertEqual((e.amount, e.branch, e.created_by), (1_500_000, self.med, self.acc_med))
        self.assertTrue(e.receipt)
        resp = self.client.get(reverse('panel:expense_receipt', args=[e.pk]))
        self.assertEqual(resp.status_code, 200)
        resp.close()

    def test_cannot_add_to_foreign_branch(self):
        r = self.add(self.acc_c, branch=self.med.pk)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Expense.objects.exists())

    def test_future_date_and_system_category_rejected(self):
        self.assertEqual(self.add(self.acc_med, date=date(TODAY.year + 1, 1, 1).isoformat()).status_code, 200)
        maosh = ExpenseCategory.objects.get(name='Maosh')
        self.assertEqual(self.add(self.acc_med, category=maosh.pk).status_code, 200)
        self.assertFalse(Expense.objects.exists())

    def test_isolation_between_branches(self):
        e_med = Expense.objects.create(branch=self.med, category=self.cat, amount=100, payee='MedIjara')
        Expense.objects.create(branch=self.center, category=self.cat, amount=200, payee='MarkazIjara')
        self.client.force_login(self.acc_c)
        body = self.client.get(reverse('panel:expenses')).content.decode()
        self.assertIn('MarkazIjara', body)
        self.assertNotIn('MedIjara', body)
        for name in ('panel:expense_edit', 'panel:expense_receipt'):
            self.assertEqual(self.client.get(reverse(name, args=[e_med.pk])).status_code, 404, name)
        self.assertEqual(self.client.post(reverse('panel:expense_delete', args=[e_med.pk])).status_code, 404)
        self.assertTrue(Expense.objects.filter(pk=e_med.pk).exists())
        self.client.force_login(self.owner)
        self.assertIn('MedIjara', self.client.get(reverse('panel:expenses'), {'oy': TODAY.strftime('%Y-%m')}).content.decode())   # «Hammasi»da oy tanlanmasa — tashkilot kartalari

    def test_profit_report_uses_income_minus_expenses_of_own_branch(self):
        g_med = Group.objects.create(name='5-A', branch=self.med)
        g_c = Group.objects.create(name='Ingliz', branch=self.center)
        for i, g in enumerate((g_med, g_c)):
            u = User.objects.create_user(f's{i}', password='x', role='student')
            Payment.objects.create(student=Student.objects.create(user=u, group=g), amount=1_000_000 * (i + 1), paid_on=TODAY)
        Expense.objects.create(branch=self.med, category=self.cat, amount=300_000, date=TODAY)
        Expense.objects.create(branch=self.center, category=self.cat, amount=500_000, date=TODAY)
        self.client.force_login(self.acc_med)
        r = self.client.get(reverse('panel:expenses'))
        self.assertEqual((r.context['income'], r.context['total'], r.context['profit']), (1_000_000, 300_000, 700_000))
        self.client.force_login(self.owner)
        r = self.client.get(reverse('panel:expenses'), {'oy': TODAY.strftime('%Y-%m')})
        self.assertEqual((r.context['income'], r.context['total'], r.context['profit']), (3_000_000, 800_000, 2_200_000))
        r = self.client.get(reverse('panel:expenses') + f'?filial={self.center.pk}')
        self.assertEqual((r.context['income'], r.context['total']), (2_000_000, 500_000))

    def test_recurring_creates_once_per_month(self):
        rec = RecurringExpense.objects.create(branch=self.med, category=self.cat, amount=2_000_000, payee='Bino', day=5, start_month=MONTH)
        self.assertIsNotNone(rec.create_for(MONTH))
        self.assertIsNone(rec.create_for(MONTH))                # qayta yozilmaydi
        self.assertEqual(Expense.objects.filter(recurring=rec).count(), 1)
        self.assertEqual(Expense.objects.get().date, MONTH.replace(day=5))
        self.assertIsNone(rec.create_for(date(MONTH.year - 1, MONTH.month, 1)))      # boshlanishdan oldingi oy

    def test_recurring_generate_button_and_scope(self):
        RecurringExpense.objects.create(branch=self.med, category=self.cat, amount=1, payee='Med', start_month=MONTH)
        RecurringExpense.objects.create(branch=self.center, category=self.cat, amount=1, payee='Markaz', start_month=MONTH)
        self.client.force_login(self.acc_c)
        self.client.post(reverse('panel:recurring_generate'))
        self.assertEqual(list(Expense.objects.values_list('payee', flat=True)), ['Markaz'])

    def test_delete_and_audit(self):
        self.add(self.acc_med)
        e = Expense.objects.get()
        self.client.post(reverse('panel:expense_delete', args=[e.pk]))
        self.assertFalse(Expense.objects.exists())
        from panel.models import AuditLog
        self.assertTrue(AuditLog.objects.filter(verb="Xarajatni o'chirdi").exists())


@FAST
class PayrollTests(TestCase):
    def setUp(self):
        cache.clear()
        self.med = default_branch()
        self.center = Branch.objects.create(organization=Organization.objects.create(name='Markaz', kind='center'), name='Filial 1')
        self.owner = staff('egasi', 'Maktab egasi', self.med)
        self.acc = staff('hisob', 'Hisobchi', self.med)
        self.acc_c = staff('hc', 'Hisobchi', self.center)

        self.t_fixed = User.objects.create_user('t1', password='x', role='teacher', first_name='Qat', last_name='Iy')
        self.t_pct = User.objects.create_user('t2', password='x', role='teacher', first_name='Foiz', last_name='Foizchiyev')
        self.t_pct.branches.set([self.center])
        subj = Subject.objects.create(name='Ingliz')
        self.group = Group.objects.create(name='A1', branch=self.center)
        Teaching.objects.create(teacher=self.t_pct, subject=subj, group=self.group)
        self.kids = []
        for i in range(3):
            u = User.objects.create_user(f'k{i}', password='x', role='student')
            self.kids.append(Student.objects.create(user=u, group=self.group))

    def pay(self, student, amount, voided=False, paid_on=None):
        return Payment.objects.create(student=student, amount=amount, paid_on=paid_on or MONTH, voided=voided)

    def test_fixed_salary(self):
        SalaryRule.objects.create(employee=self.t_fixed, branch=self.med, kind='fixed', amount=3_000_000, effective_from=MONTH)
        payroll.ensure_payslips(self.med, MONTH)
        slip = Payslip.objects.get(employee=self.t_fixed)
        self.assertEqual((slip.base_amount, slip.total), (3_000_000, 3_000_000))

    def test_percent_of_students_actual_payments(self):
        SalaryRule.objects.create(employee=self.t_pct, branch=self.center, kind='percent', percent=Decimal('40'), effective_from=MONTH)
        self.pay(self.kids[0], 400_000)
        self.pay(self.kids[1], 600_000)
        self.pay(self.kids[2], 999_999, voided=True)                                  # bekor qilingan hisobga olinmaydi
        self.pay(self.kids[0], 777_777, paid_on=MONTH.replace(year=MONTH.year - 1))      # boshqa oy
        payroll.ensure_payslips(self.center, MONTH)
        slip = Payslip.objects.get(employee=self.t_pct)
        self.assertEqual(slip.base_amount, 400_000)        # (400k + 600k) × 40%
        self.assertIn('2 ta', slip.calc_note)

    def test_other_branch_payments_not_counted(self):
        SalaryRule.objects.create(employee=self.t_pct, branch=self.center, kind='percent', percent=Decimal('40'), effective_from=MONTH)
        u = User.objects.create_user('med-kid', password='x', role='student')
        self.pay(Student.objects.create(user=u, group=Group.objects.create(name='5-A', branch=self.med)), 5_000_000)
        base, count = payroll.percent_base(self.t_pct, self.center, MONTH)
        self.assertEqual((base, count), (0, 0))

    def test_payment_split_between_two_teachers_of_a_group(self):
        other = User.objects.create_user('t3', password='x', role='teacher')
        Teaching.objects.create(teacher=other, subject=Subject.objects.create(name='Mat'), group=self.group)
        self.pay(self.kids[0], 1_000_000)
        self.assertEqual(payroll.percent_base(self.t_pct, self.center, MONTH)[0], 500_000)

    def test_rule_effective_date_keeps_old_months(self):
        prev = MONTH.replace(year=MONTH.year - 1)
        SalaryRule.objects.create(employee=self.t_fixed, branch=self.med, kind='fixed', amount=2_000_000, effective_from=prev)
        SalaryRule.objects.create(employee=self.t_fixed, branch=self.med, kind='fixed', amount=2_500_000, effective_from=MONTH)
        self.assertEqual(SalaryRule.current(self.t_fixed, self.med, prev).amount, 2_000_000)
        self.assertEqual(SalaryRule.current(self.t_fixed, self.med, MONTH).amount, 2_500_000)
        self.assertIsNone(SalaryRule.current(self.t_fixed, self.med, prev.replace(year=prev.year - 1)))

    def test_recalculate_keeps_bonus_and_payments(self):
        rule = SalaryRule.objects.create(employee=self.t_fixed, branch=self.med, kind='fixed', amount=3_000_000, effective_from=MONTH)
        payroll.ensure_payslips(self.med, MONTH)
        slip = Payslip.objects.get()
        slip.bonus, slip.deduction = 200_000, 50_000
        slip.save()
        payroll.pay(slip, 1_000_000, 'advance', TODAY, 'cash', self.acc)
        rule.amount = 3_500_000
        rule.save()
        payroll.ensure_payslips(self.med, MONTH)
        slip.refresh_from_db()
        self.assertEqual((slip.base_amount, slip.total, slip.paid, slip.remaining), (3_500_000, 3_650_000, 1_000_000, 2_650_000))
        self.assertEqual(Payslip.objects.count(), 1)

    def test_paying_salary_creates_expense_and_cancel_removes_it(self):
        SalaryRule.objects.create(employee=self.t_fixed, branch=self.med, kind='fixed', amount=3_000_000, effective_from=MONTH)
        payroll.ensure_payslips(self.med, MONTH)
        slip = Payslip.objects.get()
        p = payroll.pay(slip, 3_000_000, 'salary', TODAY, 'transfer', self.acc)
        e = Expense.objects.get()
        self.assertEqual((e.category.name, e.amount, e.branch), ('Maosh', 3_000_000, self.med))
        self.assertEqual(slip.remaining, 0)
        payroll.delete_payment(p)
        self.assertFalse(Expense.objects.exists())
        self.assertFalse(SalaryPayment.objects.exists())

    def test_pages_flow(self):
        self.client.force_login(self.acc)
        r = self.client.post(reverse('panel:salary_rule_add'), {'employee': self.t_fixed.pk, 'branch': self.med.pk, 'kind': 'fixed',
                                                                 'amount': '3 000 000', 'percent': 40, 'effective_from': MONTH.isoformat()})
        self.assertEqual(r.status_code, 302)
        self.client.post(reverse('panel:payroll_calculate'), {'oy': MONTH.strftime('%Y-%m'), 'filial': self.med.pk})
        slip = Payslip.objects.get()
        self.assertIn('Iy', self.client.get(reverse('panel:payroll')).content.decode())
        self.client.post(reverse('panel:payslip_pay', args=[slip.pk]), {'amount': '1 000 000', 'kind': 'advance', 'paid_on': TODAY.isoformat(), 'method': 'cash'})
        self.assertEqual(slip.paid, 1_000_000)
        self.assertEqual(Expense.objects.filter(category__name='Maosh').count(), 1)
        # "Maosh" xarajatini xarajatlar sahifasidan tahrirlab/o'chirib bo'lmaydi
        e = Expense.objects.get()
        self.client.post(reverse('panel:expense_delete', args=[e.pk]))
        self.assertTrue(Expense.objects.filter(pk=e.pk).exists())

    def test_fixed_rule_requires_amount(self):
        self.client.force_login(self.acc)
        r = self.client.post(reverse('panel:salary_rule_add'), {'employee': self.t_fixed.pk, 'branch': self.med.pk, 'kind': 'fixed',
                                                                 'amount': '', 'percent': 40, 'effective_from': MONTH.isoformat()})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(SalaryRule.objects.exists())

    def test_payroll_isolated_between_branches(self):
        SalaryRule.objects.create(employee=self.t_pct, branch=self.center, kind='percent', percent=Decimal('40'), effective_from=MONTH)
        payroll.ensure_payslips(self.center, MONTH)
        slip = Payslip.objects.get()
        self.client.force_login(self.acc)             # med hisobchisi
        self.assertNotIn('Foizchiyev', self.client.get(reverse('panel:payroll') + f'?filial={self.center.pk}').content.decode())
        self.assertEqual(self.client.get(reverse('panel:payslip_pay', args=[slip.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('panel:payslip_edit', args=[slip.pk])).status_code, 404)
        self.assertNotIn('Foizchiyev', self.client.get(reverse('panel:salary_rules')).content.decode())
        # med hisobchisi markaz xodimiga qoida yozolmaydi
        r = self.client.post(reverse('panel:salary_rule_add'), {'employee': self.t_pct.pk, 'branch': self.center.pk, 'kind': 'fixed',
                                                                 'amount': '1', 'percent': 40, 'effective_from': MONTH.isoformat()})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(SalaryRule.objects.count(), 1)
        self.client.force_login(self.acc_c)
        self.assertEqual(self.client.get(reverse('panel:payslip_pay', args=[slip.pk])).status_code, 200)

    def test_salary_payment_cancel_scoped(self):
        SalaryRule.objects.create(employee=self.t_pct, branch=self.center, kind='fixed', amount=1_000_000, effective_from=MONTH)
        payroll.ensure_payslips(self.center, MONTH)
        p = payroll.pay(Payslip.objects.get(), 500_000, 'advance', TODAY, 'cash', self.acc_c)
        self.client.force_login(self.acc)
        self.assertEqual(self.client.post(reverse('panel:salary_payment_delete', args=[p.pk])).status_code, 404)
        self.assertTrue(SalaryPayment.objects.filter(pk=p.pk).exists())
