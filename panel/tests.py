import json
from datetime import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from academics.models import Group, Lesson, Subject, Teaching
from access.models import AccessEvent, Device
from accounts.models import Student, User
from journal.models import Attendance, Grade
from billing.models import BillingSettings, Payment
from notices.models import Announcement

from .access import can, has_panel, is_owner, perms_of
from .models import AuditLog, Position, StaffProfile
from .perms import ALL_PERMS, normalize

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
XLSX = Path(settings.BASE_DIR) / "10-sinf o'quvchilari ro'yxati.xlsx"


def pos(name):
    return Position.objects.get(name=name)


def make_staff(username, position, perms=None, phone='', **kw):
    user = User.objects.create_user(username=username, password='x', role='staff', phone=phone, first_name=username.title(), **kw)
    p = pos(position)
    StaffProfile.objects.create(user=user, position=p, perms=list(p.default_perms) if perms is None else perms)
    return user


def NO_PAY(position):
    """Reception namunasi, lekin to'lov ruxsatlarisiz (ruxsatlar ajratilishini tekshiradigan testlar uchun)."""
    return [c for c in position.default_perms if not c.startswith('payments.')]


class NormalizeTests(SimpleTestCase):
    def test_adds_view_dependency_and_drops_unknown(self):
        self.assertEqual(normalize(['students.change', 'bogus.perm', 'students.change']), ['students.view', 'students.change'])
        self.assertEqual(normalize(['payments.view']), ['payments.view'])    # maxfiy ruxsat boshqasini talab qilmaydi
        self.assertEqual(normalize(['staff.manage', 'announcements.add']),
                         ['announcements.view', 'announcements.add', 'staff.view', 'staff.manage'])


@FAST
class AccessTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = make_staff('egasi', 'Maktab egasi')
        self.reception = make_staff('rec', 'Reception', perms=NO_PAY(pos('Reception')))
        self.accountant = make_staff('hisob', 'Hisobchi')

    def test_seeded_positions_exist(self):
        self.assertEqual(set(Position.objects.values_list('name', flat=True)),
                         {'Maktab egasi', 'Direktor', "Zam (o'quv ishlari)", 'Reception', 'Hisobchi', 'Zavxoz'})
        self.assertTrue(pos('Maktab egasi').is_owner)

    def test_perms_by_user_kind(self):
        self.assertEqual(perms_of(self.owner), set(ALL_PERMS))
        self.assertTrue(can(self.reception, 'students.add') and not can(self.reception, 'payments.view'))
        self.assertTrue(can(self.accountant, 'payments.view') and not can(self.accountant, 'sensitive.grades'))
        boss = User.objects.create_superuser('boss', password='x')
        self.assertEqual(perms_of(boss), set(ALL_PERMS))
        self.assertTrue(is_owner(boss))

    def test_user_perms_are_individual_not_tied_to_position(self):
        self.reception.staff_profile.perms = ['students.view']          # lavozim Reception, lekin ruxsat bitta
        self.reception.staff_profile.save()
        user = User.objects.get(pk=self.reception.pk)
        self.assertEqual(perms_of(user), {'students.view'})

    def test_inactive_profile_or_plain_user_has_no_panel(self):
        self.reception.staff_profile.is_active = False
        self.reception.staff_profile.save()
        self.assertFalse(has_panel(User.objects.get(pk=self.reception.pk)))
        self.assertFalse(has_panel(User.objects.create_user(username='p', password='x', role='parent')))

    def test_page_access_rules(self):
        self.assertEqual(self.client.get('/panel/').status_code, 302)                 # kirmagan -> login
        User.objects.create_user(username='par', password='x', role='parent')
        self.client.login(username='par', password='x')
        self.assertEqual(self.client.get('/panel/').status_code, 403)               # xodim emas
        self.client.login(username='rec', password='x')
        self.assertEqual(self.client.get('/panel/').status_code, 200)
        self.assertEqual(self.client.get('/panel/oquvchilar/').status_code, 200)
        denied = self.client.get('/panel/xodimlar/')
        self.assertEqual(denied.status_code, 403)                                     # staff.view yo'q
        self.assertContains(denied, "kirish ruxsatingiz yo'q", status_code=403)
        self.assertEqual(self.client.get('/panel/jurnal/').status_code, 403)

    def test_sidebar_shows_only_permitted_sections(self):
        self.client.login(username='hisob', password='x')
        html = self.client.get('/panel/').content.decode()
        self.assertIn("O'quvchilar", html)
        self.assertNotIn('Faoliyat jurnali', html)
        self.assertNotIn('href="/panel/xodimlar/"', html)
        self.client.login(username='egasi', password='x')
        html = self.client.get('/panel/').content.decode()
        self.assertIn('href="/panel/xodimlar/"', html)
        self.assertIn('Faoliyat jurnali', html)


