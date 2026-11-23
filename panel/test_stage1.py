"""1-bosqich (audit, 2026-11-23): telefonda ish maydoni, guruh nomi filial ichida noyob, ustoz/xodim filiallarini tanlash."""
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from academics.models import Group
from accounts.models import Student, User
from accounts.student_import import import_rows
from org.models import Branch, Organization
from panel.models import Position, StaffProfile


class Base(TestCase):
    def setUp(self):
        call_command('create_orgs', verbosity=0)
        self.school = Organization.objects.get(name='Asosiy maktab')
        self.center = Organization.objects.get(name="O'quv markaz")
        self.b_school = Branch.objects.get(organization=self.school)
        self.c1 = Branch.objects.get(organization=self.center, name='Filial 1')
        self.c2 = Branch.objects.create(organization=self.center, name='Filial 2')
        self.owner = User.objects.create_user('boss', password='x', role='staff', is_superuser=True, is_staff=True)

    def staff(self, username, perms, *branches, owner=False):
        pos = Position.objects.create(name=f'L-{username}', is_owner=owner)
        u = User.objects.create_user(username, password='x', role='staff', first_name='X', last_name=username)
        StaffProfile.objects.create(user=u, position=pos, perms=perms)
        u.branches.set(branches)
        return u


class MobileWorkspaceTests(Base):
    def test_owner_gets_header_chip_and_sheet(self):
        self.client.force_login(self.owner)
        body = self.client.get(reverse('panel:students')).content.decode()
        self.assertIn('id="wspBtn"', body)        # telefonda sarlavha ostidagi chip
        self.assertIn('id="wspOv"', body)         # pastdan ochiladigan varaq
        self.assertIn('data-open-wsp', body)      # «Ko'proq» ichida ham
        self.assertIn('Filial 2', body)

    def test_single_branch_staff_has_no_chip(self):
        u = self.staff('dir', ['students.view'], self.b_school)
        self.client.force_login(u)
        body = self.client.get(reverse('panel:students')).content.decode()
        self.assertNotIn('id="wspBtn"', body)
        self.assertNotIn('id="wspOv"', body)


class GroupNamePerBranchTests(Base):
    def test_same_name_allowed_in_different_branches(self):
        Group.objects.create(name='7-A', branch=self.b_school)
        Group.objects.create(name='7-A', branch=self.c1)
        self.assertEqual(Group.objects.filter(name='7-A').count(), 2)

    def test_duplicate_in_same_branch_rejected_by_db(self):
        Group.objects.create(name='7-A', branch=self.b_school)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Group.objects.create(name='7-A', branch=self.b_school)

    def test_panel_form_rejects_duplicate_in_branch_only(self):
        Group.objects.create(name='7-A', branch=self.b_school)
        self.client.force_login(self.owner)
        self.client.get(reverse('panel:set_scope'), {'s': f'branch-{self.b_school.pk}', 'next': '/panel/'})
        r = self.client.post(reverse('panel:group_add'), {'name': '7-a', 'year': 2026})
        self.assertContains(r, 'allaqachon bor')
        self.client.get(reverse('panel:set_scope'), {'s': f'branch-{self.c1.pk}', 'next': '/panel/'})
        r = self.client.post(reverse('panel:group_add'), {'name': '7-A', 'year': 2026})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Group.objects.filter(name='7-A', branch=self.c1).exists())

    def test_import_uses_target_branch(self):
        Group.objects.create(name='9-B', branch=self.b_school)
        import_rows('9-B', [('Aliyev Vali', '', None)], branch=self.c2)
        g = Group.objects.get(name='9-B', branch=self.c2)
        self.assertEqual(g.students.count(), 1)
        self.assertEqual(Group.objects.get(name='9-B', branch=self.b_school).students.count(), 0)

    def test_restore_returns_to_same_branch_group(self):
        g_school = Group.objects.create(name='5-A', branch=self.b_school)
        g_center = Group.objects.create(name='5-A', branch=self.c1)
        s = Student.objects.create(user=User.objects.create_user('st', password='x', role='student'), group=g_center, branch=self.c1)
        s.leave()
        s.refresh_from_db()
        s.restore()
        s.refresh_from_db()
        self.assertEqual(s.group, g_center)
        self.assertNotEqual(s.group, g_school)


