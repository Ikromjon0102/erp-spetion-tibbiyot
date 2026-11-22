"""Tashkilot brendi: palitra, ota-ona ilovasida farzand almashganda rang o'zgarishi, panelda rangni o'zgartirish."""
from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.html import escape

from academics.models import Group
from accounts.models import Student, User
from org import theme
from org.models import Branch, Organization, default_branch
from panel.models import Position, StaffProfile

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


class PaletteTests(SimpleTestCase):
    def test_accent_is_the_brand_color_in_light_mode(self):
        self.assertEqual(theme.palette('#166534')['light']['--accent'], '#166534')
        self.assertEqual(theme.palette('#e53935')['light']['--accent'], '#E53935')

    def test_invalid_color_falls_back_to_default(self):
        for bad in ('', 'red', '#12', '#GGGGGG', None, 'url(x)'):
            self.assertEqual(theme.palette(bad)['light']['--accent'], '#166534')

    def test_css_contains_only_safe_values(self):
        css = theme.css('#1E3A8A"; }</style><script>alert(1)</script>')
        self.assertNotIn('<script', css)
        self.assertIn('#166534', css)      # noto'g'ri rang o'rniga standart olindi

    def test_text_is_readable_on_accent(self):
        for color in ('#166534', '#1E3A8A', '#E53935', '#F97316', '#FACC15'):
            for mode in ('light', 'dark'):
                p = theme.palette(color)[mode]
                lum = theme._luminance(p['--accent'])
                self.assertEqual(p['--on-accent'], '#FFFFFF' if lum < 0.5 else '#111111')

    def test_each_org_gets_a_different_palette(self):
        accents = {theme.palette(c)['light']['--accent'] for c in ('#166534', '#1E3A8A', '#E53935', '#F97316')}
        self.assertEqual(len(accents), 4)
        self.assertNotEqual(theme.palette('#166534')['light']['--bg'], theme.palette('#1E3A8A')['light']['--bg'])


@FAST
class ThemeViewsTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command('create_orgs', verbosity=0)
        self.med = default_branch()
        self.blue = Branch.objects.get(organization__name='Asosiy maktab')
        self.orange = Branch.objects.get(organization__name="Bog'cha")
        self.parent = User.objects.create_user('998930', password='x', role='parent', first_name='Ota')

        def kid(name, group):
            u = User.objects.create_user(f'k-{name}', password='x', role='student', first_name=name, last_name='T')
            s = Student.objects.create(user=u, group=group)
            s.parents.add(self.parent)
            return s
        self.k_med = kid('Ali', Group.objects.create(name='5-A', branch=self.med))
        self.k_blue = kid('Vali', Group.objects.create(name='6-B', branch=self.blue))
        self.k_kg = kid('Gul', Group.objects.create(name='Gul', branch=self.orange))
        self.client.force_login(self.parent)

    def page(self, student):
        return self.client.get(reverse('student_detail', args=[student.pk])).content.decode()

    def test_create_orgs_is_idempotent(self):
        call_command('create_orgs', verbosity=0)
        self.assertEqual(Organization.objects.count(), 4)
        self.assertFalse(Organization.objects.get(name="O'quv markaz").meals_enabled)

    def test_child_page_uses_childs_organization_color(self):
        self.assertIn('--accent:#166534', self.page(self.k_med))
        self.assertIn('--accent:#1E3A8A', self.page(self.k_blue))
        self.assertIn('--accent:#F97316', self.page(self.k_kg))
        self.assertIn('<meta name="theme-color" content="#1E3A8A">', self.page(self.k_blue))

    def test_other_orgs_color_not_leaked_into_page_css(self):
        body = self.page(self.k_blue)
        self.assertNotIn('--accent:#F97316', body)

    def test_switcher_shows_all_kids_with_org_dot(self):
        body = self.page(self.k_blue)
        for color in ('#166534', '#1E3A8A', '#F97316'):
            self.assertIn(f'background:{color}', body)
        for name in ('Ali', 'Vali', 'Gul'):
            self.assertIn(f'>{name}</a>', body.replace('</i>', ''))

    def test_home_lists_kids_from_all_orgs_with_org_names(self):
        body = self.client.get(reverse('home')).content.decode()
        for text in ('Ali', 'Vali', 'Gul', 'Med maktab', 'Asosiy maktab', "Bog'cha"):
            self.assertIn(escape(text), body)

    def test_cannot_open_other_parents_child(self):
        stranger = User.objects.create_user('998931', password='x', role='parent')
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(reverse('student_detail', args=[self.k_blue.pk])).status_code, 403)


@FAST
class OrgSettingsPanelTests(TestCase):
    def setUp(self):
        cache.clear()
        call_command('create_orgs', verbosity=0)
        self.med = default_branch()
        self.blue = Branch.objects.get(organization__name='Asosiy maktab')

        def staff(username, position, branch):
            user = User.objects.create_user(username, password='x', role='staff')
            p = Position.objects.get(name=position)
            StaffProfile.objects.create(user=user, position=p, perms=list(p.default_perms))
            user.branches.set([branch])
            return user
        self.owner = staff('egasi', 'Maktab egasi', self.med)
        self.blue_admin = staff('ko_k', 'Direktor', self.blue)
        self.reception = staff('rec', 'Reception', self.blue)

    def post(self, user, org, **data):
        self.client.force_login(user)
        return self.client.post(reverse('panel:org_settings'), {'org': org.pk, 'name': org.name, **data})

    def test_branch_admin_changes_own_org_color(self):
        org = self.blue.organization
        r = self.post(self.blue_admin, org, brand_color='#0f766e')
        self.assertEqual(r.status_code, 302)
        org.refresh_from_db()
        self.assertEqual(org.brand_color, '#0F766E')

    def test_branch_admin_cannot_change_other_org(self):
        med_org = self.med.organization
        self.post(self.blue_admin, med_org, brand_color='#000000')
        med_org.refresh_from_db()
        self.assertEqual(med_org.brand_color, '#166534')       # o'z tashkilotiga yozildi, med'ga emas

    def test_owner_can_pick_any_org_and_toggle_modules(self):
        org = Organization.objects.get(name="O'quv markaz")
        self.post(self.owner, org, brand_color='#111111', meals_enabled='on')
        org.refresh_from_db()
        self.assertEqual(org.brand_color, '#111111')
        self.assertTrue(org.meals_enabled)

    def test_branch_admin_cannot_toggle_modules(self):
        org = self.blue.organization
        before = org.meals_enabled
        self.post(self.blue_admin, org, brand_color='#0f766e', meals_enabled='' if before else 'on')
        org.refresh_from_db()
        self.assertEqual(org.meals_enabled, before)

    def test_invalid_color_rejected(self):
        org = self.blue.organization
        r = self.post(self.blue_admin, org, brand_color='red')
        self.assertEqual(r.status_code, 200)
        org.refresh_from_db()
        self.assertEqual(org.brand_color, '#1E3A8A')

    def test_staff_without_permission_gets_403(self):
        self.client.force_login(self.reception)
        self.assertEqual(self.client.get(reverse('panel:org_settings')).status_code, 403)

    def test_panel_is_themed_by_staffs_org(self):
        self.client.force_login(self.blue_admin)
        self.assertIn('--accent:#1E3A8A', self.client.get(reverse('panel:dashboard')).content.decode())
        self.client.force_login(self.owner)
        self.assertIn('--accent:#166534', self.client.get(reverse('panel:dashboard')).content.decode())