@FAST
class DashboardTests(TestCase):
    def setUp(self):
        cache.clear()
        self.rec, self.acc = make_staff('rec', 'Reception', perms=NO_PAY(pos('Reception'))), make_staff('hisob', 'Hisobchi')
        g = Group.objects.create(name='5-Sinf')
        mk = lambda u, first: Student.objects.create(user=User.objects.create_user(username=u, role='student', first_name=first, last_name='Fam'), group=g)
        self.s1, self.s2, self.s3 = mk('a', 'Ali'), mk('b', 'Vali'), mk('c', 'Sami')
        self.demo = Student.objects.create(user=User.objects.create_user(username='sinov_o1', role='student'), group=g)   # sinov — hisobga olinmaydi
        din = Device.objects.create(name='Kirish-1', direction='in')
        AccessEvent.objects.create(device=din, student=self.s1, employee_no='1', direction='in', occurred_at=timezone.now())
        self.device = din

    def test_attendance_and_arrival_cards_for_monitoring_permission(self):
        self.client.login(username='rec', password='x')
        r = self.client.get('/panel/')
        self.assertEqual((r.context['students_total'], r.context['arrived'], r.context['not_arrived']), (3, 1, 2))
        self.assertNotIn('debtors', r.context)                                         # to'lov ruxsati yo'q

    def test_debt_card_only_with_payment_permission(self):
        BillingSettings.objects.update_or_create(pk=1, defaults={'monthly_price': 1000000, 'billing_start': timezone.localdate().replace(day=1)})
        Payment.objects.create(student=self.s1, amount=300000)
        self.client.login(username='hisob', password='x')
        r = self.client.get('/panel/')
        self.assertEqual((r.context['debtors'], r.context['debt_total']), (3, 2700000))   # 3 o'quvchi × 1 000 000, bittasi 300 000 to'lagan
        self.assertNotIn('arrived', r.context)                                          # kunlik nazorat ruxsati yo'q

    def test_missing_attendance_lists_started_lessons_only_and_ignores_demo_teachers(self):
        today = timezone.localtime()
        teacher = User.objects.create_user(username='t', role='teacher', first_name='Diyora')
        demo_teacher = User.objects.create_user(username='dt', role='teacher', is_demo=True)
        grp = Group.objects.get(name='5-Sinf')
        subj = Subject.objects.create(name='Kimyo')
        mk = lambda t, start: Lesson.objects.create(teaching=Teaching.objects.get_or_create(teacher=t, subject=subj, group=grp)[0],
                                                    weekday=min(today.weekday(), 5), period=1, start=start, end=time(23, 59))
        started, future, demo = mk(teacher, time(0, 0)), mk(teacher, time(23, 58)), mk(demo_teacher, time(0, 0))
        if today.weekday() == 6:
            self.skipTest('yakshanba')
        self.client.login(username='rec', password='x')
        ids = {l.pk for l in self.client.get('/panel/').context['missing']}
        self.assertIn(started.pk, ids)
        self.assertNotIn(demo.pk, ids)
        Attendance.objects.create(student=self.s1, lesson=started, date=today.date(), status='present')
        self.assertNotIn(started.pk, {l.pk for l in self.client.get('/panel/').context['missing']})

    def test_device_status(self):
        self.client.login(username='rec', password='x')
        down = [d for d in self.client.get('/panel/').context['devices'] if not d['ok']]
        self.assertEqual(len(down), 1)                                                 # hali signal bermagan
        self.device.last_seen = timezone.now()
        self.device.save()
        self.assertTrue(all(d['ok'] for d in self.client.get('/panel/').context['devices']))