class BranchAssignTests(Base):
    def setUp(self):
        super().setUp()
        self.teacher = User.objects.create_user('t1', password='x', role='teacher', first_name='Ustoz', last_name='Bir')
        self.teacher.branches.set([self.b_school, self.c1])

    def post_teacher(self, user, *branches):
        self.client.force_login(user)
        return self.client.post(reverse('panel:teacher_branches', args=[self.teacher.pk]), {'branch': [b.pk for b in branches]})

    def test_owner_sets_teacher_branches(self):
        self.post_teacher(self.owner, self.c1, self.c2)
        self.assertEqual(set(self.teacher.branches.all()), {self.c1, self.c2})

    def test_editor_cannot_touch_branches_outside_own_access(self):
        director = self.staff('dir', ['teachers.view', 'teachers.change'], self.b_school)
        self.post_teacher(director, self.b_school, self.c2)               # c2 ga ruxsati yo'q — e'tiborsiz qoladi
        self.assertEqual(set(self.teacher.branches.all()), {self.c1, self.b_school})
        self.post_teacher(director)             # faqat o'z filialidan olib tashlay oladi
        self.assertEqual(set(self.teacher.branches.all()), {self.c1})     # markaz filiali tegilmadi

    def test_at_least_one_branch(self):
        self.teacher.branches.set([self.c1])
        self.post_teacher(self.owner)
        self.assertEqual(set(self.teacher.branches.all()), {self.c1})

    def test_teacher_page_shows_checkboxes_for_editor(self):
        self.client.force_login(self.owner)
        body = self.client.get(reverse('panel:teacher', args=[self.teacher.pk])).content.decode()
        self.assertIn('name="branch"', body)
        self.assertIn('Filial 2', body)

    def test_staff_branches_and_guards(self):
        clerk = self.staff('clerk', ['students.view'], self.b_school)
        profile = clerk.staff_profile
        self.client.force_login(self.owner)
        self.client.post(reverse('panel:staff_branches', args=[profile.pk]), {'branch': [self.c1.pk, self.c2.pk]})
        self.assertEqual(set(clerk.branches.all()), {self.c1, self.c2})
        # o'zini o'zi o'zgartira olmaydi
        mgr = self.staff('mgr', ['staff.view', 'staff.manage'], self.c1, self.c2)
        self.client.force_login(mgr)
        self.client.post(reverse('panel:staff_branches', args=[mgr.staff_profile.pk]), {'branch': [self.c1.pk]})
        self.assertEqual(set(mgr.branches.all()), {self.c1, self.c2})


class CreateWithBranchesTests(Base):
    """Yangi xodim/ustoz faqat formada belgilangan filialga tushadi (2026-11-23: direktor Tibbiyot uchun qo'shilib,
    Bog'chaga ham tushib qolgan edi — ish maydoni + avtomatik «asosiy filial»)."""

    def setUp(self):
        super().setUp()
        from panel.models import Position
        self.med = Organization.objects.get(name='Tibbiyot maktabi')
        self.b_med = Branch.objects.filter(organization=self.med).first()
        self.kg = Branch.objects.get(organization=Organization.objects.get(name="Bog'cha"))
        self.director = Position.objects.create(name='Direktor X')
        self.client.force_login(self.owner)
        self.client.get(reverse('panel:set_scope'), {'s': f'branch-{self.kg.pk}', 'next': '/panel/'})    # ish maydoni: Bog'cha

    def test_director_gets_only_chosen_branch_and_last4_password(self):
        r = self.client.post(reverse('panel:staff_add'), {'last_name': 'Aliyev', 'first_name': 'Vali', 'phone': '+998 90 111-22-33',
                                                          'position': self.director.pk, 'branch': [self.b_med.pk]}, follow=True)
        u = User.objects.get(phone_digits='998901112233')
        self.assertEqual(set(u.branches.all()), {self.b_med})          # Bog'cha ham, avtomatik filial ham qo'shilmadi
        self.assertTrue(u.check_password('2233') and u.must_change_password)
        self.assertContains(r, 'oxirgi 4 raqami')

    def test_branch_is_required_when_several_available(self):
        r = self.client.post(reverse('panel:staff_add'), {'last_name': 'A', 'first_name': 'B', 'phone': '+998 90 111-22-44',
                                                          'position': self.director.pk})
        self.assertContains(r, 'Kamida bitta filialni belgilang')
        self.assertFalse(User.objects.filter(phone_digits='998901112244').exists())

    def test_form_preselects_current_workspace_visibly(self):
        body = self.client.get(reverse('panel:staff_add')).content.decode()
        self.assertIn(f'id="nb-{self.kg.pk}" checked', body)          # oldindan belgilangani ko'rinib turadi
        self.assertNotIn(f'id="nb-{self.b_med.pk}" checked', body)

    def test_teacher_gets_only_chosen_branches(self):
        self.client.post(reverse('panel:teacher_add'), {'last_name': 'Karimova', 'first_name': 'Nilufar', 'phone': '+998 90 111-22-55',
                                                        'branch': [self.b_med.pk, self.c1.pk]})
        t = User.objects.get(phone_digits='998901112255')
        self.assertEqual(set(t.branches.all()), {self.b_med, self.c1})
        self.assertTrue(t.check_password('2255'))


