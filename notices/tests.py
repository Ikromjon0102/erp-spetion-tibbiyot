from django.core.cache import cache
from django.test import TestCase, override_settings

from academics.models import Group, Subject, Teaching
from accounts.models import Student, User

from .models import Announcement, AnnouncementRead
from .services import read_summary, recipients_of

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


@FAST
class ReadReceiptsTests(TestCase):
    def setUp(self):
        cache.clear()
        mk = lambda u, role, **kw: User.objects.create_user(username=u, password='x', role=role, **kw)
        self.g5, self.g6 = Group.objects.create(name='5-Sinf'), Group.objects.create(name='6-Sinf')
        subject = Subject.objects.create(name='Kimyo')
        self.t1 = mk('t1', 'teacher', first_name='Diyora')                       # 5-sinfda dars beradi
        self.t2 = mk('t2', 'teacher', first_name='Azizbek')                      # 6-sinfda dars beradi
        self.t3 = mk('t3', 'teacher', first_name='Malika')                       # 5-sinfda dars beradi + 6-sinfda farzandi bor
        for t, g in ((self.t1, self.g5), (self.t2, self.g6), (self.t3, self.g5)):
            Teaching.objects.create(teacher=t, subject=subject, group=g)
        mkkid = lambda u, g, parent: Student.objects.create(user=User.objects.create_user(username=u, role='student'), group=g)
        k1, k2, k3 = mkkid('k1', self.g5, None), mkkid('k2', self.g6, None), mkkid('k3', self.g6, None)
        self.p1, self.p2 = mk('p1', 'parent', first_name='Ota5'), mk('p2', 'parent', first_name='Ota6')
        k1.parents.add(self.p1); k2.parents.add(self.p2); k3.parents.add(self.t3)
        self.nopass = User.objects.create(username='p3', role='parent', first_name='Parolsiz')   # paroli yo'q
        self.nopass.set_unusable_password(); self.nopass.save()
        k1.parents.add(self.nopass)
        self.inactive = mk('t4', 'teacher', is_active=False)
        Teaching.objects.create(teacher=self.inactive, subject=subject, group=self.g5)
        self.admin = User.objects.create_superuser(username='boss', password='x')
        self.k1 = k1

    def ann(self, audience, group=None, title='Sarlavha'):
        return Announcement.objects.create(title=title, body='Matn', audience=audience, group=group, author=self.admin)

    def names(self, a):
        return {u.username for u in recipients_of(a)}

    # --- kimga yuborilgan
    def test_recipients_by_audience_and_group(self):
        self.assertEqual(self.names(self.ann('teachers')), {'t1', 't2', 't3'})            # nofaol ustoz va admin yo'q
        self.assertEqual(self.names(self.ann('teachers', self.g5)), {'t1', 't3'})
        self.assertEqual(self.names(self.ann('parents', self.g5)), {'p1'})                # paroli yo'q ota-ona sanalmaydi
        self.assertEqual(self.names(self.ann('parents', self.g6)), {'p2', 't3'})          # ustoz-ota-ona ham
        self.assertEqual(self.names(self.ann('parents')), {'p1', 'p2', 't3'})

    def test_all_audience_counts_dual_role_user_once_and_skips_students_without_password(self):
        a = self.ann('all')
        users = recipients_of(a)
        self.assertEqual(len(users), len({u.pk for u in users}))
        self.assertEqual({u.username for u in users}, {'t1', 't2', 't3', 'p1', 'p2'})     # o'quvchilar parolsiz — yo'q

    # --- o'qildi deb belgilash
    def test_mark_read_records_first_time_only(self):
        a = self.ann('parents', self.g5)
        self.client.login(username='p1', password='x')
        r1 = self.client.post(f'/elonlar/{a.pk}/oqildi/')
        self.assertEqual(r1.json(), {'ok': True, 'recorded': True})
        first = AnnouncementRead.objects.get().read_at
        r2 = self.client.post(f'/elonlar/{a.pk}/oqildi/')
        self.assertEqual(r2.json(), {'ok': True, 'recorded': False})
        self.assertEqual(AnnouncementRead.objects.count(), 1)
        self.assertEqual(AnnouncementRead.objects.get().read_at, first)                   # vaqt o'zgarmaydi
        self.assertEqual(read_summary(a), (1, 1))

    def test_cannot_mark_foreign_announcement_or_anonymous_or_get(self):
        a = self.ann('parents', self.g5)
        self.client.login(username='p2', password='x')                                   # boshqa sinf ota-onasi
        self.assertEqual(self.client.post(f'/elonlar/{a.pk}/oqildi/').status_code, 404)
        self.assertEqual(self.client.get(f'/elonlar/{a.pk}/oqildi/').status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.post(f'/elonlar/{a.pk}/oqildi/').status_code, 302)   # kirmagan
        self.assertEqual(AnnouncementRead.objects.count(), 0)

    def test_admin_opening_is_not_counted(self):
        a = self.ann('all')
        self.client.login(username='boss', password='x')
        self.assertEqual(self.client.post(f'/elonlar/{a.pk}/oqildi/').json()['recorded'], False)
        self.assertEqual(AnnouncementRead.objects.count(), 0)

    # --- o'qilmaganlar belgisi
    def test_unread_dot_on_page_and_bell_until_opened(self):
        a = self.ann('parents', self.g5, title='Yig\'ilish')
        self.client.login(username='p1', password='x')
        page = self.client.get('/elonlar/')
        self.assertContains(page, 'class="newdot"')
        self.assertContains(page, f'data-nid="{a.pk}"')
        self.assertEqual(page.context['unread_news'], 1)
        self.client.post(f'/elonlar/{a.pk}/oqildi/')
        page = self.client.get('/elonlar/')
        self.assertNotContains(page, '<i class="newdot" title="Yangi"></i>')
        self.assertEqual(page.context['unread_news'], 0)

    def test_teacher_api_reports_read_state(self):
        a = self.ann('teachers', self.g5)
        self.client.login(username='t1', password='x')
        item = self.client.get('/ustoz/api/elonlar/').json()['items'][0]
        self.assertEqual((item['id'], item['read']), (a.pk, False))
        self.client.post(f'/elonlar/{a.pk}/oqildi/')
        self.assertTrue(self.client.get('/ustoz/api/elonlar/').json()['items'][0]['read'])

    def test_dual_role_read_counts_once_for_both_sides(self):
        a = self.ann('parents', self.g6)
        self.client.login(username='t3', password='x')                                   # ustoz, o'z farzandi 6-sinfda
        self.assertTrue(self.client.post(f'/elonlar/{a.pk}/oqildi/').json()['recorded'])
        self.assertEqual(read_summary(a), (2, 1))                                         # p2 va t3 dan 1 tasi o'qigan

    # --- admin ko'rinishi
    def test_admin_list_and_detail_show_sent_and_read_with_time(self):
        a = self.ann('teachers', self.g5, title='Kengash')
        self.client.login(username='t1', password='x')
        self.client.post(f'/elonlar/{a.pk}/oqildi/')
        self.client.logout()
        self.client.login(username='boss', password='x')

        lst = self.client.get('/admin/notices/announcement/')
        self.assertContains(lst, '<b>1</b>/2')                                            # 2 qabul qiluvchidan 1 tasi o'qigan
        self.assertContains(lst, 'title="Yuborildi">✓</span>')                            # belgilar HTML sifatida chiqadi
        self.assertNotContains(lst, '&lt;span')                                           # matn bo'lib ko'rinib qolmaydi

        detail = self.client.get(f'/admin/notices/announcement/{a.pk}/change/')
        self.assertContains(detail, 'Diyora')
        self.assertContains(detail, 'Malika')
        self.assertContains(detail, 'title="Oqildi">✓✓</span>')                           # t1 o'qigan
        self.assertContains(detail, 'title="Yuborildi">✓</span>')                         # t3 hali ochmagan
        self.assertNotContains(detail, '&lt;span')
        self.assertContains(detail, 'hali ochmagan')                                      # t3 hali ochmagan
        read_at = AnnouncementRead.objects.get().read_at
        from django.utils import timezone
        self.assertContains(detail, timezone.localtime(read_at).strftime('%d.%m.%Y %H:%M'))

    def test_admin_list_all_read_shows_double_check(self):
        a = self.ann('parents', self.g5)
        self.client.login(username='p1', password='x')
        self.client.post(f'/elonlar/{a.pk}/oqildi/')
        self.client.logout()
        self.client.login(username='boss', password='x')
        self.assertContains(self.client.get('/admin/notices/announcement/'), 'title="Oqildi">✓✓</span>')

    def test_admin_new_announcement_form_renders(self):
        self.client.login(username='boss', password='x')
        r = self.client.get('/admin/notices/announcement/add/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "saqlangandan keyin")
