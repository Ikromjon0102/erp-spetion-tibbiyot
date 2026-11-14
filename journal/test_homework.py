import json
from datetime import date, time, timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from academics.models import Group, Lesson, Subject, Teaching
from accounts.child_data import child_context
from accounts.models import Student, User

from .models import Homework, HomeworkRead

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
MON, TUE, WED = date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18)


@FAST
class HomeworkApiTests(TestCase):
    def setUp(self):
        cache.clear()
        mk = lambda u, role, **kw: User.objects.create_user(username=u, password='x', role=role, **kw)
        self.t1, self.t2, self.parent = mk('t1', 'teacher', first_name='Diyora'), mk('t2', 'teacher'), mk('p1', 'parent')
        self.g5 = Group.objects.create(name='5-Sinf')
        self.subject = Subject.objects.create(name='Ona tili')
        self.teaching = Teaching.objects.create(teacher=self.t1, subject=self.subject, group=self.g5)
        # dushanba va chorshanba darslari
        self.mon = Lesson.objects.create(teaching=self.teaching, weekday=0, period=1, start=time(8, 30), end=time(9, 15))
        Lesson.objects.create(teaching=self.teaching, weekday=2, period=1, start=time(8, 30), end=time(9, 15))
        self.client.login(username='t1', password='x')

    def at(self, day):
        return mock.patch('journal.views.timezone.localdate', return_value=day)

    def url(self, suffix='', lesson=None):
        return f'/ustoz/api/vazifa/{(lesson or self.mon).id}/{suffix}'

    def post(self, suffix, data, day=MON, lesson=None):
        with self.at(day):
            return self.client.post(self.url(suffix, lesson), json.dumps(data), content_type='application/json')

    def create(self, text='1-mashq', due=WED, day=MON):
        return self.post('saqlash/', {'text': text, 'due': due.isoformat()}, day=day).json()

    # --- ro'yxat va taklif qilingan sana
    def test_list_and_suggested_due_is_next_lesson_day(self):
        with self.at(MON):
            d = self.client.get(self.url()).json()
        self.assertEqual((d['ok'], d['items'], d['suggested']), (True, [], WED.isoformat()))   # dushanbadan keyin — chorshanba
        with self.at(WED):
            self.assertEqual(self.client.get(self.url()).json()['suggested'], '2026-11-23')  # chorshanbadan keyin — keyingi dushanba

    # --- yaratish
    def test_create_homework(self):
        r = self.create('Matnni o\'qib, 3 ta savolga javob yozing')
        self.assertTrue(r['ok'])
        self.assertEqual((r['item']['due'], r['item']['assigned'], r['item']['editable']), (WED.isoformat(), MON.isoformat(), True))
        hw = Homework.objects.get()
        self.assertEqual((hw.teaching, hw.created_by, hw.assigned_on, hw.due_date), (self.teaching, self.t1, MON, WED))

    def test_validation(self):
        self.assertEqual(self.create('   ')['err'], 'bad_text')
        self.assertEqual(self.create('x' * 2001)['err'], 'bad_text')
        self.assertEqual(self.post('saqlash/', {'text': 'a', 'due': 'kecha'}).json()['err'], 'bad_date')
        self.assertEqual(self.create(due=MON - timedelta(days=1))['err'], 'past_date')
        self.assertTrue(self.create(due=MON)['ok'])                 # bugunga topshirish ham mumkin
        self.assertEqual(Homework.objects.count(), 1)

    def test_homework_can_be_given_at_any_time_of_day_and_without_a_lesson_today(self):
        # dars kuni emas (seshanba) ham, soat nechaligidan qat'iy nazar ham berish mumkin
        self.assertTrue(self.create(day=TUE)['ok'])

    # --- tahrirlash va o'chirish: faqat berilgan kunning oxirigacha
    def test_edit_and_delete_same_day(self):
        hid = self.create()['item']['id']
        r = self.post(f'{hid}/yangilash/', {'text': 'Yangi matn', 'due': '2026-11-20'}).json()
        self.assertTrue(r['ok'])
        hw = Homework.objects.get()
        self.assertEqual((hw.text, hw.due_date.isoformat(), hw.assigned_on), ('Yangi matn', '2026-11-20', MON))
        self.assertEqual(self.post(f'{hid}/yangilash/', {'text': 'x', 'due': '2026-11-10'}).json()['err'], 'past_date')
        self.assertTrue(self.post(f'{hid}/ochirish/', {}).json()['ok'])
        self.assertFalse(Homework.objects.exists())

    def test_locked_the_next_day(self):
        hid = self.create()['item']['id']
        self.assertEqual(self.post(f'{hid}/yangilash/', {'text': 'Kech tahrir', 'due': WED.isoformat()}, day=TUE).json(),
                         {'ok': False, 'err': 'locked'})
        self.assertEqual(self.post(f'{hid}/ochirish/', {}, day=TUE).json(), {'ok': False, 'err': 'locked'})
        self.assertEqual(Homework.objects.get().text, '1-mashq')                  # o'zgarmadi
        with self.at(TUE):
            item = self.client.get(self.url()).json()['items'][0]
        self.assertFalse(item['editable'])                                          # sahifada tugmalar ko'rinmaydi

    def test_demo_account_can_edit_any_day(self):
        hid = self.create()['item']['id']
        self.t1.is_demo = True
        self.t1.save()
        self.assertTrue(self.post(f'{hid}/yangilash/', {'text': 'Sinov', 'due': WED.isoformat()}, day=TUE).json()['ok'])

    # --- ruxsatlar
    def test_other_teacher_and_parent_cannot_touch_it(self):
        hid = self.create()['item']['id']
        self.client.login(username='t2', password='x')
        self.assertEqual(self.post(f'{hid}/ochirish/', {}).status_code, 404)        # bu dars boshqa ustozniki
        self.assertEqual(self.client.get(self.url()).status_code, 404)
        self.client.login(username='p1', password='x')
        self.assertEqual(self.client.get(self.url()).status_code, 401)             # ota-ona ustoz API'sidan foydalana olmaydi
        self.assertTrue(Homework.objects.filter(pk=hid).exists())

    def test_homework_of_another_class_of_same_teacher_is_not_reachable_via_this_lesson(self):
        g6 = Group.objects.create(name='6-Sinf')
        other = Teaching.objects.create(teacher=self.t1, subject=self.subject, group=g6)
        hw = Homework.objects.create(teaching=other, text='6-sinf', due_date=WED, assigned_on=MON)
        self.assertEqual(self.post(f'{hw.id}/ochirish/', {}).status_code, 404)      # 5-sinf darsi orqali 6-sinf vazifasiga tegib bo'lmaydi
        self.assertTrue(Homework.objects.filter(pk=hw.pk).exists())


