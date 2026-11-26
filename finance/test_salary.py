"""Oylik: qo'shishda kiritish, kartadagi blok, xodimlar oyligi ro'yxati, avans (15-kun, summa qo'lda) va yakuniy hisob, eslatma."""
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from finance import payroll, salary
from finance.models import Payslip, SalaryRule
from panel.test_stage1 import Base


class SalaryBase(Base):
    def setUp(self):
        super().setUp()
        self.acc = self.staff('hisob', ['payroll.view', 'payroll.manage', 'teachers.view', 'staff.view'], self.c1, self.c2)
        self.month = timezone.localdate().replace(day=1)

    def teacher(self, phone, *branches):
        t = User.objects.create_user(phone, password='x', role='teacher', first_name='T', last_name=phone)
        t.branches.set(branches)
        return t


class CreateWithSalaryTests(SalaryBase):
    def test_owner_sets_fixed_salary_when_adding_teacher(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('panel:teacher_add'), {'last_name': 'K', 'first_name': 'N', 'phone': '+998 90 300-00-01',
                                                        'branch': [self.c1.pk, self.c2.pk], 'salary_kind': 'fixed', 'salary_amount': '3 000 000'})
        t = User.objects.get(phone_digits='998903000001')
        rules = list(SalaryRule.objects.filter(employee=t))
        self.assertEqual(len(rules), 1)                      # qat'iy oylik — faqat birinchi filialga (ikki marta hisoblanmasin)
        self.assertEqual(rules[0].amount, Decimal(3000000))
        self.assertEqual(rules[0].effective_from, self.month)

    def test_percent_goes_to_every_branch(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('panel:teacher_add'), {'last_name': 'K', 'first_name': 'N', 'phone': '+998 90 300-00-02',
                                                        'branch': [self.c1.pk, self.c2.pk], 'salary_kind': 'percent', 'salary_percent': '40'})
        t = User.objects.get(phone_digits='998903000002')
        self.assertEqual(SalaryRule.objects.filter(employee=t, kind='percent').count(), 2)

    def test_missing_amount_is_an_error(self):
        self.client.force_login(self.owner)
        r = self.client.post(reverse('panel:teacher_add'), {'last_name': 'K', 'first_name': 'N', 'phone': '+998 90 300-00-03',
                                                            'branch': [self.c1.pk], 'salary_kind': 'fixed'})
        self.assertContains(r, 'Oylik summasini kiriting')
        self.assertFalse(User.objects.filter(phone_digits='998903000003').exists())

    def test_salary_optional(self):
        self.client.force_login(self.owner)
        self.client.post(reverse('panel:teacher_add'), {'last_name': 'K', 'first_name': 'N', 'phone': '+998 90 300-00-04', 'branch': [self.c1.pk]})
        t = User.objects.get(phone_digits='998903000004')
        self.assertFalse(SalaryRule.objects.filter(employee=t).exists())

    def test_director_without_payroll_sees_no_salary_fields(self):
        d = self.staff('dir', ['teachers.view', 'teachers.add'], self.c1)
        self.client.force_login(d)
        body = self.client.get(reverse('panel:teacher_add')).content.decode()
        self.assertNotIn('name="salary_kind"', body)
        self.assertIn('hisobchi', body)
        self.client.post(reverse('panel:teacher_add'), {'last_name': 'K', 'first_name': 'N', 'phone': '+998 90 300-00-05',
                                                        'salary_kind': 'fixed', 'salary_amount': '9000000'})
        t = User.objects.get(phone_digits='998903000005')
        self.assertFalse(SalaryRule.objects.filter(employee=t).exists())     # ruxsatsiz yuborilgan oylik e'tiborsiz

    def test_staff_add_with_salary(self):
        from panel.models import Position
        pos = Position.objects.create(name='Zavxoz X')
        self.client.force_login(self.owner)
        self.client.post(reverse('panel:staff_add'), {'last_name': 'A', 'first_name': 'B', 'phone': '+998 90 300-00-06', 'position': pos.pk,
                                                      'branch': [self.b_school.pk], 'salary_kind': 'fixed', 'salary_amount': '2500000'})
        u = User.objects.get(phone_digits='998903000006')
        self.assertEqual(SalaryRule.current(u, self.b_school, self.month).amount, Decimal(2500000))


