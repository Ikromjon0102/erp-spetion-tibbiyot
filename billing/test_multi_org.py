"""Narx tashkilot bo'yicha, guruhda ixtiyoriy o'zgartiriladi; chegirmalar tashkilotga bog'langan."""
from datetime import date
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from academics.models import Group
from accounts.models import Student, User
from billing.models import BillingSettings, Charge, Discount, StudentDiscount
from billing.services import account, org_of, price_for, summaries
from org.models import Branch, Organization, default_branch
from panel.models import Position, StaffProfile

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
TODAY = date.today()
THIS_MONTH = TODAY.replace(day=1)


def student(first, group):
    u = User.objects.create_user(username=f'u-{first}', password='x', role='student', first_name=first, last_name='T')
    return Student.objects.create(user=u, group=group)


def staff(username, position, branch):
    user = User.objects.create_user(username=username, password='x', role='staff')
    p = Position.objects.get(name=position)
    StaffProfile.objects.create(user=user, position=p, perms=list(p.default_perms))
    user.branches.set([branch])
    return user


@FAST
class MultiOrgBillingTests(TestCase):
    def setUp(self):
        cache.clear()
        self.med = default_branch()
        self.org_med = self.med.organization
        self.org_c = Organization.objects.create(name='Markaz', kind='center', brand_color='#b91c1c')
        self.center = Branch.objects.create(organization=self.org_c, name='Filial 1')

        for org, price, due in ((self.org_med, 1_000_000, 10), (self.org_c, 400_000, 5)):
            BillingSettings.objects.update_or_create(organization=org, defaults={'monthly_price': price, 'due_day': due, 'billing_start': THIS_MONTH})

        self.g_med = Group.objects.create(name='5-A', branch=self.med)
        self.g_eng = Group.objects.create(name='Ingliz A1', branch=self.center)                        # umumiy narx
        self.g_math = Group.objects.create(name='Matematika', branch=self.center, monthly_price=550_000)  # o'z narxi
        self.s_med, self.s_eng, self.s_math = student('Med', self.g_med), student('Eng', self.g_eng), student('Math', self.g_math)

    def test_price_per_organization_and_group(self):
        cfg_c = BillingSettings.get(self.org_c)
        self.assertEqual(price_for(self.s_med, BillingSettings.get(self.org_med)), 1_000_000)
        self.assertEqual(price_for(self.s_eng, cfg_c), 400_000)       # guruh narxi yo'q: tashkilotniki
        self.assertEqual(price_for(self.s_math, cfg_c), 550_000)      # guruh narxi ustun

    def test_charges_use_right_price(self):
        sums = summaries([self.s_med.pk, self.s_eng.pk, self.s_math.pk])
        self.assertEqual(sums[self.s_med.pk]['charged'], 1_000_000)
        self.assertEqual(sums[self.s_eng.pk]['charged'], 400_000)
        self.assertEqual(sums[self.s_math.pk]['charged'], 550_000)
        self.assertEqual(account(self.s_math)['price'], 550_000)

    def test_new_organization_without_price_bills_nothing(self):
        org3 = Organization.objects.create(name='Bogcha', kind='kindergarten')
        b3 = Branch.objects.create(organization=org3, name='Asosiy')
        s = student('Kg', Group.objects.create(name='Gul', branch=b3))
        self.assertEqual(summaries([s.pk])[s.pk]['charged'], 0)
        self.assertEqual(Charge.objects.filter(student=s).count(), 0)

    def test_discount_applies_to_group_price(self):
        d = Discount.objects.create(organization=self.org_c, name='Aka-uka', percent=10)
        StudentDiscount.objects.create(student=self.s_math, discount=d)
        self.assertEqual(summaries([self.s_math.pk])[self.s_math.pk]['charged'], 495_000)

    def test_group_price_change_updates_current_month_only(self):
        summaries([self.s_math.pk])
        old = Charge.objects.create(student=self.s_math, month=date(2025, 1, 1), base_price=550_000, amount=550_000)
        owner = staff('egasi', 'Maktab egasi', self.med)
        self.client.force_login(owner)
        self.client.post(reverse('panel:group_edit', args=[self.g_math.pk]), {'name': 'Matematika', 'year': 2026, 'monthly_price': '600000'})
        self.g_math.refresh_from_db()
        self.assertEqual(self.g_math.monthly_price, 600_000)
        self.assertEqual(Charge.objects.get(student=self.s_math, month=THIS_MONTH).amount, 600_000)
        old.refresh_from_db()
        self.assertEqual(old.amount, 550_000)      # o'tgan oy o'zgarmaydi

    def test_org_price_change_does_not_touch_other_org(self):
        summaries([self.s_med.pk, self.s_eng.pk])
        owner = staff('egasi', 'Maktab egasi', self.med)
        self.client.force_login(owner)
        r = self.client.post(reverse('panel:finance_settings'), {'org': self.org_c.pk, 'monthly_price': 450000, 'due_day': 5,
                                                                  'billing_start': THIS_MONTH.isoformat()})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(BillingSettings.get(self.org_c).monthly_price, 450_000)
        self.assertEqual(BillingSettings.get(self.org_med).monthly_price, 1_000_000)
        self.assertEqual(Charge.objects.get(student=self.s_eng, month=THIS_MONTH).amount, 450_000)
        self.assertEqual(Charge.objects.get(student=self.s_med, month=THIS_MONTH).amount, 1_000_000)

    def test_due_day_per_organization(self):
        # to'lov muddati tashkilotga qarab: 5-kunlik tashkilotda 6-sanada muddati o'tgan, 10-kunlikda emas
        day = THIS_MONTH.replace(day=7)
        sums = summaries([self.s_med.pk, self.s_eng.pk], today=day)
        self.assertEqual(sums[self.s_eng.pk]['overdue'], 400_000)
        self.assertEqual(sums[self.s_med.pk]['overdue'], 0)

    def test_staff_cannot_change_other_org_settings(self):
        director = staff('dirc', 'Direktor', self.center)
        self.client.force_login(director)
        self.client.post(reverse('panel:finance_settings'), {'org': self.org_med.pk, 'monthly_price': 1, 'due_day': 1,
                                                              'billing_start': THIS_MONTH.isoformat()})
        self.assertEqual(BillingSettings.get(self.org_med).monthly_price, 1_000_000)      # o'z tashkilotiga yozildi, med'ga emas
        self.assertEqual(BillingSettings.get(self.org_c).monthly_price, 1)

    def test_discounts_scoped_by_org(self):
        Discount.objects.create(organization=self.org_med, name='MedChegirma', percent=5)
        Discount.objects.create(organization=self.org_c, name='MarkazChegirma', percent=5)
        director = staff('dirc', 'Direktor', self.center)
        self.client.force_login(director)
        body = self.client.get(reverse('panel:discounts')).content.decode()
        self.assertIn('MarkazChegirma', body)
        self.assertNotIn('MedChegirma', body)
        med_d = Discount.objects.get(name='MedChegirma')
        self.assertEqual(self.client.get(reverse('panel:discount_edit', args=[med_d.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('panel:discount_delete', args=[med_d.pk])).status_code, 404)

    def test_cannot_assign_other_org_discount(self):
        med_d = Discount.objects.create(organization=self.org_med, name='MedChegirma', percent=5)
        director = staff('dirc', 'Direktor', self.center)
        self.client.force_login(director)
        self.client.post(reverse('panel:student_discount_add', args=[self.s_eng.pk]), {'discount': med_d.pk})
        self.assertFalse(StudentDiscount.objects.filter(student=self.s_eng).exists())

    def test_same_discount_name_allowed_in_different_orgs(self):
        Discount.objects.create(organization=self.org_med, name='Aka-uka', percent=5)
        Discount.objects.create(organization=self.org_c, name='Aka-uka', percent=10)
        self.assertEqual(Discount.objects.filter(name='Aka-uka').count(), 2)
        self.assertEqual(org_of(self.s_eng), self.org_c)