@FAST
class HomeworkParentSideTests(TestCase):
    def setUp(self):
        cache.clear()
        mk = lambda u, role, **kw: User.objects.create_user(username=u, password='x', role=role, **kw)
        self.teacher = mk('t1', 'teacher', first_name='Diyora')
        self.parent, self.stranger, self.admin = mk('p1', 'parent'), mk('p2', 'parent'), User.objects.create_superuser('boss', password='x')
        self.g5, self.g6 = Group.objects.create(name='5-Sinf'), Group.objects.create(name='6-Sinf')
        self.lang, self.math = Subject.objects.create(name='Ona tili'), Subject.objects.create(name='Matematika')
        self.t_lang = Teaching.objects.create(teacher=self.teacher, subject=self.lang, group=self.g5)
        self.t_math = Teaching.objects.create(teacher=self.teacher, subject=self.math, group=self.g5)
        t_other = Teaching.objects.create(teacher=self.teacher, subject=self.lang, group=self.g6)
        today = timezone.localdate()
        for t in (self.t_lang, self.t_math):
            Lesson.objects.create(teaching=t, weekday=today.weekday() % 6, period=1, start=time(8, 30), end=time(9, 15))
        self.kid = Student.objects.create(user=mk('k1', 'student', first_name='Madina', last_name='Karimova'), group=self.g5)
        self.kid.parents.add(self.parent)
        mk_hw = lambda t, text, due=1, assigned=0: Homework.objects.create(
            teaching=t, text=text, due_date=today + timedelta(days=due), assigned_on=today - timedelta(days=assigned))
        self.h1 = mk_hw(self.t_lang, 'Ona tili: 12-mashq', due=1)
        self.h2 = mk_hw(self.t_lang, 'Ona tili: she\'r yodlash', due=3)
        self.h3 = mk_hw(self.t_math, 'Matematika: 5-masala', due=2)
        self.other = mk_hw(t_other, '6-sinf vazifasi')                        # boshqa sinf — ko'rinmaydi

    def ctx(self, viewer=None):
        return child_context(self.kid, viewer or self.parent)

    # --- ma'lumotlar
    def test_homework_is_grouped_by_subject_and_only_for_the_childs_class(self):
        c = self.ctx()
        self.assertEqual(set(c['homework']), {'Ona tili', 'Matematika'})
        self.assertEqual([h['text'] for h in c['homework']['Ona tili']], ["Ona tili: she'r yodlash", 'Ona tili: 12-mashq'])  # yangisi tepada
        self.assertNotIn('6-sinf vazifasi', json.dumps(c['homework']))
        self.assertEqual(c['hw_unread'], 3)
        item = next(h for h in c['homework']['Ona tili'] if h['id'] == self.h1.pk)
        self.assertEqual((item['days_left'], item['past'], item['read'], item['teacher']), (1, False, False, 'Diyora'))

    def test_old_and_excess_homework_is_trimmed(self):
        today = timezone.localdate()
        Homework.objects.create(teaching=self.t_math, text='Eski', due_date=today - timedelta(days=31), assigned_on=today - timedelta(days=40))
        for i in range(12):
            Homework.objects.create(teaching=self.t_math, text=f'#{i}', due_date=today + timedelta(days=1), assigned_on=today)
        math = self.ctx()['homework']['Matematika']
        self.assertEqual(len(math), 10)
        self.assertNotIn('Eski', [h['text'] for h in math])

    def test_schedule_rows_get_homework_badge_counts(self):
        today_idx = timezone.localdate().weekday()
        if today_idx > 5:
            self.skipTest('yakshanba')
        rows = {l['subject']: l for l in self.ctx()['days'][today_idx]['lessons']}
        self.assertEqual((rows['Ona tili']['hw'], rows['Ona tili']['hw_unread']), (2, 2))
        self.assertEqual((rows['Matematika']['hw'], rows['Matematika']['hw_unread']), (1, 1))

    # --- "o'qildi" belgisi va qizil nuqta
    def test_mark_read_clears_dots(self):
        self.client.login(username='p1', password='x')
        r = self.client.post('/vazifa/oqildi/', json.dumps({'ids': [self.h1.pk, self.h2.pk]}), content_type='application/json')
        self.assertEqual(r.json(), {'ok': True, 'marked': 2})
        again = self.client.post('/vazifa/oqildi/', json.dumps({'ids': [self.h1.pk]}), content_type='application/json')
        self.assertEqual(again.json()['marked'], 0)                                       # qayta belgilanmaydi
        c = self.ctx()
        self.assertEqual(c['hw_unread'], 1)                                               # faqat matematika qoldi
        self.assertTrue(all(h['read'] for h in c['homework']['Ona tili']))
        self.assertEqual(HomeworkRead.objects.filter(user=self.parent).count(), 2)

    def test_unrelated_parent_cannot_mark_foreign_homework(self):
        self.client.login(username='p2', password='x')
        r = self.client.post('/vazifa/oqildi/', json.dumps({'ids': [self.h1.pk]}), content_type='application/json')
        self.assertEqual(r.json(), {'ok': True, 'marked': 0})
        self.assertFalse(HomeworkRead.objects.exists())
        self.assertEqual(self.client.post('/vazifa/oqildi/', 'xx', content_type='application/json').status_code, 400)
        self.client.logout()
        self.assertEqual(self.client.post('/vazifa/oqildi/', '{}', content_type='application/json').status_code, 302)

    def test_teacher_and_admin_viewers_get_no_dots_and_leave_no_traces(self):
        self.assertEqual(self.ctx(self.teacher)['hw_unread'], 0)
        self.assertEqual(self.ctx(self.admin)['hw_unread'], 0)
        self.assertTrue(all(h['read'] for hs in self.ctx(self.teacher)['homework'].values() for h in hs))

    # --- sahifa
    def test_child_page_shows_tab_dot_and_tappable_subject_rows(self):
        if timezone.localdate().weekday() > 5:
            self.skipTest('yakshanba')
        self.client.login(username='p1', password='x')
        page = self.client.get(f'/oquvchi/{self.kid.pk}/')
        self.assertContains(page, 'id="hw-data"')
        self.assertContains(page, 'id="hwBadge"')                                         # Jadval tabida qizil nuqta
        self.assertContains(page, 'class="row tap"')                                      # vazifasi bor fan bosiladigan
        self.assertContains(page, 'data-subject="Ona tili"')
        self.assertContains(page, '12-mashq')                                             # matn sahifa ma'lumotida
        self.client.post('/vazifa/oqildi/', json.dumps({'ids': [self.h1.pk, self.h2.pk, self.h3.pk]}), content_type='application/json')
        self.assertNotContains(self.client.get(f'/oquvchi/{self.kid.pk}/'), 'id="hwBadge"')   # hammasi o'qildi

    def test_subject_without_homework_is_not_tappable(self):
        art = Subject.objects.create(name='Rasm')
        Lesson.objects.create(teaching=Teaching.objects.create(teacher=self.teacher, subject=art, group=self.g5),
                              weekday=timezone.localdate().weekday() % 6, period=3, start=time(10, 10), end=time(10, 55))
        self.client.login(username='p1', password='x')
        html = self.client.get(f'/oquvchi/{self.kid.pk}/').content.decode()
        self.assertIn('data-subject="Rasm"', html)
        self.assertNotIn('class="row tap" data-start="10:10"', html)
