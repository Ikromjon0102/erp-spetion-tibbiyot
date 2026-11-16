import json

from django.test import TestCase


class PwaTests(TestCase):
    def test_manifest_ochiq_va_togri(self):
        r = self.client.get('/manifest.webmanifest')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content)
        self.assertEqual(data['name'], 'Spetion Tibbiyot')
        self.assertEqual(data['display'], 'standalone')
        self.assertTrue(any(i['purpose'] == 'maskable' for i in data['icons']))

    def test_service_worker_ildizda(self):
        r = self.client.get('/sw.js')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Service-Worker-Allowed'], '/')
        self.assertIn('javascript', r['Content-Type'])

    def test_login_sahifada_manifest_va_oornatish(self):
        html = self.client.get('/login/').content.decode()
        self.assertIn('rel="manifest"', html)
        self.assertIn('id="pwa-bar"', html)