class FounderOnlyTests(Base):
    """Founder boshqalarga ko'rinmaydi; tashkilot va filial qo'shishni faqat founder qiladi (2026-11-23)."""

    def setUp(self):
        super().setUp()
        from panel.models import AuditLog
        self.founder_pos = Position.objects.create(name='Maktab egasi X', is_owner=True)
        self.founder = User.objects.create_user('founder', password='x', role='staff', first_name='Bahodir', last_name='Raximov')
        StaffProfile.objects.create(user=self.founder, position=self.founder_pos, perms=[])
        self.founder.branches.set([self.b_school, self.c1, self.c2])
        self.dir = self.staff('cdir', ['staff.view', 'staff.manage', 'audit.view', 'org.settings'], self.c1, self.c2)
        AuditLog.objects.create(actor=self.founder, actor_name='Raximov Bahodir', verb="Xodim qo'shdi", target_label='kimdir')

    def test_founder_hidden_from_other_staff(self):
        self.client.force_login(self.dir)
        self.client.get(reverse('panel:set_scope'), {'s': f'branch-{self.c1.pk}', 'next': '/panel/'})
        body = self.client.get(reverse('panel:staff')).content.decode()
        self.assertNotIn('Raximov', body)
        self.assertEqual(self.client.get(reverse('panel:staff_detail', args=[self.founder.staff_profile.pk])).status_code, 404)

    def test_founder_actions_hidden_in_audit(self):
        self.client.force_login(self.dir)
        body = self.client.get(reverse('panel:audit')).content.decode()
        self.assertNotIn('Raximov', body)
        self.assertNotIn('kimdir', body)                    # founder qilgan ish quyi xodimga umuman ko'rinmaydi
        self.client.force_login(self.founder)
        self.assertIn('kimdir', self.client.get(reverse('panel:audit')).content.decode())     # founderning o'ziga ko'rinadi
        self.client.force_login(self.dir)
        self.assertNotIn('kimdir', self.client.get(reverse('panel:audit'), {'kim': 'Raximov'}).content.decode())

    def test_founder_sees_everyone(self):
        self.client.force_login(self.founder)
        self.client.get(reverse('panel:set_scope'), {'s': f'branch-{self.c1.pk}', 'next': '/panel/'})
        self.assertIn('Raximov', self.client.get(reverse('panel:staff')).content.decode())

    def test_only_founder_adds_branch(self):
        self.client.force_login(self.dir)
        r = self.client.post(reverse('panel:branch_add'), {'org': self.center.pk, 'name': 'Filial 9'})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Branch.objects.filter(name='Filial 9').exists())
        self.client.force_login(self.founder)
        self.client.post(reverse('panel:branch_add'), {'org': self.center.pk, 'name': 'Filial 9'})
        self.assertTrue(Branch.objects.filter(organization=self.center, name='Filial 9').exists())
        self.client.post(reverse('panel:branch_add'), {'org': self.center.pk, 'name': 'filial 9'})      # takror — yo'q
        self.assertEqual(Branch.objects.filter(organization=self.center, name__iexact='Filial 9').count(), 1)

    def test_only_founder_adds_organization(self):
        data = {'name': 'Yangi litsey', 'short_name': 'Litsey', 'kind': 'school', 'brand_color': '#7C3AED', 'first_branch': 'Asosiy'}
        self.client.force_login(self.dir)
        self.assertEqual(self.client.post(reverse('panel:org_add'), data).status_code, 403)
        self.client.force_login(self.founder)
        r = self.client.post(reverse('panel:org_add'), data)
        org = Organization.objects.get(name='Yangi litsey')
        self.assertEqual(list(org.branches.values_list('name', flat=True)), ['Asosiy'])
        self.assertIn('maydon', r['Location'])          # yangi tashkilot ish maydonida tanlanadi
        page = self.client.get(reverse('panel:org_settings'), {'org': org.pk}).content.decode()
        self.assertIn('Filiallar', page)

    def test_founder_changes_hidden_on_staff_card(self):
        from panel.models import AuditLog
        clerk = self.staff('clerk2', ['students.view'], self.c1)
        AuditLog.objects.create(actor=self.founder, actor_name='Raximov Bahodir', verb="Xodim ruxsatlarini o'zgartirdi",
                                target_type='staff', target_id=clerk.staff_profile.pk, target_label='clerk2')
        self.client.force_login(self.dir)
        body = self.client.get(reverse('panel:staff_detail', args=[clerk.staff_profile.pk])).content.decode()
        self.assertNotIn('Raximov', body)
        self.assertNotIn("Xodim ruxsatlarini o'zgartirdi", body)


