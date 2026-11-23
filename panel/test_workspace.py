from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from academics.models import Group
from accounts.models import Student, User
from org.models import Branch, Organization
from panel.models import Position, StaffProfile


class WorkspaceFixture:
    def setUp(self):
        call_command('create_orgs', verbosity=0)
        self.school = Organization.objects.get(name='Asosiy maktab')
        self.kg = Organization.objects.get(name="Bog'cha")
        self.center = Organization.objects.get(name="O'quv markaz")
        self.b_school = Branch.objects.get(organization=self.school)
        self.b_kg = Branch.objects.get(organization=self.kg)
        self.c1 = Branch.objects.get(organization=self.center, name='Filial 1')
        self.c2 = Branch.objects.create(organization=self.center, name='Filial 2')
        for name, br in (('Aliyev', self.b_school), ('Valiyev', self.b_school), ('Gulova', self.b_kg), ('Soliyev', self.c1), ('Karimov', self.c2)):
            u = User.objects.create_user(f'u-{name}', password='x', role='student', first_name='X', last_name=name)
            Student.objects.create(user=u, branch=br, group=Group.objects.create(name=f'g-{name}', branch=br))
        self.owner = User.objects.create_user('boss', password='x', role='staff', is_superuser=True, is_staff=True)
        self.client.force_login(self.owner)

    def pick(self, value, nxt='/panel/oquvchilar/'):
        return self.client.get(reverse('panel:set_scope'), {'s': value, 'next': nxt})

    def students_page(self):
        return self.client.get(reverse('panel:students')).content.decode()


class WorkspaceScopeTests(WorkspaceFixture, TestCase):
    def test_all_scope_shows_org_cards_not_raw_list(self):
        body = self.students_page()
        self.assertIn('hub-card', body)
        self.assertNotIn('Aliyev', body)
        self.assertIn('Filial 2', body)          # markaz filiallari kartada alohida

    def test_search_bypasses_hub(self):
        body = self.client.get(reverse('panel:students'), {'q': 'Gulova'}).content.decode()
        self.assertIn('Gulova', body)
        self.assertNotIn('hub-card', body)

    def test_org_scope_limits_students(self):
        self.assertEqual(self.pick(f'org-{self.school.pk}').status_code, 302)
        body = self.students_page()
        self.assertIn('Aliyev', body)
        self.assertIn('Valiyev', body)
        self.assertNotIn('Gulova', body)
        self.assertNotIn('Soliyev', body)

    def test_branch_scope_is_even_narrower(self):
        self.pick(f'branch-{self.c2.pk}')
        body = self.students_page()
        self.assertIn('Karimov', body)
        self.assertNotIn('Soliyev', body)
        self.assertNotIn('Aliyev', body)

    def test_scope_persists_and_can_return_to_all(self):
        self.pick(f'org-{self.kg.pk}')
        self.assertIn('Gulova', self.students_page())
        self.pick('all')
        self.assertIn('hub-card', self.students_page())

    def test_dashboard_follows_scope(self):
        self.pick(f'org-{self.kg.pk}', '/panel/')
        body = self.client.get(reverse('panel:dashboard')).content.decode()
        self.assertIn('Bog&#x27;cha', body)
        self.assertNotIn('Asosiy maktab</h3>', body)
        self.assertIn('--accent:' + self.kg.brand_color.upper(), body)       # panel tanlangan tashkilot rangida

    def test_bad_scope_values_fall_back_to_all(self):
        for bad in ('org-99999', 'branch-abc', 'zzz', ''):
            self.pick(bad)
            self.assertIn('hub-card', self.students_page())

    def test_next_cannot_leave_panel(self):
        r = self.pick('all', 'https://evil.example/')
        self.assertEqual(r['Location'], '/panel/')

    def staff(self, username, *branches):
        pos = Position.objects.create(name=f'Lavozim {username}')
        u = User.objects.create_user(username, password='x', role='staff')
        StaffProfile.objects.create(user=u, position=pos, perms=['students.view', 'teachers.view'])
        u.branches.set(branches)       # signal asosiy filialni avtomatik qo'shgan bo'lishi mumkin
        return u

    def test_single_branch_staff_has_no_selector_and_no_hub(self):
        u = self.staff('dir', self.b_school)
        self.client.force_login(u)
        body = self.students_page()
        self.assertNotIn('hub-card', body)
        self.assertNotIn('id="wsp"', body)
        self.assertIn('Aliyev', body)
        self.assertNotIn('Gulova', body)

    def test_multi_branch_staff_gets_selector_limited_to_own_branches(self):
        u = self.staff('mgr', self.b_school, self.b_kg)
        self.client.force_login(u)
        body = self.students_page()
        self.assertIn('hub-card', body)
        self.assertNotIn('Soliyev', body)
        self.assertNotIn('Filial 2', body)
        # ruxsatsiz filialni tanlab bo'lmaydi
        self.pick(f'branch-{self.c1.pk}')
        self.assertIn('hub-card', self.students_page())
        self.pick(f'org-{self.kg.pk}')
        self.assertIn('Gulova', self.students_page())

    def test_teachers_hub_and_scope(self):
        t = User.objects.create_user('t1', password='x', role='teacher', first_name='Ustoz', last_name='Birinchi')
        t.branches.add(self.b_kg)
        body = self.client.get(reverse('panel:teachers')).content.decode()
        self.assertIn('hub-card', body)
        self.pick(f'org-{self.kg.pk}', '/panel/ustozlar/')
        self.assertIn('Birinchi', self.client.get(reverse('panel:teachers')).content.decode())
        self.pick(f'org-{self.school.pk}', '/panel/ustozlar/')
        self.assertNotIn('Birinchi', self.client.get(reverse('panel:teachers')).content.decode())


