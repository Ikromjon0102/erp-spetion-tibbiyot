from django.core.cache import cache
from django.test import TestCase, override_settings

from accounts.models import User

from .models import Position, StaffProfile

FAST = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


def make_staff(username, position, perms=None):
    user = User.objects.create_user(username=username, password='x', role='staff', first_name=username.title())
    p = Position.objects.get(name=position)
    StaffProfile.objects.create(user=user, position=p, perms=list(p.default_perms) if perms is None else perms)
    return user


@FAST
class MobileAppShellTests(TestCase):
    def setUp(self):
        cache.clear()
        make_staff('egasi', 'Maktab egasi')
        make_staff('rec', 'Reception')
        make_staff('zavxoz', 'Zavxoz')

    def html(self, username, path='/panel/'):
        self.client.login(username=username, password='x')
        return self.client.get(path).content.decode()

    def more_sheet(self, html):
        return html.split('id="moreOv"')[1].split('<script>')[0]

    def tab_bar(self, html):
        return html.split('class="mtab"')[1].split('</nav>')[0]

    def test_bottom_tab_bar_follows_permissions(self):
        owner = self.tab_bar(self.html('egasi'))
        for label in ('Bosh', "O'quvchilar", "E'lonlar", "Ko'proq"):
            self.assertIn(label, owner)
        self.assertIn('href="/panel/tolovlar/"', self.tab_bar(self.html('rec')))        # kassirda To'lovlar tab
        zavxoz = self.tab_bar(self.html('zavxoz'))               # Zavxozda o'quvchilar ruxsati yo'q
        self.assertIn('Bosh', zavxoz)
        self.assertNotIn("O'quvchilar", zavxoz)
        self.assertIn("E'lonlar", zavxoz)
        self.assertNotIn("To'lovlar", zavxoz)

    def test_more_sheet_lists_only_allowed_sections(self):
        owner = self.more_sheet(self.html('egasi'))
        for href in ('/panel/sinflar/', '/panel/xodimlar/', '/panel/lavozimlar/', '/panel/jurnal/'):
            self.assertIn(f'href="{href}"', owner)
        rec = self.more_sheet(self.html('rec'))                  # Reception: sinflarni ko'radi, xodimlar va jurnalni yo'q
        self.assertIn('href="/panel/sinflar/"', rec)
        self.assertNotIn('href="/panel/xodimlar/"', rec)
        self.assertNotIn('href="/panel/jurnal/"', rec)
        self.assertIn('Chiqish', rec)
        self.assertIn("Parolni o'zgartirish", rec)

    def test_technical_admin_link_only_for_superuser(self):
        User.objects.create_superuser('boss', password='x')
        self.assertIn('Texnik admin', self.more_sheet(self.html('boss')))
        self.assertNotIn('Texnik admin', self.more_sheet(self.html('egasi')))

    def test_page_uses_safe_area_viewport_for_phones(self):
        self.assertIn('viewport-fit=cover', self.html('egasi'))
