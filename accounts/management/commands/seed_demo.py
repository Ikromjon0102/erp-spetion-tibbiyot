from datetime import date, time

from django.core.management.base import BaseCommand

from academics.models import Group, Lesson, Subject, Teaching
from accounts.models import Student, User
from access.models import Device
from journal.models import Attendance, Grade
from billing.services import add_test_payment
from notices.models import Announcement

PASSWORD = 'demo12345'


class Command(BaseCommand):
    help = "Demo ma'lumotlar yaratadi (admin, ota-ona, o'quvchilar, qurilmalar). Ustozlar import_schedule orqali keladi."

    def handle(self, *args, **opts):
        def user(username, first, last, role, **kw):
            u, created = User.objects.get_or_create(
                username=username, defaults=dict(first_name=first, last_name=last, role=role, **kw))
            if created:
                u.set_password(PASSWORD)
                u.save()
            return u

        admin = user('admin1', 'Dilnoza', 'Karimova', 'admin', is_staff=True, is_superuser=True)
        parent = user('ota1', 'Bahodir', 'Aliyev', 'parent', phone='+998901112233')
        group, _ = Group.objects.get_or_create(name='Demo-sinf')
        teacher = user('demoustoz', 'Demo', 'Ustoz', 'teacher')
        teaching, _ = Teaching.objects.get_or_create(
            teacher=teacher, subject=Subject.objects.get_or_create(name='Biologiya')[0], group=group)
        today = date.today()
        lesson, _ = Lesson.objects.get_or_create(teaching=teaching, weekday=today.weekday() % 6, period=1,
                                                 defaults={'start': time(8, 30), 'end': time(9, 15)})

        for i, (first, last) in enumerate([('Madina', 'Aliyeva'), ('Jasur', 'Aliyev'), ('Sevara', 'Qodirova')]):
            su = user(f'oquvchi{i + 1}', first, last, 'student')
            st, _ = Student.objects.get_or_create(user=su, defaults={'group': group, 'access_id': str(1001 + i)})
            if i < 2:
                st.parents.add(parent)
            Grade.objects.get_or_create(student=st, teaching=teaching, date=today, defaults={'score': 4 + i % 2})
            Attendance.objects.get_or_create(student=st, lesson=lesson, date=today, defaults={'status': 'present'})
            add_test_payment(st, today, 1500000, 1500000 if i == 0 else 500000)
        for name, direction in [('Kirish-1', 'in'), ('Kirish-2', 'in'), ('Chiqish-1', 'out'), ('Chiqish-2', 'out')]:
            Device.objects.get_or_create(name=name, defaults={'direction': direction})
        Announcement.objects.get_or_create(
            title="Ota-onalar yig'ilishi", defaults={'body': 'Juma kuni soat 15:00 da.', 'audience': 'parents',
                                                     'author': admin})
        self.stdout.write(self.style.SUCCESS(f"Tayyor. Loginlar: admin1, ota1, oquvchi1..3, demoustoz — parol: {PASSWORD}"))
