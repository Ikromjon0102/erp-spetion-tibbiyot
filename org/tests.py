from django.test import TestCase

from access.models import Device
from academics.models import Group
from org.models import Branch, Organization, default_branch


class OrgTests(TestCase):
    def test_default_org_and_branch_created_by_migration(self):
        self.assertEqual(Organization.objects.count(), 1)
        org = Organization.objects.get()
        self.assertEqual(org.brand_color, '#166534')
        self.assertEqual(default_branch().organization, org)

    def test_new_group_and_device_get_default_branch(self):
        g = Group.objects.create(name='5-A')
        d = Device.objects.create(name='Kirish-1', direction='in')
        self.assertEqual(g.branch, default_branch())
        self.assertEqual(d.branch, default_branch())

    def test_branch_name_unique_per_org_only(self):
        org2 = Organization.objects.create(name="O'quv markaz", kind='center', brand_color='#b91c1c')
        Branch.objects.create(organization=org2, name='Asosiy')  # boshqa tashkilotda bir xil nom mumkin
        with self.assertRaises(Exception):
            Branch.objects.create(organization=org2, name='Asosiy')

    def test_explicit_branch_kept(self):
        org2 = Organization.objects.create(name='Bogcha', kind='kindergarten', brand_color='#ea580c')
        b = Branch.objects.create(organization=org2, name='Asosiy')
        self.assertEqual(Group.objects.create(name='B-1', branch=b).branch, b)