class CardAndEditTests(SalaryBase):
    def setUp(self):
        super().setUp()
        self.t = self.teacher('ust1', self.c1)

    def test_card_shows_unset_then_set(self):
        self.client.force_login(self.acc)
        r = self.client.get(reverse('panel:teacher', args=[self.t.pk]))
        self.assertContains(r, 'oylik belgilanmagan')
        r = self.client.post(reverse('panel:employee_salary', args=[self.t.pk]),
                             {'branch': self.c1.pk, 'salary_kind': 'fixed', 'salary_amount': '4 000 000', 'effective_from': f'{self.month:%Y-%m}'},
                             follow=True)
        self.assertContains(r, 'Oylik saqlandi')
        self.assertTrue(Payslip.objects.filter(employee=self.t, month=self.month, base_amount=4000000).exists())   # shu oy darhol hisoblandi
        r = self.client.get(reverse('panel:teacher', args=[self.t.pk]))
        self.assertContains(r, '4 000 000')
        self.assertContains(r, 'Avans')

    def test_raise_from_next_month_keeps_current(self):
        SalaryRule.objects.create(employee=self.t, branch=self.c1, effective_from=self.month, amount=3000000)
        nxt = (self.month + timedelta(days=32)).replace(day=1)
        self.client.force_login(self.acc)
        self.client.post(reverse('panel:employee_salary', args=[self.t.pk]),
                         {'branch': self.c1.pk, 'salary_kind': 'fixed', 'salary_amount': '3500000', 'effective_from': f'{nxt:%Y-%m}'})
        self.assertEqual(SalaryRule.current(self.t, self.c1, self.month).amount, 3000000)
        self.assertEqual(SalaryRule.current(self.t, self.c1, nxt).amount, 3500000)

    def test_same_value_creates_nothing(self):
        SalaryRule.objects.create(employee=self.t, branch=self.c1, effective_from=self.month, amount=3000000)
        self.client.force_login(self.acc)
        self.client.post(reverse('panel:employee_salary', args=[self.t.pk]),
                         {'branch': self.c1.pk, 'salary_kind': 'fixed', 'salary_amount': '3000000', 'effective_from': f'{self.month:%Y-%m}'})
        self.assertEqual(SalaryRule.objects.filter(employee=self.t).count(), 1)

    def test_director_without_payroll_sees_no_salary_card(self):
        d = self.staff('dir', ['teachers.view'], self.c1)
        self.client.force_login(d)
        self.assertNotContains(self.client.get(reverse('panel:teacher', args=[self.t.pk])), 'Oylik <small')
        self.assertEqual(self.client.get(reverse('panel:employee_salary', args=[self.t.pk])).status_code, 403)

    def test_people_list_unset_first_and_founder_hidden(self):
        boss = self.staff('founder2', [], self.c1, owner=True)
        SalaryRule.objects.create(employee=self.teacher('ust2', self.c1), branch=self.c1, effective_from=self.month, amount=1)
        self.client.force_login(self.acc)
        body = self.client.get(reverse('panel:salary_rules'), {'filial': self.c1.pk}).content.decode()
        self.assertIn('belgilanmagan', body)
        self.assertLess(body.index('ust1'), body.index('ust2'))
        self.assertNotIn(boss.last_name, body)


class ScheduleTests(SalaryBase):
    def setUp(self):
        super().setUp()
        self.t = self.teacher('ust1', self.c1)
        SalaryRule.objects.create(employee=self.t, branch=self.c1, effective_from=self.month, amount=3000000)

    def test_advance_is_entered_amount(self):
        payroll.ensure_payslips(self.c1, self.month)
        slip = Payslip.objects.get(employee=self.t)
        st = salary.slip_status(slip)
        self.assertEqual((st['adv_paid'], st['adv_waiting'], st['remaining']), (0, True, Decimal(3000000)))
        payroll.pay(slip, 700000, 'advance', timezone.localdate(), 'cash', self.acc)     # hisobchi istalgan summani yozadi
        slip = Payslip.objects.prefetch_related('payments').get(pk=slip.pk)
        st = salary.slip_status(slip)
        self.assertEqual((st['adv_paid'], st['adv_waiting'], st['remaining']), (Decimal(700000), False, Decimal(2300000)))
        sch = salary.schedule(self.center, self.month, [slip], timezone.localdate())['advance']
        self.assertEqual((sch['paid'], sch['given'], sch['people']), (Decimal(700000), 1, 0))

    def test_payroll_page_autocalculates_and_shows_both_dates(self):
        self.client.force_login(self.acc)
        r = self.client.get(reverse('panel:payroll'), {'filial': self.c1.pk, 'oy': f'{self.month:%Y-%m}'})
        self.assertContains(r, 'Avans')
        self.assertContains(r, 'Yakuniy hisob')
        self.assertTrue(Payslip.objects.filter(employee=self.t, month=self.month).exists())
        slip = Payslip.objects.get(employee=self.t)
        r = self.client.get(reverse('panel:payslip_pay', args=[slip.pk]), {'turi': 'avans'})
        self.assertNotContains(r, '1 500 000')                       # avans summasi oldindan to'ldirilmaydi
        self.assertContains(r, 'hali berilmagan')

    def test_settings_change_advance(self):
        self.client.force_login(self.acc)
        self.client.post(reverse('panel:payroll_settings'), {'filial': self.c1.pk, 'advance_day': 16})
        self.center.refresh_from_db()
        self.assertEqual(self.center.advance_day, 16)

    def test_reminder_window(self):
        def at(day):
            return self.month.replace(day=day)
        self.assertTrue(any(p['kind'] == 'advance' for p in salary.reminders(self.acc, at(13))))     # 2 kun qoldi
        self.assertFalse(any(p['kind'] == 'advance' for p in salary.reminders(self.acc, at(5))))     # hali erta
        slip = Payslip.objects.get(employee=self.t, month=self.month)
        payroll.pay(slip, 500000, 'advance', at(1), 'cash', self.acc)
        self.assertFalse(any(p['kind'] == 'advance' for p in salary.reminders(self.acc, at(15))))    # avans berilgan
        end = salary.month_end(self.month)
        self.assertTrue(any(p['kind'] == 'final' for p in salary.reminders(self.acc, end)))

    def test_dashboard_shows_reminder(self):
        self.client.force_login(self.acc)
        with mock.patch('panel.views_core.timezone.localdate', return_value=self.month.replace(day=14)):
            r = self.client.get(reverse('panel:dashboard'), {'kunlik': 1})
        self.assertContains(r, 'payday')
