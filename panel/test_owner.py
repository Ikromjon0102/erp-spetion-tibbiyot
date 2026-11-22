from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import Group
from accounts.models import Student, User
from billing.models import BillingSettings, Discount, Payment, StudentDiscount
from billing.services import ensure_charges
from finance.models import Expense, ExpenseCategory
from org.models import Branch, Organization
from panel import owner_stats


class OwnerDashboardTests(TestCase):
    """Founder misoli: narx 2 000 000; 6 ta to'liq, 2 ta −10% (1 800 000), 1 ta −25% (1 500 000), 1 ta grant (100%)."""

    def setUp(self):
        call_command('create_orgs', verbosity=0)
        self.today = timezone.localdate()
        self.month = self.today.replace(day=1)
        self.org = Organization.objects.get(name='Asosiy maktab')
        self.branch = Branch.objects.get(organization=self.org)
        cfg = BillingSettings.get(self.org)
        cfg.monthly_price, cfg.billing_start = 2_000_000, self.month
        cfg.save()
        self.d10 = Discount.objects.create(organization=self.org, name='10%', percent=10)
        self.d25 = Discount.objects.create(organization=self.org, name='25%', percent=25)
        self.grant = Discount.objects.create(organization=self.org, name='Grant', percent=100)
        self.group = Group.objects.create(name='5-A', branch=self.branch)
        self.students = []
        plan = [None] * 6 + [self.d10] * 2 + [self.d25] + [self.grant]
        for i, disc in enumerate(plan):
            u = User.objects.create_user(f's{i}', password='x', role='student', first_name=f'S{i}', last_name='T')
            st = Student.objects.create(user=u, group=self.group, branch=self.branch)
            if disc:
                StudentDiscount.objects.create(student=st, discount=disc)
            self.students.append(st)
        ensure_charges([s.pk for s in self.students], self.today)
        self.owner = User.objects.create_user('boss', password='x', role='staff', is_superuser=True, is_staff=True)

    def report(self, **kw):
        return owner_stats.build_report(self.owner, self.month, self.today, **kw)

    def org_row(self, rep):
        return next(o for o in rep['orgs'] if o['org'] == self.org)

    def test_expected_income_with_discounts_and_grant(self):
        o = self.org_row(self.report())
        self.assertEqual(o['total']['expected'], 6 * 2_000_000 + 2 * 1_800_000 + 1_500_000)
        tiers = {(t['percent'], t['price']): t['n'] for t in o['tier_rows']}
        self.assertEqual(tiers[(Decimal(0), Decimal(2_000_000))], 6)
        self.assertEqual(tiers[(Decimal(10), Decimal(1_800_000))], 2)
        self.assertEqual(tiers[(Decimal(25), Decimal(1_500_000))], 1)
        self.assertEqual(tiers[(Decimal(100), Decimal(0))], 1)
        self.assertIn('Grant (100% chegirma)', [t['label'] for t in o['tier_rows']])
        self.assertEqual(o['total']['students'], 10)

    def test_profit_is_cash_income_minus_expenses_including_salary(self):
        Payment.objects.create(student=self.students[0], amount=2_000_000, paid_on=self.today)
        Payment.objects.create(student=self.students[1], amount=1_000_000, paid_on=self.today)
        voided = Payment.objects.create(student=self.students[2], amount=9_000_000, paid_on=self.today, voided=True)
        cat, _ = ExpenseCategory.objects.get_or_create(name='Ijara')
        sal, _ = ExpenseCategory.objects.get_or_create(name='Maosh')
        Expense.objects.create(branch=self.branch, category=cat, date=self.today, amount=500_000)
        Expense.objects.create(branch=self.branch, category=sal, date=self.today, amount=700_000)
        o = self.org_row(self.report())['total']
        self.assertEqual(o['income_m'], 3_000_000)      # bekor qilingan to'lov hisobga olinmaydi
        self.assertEqual(o['expense_m'], 1_200_000)
        self.assertEqual(o['profit_m'], 1_800_000)
        self.assertEqual(o['pct'], round(100 * 3_000_000 / o['expected']))
        self.assertEqual(o['left'], o['expected'] - 3_000_000)
        self.assertTrue(voided.voided)

    def test_debt_is_charged_minus_paid(self):
        Payment.objects.create(student=self.students[0], amount=500_000, paid_on=self.today)
        o = self.org_row(self.report())['total']
        self.assertEqual(o['debt'], o['expected'] - 500_000)

    def test_center_branches_are_separate(self):
        center = Organization.objects.get(name="O'quv markaz")
        b2 = Branch.objects.create(organization=center, name='Filial 2')
        b1 = Branch.objects.get(organization=center, name='Filial 1')
        cfg = BillingSettings.get(center)
        cfg.monthly_price, cfg.billing_start = 1_000_000, self.month
        cfg.save()
        for n, br in (('a', b1), ('b', b2), ('c', b2)):
            u = User.objects.create_user(f'c{n}', password='x', role='student')
            Student.objects.create(user=u, branch=br, group=Group.objects.create(name=f'g{n}', branch=br))
        ensure_charges(list(Student.objects.filter(branch__in=[b1, b2]).values_list('pk', flat=True)), self.today)
        o = next(x for x in self.report()['orgs'] if x['org'] == center)
        self.assertTrue(o['multi'])
        counts = {r['branch'].name: r['students'] for r in o['rows']}
        self.assertEqual(counts['Filial 1'], 1)
        self.assertEqual(counts['Filial 2'], 2)
        self.assertEqual(o['total']['expected'], 3_000_000)

    def test_scope_limits_report_to_selected_org(self):
        self.owner._scope_ids = [self.branch.pk]
        rep = self.report()
        self.assertEqual([o['org'] for o in rep['orgs']], [self.org])

    def test_page_renders_for_owner_and_old_panel_still_available(self):
        self.client.force_login(self.owner)
        body = self.client.get(reverse('panel:dashboard')).content.decode()
        self.assertIn('kassaga kirgan pul', body)
        self.assertIn('Grant (100% chegirma)', body)
        old = self.client.get(reverse('panel:dashboard') + '?kunlik=1').content.decode()
        self.assertIn('Bugun maktabda', old)

    def test_non_owner_gets_daily_panel(self):
        from panel.models import Position, StaffProfile
        pos = Position.objects.create(name='Hisobchi X')
        u = User.objects.create_user('acc', password='x', role='staff')
        StaffProfile.objects.create(user=u, position=pos)
        u.branches.add(self.branch)
        self.client.force_login(u)
        r = self.client.get(reverse('panel:dashboard'))
        self.assertNotIn('kassaga kirgan pul', r.content.decode())

    def test_month_parsing_never_future(self):
        self.assertEqual(owner_stats.parse_month('2099-01', self.today), self.month)
        self.assertEqual(owner_stats.parse_month('abc', self.today), self.month)
        self.assertEqual(owner_stats.parse_month('2026-03', self.today), date(2026, 3, 1))