@FAST
class StudentsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner, self.rec, self.acc = make_staff('egasi', 'Maktab egasi'), make_staff('rec', 'Reception', perms=NO_PAY(pos('Reception'))), make_staff('hisob', 'Hisobchi')
        self.zam = make_staff('zam', "Zam (o'quv ishlari)")
        self.g5, self.g6 = Group.objects.create(name='5-Sinf'), Group.objects.create(name='6-Sinf')
        mk = lambda u, first, last, g: Student.objects.create(user=User.objects.create_user(username=u, role='student', first_name=first, last_name=last), group=g)
        self.madina = mk('m', 'Madina', 'Aliyeva', self.g5)
        self.jasur = mk('j', 'Jasur', 'Karimov', self.g6)
        self.demo = mk('sinov_o1', 'Sinov', 'Bola', self.g5)
        self.parent = User.objects.create(username='998901112233', role='parent', first_name='Ona Aliyeva', phone='+998 90 111-22-33')
        self.parent.set_unusable_password()
        self.parent.save()
        self.madina.parents.add(self.parent)

    def names(self, response):
        return [r['s'].user.first_name for r in response.context['rows']]

    def test_list_search_filter_and_hidden_demo(self):
        self.client.login(username='rec', password='x')
        self.assertEqual(self.names(self.client.get('/panel/oquvchilar/')), ['Madina', 'Jasur'])
        self.assertEqual(self.names(self.client.get('/panel/oquvchilar/?q=aliyeva madina')), ['Madina'])    # ko'p so'zli qidiruv
        self.assertEqual(self.names(self.client.get(f'/panel/oquvchilar/?sinf={self.g6.pk}')), ['Jasur'])
        self.assertNotIn('Sinov', self.names(self.client.get('/panel/oquvchilar/?q=sinov')))                # sinov o'quvchisi ko'rinmaydi

    def test_phone_search_and_display_need_phone_permission(self):
        self.client.login(username='rec', password='x')                              # Reception: telefonlarni ko'radi
        r = self.client.get('/panel/oquvchilar/?q=1112233')
        self.assertEqual(self.names(r), ['Madina'])
        self.assertContains(r, '+998 90 111-22-33')
        self.client.login(username='zam', password='x')                              # Zam: telefon ruxsati yo'q
        r = self.client.get('/panel/oquvchilar/?q=1112233')
        self.assertEqual(self.names(r), [])                                           # telefon bo'yicha ham topilmaydi
        self.assertNotContains(self.client.get('/panel/oquvchilar/'), '+998 90 111-22-33')

    def test_status_and_debt_filters_need_their_permissions(self):
        BillingSettings.objects.update_or_create(pk=1, defaults={'monthly_price': 100, 'billing_start': timezone.localdate().replace(day=1)})
        Payment.objects.create(student=self.jasur, amount=100)                         # Jasur qarzini to'lagan
        din = Device.objects.create(name='K', direction='in')
        AccessEvent.objects.create(device=din, student=self.madina, employee_no='1', direction='in', occurred_at=timezone.now())
        self.client.login(username='hisob', password='x')                            # Hisobchi: qarz ko'radi, kunlik nazorat yo'q
        self.assertEqual(self.names(self.client.get('/panel/oquvchilar/?holat=qarz')), ['Madina'])
        self.assertEqual(sorted(self.names(self.client.get('/panel/oquvchilar/?holat=kelmagan'))), ['Jasur', 'Madina'])   # filtr e'tiborsiz
        self.client.login(username='rec', password='x')                              # Reception: nazorat bor, qarz yo'q
        self.assertEqual(self.names(self.client.get('/panel/oquvchilar/?holat=kelmagan')), ['Jasur'])
        self.assertEqual(sorted(self.names(self.client.get('/panel/oquvchilar/?holat=qarz'))), ['Jasur', 'Madina'])

    def test_card_tabs_follow_permissions(self):
        Grade.objects.create(student=self.madina, teaching=Teaching.objects.create(
            teacher=User.objects.create_user(username='t', role='teacher'), subject=Subject.objects.create(name='Kimyo'), group=self.g5), score=5)
        BillingSettings.objects.update_or_create(pk=1, defaults={'monthly_price': 100, 'billing_start': timezone.localdate().replace(day=1)})
        url = f'/panel/oquvchilar/{self.madina.pk}/'
        self.client.login(username='rec', password='x')
        html = self.client.get(url).content.decode()
        self.assertNotIn('data-tab="grades"', html)
        self.assertNotIn('data-tab="pay"', html)
        self.client.login(username='zam', password='x')
        self.assertIn('data-tab="grades"', self.client.get(url).content.decode())
        self.client.login(username='hisob', password='x')
        html = self.client.get(url).content.decode()
        self.assertIn('data-tab="pay"', html)
        self.assertNotIn('data-tab="grades"', html)

    # --- qo'shish va tahrirlash
    def test_add_student_creates_account_logs_it_and_requires_permission(self):
        self.client.login(username='zam', password='x')                              # Zam: students.add yo'q
        self.assertEqual(self.client.get('/panel/oquvchilar/yangi/').status_code, 403)
        self.client.login(username='rec', password='x')
        r = self.client.post('/panel/oquvchilar/yangi/', {'last_name': 'Yusupov', 'first_name': 'Sardor', 'group': self.g5.pk,
                                                         'birth_date': '2014-05-01', 'access_id': 'F77'})
        s = Student.objects.get(user__last_name='Yusupov')
        self.assertRedirects(r, f'/panel/oquvchilar/{s.pk}/', fetch_redirect_response=False)
        self.assertEqual((s.group, s.access_id, s.user.role, s.user.has_usable_password()), (self.g5, 'F77', 'student', False))
        entry = AuditLog.objects.get(verb="O'quvchi qo'shdi")
        self.assertEqual((entry.actor, entry.target_id), (self.rec, s.pk))

    def test_add_student_with_parent_in_one_step(self):
        self.client.login(username='rec', password='x')
        post = lambda **d: self.client.post('/panel/oquvchilar/yangi/', {'last_name': 'Olimov', 'first_name': 'Ali', 'group': self.g5.pk, **d})
        r = post(parent_phone='90 777 11 22')                                        # yangi raqam, ism yo'q -> so'raydi
        self.assertIn('parent_name', r.context['form'].errors)
        self.assertIn('parent_phone', post(parent_name='Olim Olimov').context['form'].errors)
        self.assertFalse(Student.objects.filter(user__last_name='Olimov').exists())
        post(parent_phone='90 777 11 22', parent_name='Olim Olimov')
        s1 = Student.objects.get(user__last_name='Olimov')
        parent = s1.parents.get()
        self.assertEqual((parent.role, parent.phone, parent.first_name, parent.has_usable_password()),
                         ('parent', '+998 90 777-11-22', 'Olim Olimov', False))
        self.assertTrue(AuditLog.objects.filter(verb='Ota-ona biriktirdi', target_id=s1.pk).exists())
        self.client.post('/panel/oquvchilar/yangi/', {'last_name': 'Olimova', 'first_name': 'Guli', 'parent_phone': '+998907771122'})
        self.assertEqual(Student.objects.get(user__last_name='Olimova').parents.get(), parent)   # ukasi: o'sha hisob, ism shart emas
        self.assertNotContains(self.client.get(f'/panel/oquvchilar/{s1.pk}/tahrirlash/'), 'parent_phone')

    def test_duplicate_face_id_is_rejected(self):
        self.madina.access_id = 'F1'
        self.madina.save()
        self.client.login(username='rec', password='x')
        r = self.client.post('/panel/oquvchilar/yangi/', {'last_name': 'A', 'first_name': 'B', 'access_id': 'F1'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'boshqa o')
        self.assertEqual(Student.objects.count(), 3)

    def test_edit_logs_only_real_changes(self):
        self.client.login(username='rec', password='x')
        r = self.client.post(f'/panel/oquvchilar/{self.madina.pk}/tahrirlash/',
                             {'last_name': 'Aliyeva', 'first_name': 'Madina', 'group': self.g6.pk, 'birth_date': '', 'access_id': 'F5'})
        self.assertEqual(r.status_code, 302)
        self.madina.refresh_from_db()
        self.assertEqual((self.madina.group, self.madina.access_id), (self.g6, 'F5'))
        details = AuditLog.objects.get(verb="O'quvchini o'zgartirdi").details
        self.assertEqual(details['Sinf'], {'eski': '5-Sinf', 'yangi': '6-Sinf'})
        self.assertNotIn('Familiya', details)                                          # o'zgarmagan maydon yozilmaydi

    # --- ota-onalar
    def test_add_new_parent_and_reuse_teacher_account_by_phone(self):
        self.client.login(username='rec', password='x')
        url = f'/panel/oquvchilar/{self.jasur.pk}/ota-ona/'
        self.client.post(url, {'name': 'Otasi Karimov', 'phone': '95-010-76-39'})
        p = self.jasur.parents.get()
        self.assertEqual((p.username, p.phone, p.role, p.has_usable_password()), ('998950107639', '+998 95 010-76-39', 'parent', False))
        teacher = User.objects.create_user(username='dil', password='x', role='teacher', first_name='Dilafruz', phone='+998 93 000-11-22')
        self.client.post(url, {'name': 'Boshqa ism', 'phone': '93 000 11 22'})
        self.assertIn(teacher, self.jasur.parents.all())                                # yangi hisob ochilmadi
        self.assertEqual(User.objects.filter(phone_digits='998930001122').count(), 1)

    def test_invalid_phone_is_rejected(self):
        self.client.login(username='rec', password='x')
        self.client.post(f'/panel/oquvchilar/{self.jasur.pk}/ota-ona/', {'name': 'X', 'phone': '123'})
        self.assertEqual(self.jasur.parents.count(), 0)

    def test_issue_temp_password_shows_it_once_and_protects_teachers(self):
        self.client.login(username='rec', password='x')
        r = self.client.post(f'/panel/oquvchilar/{self.madina.pk}/ota-ona/{self.parent.pk}/parol/', follow=True)
        self.parent.refresh_from_db()
        self.assertTrue(self.parent.must_change_password and self.parent.has_usable_password())
        msg = next(str(m) for m in r.context['messages'])
        password = msg.split('bir martalik parol: ')[1].split()[0]
        self.assertTrue(self.parent.check_password(password))
        self.assertEqual(self.client.post('/login/', {'username': '90 111 22 33', 'password': password}).status_code, 302)  # telefon bilan kiradi
        # ustoz-ota-onaning parolini reception o'zgartira olmaydi
        teacher = User.objects.create_user(username='dil', password='keep', role='teacher', phone='+998 93 000-11-22')
        self.jasur.parents.add(teacher)
        self.client.login(username='rec', password='x')
        self.client.post(f'/panel/oquvchilar/{self.jasur.pk}/ota-ona/{teacher.pk}/parol/')
        teacher.refresh_from_db()
        self.assertTrue(teacher.check_password('keep'))

    def test_remove_parent(self):
        self.client.login(username='rec', password='x')
        self.client.post(f'/panel/oquvchilar/{self.madina.pk}/ota-ona/{self.parent.pk}/ajratish/')
        self.assertEqual(self.madina.parents.count(), 0)
        self.assertTrue(User.objects.filter(pk=self.parent.pk).exists())               # hisob o'chmaydi

    # --- CSV va Excel
    def test_csv_columns_follow_phone_permission_and_export_is_logged(self):
        self.client.login(username='rec', password='x')
        r = self.client.get('/panel/oquvchilar/royxat.csv')
        text = r.content.decode('utf-8')
        self.assertTrue(text.startswith('﻿'))
        self.assertIn('Telefon', text.splitlines()[0])
        self.assertIn('+998 90 111-22-33', text)
        self.client.login(username='zam', password='x')
        text = self.client.get('/panel/oquvchilar/royxat.csv').content.decode('utf-8')
        self.assertNotIn('Telefon', text.splitlines()[0])
        self.assertNotIn('+998 90 111-22-33', text)
        self.assertEqual(AuditLog.objects.filter(verb="Ro'yxatni yuklab oldi").count(), 2)

    def test_excel_import_requires_permission_and_works(self):
        if not XLSX.exists():
            self.skipTest('Excel fayl topilmadi')
        self.client.login(username='hisob', password='x')
        self.assertEqual(self.client.get('/panel/oquvchilar/yuklash/').status_code, 403)
        self.client.login(username='egasi', password='x')
        with open(XLSX, 'rb') as f:
            upload = SimpleUploadedFile("10-sinf o'quvchilari ro'yxati.xlsx", f.read())
        r = self.client.post('/panel/oquvchilar/yuklash/', {'group': '', 'file': upload})
        self.assertEqual(r.context['report']['created'], 20)
        self.assertEqual(Student.objects.filter(group__name='10-Sinf').count(), 20)
        bad = self.client.post('/panel/oquvchilar/yuklash/', {'group': '10-Sinf', 'file': SimpleUploadedFile('x.txt', b'abc')})
        self.assertContains(bad, 'Faqat .xlsx')


@FAST
class GroupsAndNewsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner, self.rec, self.hisob = make_staff('egasi', 'Maktab egasi'), make_staff('rec', 'Reception', perms=NO_PAY(pos('Reception'))), make_staff('hisob', 'Hisobchi')
        self.zam = make_staff('zam', "Zam (o'quv ishlari)")
        self.g5 = Group.objects.create(name='5-Sinf')
        Group.objects.create(name='Sinov-sinf')
        self.t = User.objects.create_user(username='t', password='x', role='teacher', first_name='Diyora')
        Teaching.objects.create(teacher=self.t, subject=Subject.objects.create(name='Kimyo'), group=self.g5)
        self.p = User.objects.create_user(username='p', password='x', role='parent', first_name='Ota')
        Student.objects.create(user=User.objects.create_user(username='k', role='student'), group=self.g5).parents.add(self.p)

    def test_groups_list_hides_demo_and_edit_needs_permission(self):
        self.client.login(username='rec', password='x')
        names = [g.name for g in self.client.get('/panel/sinflar/').context['groups']]
        self.assertEqual(names, ['5-Sinf'])
        self.assertEqual(self.client.get('/panel/sinflar/yangi/').status_code, 403)
        self.client.login(username='zam', password='x')
        self.assertEqual(self.client.post('/panel/sinflar/yangi/', {'name': '7-Sinf', 'year': 2026}).status_code, 302)
        self.assertTrue(Group.objects.filter(name='7-Sinf').exists())
        self.client.post(f'/panel/sinflar/{self.g5.pk}/', {'name': '5-A', 'year': 2026})
        self.assertEqual(AuditLog.objects.get(verb="Sinfni o'zgartirdi").details['nom'], {'eski': '5-Sinf', 'yangi': '5-A'})

    def test_send_announcement_and_see_who_read_it(self):
        self.client.login(username='zam', password='x')
        r = self.client.post('/panel/elonlar/yangi/', {'title': 'Yig\'ilish', 'body': 'Juma kuni', 'audience': 'parents', 'group': self.g5.pk})
        a = Announcement.objects.get(title="Yig'ilish")
        self.assertRedirects(r, f'/panel/elonlar/{a.pk}/', fetch_redirect_response=False)
        self.assertEqual(a.author, self.zam)
        detail = self.client.get(f'/panel/elonlar/{a.pk}/')
        self.assertEqual((detail.context['read'], detail.context['total']), (0, 1))
        self.client.login(username='p', password='x')
        self.client.post(f'/elonlar/{a.pk}/oqildi/')
        self.client.login(username='zam', password='x')
        detail = self.client.get(f'/panel/elonlar/{a.pk}/')
        self.assertEqual(detail.context['read'], 1)
        self.assertContains(detail, '✓✓')
        row = self.client.get('/panel/elonlar/').context['rows'][0]
        self.assertEqual((row['read'], row['total']), (1, 1))
        self.assertTrue(AuditLog.objects.filter(verb="E'lon yubordi").exists())

    def test_announcement_permissions_and_demo_hidden(self):
        Announcement.objects.create(title='[Sinov] xx', body='x', audience='all')
        real = Announcement.objects.create(title='Haqiqiy', body='x', audience='all')
        self.client.login(username='rec', password='x')                               # Reception: faqat ko'radi
        titles = [r['a'].title for r in self.client.get('/panel/elonlar/').context['rows']]
        self.assertEqual(titles, ['Haqiqiy'])
        self.assertEqual(self.client.get('/panel/elonlar/yangi/').status_code, 403)
        self.assertEqual(self.client.post(f'/panel/elonlar/{real.pk}/ochirish/').status_code, 403)
        self.assertTrue(Announcement.objects.filter(pk=real.pk).exists())
        self.client.login(username='hisob', password='x')                              # Hisobchi: e'lon ko'radi, yubormaydi
        self.assertEqual(self.client.get('/panel/elonlar/yangi/').status_code, 403)
        self.client.login(username='zam', password='x')
        self.client.post(f'/panel/elonlar/{real.pk}/ochirish/')
        self.assertFalse(Announcement.objects.filter(pk=real.pk).exists())
        self.assertTrue(AuditLog.objects.filter(verb="E'lonni o'chirdi", target_label='Haqiqiy').exists())


@FAST
class StaffTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = make_staff('egasi', 'Maktab egasi')
        self.director = make_staff('dir', 'Direktor', perms=list(pos('Direktor').default_perms) + ['staff.manage'])
        self.rec = make_staff('rec', 'Reception', perms=NO_PAY(pos('Reception')))

    def add(self, **data):
        base = {'last_name': 'Yangi', 'first_name': 'Xodim', 'phone': '+998 90 555-66-77', 'position': pos('Reception').pk}
        return self.client.post('/panel/xodimlar/yangi/', {**base, **data}, follow=True)

    # --- xodim qo'shish
    def test_position_has_no_default_and_is_required(self):
        self.client.login(username='egasi', password='x')
        self.assertContains(self.client.get('/panel/xodimlar/yangi/'), '— lavozimni tanlang —')
        before = StaffProfile.objects.count()
        self.add(position='')
        self.assertEqual(StaffProfile.objects.count(), before)

    def test_only_with_manage_permission(self):
        self.client.login(username='rec', password='x')
        self.assertEqual(self.client.get('/panel/xodimlar/yangi/').status_code, 403)
        self.assertEqual(self.client.get('/panel/xodimlar/').status_code, 403)

    def test_add_new_staff_gets_temp_password_and_position_defaults(self):
        self.client.login(username='egasi', password='x')
        r = self.add()
        user = User.objects.get(phone_digits='998905556677')
        profile = user.staff_profile
        self.assertEqual((user.role, profile.position.name, user.must_change_password), ('staff', 'Reception', True))
        self.assertEqual(profile.perms, normalize(pos('Reception').default_perms))
        password = next(str(m) for m in r.context['messages']).split('bir martalik parol: ')[1].split()[0]
        self.client.logout()
        self.assertEqual(self.client.post('/login/', {'username': '90-555-66-77', 'password': password}).status_code, 302)
        self.assertRedirects(self.client.get('/', follow=False), '/parol/', fetch_redirect_response=False)      # majburiy almashtirish
        self.client.post('/parol/', {'new_password1': 'Yangi-parol-9', 'new_password2': 'Yangi-parol-9'})
        self.assertRedirects(self.client.get('/', follow=False), '/panel/', fetch_redirect_response=False)     # keyin — panel

    def test_existing_teacher_by_phone_gets_panel_access_without_password_change(self):
        teacher = User.objects.create_user(username='dil', password='keep', role='teacher', first_name='Dilafruz', phone='+998 90 555-66-77')
        self.client.login(username='egasi', password='x')
        self.add()
        teacher.refresh_from_db()
        self.assertTrue(teacher.check_password('keep') and not teacher.must_change_password)
        self.assertEqual(teacher.role, 'teacher')
        self.assertEqual(teacher.staff_profile.position.name, 'Reception')
        self.assertEqual(User.objects.filter(phone_digits='998905556677').count(), 1)

    def test_duplicate_staff_and_technical_admin_are_rejected(self):
        User.objects.create_superuser('boss', password='x', phone='+998 90 000-00-01')
        self.client.login(username='egasi', password='x')
        self.add()
        again = self.add(first_name='Yana')
        self.assertContains(again, 'allaqachon mavjud')
        self.assertContains(self.add(phone='+998 90 000-00-01'), 'allaqachon mavjud')

    def test_non_owner_cannot_create_owner_and_grants_only_own_permissions(self):
        self.client.login(username='dir', password='x')
        self.assertNotIn(pos('Maktab egasi'), self.client.get('/panel/xodimlar/yangi/').context['form'].fields['position'].queryset)
        self.add(position=pos('Maktab egasi').pk)
        self.assertFalse(User.objects.filter(phone_digits='998905556677').exists())
        # Hisobchi namunasida 'payments.view' bor, direktorda ham bor; direktorda yo'q ruxsatni ola olmaydi:
        weak = make_staff('weakdir', 'Direktor', perms=['staff.view', 'staff.manage', 'students.view'])
        self.client.login(username='weakdir', password='x')
        self.add(position=pos('Hisobchi').pk)
        created = User.objects.get(phone_digits='998905556677').staff_profile
        self.assertEqual(set(created.perms), {'students.view'})                          # faqat o'zida borlari

    # --- ruxsatlarni o'zgartirish
    def test_owner_edits_permissions_and_it_is_logged(self):
        self.client.login(username='egasi', password='x')
        pid = self.rec.staff_profile.pk
        r = self.client.post(f'/panel/xodimlar/{pid}/', {'position': pos('Reception').pk, 'is_active': 'on',
                                                         'perms': ['students.view', 'payments.view']})
        self.assertEqual(r.status_code, 302)
        self.rec.staff_profile.refresh_from_db()
        self.assertEqual(self.rec.staff_profile.perms, ['students.view', 'payments.view'])
        d = AuditLog.objects.get(verb="Xodim ruxsatlarini o'zgartirdi").details
        self.assertIn("To'lovlar, qarzdorlar va chegirmalarni ko'rish", d["qo'shildi"])
        self.assertIn("Telefon raqamlarni ko'rish", d['olib tashlandi'])
        self.assertTrue(can(User.objects.get(pk=self.rec.pk), 'payments.view'))     # darhol kuchga kiradi

    def test_apply_position_preset(self):
        self.client.login(username='egasi', password='x')
        pid = self.rec.staff_profile.pk
        self.client.post(f'/panel/xodimlar/{pid}/', {'position': pos('Hisobchi').pk, 'is_active': 'on', 'perms': ['students.view'], 'apply_preset': '1'})
        self.rec.staff_profile.refresh_from_db()
        self.assertEqual(self.rec.staff_profile.perms, normalize(pos('Hisobchi').default_perms))
        self.assertEqual(self.rec.staff_profile.position.name, 'Hisobchi')

    def test_cannot_edit_own_permissions_or_owners_or_grant_missing_ones(self):
        self.client.login(username='dir', password='x')
        me = self.director.staff_profile
        self.client.post(f'/panel/xodimlar/{me.pk}/', {'position': pos('Direktor').pk, 'is_active': 'on', 'perms': ALL_PERMS})
        me.refresh_from_db()
        self.assertNotIn('staff.manage_extra', me.perms)
        self.assertEqual(set(me.perms), set(normalize(list(pos('Direktor').default_perms) + ['staff.manage'])))   # o'zgarmadi
        owner_p = self.owner.staff_profile
        self.client.post(f'/panel/xodimlar/{owner_p.pk}/', {'position': pos('Reception').pk, 'is_active': 'on', 'perms': []})
        owner_p.refresh_from_db()
        self.assertEqual(owner_p.position.name, 'Maktab egasi')                           # direktor egani o'zgartira olmaydi
        # direktor 'sensitive.grades' ni o'zida bo'lmagan holda bera olmaydi
        weak = make_staff('weak', 'Direktor', perms=['staff.view', 'staff.manage', 'students.view'])
        self.client.login(username='weak', password='x')
        pid = self.rec.staff_profile.pk
        self.client.post(f'/panel/xodimlar/{pid}/', {'position': pos('Reception').pk, 'is_active': 'on', 'perms': ['students.view', 'sensitive.grades']})
        self.rec.staff_profile.refresh_from_db()
        self.assertEqual(self.rec.staff_profile.perms, ['students.view'])

    def test_owners_are_only_managed_by_other_owners_never_by_themselves(self):
        """Egani faqat boshqa ega o'zgartira oladi va hech kim o'zini o'zgartira olmaydi => oxirgi egani chetlatib bo'lmaydi."""
        second = make_staff('egasi2', 'Maktab egasi')
        own = self.owner.staff_profile.pk
        # direktor (staff.manage bor) egani o'zgartira/olib tashlay olmaydi
        self.client.login(username='dir', password='x')
        self.client.post(f'/panel/xodimlar/{own}/olib-tashlash/')
        self.client.post(f'/panel/xodimlar/{own}/', {'position': pos('Reception').pk, 'perms': []})
        self.assertEqual(StaffProfile.objects.get(pk=own).position.name, 'Maktab egasi')
        # ega o'zini olib tashlay yoki tushira olmaydi
        self.client.login(username='egasi', password='x')
        self.client.post(f'/panel/xodimlar/{own}/olib-tashlash/')
        self.client.post(f'/panel/xodimlar/{own}/', {'position': pos('Reception').pk, 'is_active': 'on', 'perms': []})
        self.assertEqual(StaffProfile.objects.get(pk=own).position.name, 'Maktab egasi')
        # lekin boshqa ega uni tushira oladi (shundan keyin egasi2 yagona ega bo'lib qoladi va u himoyalangan)
        self.client.login(username='egasi2', password='x')
        self.client.post(f'/panel/xodimlar/{own}/', {'position': pos('Reception').pk, 'is_active': 'on', 'perms': ['students.view']})
        self.assertEqual(StaffProfile.objects.get(pk=own).position.name, 'Reception')
        self.client.post(f'/panel/xodimlar/{second.staff_profile.pk}/olib-tashlash/')
        self.assertTrue(StaffProfile.objects.filter(user=second).exists())

    def test_demoted_owner_loses_everything_immediately(self):
        make_staff('egasi2', 'Maktab egasi')
        self.client.login(username='egasi2', password='x')
        self.client.post(f'/panel/xodimlar/{self.owner.staff_profile.pk}/', {'position': pos('Reception').pk, 'is_active': 'on', 'perms': ['students.view']})
        self.client.login(username='egasi', password='x')
        self.assertEqual(self.client.get('/panel/xodimlar/').status_code, 403)
        self.assertEqual(self.client.get('/panel/oquvchilar/').status_code, 200)

    def test_deactivating_staff_account_blocks_login(self):
        self.client.login(username='egasi', password='x')
        pid = self.rec.staff_profile.pk
        self.client.post(f'/panel/xodimlar/{pid}/', {'position': pos('Reception').pk, 'perms': ['students.view']})   # is_active belgisi yo'q
        self.rec.refresh_from_db()
        self.assertFalse(self.rec.is_active)
        self.client.logout()
        self.assertEqual(self.client.post('/login/', {'username': 'rec', 'password': 'x'}).status_code, 200)

    def test_remove_panel_access_deactivates_panel_only_account_but_keeps_teacher_account(self):
        teacher = User.objects.create_user(username='dil', password='keep', role='teacher', phone='+998 90 555-66-77')
        self.client.login(username='egasi', password='x')
        self.add()
        t_profile = teacher.staff_profile
        self.client.post(f'/panel/xodimlar/{t_profile.pk}/olib-tashlash/')
        teacher.refresh_from_db()
        self.assertTrue(teacher.is_active)                                               # ustoz hisobi saqlanadi
        self.assertFalse(has_panel(User.objects.get(pk=teacher.pk)))
        pid = self.rec.staff_profile.pk
        self.client.post(f'/panel/xodimlar/{pid}/olib-tashlash/')
        self.rec.refresh_from_db()
        self.assertFalse(self.rec.is_active)                                              # faqat panel uchun ochilgan hisob yopildi

    def test_reset_password_rules(self):
        self.client.login(username='egasi', password='x')
        pid = self.rec.staff_profile.pk
        r = self.client.post(f'/panel/xodimlar/{pid}/parol/', follow=True)
        self.rec.refresh_from_db()
        self.assertTrue(self.rec.must_change_password)
        self.assertIn('bir martalik parol:', ' '.join(str(m) for m in r.context['messages']))
        before = User.objects.get(pk=self.owner.pk).password
        self.client.post(f'/panel/xodimlar/{self.owner.staff_profile.pk}/parol/')          # o'zining parolini bu yerdan o'zgartira olmaydi
        self.assertEqual(User.objects.get(pk=self.owner.pk).password, before)

    # --- lavozimlar
    def test_positions_crud_with_owner_rules(self):
        self.client.login(username='egasi', password='x')
        r = self.client.post('/panel/lavozimlar/yangi/', {'name': 'Kadrlar', 'perms': ['staff.view', 'students.change']})
        self.assertEqual(r.status_code, 302)
        p = Position.objects.get(name='Kadrlar')
        self.assertEqual(p.default_perms, ['students.view', 'students.change', 'staff.view'])
        self.assertFalse(p.is_owner)
        self.client.post(f'/panel/lavozimlar/{p.pk}/ochirish/')
        self.assertFalse(Position.objects.filter(name='Kadrlar').exists())
        self.assertEqual(Position.objects.filter(is_owner=True).count(), 1)
        self.client.post(f'/panel/lavozimlar/{pos("Reception").pk}/ochirish/')            # xodimi bor lavozim o'chmaydi
        self.assertTrue(Position.objects.filter(name='Reception').exists())

    def test_director_cannot_touch_owner_position_or_make_owner_positions(self):
        self.client.login(username='dir', password='x')
        owner_pos = pos('Maktab egasi')
        self.client.post(f'/panel/lavozimlar/{owner_pos.pk}/', {'name': 'Hack', 'perms': []})
        owner_pos.refresh_from_db()
        self.assertEqual(owner_pos.name, 'Maktab egasi')
        self.client.post('/panel/lavozimlar/yangi/', {'name': 'Yarim ega', 'is_owner': 'on', 'perms': ['students.view']})
        self.assertFalse(Position.objects.get(name='Yarim ega').is_owner)                  # direktor ega lavozimini yarata olmaydi

    # --- jurnal
    def test_audit_log_requires_permission_and_filters(self):
        self.client.login(username='egasi', password='x')
        self.add()
        self.assertContains(self.client.get('/panel/jurnal/?amal=Xodim'), "Xodim qo&#x27;shdi")
        self.assertNotContains(self.client.get('/panel/jurnal/?amal=yo%27q-bunaqa'), "Xodim qo&#x27;shdi")
        self.client.login(username='rec', password='x')
        self.assertEqual(self.client.get('/panel/jurnal/').status_code, 403)


@FAST
class RoutingTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_panel_only_staff_lands_in_panel_and_superuser_too(self):
        make_staff('rec', 'Reception', perms=NO_PAY(pos('Reception')))
        self.client.login(username='rec', password='x')
        self.assertRedirects(self.client.get('/'), '/panel/', fetch_redirect_response=False)
        User.objects.create_superuser('boss', password='x')
        self.client.login(username='boss', password='x')
        self.assertRedirects(self.client.get('/'), '/panel/', fetch_redirect_response=False)

    def test_staff_without_active_panel_gets_clear_message(self):
        user = make_staff('rec', 'Reception', perms=NO_PAY(pos('Reception')))
        user.staff_profile.is_active = False
        user.staff_profile.save()
        self.client.login(username='rec', password='x')
        self.assertContains(self.client.get('/'), 'ruxsati berilmagan', status_code=403)

    def test_teacher_with_panel_gets_mode_switch_and_remembered_mode(self):
        teacher = User.objects.create_user(username='dil', password='x', role='teacher', first_name='Dilafruz')
        StaffProfile.objects.create(user=teacher, position=pos('Zavxoz'), perms=pos('Zavxoz').default_perms)
        self.client.login(username='dil', password='x')
        self.assertRedirects(self.client.get('/'), '/ustoz/', fetch_redirect_response=False)       # birinchi — ustoz
        menu = self.client.get('/ustoz/').content.decode()
        self.assertIn('class="menu-sw"', menu)
        self.assertIn('Boshqaruv paneli', menu)
        self.client.get('/panel/')
        self.assertRedirects(self.client.get('/'), '/panel/', fetch_redirect_response=False)       # panelda qolgan edi
        self.client.get('/ustoz/')
        self.assertRedirects(self.client.get('/'), '/ustoz/', fetch_redirect_response=False)

    def test_regular_teacher_has_no_panel_link(self):
        User.objects.create_user(username='t', password='x', role='teacher')
        self.client.login(username='t', password='x')
        self.assertNotContains(self.client.get('/ustoz/'), 'Boshqaruv paneli')
        self.assertEqual(self.client.get('/panel/').status_code, 403)

    def test_teacher_who_is_also_parent_and_staff_sees_three_modes(self):
        t = User.objects.create_user(username='t', password='x', role='teacher', first_name='Diyora')
        StaffProfile.objects.create(user=t, position=pos('Zavxoz'), perms=[])
        Student.objects.create(user=User.objects.create_user(username='k', role='student'), group=Group.objects.create(name='5')).parents.add(t)
        self.client.login(username='t', password='x')
        menu = self.client.get('/ustoz/').content.decode()
        for label in ('Ustoz sahifasi', 'Farzandlarim', 'Boshqaruv paneli'):
            self.assertIn(label, menu)
