"""Galereya: xodim albom yuklaydi va bolalarni belgilaydi; ota-ona FAQAT o'z farzandi belgilangan rasmni ko'radi."""
import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from academics.models import Group
from accounts.models import Student, User
from gallery.models import Album, Photo
from org.models import Branch, Organization
from panel.test_stage1 import Base

MEDIA = tempfile.mkdtemp()


def jpeg(name='a.jpg', size=(1200, 900)):
    from PIL import Image
    buf = BytesIO()
    Image.new('RGB', size, (200, 120, 50)).save(buf, 'JPEG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


@override_settings(MEDIA_ROOT=MEDIA)
class GalleryTests(Base):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.kg = Organization.objects.get(kind='kindergarten')
        self.assertTrue(self.kg.gallery_enabled)
        self.bk = Branch.objects.get(organization=self.kg)
        self.grp = Group.objects.create(name='Quyoshcha', branch=self.bk)
        self.kid1, self.par1 = self.child('k1', 'p1')
        self.kid2, self.par2 = self.child('k2', 'p2')
        self.boss = self.staff('tarb', ['gallery.view', 'gallery.manage', 'students.view'], self.bk)

    def child(self, kid, parent):
        u = User.objects.create_user(kid, password='x', role='student', first_name=kid.upper(), last_name='Bola')
        s = Student.objects.create(user=u, group=self.grp)
        p = User.objects.create_user(parent, password='x', role='parent', first_name=parent)
        s.parents.add(p)
        return s, p

    def upload(self, n=2):
        self.client.force_login(self.boss)
        r = self.client.post(reverse('panel:album_add') + f'?org={self.kg.pk}',
                             {'group': self.grp.pk, 'title': 'Bayram', 'date': '2026-11-25',
                              'photos': [jpeg(f'{i}.jpg') for i in range(n)]})
        self.assertEqual(r.status_code, 302)
        return Album.objects.get(title='Bayram')

    def test_upload_resizes_and_starts_untagged(self):
        album = self.upload()
        self.assertEqual(album.branch, self.bk)
        photos = list(album.photos.all())
        self.assertEqual(len(photos), 2)
        from PIL import Image
        self.assertLessEqual(max(Image.open(photos[0].thumb.path).size), 480)
        self.assertFalse(photos[0].children.exists())
        self.assertContains(self.client.get(reverse('panel:album', args=[album.pk])), 'hech kim belgilanmagan')

    def test_parent_sees_only_own_child(self):
        album = self.upload()
        p1, p2 = album.photos.all()
        self.client.post(reverse('panel:album', args=[album.pk]), {f'p{p1.pk}': [self.kid1.pk], f'p{p2.pk}': [self.kid2.pk]})
        self.assertEqual(list(p1.children.all()), [self.kid1])

        self.client.force_login(self.par1)
        page = self.client.get(reverse('student_detail', args=[self.kid1.pk])).content.decode()
        self.assertIn(reverse('gallery_photo', args=[p1.pk]), page)
        self.assertNotIn(reverse('gallery_photo', args=[p2.pk]), page)
        self.assertEqual(self.client.get(reverse('gallery_photo', args=[p1.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('gallery_photo', args=[p2.pk])).status_code, 404)     # boshqa bolaning rasmi
        self.assertEqual(self.client.get(reverse('panel:album', args=[album.pk])).status_code in (302, 403), True)

    def test_untagged_photo_hidden_from_all_parents(self):
        album = self.upload(1)
        ph = album.photos.get()
        for p in (self.par1, self.par2):
            self.client.force_login(p)
            self.assertEqual(self.client.get(reverse('gallery_photo', args=[ph.pk])).status_code, 404)

    def test_cannot_tag_child_from_other_group(self):
        album = self.upload(1)
        ph = album.photos.get()
        other = Group.objects.create(name='Boshqa', branch=self.bk)
        u = User.objects.create_user('k3', password='x', role='student')
        outsider = Student.objects.create(user=u, group=other)
        self.client.post(reverse('panel:album', args=[album.pk]), {f'p{ph.pk}': [outsider.pk, self.kid1.pk]})
        self.assertEqual(list(ph.children.all()), [self.kid1])

    def test_staff_of_other_branch_cannot_open(self):
        album = self.upload(1)
        ph = album.photos.get()
        stranger = self.staff('x2', ['gallery.view', 'gallery.manage'], self.c1)
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(reverse('panel:album', args=[album.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('gallery_photo', args=[ph.pk])).status_code, 404)

    def test_no_tab_when_module_off(self):
        self.kg.gallery_enabled = False
        self.kg.save()
        self.client.force_login(self.par1)
        self.assertNotContains(self.client.get(reverse('student_detail', args=[self.kid1.pk])), 'data-tab="gallery"')

    def test_delete_album_removes_files(self):
        import os
        album = self.upload(1)
        path = album.photos.get().image.path
        self.client.post(reverse('panel:album_delete', args=[album.pk]))
        self.assertFalse(Photo.objects.exists())
        self.assertFalse(os.path.exists(path))

    def test_presets_have_gallery(self):
        from panel.perms import PRESETS
        for name in ('Direktor', 'Filial rahbari'):
            self.assertIn('gallery.manage', next(p[2] for p in PRESETS if p[0] == name))
