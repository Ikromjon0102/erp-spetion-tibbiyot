import json
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from academics.models import Group, Subject, Teaching
from access.models import AccessEvent, Device
from accounts.models import Student, User
from journal.models import Grade
from notices.models import Announcement

from . import services
from .models import LinkCode, TelegramLink

P = '+998911112233'


@override_settings(BOT_TOKEN='123:TEST')
class BotTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name='5-A')
        self.parent = User.objects.create_user('p', password='x', role='parent', phone=P,
                                               first_name='Ona', last_name='Onaeva')
        su = User.objects.create_user('s', password='x', role='student', first_name='Ali', last_name='Aliev')
        self.st = Student.objects.create(user=su, group=self.group)
        self.st.parents.add(self.parent)
        self.sent = []
        p = mock.patch('tgbot.services.api', side_effect=lambda m, **kw: self.sent.append((m, kw)) or {'ok': True})
        p.start()
        self.addCleanup(p.stop)

    def post(self, payload, secret=None):
        return Client().post('/tg/webhook/', json.dumps(payload), content_type='application/json',
                             HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=services.webhook_secret() if secret is None else secret)

    def msg(self, **kw):
        return {'message': {'chat': {'id': 5}, 'from': {'id': 5, 'username': 'u'}, **kw}}

    def texts(self):
        return [kw.get('text', '') for m, kw in self.sent if m == 'sendMessage']

    def test_bad_secret_rejected(self):
        self.assertEqual(self.post(self.msg(text='/start'), secret='x').status_code, 403)
        self.assertEqual(self.sent, [])

    def test_contact_links_parent(self):
        self.post(self.msg(contact={'phone_number': '998911112233', 'user_id': 5}))
        self.assertEqual(TelegramLink.objects.get(chat_id=5).user, self.parent)
        self.assertIn('Aliev', self.texts()[-1])

    def test_foreign_contact_refused(self):
        self.post(self.msg(contact={'phone_number': '998911112233', 'user_id': 99}))
        self.assertFalse(TelegramLink.objects.exists())

    def test_unknown_phone(self):
        self.post(self.msg(contact={'phone_number': '998900000000', 'user_id': 5}))
        self.assertFalse(TelegramLink.objects.exists())

    def test_link_code_single_use(self):
        code = LinkCode.objects.create(user=self.parent).code
        self.post(self.msg(text=f'/start {code}'))
        self.assertTrue(TelegramLink.objects.filter(chat_id=5).exists())
        self.assertFalse(LinkCode.objects.exists())

    def test_unlinked_gets_no_data(self):
        self.post(self.msg(text='/bugun'))
        self.assertNotIn('Aliev', self.texts()[-1])

    def test_today_and_unlink(self):
        TelegramLink.objects.create(user=self.parent, chat_id=5)
        self.post(self.msg(text='/bugun'))
        self.assertIn('hali kelmagan', self.texts()[-1])
        self.post(self.msg(text='/chiqish'))
        self.assertFalse(TelegramLink.objects.exists())


@override_settings(BOT_TOKEN='123:TEST')
class NotifyTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name='5-A')
        self.parent = User.objects.create_user('p', password='x', role='parent', phone=P)
        su = User.objects.create_user('s', password='x', role='student', first_name='Ali', last_name='Aliev')
        self.st = Student.objects.create(user=su, group=self.group)
        self.st.parents.add(self.parent)
        TelegramLink.objects.create(user=self.parent, chat_id=7)
        self.dev = Device.objects.create(name='K1', direction='in')
        self.sent = []
        p = mock.patch('tgbot.services.api', side_effect=lambda m, **kw: self.sent.append(kw))
        p.start()
        self.addCleanup(p.stop)

    def test_arrival_notifies_but_old_event_does_not(self):
        AccessEvent.objects.create(device=self.dev, student=self.st, employee_no='1', direction='in',
                                   occurred_at=timezone.now())
        self.assertEqual(len(self.sent), 1)
        self.assertIn('keldi', self.sent[0]['text'])
        AccessEvent.objects.create(device=self.dev, student=self.st, employee_no='1', direction='in',
                                   occurred_at=timezone.now() - timezone.timedelta(hours=5))
        self.assertEqual(len(self.sent), 1)

    def test_grade_and_announcement(self):
        t = Teaching.objects.create(subject=Subject.objects.create(name='Fizika'), group=self.group)
        Grade.objects.create(student=self.st, teaching=t, score=5)
        self.assertIn('Fizika', self.sent[-1]['text'])
        Announcement.objects.create(title='Yig‘ilish', body='Ertaga', audience='parents')
        self.assertIn('Yig‘ilish', self.sent[-1]['text'])
        n = len(self.sent)
        Announcement.objects.create(title='Ustozlarga', body='x', audience='teachers')
        self.assertEqual(len(self.sent), n)

    def test_no_token_is_silent(self):
        with override_settings(BOT_TOKEN=''):
            Grade.objects.create(student=self.st, score=4, teaching=Teaching.objects.create(
                subject=Subject.objects.create(name='X'), group=self.group))
        self.assertEqual(self.sent, [])


@override_settings(BOT_TOKEN='123:TEST')
class MiniAppTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user('p', password='x', role='parent', phone=P)
        TelegramLink.objects.create(user=self.parent, chat_id=42)

    def init_data(self, uid=42, age=0, tamper=False):
        import hashlib
        import hmac as h
        import time
        from urllib.parse import urlencode
        d = {'auth_date': str(int(time.time()) - age), 'user': json.dumps({'id': uid})}
        check = '\n'.join(f'{k}={v}' for k, v in sorted(d.items()))
        secret = h.new(b'WebAppData', b'123:TEST', hashlib.sha256).digest()
        d['hash'] = h.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if tamper:
            d['user'] = json.dumps({'id': 43})
        return urlencode(d)

    def test_valid_login(self):
        c = Client()
        r = c.post('/tg/auth/', {'initData': self.init_data()})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(int(c.session['_auth_user_id']), self.parent.pk)

    def test_rejected_cases(self):
        for data in (self.init_data(tamper=True), self.init_data(age=3 * 24 * 3600), self.init_data(uid=99), ''):
            c = Client()
            self.assertEqual(c.post('/tg/auth/', {'initData': data}).status_code, 403)
            self.assertNotIn('_auth_user_id', c.session)

    def test_app_page_public(self):
        self.assertEqual(Client().get('/tg/app/').status_code, 200)


@override_settings(BOT_TOKEN='123:TEST')
class OpenAppButtonTests(BotTests):
    def test_open_app_uses_inline_button(self):
        TelegramLink.objects.create(user=self.parent, chat_id=5)
        self.post(self.msg(text='📱 Ilovani ochish'))
        kb = [kw for m, kw in self.sent if m == 'sendMessage'][-1]['reply_markup']
        self.assertIn('inline_keyboard', kb)
        self.assertIn('web_app', kb['inline_keyboard'][0][0])
