"""Taomnoma: sikl hisobi, menyu yuklash, taom rasmi (bir marta), ota-ona sahifasi, ruxsat va tashkilotlar ajratilishi."""
import shutil
import tempfile
from datetime import date, timedelta
from io import BytesIO

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from academics.models import Group
from accounts.models import Student, User
from meals import services
from meals.models import Dish, MealPlan, MealType, MenuEntry, NoMealDay
from org.models import Branch, Organization, default_branch
from panel.access import can
from panel.models import Position, StaffProfile

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
MONDAY = date(2026, 11, 2)       # dushanba


def staff(username, position, branch, perms=None):
    user = User.objects.create_user(username=username, password='x', role='staff')
    p = Position.objects.get(name=position)
    StaffProfile.objects.create(user=user, position=p, perms=list(p.default_perms) if perms is None else perms)
    user.branches.set([branch])
    return user


def image(name='x.png', size=(3000, 2000), fmt='PNG'):
    from PIL import Image
    buf = BytesIO()
    Image.new('RGB', size, 'orange').save(buf, fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


class MediaMixin:
    def use_temp_media(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)


@FAST
class CycleTests(TestCase):
    def setUp(self):
        self.org = default_branch().organization
        self.org.meals_enabled = True
        self.org.save()
        self.plan = services.get_plan(self.org)
        self.plan.anchor_date, self.plan.anchor_day = MONDAY, 1
        self.plan.weekdays = '0,1,2,3,4,5'
        self.plan.save()

    def day(self, d):
        return self.plan.cycle_day(d)

    def test_counts_only_served_days(self):
        self.assertEqual(self.day(MONDAY), 1)
        self.assertEqual(self.day(MONDAY + timedelta(days=5)), 6)       # shanba
        self.assertIsNone(self.day(MONDAY + timedelta(days=6)))         # yakshanba: ovqat yo'q
        self.assertEqual(self.day(MONDAY + timedelta(days=7)), 7)       # keyingi dushanba davom etadi
        self.assertEqual(self.day(MONDAY + timedelta(days=12)), 12)

    def test_wraps_after_cycle_length(self):
        self.assertEqual(self.day(MONDAY + timedelta(days=14 + 2 + 0)), 15 % 14 or 14)   # 14 ta ovqatli kundan keyin 1-kun
        self.assertEqual(self.day(MONDAY + timedelta(days=16)), 1)

    def test_before_anchor_is_none(self):
        self.assertIsNone(self.day(MONDAY - timedelta(days=1)))

    def test_holiday_pauses_the_cycle(self):
        NoMealDay.objects.create(organization=self.org, start=MONDAY + timedelta(days=1), end=MONDAY + timedelta(days=3), reason='Bayram')
        self.assertEqual(self.day(MONDAY), 1)
        self.assertIsNone(self.day(MONDAY + timedelta(days=2)))
        self.assertEqual(self.day(MONDAY + timedelta(days=4)), 2)       # payshanba: seshanba-chorshanba o'tib ketmadi, sikl to'xtab turdi

    def test_changing_weekdays_does_not_break_todays_cycle_day(self):
        wed = MONDAY + timedelta(days=2)
        before = self.plan.cycle_day(wed)
        self.plan.set_weekdays({0, 1, 2, 3, 4}, today=wed)       # shanba olib tashlandi
        self.plan.save()
        self.assertEqual(self.plan.cycle_day(wed), before)
        self.assertEqual(self.plan.cycle_day(wed + timedelta(days=1)), before + 1)
        self.assertIsNone(self.plan.cycle_day(MONDAY + timedelta(days=5)))

    def test_adding_saturday_later_keeps_continuity(self):
        friday = MONDAY + timedelta(days=11)       # 2-haftaning juma kuni
        self.plan.weekdays = '0,1,2,3,4'
        self.plan.anchor_date, self.plan.anchor_day = MONDAY, 1
        self.plan.save()
        d = self.plan.cycle_day(friday)
        self.plan.set_weekdays({0, 1, 2, 3, 4, 5}, today=friday)       # dekabrdan shanba qo'shildi
        self.plan.save()
        self.assertEqual(self.plan.cycle_day(friday), d)
        self.assertEqual(self.plan.cycle_day(friday + timedelta(days=1)), d % 14 + 1)      # shanba — keyingi kun

    def test_set_today(self):
        self.plan.set_today(9, today=MONDAY + timedelta(days=21))
        self.assertEqual(self.plan.cycle_day(MONDAY + timedelta(days=21)), 9)


class HelperTests(TestCase):
    def test_split_dishes(self):
        self.assertEqual(services.split_dishes("Osh, salat; non\nchoy,  Osh ,,"), ['Osh', 'salat', 'non', 'choy'])
        self.assertEqual(services.split_dishes(''), [])

    def test_same_dish_in_different_case_shares_one_record(self):
        a = services.find_or_create_dish('Non')
        b = services.find_or_create_dish('non')
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(Dish.objects.count(), 1)


@FAST
class SeedTests(TestCase):
    def setUp(self):
        call_command('create_orgs', verbosity=0)

    def test_seed_menu_loads_14_days_for_school_orgs(self):
        call_command('seed_menu', verbosity=0)
        for org in Organization.objects.filter(kind='school'):
            self.assertEqual(MenuEntry.objects.filter(organization=org).count(), 28)        # 14 kun x 2 ovqat
            snack = MealType.objects.get(organization=org, name__startswith='Ikkinchi')
            for day in (6, 14):
                self.assertTrue(MenuEntry.objects.get(organization=org, cycle_day=day, meal_type=snack).not_served)
            first = MenuEntry.objects.get(organization=org, cycle_day=1, meal_type__name='Tushlik')
            self.assertEqual([d.name for d in first.ordered_dishes()], ["Mol go'shtli osh", 'Karam-sabzi salati', 'Non', 'Choy'])
        self.assertEqual(Dish.objects.filter(name__iexact='non').count(), 1)       # bitta rasm hamma kunlar uchun

    def test_seed_is_idempotent_and_skips_other_kinds(self):
        call_command('seed_menu', verbosity=0)
        n = MenuEntry.objects.count()
        call_command('seed_menu', verbosity=0)
        self.assertEqual(MenuEntry.objects.count(), n)
        self.assertFalse(MenuEntry.objects.filter(organization__kind='center').exists())


@FAST
class PanelTests(MediaMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.use_temp_media()
        call_command('create_orgs', verbosity=0)
        self.med = default_branch()
        self.blue = Branch.objects.get(organization__name='Asosiy maktab')
        self.kg = Branch.objects.get(organization__name="Bog'cha")
        for org in (self.med.organization, self.blue.organization, self.kg.organization):
            org.meals_enabled = True
            org.save()
        call_command('seed_menu', '--org', 'Tibbiyot maktabi', verbosity=0)
        self.owner = staff('egasi', 'Maktab egasi', self.med)
        self.zavxoz = staff('zav', 'Zavxoz', self.med)
        self.reception = staff('rec', 'Reception', self.med)
        self.blue_dir = staff('bluedir', 'Direktor', self.blue)

    def test_permissions(self):
        self.assertTrue(can(self.zavxoz, 'meals.manage'))
        self.assertTrue(can(self.blue_dir, 'meals.manage'))
        self.assertFalse(can(self.reception, 'meals.view'))
        self.client.force_login(self.reception)
        self.assertEqual(self.client.get(reverse('panel:meals')).status_code, 403)

    def test_founder_can_give_view_only(self):
        profile = StaffProfile.objects.get(user=self.reception)
        profile.perms = ['meals.view']
        profile.save()
        self.client.force_login(self.reception)
        self.assertEqual(self.client.get(reverse('panel:meals')).status_code, 200)
        self.assertEqual(self.client.get(reverse('panel:meals_day', args=[1])).status_code, 403)

    def test_menu_table_shows_dishes(self):
        self.client.force_login(self.zavxoz)
        body = self.client.get(reverse('panel:meals')).content.decode()
        self.assertIn("Mol go&#x27;shtli osh", body)
        self.assertIn('1-kun', body)
        self.assertIn('14-kun', body)

    def test_edit_day_saves_and_reuses_dishes(self):
        self.client.force_login(self.zavxoz)
        lunch = MealType.objects.get(organization=self.med.organization, name='Tushlik')
        snack = MealType.objects.get(organization=self.med.organization, name__startswith='Ikkinchi')
        self.client.post(reverse('panel:meals_day', args=[3]), {f'meal_{lunch.pk}': 'Palov, Non, Yangi salat', f'meal_{snack.pk}': '', f'ns_{snack.pk}': 'on'})
        e = MenuEntry.objects.get(organization=self.med.organization, cycle_day=3, meal_type=lunch)
        self.assertEqual([d.name for d in e.ordered_dishes()], ['Palov', 'Non', 'Yangi salat'])
        self.assertEqual(Dish.objects.filter(name__iexact='non').count(), 1)
        self.assertTrue(MenuEntry.objects.get(organization=self.med.organization, cycle_day=3, meal_type=snack).not_served)

    def test_other_org_staff_edits_only_their_own_menu(self):
        self.client.force_login(self.blue_dir)
        lunch_med = MealType.objects.get(organization=self.med.organization, name='Tushlik')
        self.client.post(reverse('panel:meals_day', args=[1]) + f'?org={self.med.organization.pk}', {f'meal_{lunch_med.pk}': 'Buzilgan'})
        e = MenuEntry.objects.get(organization=self.med.organization, cycle_day=1, meal_type=lunch_med)
        self.assertNotIn('Buzilgan', [d.name for d in e.ordered_dishes()])      # med menyusi o'zgarmadi
        body = self.client.get(reverse('panel:meals') + f'?org={self.med.organization.pk}').content.decode()
        self.assertNotIn("Mol go&#x27;shtli osh", body)           # o'z tashkiloti (menyusi hali bo'sh) ko'rinadi

    def test_photo_upload_once_and_shrunk(self):
        dish = Dish.objects.get(name__iexact='non')
        self.client.force_login(self.zavxoz)
        r = self.client.post(reverse('panel:dish_edit', args=[dish.pk]), {'name': 'Non', 'photo': image()})
        self.assertEqual(r.status_code, 302)
        dish.refresh_from_db()
        from PIL import Image
        with Image.open(dish.photo.path) as im:
            self.assertLessEqual(max(im.size), 1000)
            self.assertEqual(im.format, 'JPEG')

    def test_non_image_rejected(self):
        dish = Dish.objects.get(name__iexact='non')
        self.client.force_login(self.zavxoz)
        bad = SimpleUploadedFile('x.png', b'not an image', content_type='image/png')
        self.assertEqual(self.client.post(reverse('panel:dish_edit', args=[dish.pk]), {'name': 'Non', 'photo': bad}).status_code, 200)
        dish.refresh_from_db()
        self.assertFalse(dish.photo)

    def test_bulk_upload_matches_by_file_name(self):
        self.client.force_login(self.zavxoz)
        self.client.post(reverse('panel:dishes_bulk'), {'photos': [image('Non.jpg', (200, 200)), image("mol go'shtli osh.png", (200, 200)),
                                                                   image('nomalum_taom.png', (200, 200))]})
        self.assertTrue(Dish.objects.get(name__iexact='non').photo)
        self.assertTrue(Dish.objects.get(name="Mol go'shtli osh").photo)
        self.assertFalse(Dish.objects.filter(name__icontains='nomalum').exists())

    def test_cannot_delete_dish_in_use(self):
        dish = Dish.objects.get(name__iexact='non')
        self.client.force_login(self.zavxoz)
        self.client.post(reverse('panel:dish_delete', args=[dish.pk]))
        self.assertTrue(Dish.objects.filter(pk=dish.pk).exists())
        unused = Dish.objects.create(name='Ishlatilmagan')
        self.client.post(reverse('panel:dish_delete', args=[unused.pk]))
        self.assertFalse(Dish.objects.filter(pk=unused.pk).exists())

    def test_settings_today_day_and_holiday(self):
        self.client.force_login(self.zavxoz)
        self.client.post(reverse('panel:meals_settings'), {'action': 'plan', 'weekdays': ['0', '1', '2', '3', '4', '5', '6'], 'cycle_length': '14', 'today_day': '9'})
        plan = MealPlan.objects.get(organization=self.med.organization)
        self.assertEqual(plan.cycle_day(timezone.localdate()), 9)
        self.assertEqual(plan.days, {0, 1, 2, 3, 4, 5, 6})
        self.client.post(reverse('panel:meals_settings'), {'action': 'holiday_add', 'start': timezone.localdate().isoformat(), 'reason': 'Bayram'})
        self.assertIsNone(plan.cycle_day(timezone.localdate()))

    def test_photo_view_requires_login(self):
        dish = Dish.objects.get(name__iexact='non')
        services.save_dish_photo(dish, image('a.png', (100, 100)))
        self.assertEqual(self.client.get(reverse('dish_photo', args=[dish.pk])).status_code, 302)
        parent = User.objects.create_user('998950', password='x', role='parent')
        self.client.force_login(parent)
        r = self.client.get(reverse('dish_photo', args=[dish.pk]))
        self.assertEqual(r.status_code, 200)
        r.close()
        no_photo = Dish.objects.create(name='Rasmsiz')
        self.assertEqual(self.client.get(reverse('dish_photo', args=[no_photo.pk])).status_code, 404)


@FAST
class ParentViewTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command('create_orgs', verbosity=0)
        self.med = default_branch()
        self.blue = Branch.objects.get(organization__name='Asosiy maktab')
        self.markaz = Branch.objects.get(organization__name="O'quv markaz")
        for org in (self.med.organization, self.blue.organization):
            org.meals_enabled = True
            org.save()
            plan = services.get_plan(org)
            plan.weekdays = '0,1,2,3,4,5,6'        # kun haftasidan mustaqil bo'lsin
            plan.set_today(1)
            plan.save()
        lunch = MealType.objects.get(organization=self.med.organization, name='Tushlik')
        lunch_b = MealType.objects.get(organization=self.blue.organization, name='Tushlik')
        for day in range(1, 15):        # jadvalda haftaning hamma kuni ko'rinadi, shuning uchun sikl to'liq to'ldiriladi
            services.set_entry(self.med.organization, day, lunch, ['Osh', 'Non'])
            services.set_entry(self.blue.organization, day, lunch_b, ['Lag\'mon'])
        self.parent = User.objects.create_user('998960', password='x', role='parent')

        def kid(name, branch):
            u = User.objects.create_user(f'k-{name}', password='x', role='student', first_name=name, last_name='T')
            s = Student.objects.create(user=u, group=Group.objects.create(name=f'g-{name}', branch=branch))
            s.parents.add(self.parent)
            return s
        self.k_med, self.k_blue, self.k_center = kid('Ali', self.med), kid('Vali', self.blue), kid('Gul', self.markaz)
        self.client.force_login(self.parent)

    def page(self, student):
        return self.client.get(reverse('student_detail', args=[student.pk])).content.decode()

    def test_each_child_sees_own_organizations_menu(self):
        body = self.page(self.k_med)
        self.assertIn('data-meal=', body)
        self.assertIn('Osh', body)
        self.assertNotIn('Lag&#x27;mon', body)
        self.assertNotIn('Lag\\u0027mon', body)
        body = self.page(self.k_blue)
        self.assertIn('Lag&#x27;mon', body)
        self.assertNotIn('>Osh<', body)

    def test_menu_is_in_schedule_not_home_card(self):
        body = self.page(self.k_med)
        self.assertNotIn('Bugungi menyu', body)
        self.assertIn('class="row meal-row"', body)
        self.assertIn('12:30', body)        # tushlik standart soati

    def test_meal_time_is_editable(self):
        from datetime import time
        MealType.objects.filter(organization=self.med.organization, name='Tushlik').update(at=time(13, 15))
        self.assertIn('13:15', self.page(self.k_med))

    def test_center_has_no_menu(self):
        self.assertNotIn('meal-row"', self.page(self.k_center))

    def test_disabled_org_hides_menu(self):
        org = self.med.organization
        org.meals_enabled = False
        org.save()
        self.assertNotIn('data-meal=', self.page(self.k_med))

    def test_no_menu_on_holiday(self):
        NoMealDay.objects.create(organization=self.med.organization, start=timezone.localdate() - timedelta(days=7),
                                 end=timezone.localdate() + timedelta(days=14), reason='Bayram')
        self.assertNotIn('data-meal=', self.page(self.k_med))

    def test_shows_dish_photo_when_uploaded(self):
        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, True)
        with override_settings(MEDIA_ROOT=media):
            dish = Dish.objects.get(name='Osh')
            services.save_dish_photo(dish, image('a.png', (100, 100)))
            self.assertIn(reverse('dish_photo', args=[dish.pk]), self.page(self.k_med))
