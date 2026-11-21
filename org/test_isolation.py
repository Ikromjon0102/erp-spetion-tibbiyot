"""Tashkilotlar o'rtasida ma'lumot ajratilishi: bir tashkilot xodimi boshqasining ma'lumotini ko'rmasligi kerak."""
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from academics.models import Group, Lesson, Subject, Teaching
from access.models import Device
from access.sync import eligible_users
from accounts.models import Student, User
from billing.models import Payment
from notices.models import Announcement
from notices.services import recipients_of
from notices.views import announcements_for
from org.models import Branch, Organization, default_branch
from panel.models import Position, StaffProfile

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


def staff(username, position, branch):
    user = User.objects.create_user(username=username, password='x', role='staff', first_name=username.title())
    p = Position.objects.get(name=position)
    StaffProfile.objects.create(user=user, position=p, perms=list(p.default_perms))
    user.branches.set([branch])      # signal avval asosiy filialni qo'shgan bo'lishi mumkin: aniq filialga o'tkazamiz
    return user


def make_student(first, group):
    u = User.objects.create_user(username=f's-{first}', password='x', role='student', first_name=first, last_name='Test')
    return Student.objects.create(user=u, group=group)


@FAST
class IsolationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.med = default_branch()
        org2 = Organization.objects.create(name='Bogcha', kind='kindergarten', brand_color='#ea580c')
        self.kg = Branch.objects.create(organization=org2, name='Asosiy')

        self.g_med = Group.objects.create(name='5-A', branch=self.med)
        self.g_kg = Group.objects.create(name='Gulchechak', branch=self.kg)
        self.s_med = make_student('Ali', self.g_med)
        self.s_kg = make_student('Vali', self.g_kg)

        self.owner = staff('egasi', 'Maktab egasi', self.med)
        self.dir_med = staff('dirmed', 'Direktor', self.med)
        self.dir_kg = staff('dirkg', 'Direktor', self.kg)

        for s in (self.s_med, self.s_kg):
            Payment.objects.create(student=s, amount=100000, method='cash', paid_on=timezone.localdate(), received_by=self.owner)

    def get(self, user, name, *args):
        self.client.force_login(user)
        return self.client.get(reverse(name, args=args))

    def test_student_branch_follows_group(self):
        self.assertEqual(self.s_med.branch, self.med)
        self.assertEqual(self.s_kg.branch, self.kg)

    def test_students_list_only_own_branch(self):
        body = self.get(self.dir_kg, 'panel:students').content.decode()
        self.assertIn('Vali', body)
        self.assertNotIn('Ali Test', body)
        body = self.get(self.dir_med, 'panel:students').content.decode()
        self.assertIn('Ali', body)
        self.assertNotIn('Vali', body)

    def test_owner_sees_everything(self):
        body = self.get(self.owner, 'panel:students').content.decode()
        self.assertIn('Ali', body)
        self.assertIn('Vali', body)

    def test_other_branch_student_pages_are_404(self):
        self.client.force_login(self.dir_kg)
        for name in ('panel:student', 'panel:student_edit', 'panel:pay'):
            self.assertEqual(self.client.get(reverse(name, args=[self.s_med.pk])).status_code, 404, name)
        for name in ('panel:student_leave', 'panel:student_delete', 'panel:student_restore', 'panel:parent_add'):
            self.assertEqual(self.client.post(reverse(name, args=[self.s_med.pk])).status_code, 404, name)
        self.assertEqual(self.client.get(reverse('panel:student', args=[self.s_kg.pk])).status_code, 200)

    def test_payments_isolated(self):
        pay_med = Payment.objects.get(student=self.s_med)
        self.client.force_login(self.dir_kg)
        self.assertEqual(self.client.post(reverse('panel:payment_void', args=[pay_med.pk]), {'reason': 'x'}).status_code, 404)
        pay_med.refresh_from_db()
        self.assertFalse(pay_med.voided)
        self.assertEqual(self.client.get(reverse('receipt', args=[self.s_med.pk, pay_med.pk])).status_code, 403)
        body = self.client.get(reverse('panel:finance')).content.decode()
        self.assertNotIn('Ali', body)

    def test_reports_scoped(self):
        self.client.force_login(self.dir_kg)
        body = self.client.get(reverse('panel:reports') + '?r=tushum').content.decode()
        self.assertIn('Vali', body)
        self.assertNotIn('Ali Test', body)

    def test_groups_scoped(self):
        body = self.get(self.dir_kg, 'panel:groups').content.decode()
        self.assertIn('Gulchechak', body)
        self.assertNotIn('5-A', body)
        self.assertEqual(self.client.get(reverse('panel:group_edit', args=[self.g_med.pk])).status_code, 404)

    def test_new_group_goes_to_creators_branch(self):
        self.client.force_login(self.dir_kg)
        self.client.post(reverse('panel:group_add'), {'name': 'Yangi', 'year': 2026})
        self.assertEqual(Group.objects.get(name='Yangi').branch, self.kg)

    def test_student_add_uses_own_branch_and_rejects_foreign_group(self):
        self.client.force_login(self.dir_kg)
        r = self.client.post(reverse('panel:student_add'), {'last_name': 'Yangi', 'first_name': 'Bola', 'group': self.g_med.pk})
        self.assertEqual(r.status_code, 200)      # forma xatosi: boshqa filial guruhi tanlanmaydi
        self.assertFalse(Student.objects.filter(user__last_name='Yangi').exists())
        self.client.post(reverse('panel:student_add'), {'last_name': 'Yangi', 'first_name': 'Bola'})
        self.assertEqual(Student.objects.get(user__last_name='Yangi').branch, self.kg)

    def test_devices_scoped(self):
        d_med = Device.objects.create(name='Med-1', direction='in', branch=self.med)
        d_kg = Device.objects.create(name='KG-1', direction='in', branch=self.kg)
        body = self.get(self.dir_kg, 'panel:devices').content.decode()
        self.assertIn('KG-1', body)
        self.assertNotIn('Med-1', body)
        self.assertEqual(self.client.get(reverse('panel:device_edit', args=[d_med.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('panel:device_test', args=[d_med.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('panel:device_sync', args=[d_med.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('panel:device_edit', args=[d_kg.pk])).status_code, 200)

    def test_terminal_gets_only_its_branch_people(self):
        for s in (self.s_med, self.s_kg):
            s.user.photo.save('x.jpg', ContentFile(b'jpg'), save=True)
        d_med = Device.objects.create(name='Med-1', direction='in', branch=self.med)
        d_kg = Device.objects.create(name='KG-1', direction='in', branch=self.kg)
        self.assertEqual({u.pk for u in eligible_users(d_med)}, {self.s_med.user_id})
        self.assertEqual({u.pk for u in eligible_users(d_kg)}, {self.s_kg.user_id})

    def test_teachers_and_schedule_scoped(self):
        t_med = User.objects.create_user('tm', password='x', role='teacher', first_name='Tmed')
        t_kg = User.objects.create_user('tk', password='x', role='teacher', first_name='Tkg')
        t_kg.branches.set([self.kg])
        self.assertEqual(list(t_med.branches.all()), [self.med])
        body = self.get(self.dir_kg, 'panel:teachers').content.decode()
        self.assertIn('Tkg', body)
        self.assertNotIn('Tmed', body)
        self.assertEqual(self.client.get(reverse('panel:teacher', args=[t_med.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('panel:teacher_toggle', args=[t_med.pk])).status_code, 404)
        subj = Subject.objects.create(name='Fan')
        lesson = Lesson.objects.create(teaching=Teaching.objects.create(teacher=t_med, subject=subj, group=self.g_med), weekday=0, period=1,
                                       start='09:00', end='09:45')
        self.assertEqual(self.client.get(reverse('panel:lesson_edit', args=[lesson.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('panel:lesson_delete', args=[lesson.pk])).status_code, 404)

    def test_parents_scoped_and_other_org_children_hidden(self):
        p_med = User.objects.create_user('998901', password='x', role='parent', first_name='Otamed', phone='+998 90 100-00-01')
        p_both = User.objects.create_user('998902', password='x', role='parent', first_name='Otaikki', phone='+998 90 100-00-02')
        self.s_med.parents.add(p_med, p_both)
        self.s_kg.parents.add(p_both)
        body = self.get(self.dir_kg, 'panel:parents').content.decode()
        self.assertNotIn('Otamed', body)
        self.assertIn('Otaikki', body)
        self.assertEqual(self.client.get(reverse('panel:parent', args=[p_med.pk])).status_code, 404)
        detail = self.client.get(reverse('panel:parent', args=[p_both.pk])).content.decode()
        self.assertIn('Vali', detail)
        self.assertNotIn('Ali Test', detail)
        self.assertEqual(self.client.post(reverse('panel:parent_link', args=[p_both.pk, self.s_med.pk])).status_code, 404)

    def test_announcements_scoped_for_staff(self):
        a_med = Announcement.objects.create(title='MedElon', body='x', audience='all', author=self.owner, branch=self.med)
        Announcement.objects.create(title='KgElon', body='x', audience='all', author=self.owner, branch=self.kg)
        body = self.get(self.dir_kg, 'panel:news').content.decode()
        self.assertIn('KgElon', body)
        self.assertNotIn('MedElon', body)
        self.assertEqual(self.client.get(reverse('panel:news_detail', args=[a_med.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('panel:news_delete', args=[a_med.pk])).status_code, 404)

    def test_announcement_recipients_follow_branch(self):
        p_med = User.objects.create_user('998911', password='x', role='parent')
        p_kg = User.objects.create_user('998912', password='x', role='parent')
        self.s_med.parents.add(p_med)
        self.s_kg.parents.add(p_kg)
        a = Announcement.objects.create(title='T', body='x', audience='parents', author=self.owner, branch=self.kg)
        self.assertEqual([u.pk for u in recipients_of(a)], [p_kg.pk])

    def test_parent_sees_announcements_of_all_childs_branches_only(self):
        parent = User.objects.create_user('998920', password='x', role='parent')
        self.s_med.parents.add(parent)
        self.s_kg.parents.add(parent)
        b3 = Branch.objects.create(organization=Organization.objects.create(name='Markaz', kind='center'), name='F1')
        Announcement.objects.create(title='A-med', body='x', audience='parents', branch=self.med)
        Announcement.objects.create(title='A-kg', body='x', audience='parents', branch=self.kg)
        Announcement.objects.create(title='A-markaz', body='x', audience='parents', branch=b3)
        titles = set(announcements_for(parent).values_list('title', flat=True))
        self.assertEqual(titles, {'A-med', 'A-kg'})

    def test_staff_list_scoped(self):
        body = self.get(self.dir_kg, 'panel:staff').content.decode()
        self.assertIn('Dirkg', body)
        self.assertNotIn('Dirmed', body)

    def test_dashboard_counts_only_own(self):
        self.assertEqual(self.get(self.dir_kg, 'panel:dashboard').context['students_total'], 1)
        self.assertEqual(self.get(self.owner, 'panel:dashboard').context['students_total'], 2)

    def test_staff_without_branches_sees_nothing(self):
        nobody = staff('nobody', 'Direktor', self.med)
        nobody.branches.clear()
        body = self.get(nobody, 'panel:students').content.decode()
        self.assertNotIn('Ali', body)
        self.assertNotIn('Vali', body)