class SectionHubTests(WorkspaceFixture, TestCase):
    """Hamma bo'lim «Hammasi»da tashkilot kartalari, tashkilot tanlansa — odatiy sahifa."""

    def test_every_section_has_hub_and_drills_down(self):
        for name in ('groups', 'schedule', 'finance', 'expenses', 'payroll', 'news', 'devices', 'teachers', 'staff', 'parents', 'students'):
            self.pick('all')
            r = self.client.get(reverse(f'panel:{name}'))
            self.assertEqual(r.status_code, 200, name)
            self.assertIn('hub-card', r.content.decode(), name)
            self.pick(f'org-{self.kg.pk}', reverse(f'panel:{name}'))
            r = self.client.get(reverse(f'panel:{name}'))
            self.assertEqual(r.status_code, 200, name)
            self.assertNotIn('hub-card', r.content.decode(), name)


class BranchLevelHubTests(WorkspaceFixture, TestCase):
    """Bitta tashkilot, bir nechta filial (markaz direktori yoki founder «Markaz»ni tanlaganda) — filial kartalari."""

    def center_director(self):
        pos = Position.objects.create(name='Markaz direktori X')
        u = User.objects.create_user('mdir', password='x', role='staff')
        StaffProfile.objects.create(user=u, position=pos, perms=['students.view', 'teachers.view', 'devices.view', 'payments.view', 'monitoring.view'])
        u.branches.set([self.c1, self.c2])
        return u

    def test_center_director_sees_branch_cards(self):
        self.client.force_login(self.center_director())
        body = self.students_page()
        self.assertIn('hub-card', body)
        self.assertIn('Filial 1', body)
        self.assertIn('Filial 2', body)
        self.assertIn('filiali', body)
        self.assertNotIn('Soliyev', body)                    # ro'yxat emas, kartalar
        for name in ('teachers', 'devices', 'finance'):
            self.assertIn('hub-card', self.client.get(reverse(f'panel:{name}')).content.decode(), name)

    def test_branch_card_opens_branch_list(self):
        self.client.force_login(self.center_director())
        self.pick(f'branch-{self.c2.pk}')
        body = self.students_page()
        self.assertIn('Karimov', body)
        self.assertNotIn('Soliyev', body)

    def test_owner_choosing_center_gets_branch_cards(self):
        self.pick(f'org-{self.center.pk}')
        body = self.students_page()
        self.assertIn('hub-card', body)
        self.assertIn('branch-', body)

    def test_dashboard_has_per_branch_table(self):
        self.client.force_login(self.center_director())
        body = self.client.get(reverse('panel:dashboard')).content.decode()
        self.assertIn("Filiallar bo'yicha", body)
        self.assertIn('units-tbl', body)

    def test_single_branch_org_has_no_hub(self):
        self.pick(f'org-{self.school.pk}')
        self.assertNotIn('hub-card', self.students_page())
