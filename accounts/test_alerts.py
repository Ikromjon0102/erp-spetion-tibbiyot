import logging
import os
from unittest import mock

from django.core.cache import cache
from django.test import RequestFactory, TestCase

from config import alerts


class TelegramAlertTests(TestCase):
    def setUp(self):
        cache.clear()
        self.handler = alerts.TelegramErrorHandler()

    def record(self, path='/panel/x/'):
        try:
            raise ValueError('buzildi')
        except ValueError:
            import sys
            rec = logging.LogRecord('django.request', logging.ERROR, __file__, 1, 'Internal Server Error', None, sys.exc_info())
        rec.request = RequestFactory().get(path)
        return rec

    def test_sends_once_per_signature_and_never_raises(self):
        with mock.patch.dict(os.environ, {'ALERT_BOT_TOKEN': 't', 'ALERT_CHAT_ID': '1'}), \
             mock.patch.object(alerts.threading, 'Thread') as th:
            self.handler.emit(self.record())
            self.handler.emit(self.record())                  # takror — yuborilmaydi
            self.handler.emit(self.record('/boshqa/'))        # boshqa joy — yuboriladi
        self.assertEqual(th.call_count, 2)
        text = th.call_args_list[0].kwargs['args'][2]
        self.assertIn('GET /panel/x/', text)
        self.assertIn('ValueError: buzildi', text)

    def test_silent_without_config(self):
        with mock.patch.dict(os.environ, {'ALERT_BOT_TOKEN': '', 'ALERT_CHAT_ID': ''}), \
             mock.patch.object(alerts.threading, 'Thread') as th:
            self.handler.emit(self.record())
        th.assert_not_called()
