from django.test import TestCase
from django.urls import reverse

from academics.models import Group
from accounts.models import Student, User
from org.models import Branch, Organization


class KindergartenChildPageTests(TestCase):
    """Bog'chada baho, imtihon va vazifa yo'q; jadval — mashg'ulotlar."""

    def setUp(self):
        parent = User.objects.create_user('998970', password='x', role='parent')
        self.kg_org = Organization.objects.create(name="Bog'cha T", short_name='BT', kind='kindergarten', brand_color='#F97316')
        self.school_org = Organization.objects.create(name='Maktab T', short_name='MT', kind='school', brand_color='#1E3A8A')
        self.kids = []
        for name, org in (('Bobur', self.kg_org), ('Aziz', self.school_org)):
            br = Branch.objects.create(organization=org, name='Asosiy')
            u = User.objects.create_user(f'k-{name}', password='x', role='student', first_name=name, last_name='T')
            s = Student.objects.create(user=u, group=Group.objects.create(name=f'g-{name}', branch=br))
            s.parents.add(parent)
            self.kids.append(s)
        self.client.force_login(parent)

    def page(self, student):
        return self.client.get(reverse('student_detail', args=[student.pk])).content.decode()

    def test_kindergarten_page_has_no_grades(self):
        body = self.page(self.kids[0])
        self.assertNotIn('data-tab="grades"', body)
        self.assertNotIn('id="tab-grades"', body)
        self.assertNotIn("O'rtacha baho", body)
        self.assertIn("Mashg'ulot", body)

    def test_school_page_keeps_grades(self):
        body = self.page(self.kids[1])
        self.assertIn('data-tab="grades"', body)
        self.assertIn('Jadval', body)

    def test_each_child_page_has_own_color(self):
        self.assertIn('--accent:#F97316', self.page(self.kids[0]))
        self.assertIn('--accent:#1E3A8A', self.page(self.kids[1]))

    def test_home_card_hides_average_for_kindergarten(self):
        body = self.client.get(reverse('home')).content.decode()
        self.assertEqual(body.count("O'rtacha baho"), 1)