class NewBranchAutoAssignTests(Base):
    """Yangi filial tashkilotning HAMMA filialini ko'radigan xodimlarga (markaz direktori, hisobchi) o'zi qo'shiladi."""

    def test_whole_org_staff_get_new_branch(self):
        director = self.staff('mdir', ['students.view'], self.c1, self.c2)
        reception = self.staff('rec', ['students.view'], self.c1)                 # bitta filial — qo'shilmaydi
        accountant = self.staff('acc', ['payroll.view'], self.c1, self.c2, self.b_school)
        teacher = User.objects.create_user('t1', password='x', role='teacher')
        teacher.branches.set([self.c1, self.c2])                                  # ustoz — qo'shilmaydi
        self.client.force_login(self.owner)
        r = self.client.post(reverse('panel:branch_add'), {'org': self.center.pk, 'name': 'Filial 9'}, follow=True)
        new = Branch.objects.get(organization=self.center, name='Filial 9')
        self.assertIn(new, director.branches.all())
        self.assertIn(new, accountant.branches.all())
        self.assertNotIn(new, reception.branches.all())
        self.assertNotIn(new, teacher.branches.all())
        self.assertContains(r, 'avtomatik qo')

    def test_single_branch_org_assigns_nobody(self):
        d = self.staff('sdir', ['students.view'], self.b_school)
        self.client.force_login(self.owner)
        self.client.post(reverse('panel:branch_add'), {'org': self.school.pk, 'name': 'Ikkinchi bino'})
        self.assertEqual(list(d.branches.all()), [self.b_school])


class BranchHeadTests(Base):
    """«Filial rahbari»: o'z filialida kundalik boshqaruv; xodim, pul (xarajat/oylik), narx, jurnal — yo'q; faqat o'z filiali."""

    def test_preset_and_scope(self):
        from django.core.management import call_command
        from panel.models import Position
        from panel.perms import PRESETS
        perms = next(p[2] for p in PRESETS if p[0] == 'Filial rahbari')
        for code in ('students.add', 'teachers.add', 'payments.accept', 'monitoring.view', 'staff.view'):
            self.assertIn(code, perms)
        for code in ('staff.manage', 'expenses.view', 'payroll.view', 'payments.void', 'payments.settings', 'audit.view', 'org.settings'):
            self.assertNotIn(code, perms)
        self.assertTrue(Position.objects.filter(name='Filial rahbari').exists())
        head = self.staff('head', perms, self.c1)
        from org.scope import branch_ids
        self.assertEqual(set(branch_ids(head)), {self.c1.pk})
        self.client.force_login(head)
        self.assertEqual(self.client.get(reverse('panel:payroll')).status_code, 403)
        self.assertEqual(self.client.get(reverse('panel:students')).status_code, 200)
